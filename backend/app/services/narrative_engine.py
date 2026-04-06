"""
叙事引擎 (Narrative Engine)
核心服务：替代 simulation_runner.py + simulation_ipc.py
运行 in-process 的叙事世界循环，使用线程暂停/恢复实现玩家交互
"""

import json
import os
import time
import uuid
import random
import threading
import atexit
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

from zep_cloud.client import Zep

from ..config import Config
from ..utils.llm_client import LLMClient, get_client_for_prompt
from ..utils.logger import get_logger
from .narrative_profile_generator import NarrativeCharacterProfile
from .prompt_config import get_system, get_template, safe_render, get_llm_params
from .narrative_engine_config import get_setting
from .falkordb_entity_reader import search_entity_facts_by_name, search_entity_context, read_nodes_by_uuids

logger = get_logger('agars.narrative_engine')


# ============================================================
# Enums & Dataclasses
# ============================================================

class NarrativeStatus(str, Enum):
    IDLE = "idle"
    PREPARED = "prepared"
    RUNNING = "running"
    AWAITING_PLAYER = "awaiting_player"
    PROCESSING_PLAYER = "processing_player"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class NarrativeEvent:
    """单个叙事事件（NPC 或玩家动作）"""
    turn_number: int
    agent_name: str
    agent_uuid: str
    action_type: str
    action_description: str
    location: str = ""
    importance: float = 0.5
    is_player: bool = False
    visible_to_player: bool = True
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_episode_text(self) -> str:
        """转换为自然语言描述，用于写入 Zep 图谱"""
        loc = f"（在{self.location}）" if self.location else ""
        return f"{self.agent_name}{loc}: {self.action_description}"


@dataclass
class PlayerChoice:
    """玩家选项"""
    id: str
    label: str
    description: str
    risk_level: str  # safe / moderate / exploratory / risky

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerTurnData:
    """玩家回合数据（引擎暂停时发送给前端）"""
    turn_number: int
    narrative_text: str
    choices: List[PlayerChoice] = field(default_factory=list)
    scene_description: str = ""
    current_location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["choices"] = [c.to_dict() if isinstance(c, PlayerChoice) else c for c in self.choices]
        return d


@dataclass
class NarrativeState:
    """叙事会话状态（可序列化）"""
    session_id: str
    graph_id: str
    project_id: str
    simulation_id: str = ""  # 来源 simulation 记录的 ID，用于历史导航
    status: str = NarrativeStatus.IDLE.value
    current_turn: int = 0
    player_entity_uuid: str = ""
    npc_turns_since_player: int = 0
    max_npc_turns_between_player: int = 3
    initial_scene: str = ""
    opening_text: str = ""  # 用户直写的开篇正文（非空时跳过 AI 生成）
    prior_summary: str = ""  # 前文摘要（非空时切换为续写模式）
    custom_title: str = ""   # 用户自定义标题（非空时覆盖自动生成的标题）

    # 所有事件 & 叙事段落（每个段落为 dict: {text, type, turn_number, timestamp, events?}）
    all_events: List[Dict] = field(default_factory=list)
    narrative_segments: List[Dict] = field(default_factory=list)

    # 玩家回合数据（当 status == AWAITING_PLAYER 时有值）
    player_turn_data: Optional[Dict] = None

    # 角色位置追踪
    agent_locations: Dict[str, str] = field(default_factory=dict)
    # 角色上次行动的回合
    agent_last_acted: Dict[str, int] = field(default_factory=dict)

    # 剧情规划结果（玩家行动后由 _plot_planning 生成，指导后续 NPC 回合）
    plot_plan: Optional[Dict] = None

    # 世界时间（每个行动前推进）
    world_day: int = 1       # 故事内第几天
    world_hour: float = 6.0  # 当前小时（0.0-24.0，满24进一天）

    # 世界地图（prepare 阶段由 AI 生成，存储地点邻接关系）
    # 格式: {"地点名": {"description": "...", "adjacent": ["邻接地点1", ...]}}
    world_map: Dict = field(default_factory=dict)

    # 世界物品（叙事过程中动态引入的物品实体）
    # 格式: {"物品名": {"uuid": "...", "description": "...", "location": "...", "owner": "...", "properties": "..."}}
    world_items: Dict = field(default_factory=dict)

    # 错误信息
    error_message: str = ""

    # 时间戳
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NarrativeState':
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ============================================================
# 事件格式化辅助函数
# ============================================================

def _sync_profile_location(profiles: List[Dict], entity_uuid: str, new_loc: str):
    """将移动后的位置同步回 profile dict，保持与 agent_locations 一致"""
    for p in profiles:
        if p.get("entity_uuid") == entity_uuid:
            p["current_location"] = new_loc
            break


def _has_segment(state, seg_type: str, turn_number: int) -> bool:
    """检查 narrative_segments 中是否已存在指定 turn+type 的段落"""
    return any(
        s.get("type") == seg_type and s.get("turn_number") == turn_number
        for s in state.narrative_segments
    )


def _world_time_str(world_day: int, world_hour: float) -> str:
    """将世界时间转换为中文时间段字符串，如 '第2日 傍晚 17:30'"""
    h = int(world_hour % 24)
    m = int((world_hour % 1) * 60)
    if 5 <= h < 7:
        period = "清晨"
    elif 7 <= h < 12:
        period = "上午"
    elif 12 <= h < 14:
        period = "午时"
    elif 14 <= h < 17:
        period = "午后"
    elif 17 <= h < 19:
        period = "傍晚"
    elif 19 <= h < 22:
        period = "入夜"
    else:
        period = "深夜"
    return f"第{world_day}日 {period} {h:02d}:{m:02d}"


def _advance_world_time(state, hours: float = 0.5):
    """每个行动前统一推进世界时间，返回推进后的时间字符串"""
    state.world_hour += hours
    if state.world_hour >= 24.0:
        state.world_hour -= 24.0
        state.world_day += 1
    return _world_time_str(state.world_day, state.world_hour)




def _format_event_line(e: Dict[str, Any], include_turn: bool = True) -> str:
    """
    统一事件格式化：优先使用世界时间，格式: [第N日 时段 HH:MM] 角色名（位置）: 行动描述
    """
    parts = []

    # 优先显示世界时间，否则回退到回合号
    wt = e.get("world_time", "")
    if wt:
        parts.append(f"[{wt}]")
    elif include_turn:
        parts.append(f"[回合{e.get('turn_number', '?')}]")

    # 角色名 + 位置
    agent_name = e.get("agent_name", "未知")
    location = e.get("location", "")
    if location:
        parts.append(f"{agent_name}（{location}）:")
    else:
        parts.append(f"{agent_name}:")

    parts.append(e.get("action_description", ""))
    return " ".join(parts)


# ============================================================
# NarrativeEngine — 核心引擎类
# ============================================================

class NarrativeEngine:
    """
    叙事引擎 - 管理叙事世界循环
    使用类级别状态（同 SimulationRunner 模式）
    """

    # 类级别共享状态
    _sessions: Dict[str, NarrativeState] = {}
    _engine_threads: Dict[str, threading.Thread] = {}
    _player_input_events: Dict[str, threading.Event] = {}
    _player_inputs: Dict[str, Dict] = {}
    _stop_flags: Dict[str, threading.Event] = {}
    _agent_profiles: Dict[str, List[Dict]] = {}  # session_id → profile dicts
    _locks: Dict[str, threading.Lock] = {}
    _npc_graph_cache: Dict[str, Dict[str, str]] = {}  # session_id → {agent_name: graph_context}

    # ---- 会话管理 ----

    @classmethod
    def create_session(
        cls,
        graph_id: str,
        project_id: str,
        player_entity_uuid: str,
        agent_profiles: List[NarrativeCharacterProfile],
        initial_scene: str = "",
        opening_text: str = "",
        prior_summary: str = "",
        max_npc_turns: int = None,
        simulation_id: str = ""
    ) -> NarrativeState:
        """创建叙事会话"""
        session_id = str(uuid.uuid4())

        state = NarrativeState(
            session_id=session_id,
            graph_id=graph_id,
            project_id=project_id,
            simulation_id=simulation_id,
            player_entity_uuid=player_entity_uuid,
            max_npc_turns_between_player=max_npc_turns or Config.NARRATIVE_MAX_NPC_TURNS,
            initial_scene=initial_scene,
            opening_text=opening_text,
            prior_summary=prior_summary
        )

        # 初始化角色位置
        for p in agent_profiles:
            state.agent_locations[p.entity_uuid] = p.current_location or "未知"
            state.agent_last_acted[p.entity_uuid] = -1

        cls._sessions[session_id] = state
        cls._agent_profiles[session_id] = [p.to_dict() for p in agent_profiles]
        cls._locks[session_id] = threading.Lock()
        cls._player_input_events[session_id] = threading.Event()
        cls._stop_flags[session_id] = threading.Event()

        # 持久化
        cls._save_state(state)

        logger.info(f"叙事会话已创建: {session_id} (graph={graph_id}, player={player_entity_uuid})")
        return state

    @classmethod
    def start_session(cls, session_id: str) -> NarrativeState:
        """启动叙事引擎循环"""
        state = cls._sessions.get(session_id)
        if not state:
            raise ValueError(f"会话不存在: {session_id}")

        if state.status == NarrativeStatus.RUNNING.value:
            logger.warning(f"会话已在运行: {session_id}")
            return state

        # 如果内存中没有 profiles（服务重启），从磁盘加载
        if not cls._agent_profiles.get(session_id):
            profiles = cls._load_profiles(session_id)
            if profiles:
                cls._agent_profiles[session_id] = profiles
                logger.info(f"从磁盘恢复角色档案: {len(profiles)} 个")

        state.status = NarrativeStatus.RUNNING.value
        state.updated_at = datetime.now().isoformat()
        cls._stop_flags[session_id].clear()
        cls._player_input_events[session_id].clear()

        thread = threading.Thread(
            target=cls._engine_loop,
            args=(session_id,),
            daemon=True,
            name=f"NarrativeEngine-{session_id[:8]}"
        )
        thread.start()
        cls._engine_threads[session_id] = thread

        cls._save_state(state)
        logger.info(f"叙事引擎已启动: {session_id}")
        return state

    @classmethod
    def stop_session(cls, session_id: str) -> NarrativeState:
        """停止叙事引擎"""
        state = cls._sessions.get(session_id)
        if not state:
            raise ValueError(f"会话不存在: {session_id}")

        cls._stop_flags.get(session_id, threading.Event()).set()
        # 解除可能的等待阻塞
        cls._player_input_events.get(session_id, threading.Event()).set()

        state.status = NarrativeStatus.COMPLETED.value
        state.updated_at = datetime.now().isoformat()
        cls._save_state(state)

        logger.info(f"叙事引擎已停止: {session_id}")
        return state

    @classmethod
    def resume_session(cls, session_id: str) -> NarrativeState:
        """从磁盘恢复会话并重启引擎循环"""
        # 确保状态已加载到内存
        state = cls.get_session(session_id)
        if not state:
            raise ValueError(f"会话不存在（内存和磁盘均未找到）: {session_id}")

        # 如果引擎线程仍然存活，直接返回
        existing_thread = cls._engine_threads.get(session_id)
        if existing_thread and existing_thread.is_alive():
            logger.info(f"会话引擎线程仍在运行，无需恢复: {session_id}")
            return state

        # 线程已死（服务器重启/崩溃），需要重启引擎线程
        if state.status == NarrativeStatus.AWAITING_PLAYER.value:
            logger.info(f"恢复等待玩家输入的会话: {session_id} (turn={state.current_turn})")
            # 保持 awaiting_player 状态，引擎线程启动后会在 wait() 处继续等待玩家输入
        else:
            # 其他状态（running/completed/failed）统一重置为 running
            state.status = NarrativeStatus.RUNNING.value
        state.updated_at = datetime.now().isoformat()
        cls._stop_flags[session_id].clear()
        cls._player_input_events[session_id].clear()

        # 启动引擎线程
        thread = threading.Thread(
            target=cls._engine_loop,
            args=(session_id,),
            daemon=True,
            name=f"NarrativeEngine-{session_id[:8]}"
        )
        thread.start()
        cls._engine_threads[session_id] = thread

        cls._save_state(state)
        logger.info(f"叙事引擎已恢复: {session_id} (turn={state.current_turn})")
        return state

    @classmethod
    def get_session(cls, session_id: str) -> Optional[NarrativeState]:
        """获取会话状态（内存优先，磁盘回退）"""
        state = cls._sessions.get(session_id)
        if state:
            return state

        # 内存中没有，尝试从磁盘加载（只读，不恢复引擎）
        state = cls._load_state(session_id)
        if state:
            cls._sessions[session_id] = state
            cls._locks.setdefault(session_id, threading.Lock())
            cls._player_input_events.setdefault(session_id, threading.Event())
            cls._stop_flags.setdefault(session_id, threading.Event())
            # 加载 profiles
            profiles = cls._load_profiles(session_id)
            if profiles:
                cls._agent_profiles[session_id] = profiles
        return state

    @classmethod
    def get_profiles(cls, session_id: str) -> List[Dict]:
        """获取角色档案（relationships 从 FalkorDB 边实时读取）"""
        profiles = cls._agent_profiles.get(session_id, [])
        state = cls._sessions.get(session_id)
        if not state or not profiles:
            return profiles

        # 用 FalkorDB 边刷新每个 profile 的 relationships
        try:
            from .falkordb_entity_reader import read_entity_edges
            for p in profiles:
                eu = p.get("entity_uuid", "")
                # 跳过自定义创建的角色（没有真实图谱节点）
                if not eu or eu.startswith("custom_"):
                    continue
                try:
                    edges = read_entity_edges(state.graph_id, eu)
                    if edges:
                        graph_rels = []
                        seen = set()
                        for edge in edges:
                            other_name = edge.get("other_name", "")
                            fact = edge.get("fact", "") or edge.get("edge_name", "")
                            if not other_name or not fact:
                                continue
                            dedup = (other_name, fact)
                            if dedup in seen:
                                continue
                            seen.add(dedup)
                            graph_rels.append({
                                "name": other_name,
                                "relation": fact,
                                "source": "graph",
                            })
                        # 保留 LLM 补充的（如果原来有），但 graph 的覆盖同名
                        old_rels = p.get("relationships", [])
                        graph_names = {r["name"] for r in graph_rels}
                        for old_r in old_rels:
                            if old_r.get("source") == "llm" and old_r.get("name") not in graph_names:
                                graph_rels.append(old_r)
                        p["relationships"] = graph_rels
                except Exception:
                    pass  # 单个 profile 查询失败不影响其他
        except Exception as e:
            logger.debug(f"刷新 relationships 失败（非致命）: {e}")

        return profiles

    @classmethod
    def submit_player_input(
        cls,
        session_id: str,
        choice_id: Optional[str] = None,
        free_text: Optional[str] = None
    ) -> bool:
        """提交玩家输入，恢复引擎"""
        state = cls._sessions.get(session_id)
        if not state or state.status != NarrativeStatus.AWAITING_PLAYER.value:
            return False

        cls._player_inputs[session_id] = {
            "choice_id": choice_id,
            "free_text": free_text,
            "timestamp": datetime.now().isoformat()
        }

        state.status = NarrativeStatus.PROCESSING_PLAYER.value
        state.updated_at = datetime.now().isoformat()

        # 唤醒引擎线程
        cls._player_input_events[session_id].set()
        logger.info(f"玩家输入已提交: session={session_id}, choice={choice_id}, text={free_text}")
        return True

    # ---- 引擎循环 (daemon thread) ----

    @classmethod
    def _engine_loop(cls, session_id: str):
        """主引擎循环 - 在守护线程中运行"""
        state = cls._sessions.get(session_id)
        if not state:
            return

        stop_flag = cls._stop_flags[session_id]
        profiles = cls._agent_profiles.get(session_id, [])

        try:
            llm = LLMClient()
            zep_client = Zep(api_key=Config.ZEP_API_KEY) if Config.ZEP_API_KEY else None

            # 修正 is_player 标记：prepare 阶段 player_uuid 可能为 'pending'，
            # 此处根据当前 state.player_entity_uuid 补正，确保玩家档案可被正确识别
            player_uuid = state.player_entity_uuid
            if player_uuid and player_uuid != 'pending' and profiles:
                corrected = False
                for p in profiles:
                    expected = (p.get("entity_uuid") == player_uuid)
                    if bool(p.get("is_player")) != expected:
                        p["is_player"] = expected
                        corrected = True
                if corrected:
                    cls._agent_profiles[session_id] = profiles
                    cls._save_state(state)
                    logger.info(f"已修正玩家标记: player_uuid={player_uuid}")

            # 生成初始叙事（仅在尚未生成时）
            # _generate_opening_narrative 有 initial_scene 的 fallback，无需强制非空
            if state.current_turn == 0 and not _has_segment(state, "opening", 0):
                if state.opening_text:
                    opening = state.opening_text
                else:
                    opening = cls._generate_opening_narrative(state, profiles, llm)
                state.narrative_segments.append({
                    "text": opening,
                    "type": "opening",
                    "turn_number": 0,
                    "timestamp": datetime.now().isoformat()
                })
                cls._save_state(state)

            # 恢复时如果已在等待玩家，直接进入等待，不跳 turn
            if state.player_turn_data and _has_segment(state, "player_scene", state.current_turn):
                state.status = NarrativeStatus.AWAITING_PLAYER.value
                cls._save_state(state)
                logger.info(f"恢复等待玩家输入... (turn={state.current_turn})")
                cls._player_input_events[session_id].clear()
                cls._player_input_events[session_id].wait()

                if not stop_flag.is_set():
                    profiles = cls._agent_profiles.get(session_id, [])
                    player_input = cls._player_inputs.pop(session_id, {})
                    cls._process_player_action(state, player_input, profiles, llm, zep_client)
                    state.npc_turns_since_player = 0
                    planned_turns = state.plot_plan.get("total_npc_turns") if state.plot_plan else None
                    state.max_npc_turns_between_player = planned_turns if planned_turns and 1 <= planned_turns <= 20 else random.randint(3, 8)
                    state.player_turn_data = None
                    state.status = NarrativeStatus.RUNNING.value
                    profiles = cls._agent_profiles.get(session_id, [])
                    cls._save_state(state)

            while not stop_flag.is_set():
                state.current_turn += 1
                state.updated_at = datetime.now().isoformat()

                # 1. 判断是否需要玩家行动
                if cls._should_player_act(state):
                    # 每次玩家回合前刷新 profiles（避免 prepare 比 start 晚完成的竞态）
                    profiles = cls._agent_profiles.get(session_id, [])
                    # 生成玩家叙事 & 选项
                    cls._prepare_player_turn(state, profiles, llm, zep_client)
                    cls._save_state(state)

                    # 只有在成功进入 awaiting_player 状态时才等待（_prepare_player_turn 失败则重试）
                    if state.status != NarrativeStatus.AWAITING_PLAYER.value:
                        logger.warning(f"_prepare_player_turn 未能进入 awaiting_player，回退重试 (turn={state.current_turn})")
                        state.current_turn -= 1  # 回退，下次循环重试同一回合
                        state.status = NarrativeStatus.RUNNING.value
                        time.sleep(2)
                        continue

                    # 等待玩家输入
                    logger.info(f"等待玩家输入... (turn={state.current_turn})")
                    cls._player_input_events[session_id].clear()
                    cls._player_input_events[session_id].wait()

                    if stop_flag.is_set():
                        break

                    # 重新读取 profiles（仿真中可能已被编辑）
                    profiles = cls._agent_profiles.get(session_id, [])

                    # 处理玩家输入
                    player_input = cls._player_inputs.pop(session_id, {})
                    cls._process_player_action(state, player_input, profiles, llm, zep_client)
                    state.npc_turns_since_player = 0
                    planned_turns = state.plot_plan.get("total_npc_turns") if state.plot_plan else None
                    state.max_npc_turns_between_player = planned_turns if planned_turns and 1 <= planned_turns <= 20 else random.randint(3, 8)
                    state.player_turn_data = None
                    state.status = NarrativeStatus.RUNNING.value
                    # 剧情规划可能引入/移除角色，重新加载 profiles
                    profiles = cls._agent_profiles.get(session_id, [])
                    cls._save_state(state)
                else:
                    # 2. NPC 回合（优先使用剧情规划的智能调度）
                    profiles = cls._agent_profiles.get(session_id, [])
                    selected_agents, time_minutes = cls._select_agents_for_turn(state, profiles)
                    # 在回合开始时统一推进世界时间（本回合所有NPC共用同一时间点）
                    _advance_world_time(state, time_minutes / 60.0)
                    current_world_time = _world_time_str(state.world_day, state.world_hour)
                    for agent in selected_agents:
                        if stop_flag.is_set():
                            break
                        cls._process_npc_turn(state, agent, profiles, llm, zep_client, current_world_time)
                    state.npc_turns_since_player += 1

                    # 注入当前回合 NPC 事件段落（供正文折叠显示）
                    turn_npc_events = [
                        e for e in state.all_events
                        if e.get("turn_number") == state.current_turn and not e.get("is_player")
                    ]
                    if turn_npc_events and not _has_segment(state, "npc_events", state.current_turn):
                        state.narrative_segments.append({
                            "text": "",
                            "type": "npc_events",
                            "turn_number": state.current_turn,
                            "world_time": _world_time_str(state.world_day, state.world_hour),
                            "events": turn_npc_events,
                            "timestamp": datetime.now().isoformat()
                        })

                    cls._save_state(state)

                # 短暂延迟避免高频循环
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"叙事引擎异常: {session_id}: {e}", exc_info=True)
            state.status = NarrativeStatus.FAILED.value
            state.error_message = str(e)
        finally:
            if state.status == NarrativeStatus.RUNNING.value:
                state.status = NarrativeStatus.COMPLETED.value
            state.updated_at = datetime.now().isoformat()
            cls._save_state(state)
            logger.info(f"叙事引擎循环结束: {session_id} (status={state.status})")

    # ---- 开场叙事 ----

    @classmethod
    def _generate_opening_narrative(
        cls,
        state: NarrativeState,
        profiles: List[Dict],
        llm: LLMClient
    ) -> str:
        """生成开场叙事段落（注入图谱背景信息）"""
        player_profile = next((p for p in profiles if p.get("is_player")), None)
        npc_profiles = [p for p in profiles if not p.get("is_player")]

        # ---- 玩家角色完整描述 ----
        player_desc = ""
        if player_profile:
            lines = [f"名字: {player_profile.get('name', '未知')}"]
            # profession 优先，fallback 到 entity_type（问题 A/B：两者之前均未传入）
            profession = player_profile.get('profession') or player_profile.get('entity_type', '')
            if profession:
                lines.append(f"职业/身份: {profession}")
            if player_profile.get('personality') or player_profile.get('persona'):
                lines.append(f"性格: {player_profile.get('personality') or player_profile.get('persona')}")
            bio = player_profile.get('bio') or player_profile.get('backstory')
            if bio:
                lines.append(f"背景: {bio[:300]}")
            goals = player_profile.get('goals') or player_profile.get('interested_topics')
            if goals:
                g = goals if isinstance(goals, str) else '、'.join(goals[:3])
                lines.append(f"目标/关注: {g}")
            loc = state.agent_locations.get(
                player_profile.get('entity_uuid', '')) or player_profile.get('current_location', '未知')
            lines.append(f"当前位置: {loc}")
            player_desc = "\n".join(lines)

        # ---- NPC 完整描述（取前 6 个最重要的）----
        npc_parts = []
        for p in npc_profiles[:6]:
            lines = [f"【{p['name']}】"]
            profession = p.get('profession') or p.get('entity_type', '')
            if profession:
                lines.append(f"  职业/身份: {profession}")
            if p.get('personality') or p.get('persona'):
                lines.append(f"  性格: {(p.get('personality') or p.get('persona'))[:100]}")
            bio = p.get('bio') or p.get('backstory')
            if bio:
                lines.append(f"  背景: {bio[:200]}")
            loc = state.agent_locations.get(p.get('entity_uuid', '')) or p.get('current_location', '未知')
            lines.append(f"  位置: {loc}")
            npc_parts.append("\n".join(lines))
        npc_descs = "\n".join(npc_parts) if npc_parts else "（暂无其他角色）"

        # ---- 角色关系总览（从 profiles 的 relationships 字段提取）----
        rel_lines = []
        for p in profiles:
            name = p.get('name', '')
            for rel in (p.get('relationships') or [])[:4]:
                other = rel.get('name', '')
                relation = rel.get('relation', '')
                if other and relation:
                    rel_lines.append(f"- {name} → {other}：{relation}")
        relationships_overview = "\n".join(rel_lines[:20]) if rel_lines else "（暂无已知关系数据）"

        # 从 FalkorDB 图谱中查询玩家和关键 NPC 的背景上下文
        graph_context = cls._build_opening_graph_context(state, player_profile, npc_profiles)

        if state.prior_summary:
            template_key = 'narrative_continuation'
            prompt = safe_render(get_template('narrative_continuation'), {
                'prior_summary': state.prior_summary,
                'initial_scene': state.initial_scene or "",
                'player_desc': player_desc,
                'npc_descs': npc_descs,
                'relationships_overview': relationships_overview,
                'graph_context': graph_context,
            })
        else:
            template_key = 'narrative_opening'
            prompt = safe_render(get_template('narrative_opening'), {
                'initial_scene': state.initial_scene or "一个充满未知的世界",
                'player_desc': player_desc,
                'npc_descs': npc_descs,
                'relationships_overview': relationships_overview,
                'graph_context': graph_context,
            })

        try:
            _p = get_llm_params(template_key)
            text = get_client_for_prompt(template_key).chat(
                messages=[
                    {"role": "system", "content": get_system(template_key)},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )
            return text.strip()
        except Exception as e:
            logger.error(f"生成开场叙事失败: {e}")
            return f"你睁开眼睛，发现自己身处一个陌生的地方。{state.initial_scene or '周围的一切都还模糊不清。'}"

    @classmethod
    def _build_opening_graph_context(
        cls,
        state: NarrativeState,
        player_profile: Optional[Dict],
        npc_profiles: List[Dict]
    ) -> str:
        """
        从 FalkorDB 查询玩家和关键 NPC 的图谱上下文，拼装为开场 prompt 用的文本。
        查询失败时静默降级，不影响开场叙事生成。
        """
        group_id = state.graph_id
        if not group_id:
            return "（暂无图谱信息）"

        parts = []

        # 查询玩家
        if player_profile:
            name = player_profile.get("name", "")
            if name:
                try:
                    ctx = search_entity_context(group_id, name, limit=6)
                    if ctx.strip():
                        parts.append(f"[{name}（玩家）]\n{ctx}")
                except Exception as e:
                    logger.warning(f"查询玩家图谱上下文失败 ({name}): {e}")

        # 查询前 5 个 NPC（过多会超 token）
        for p in npc_profiles[:5]:
            name = p.get("name", "")
            if not name:
                continue
            try:
                ctx = search_entity_context(group_id, name, limit=4)
                if ctx.strip():
                    parts.append(f"[{name}]\n{ctx}")
            except Exception as e:
                logger.warning(f"查询 NPC 图谱上下文失败 ({name}): {e}")

        if not parts:
            return "（暂无图谱信息）"

        return "\n\n".join(parts)

    # ---- 世界地图构建 ----

    @classmethod
    def _build_world_map_from_scene(
        cls,
        initial_scene: str,
        llm: LLMClient,
        source_text: str = ""
    ) -> Dict:
        """
        第一步：根据初始场景描述+原始文件文本生成世界地图（规范地名来源）。
        在角色档案生成之前调用，确保地名规范统一。
        """
        if not initial_scene and not source_text:
            return {}
        prompt = safe_render(get_template('world_map_from_scene'), {
            'initial_scene': initial_scene or "（用户未提供场景描述，请根据文件内容推断）",
            'source_text': source_text or "（无原始文件内容）",
        })
        try:
            _p = get_llm_params('world_map_from_scene')
            result = get_client_for_prompt('world_map_from_scene').chat_json(
                messages=[
                    {"role": "system", "content": get_system('world_map_from_scene')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )
            world_map = result.get("locations", result)
            if isinstance(world_map, dict) and world_map:
                world_map = cls._normalize_world_map(world_map)
                logger.info(f"场景地图预生成完成: {len(world_map)} 个规范地点: {list(world_map.keys())}")
                return world_map
        except Exception as e:
            logger.error(f"场景地图预生成失败: {e}")
        return {}

    @classmethod
    def _extract_locations_from_text(cls, text: str, llm: LLMClient) -> List[str]:
        """
        对全文分块并行提取地点名称，合并去重后返回。
        用于在世界地图构建前获得完整的地点名单。
        """
        import concurrent.futures

        chunk_size = 5000
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

        def extract_chunk(chunk_text: str, idx: int) -> List[str]:
            prompt = safe_render(get_template('location_extraction'), {
                'section_text': chunk_text,
            })
            try:
                _p = get_llm_params('location_extraction')
                result = get_client_for_prompt('location_extraction').chat_json(
                    messages=[
                        {"role": "system", "content": get_system('location_extraction')},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_p['temperature'],
                    max_tokens=_p['max_tokens'],
                )
                locs = result.get("locations", [])
                if isinstance(locs, list):
                    return [str(l).strip() for l in locs if str(l).strip()]
            except Exception as e:
                logger.warning(f"地点提取块 {idx} 失败: {e}")
            return []

        all_locations: set = set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(extract_chunk, chunk, i): i for i, chunk in enumerate(chunks)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    all_locations.update(future.result())
                except Exception as e:
                    logger.warning(f"地点提取块异常: {e}")

        location_list = sorted(all_locations)
        logger.info(f"全文地点提取完成: {len(location_list)} 个: {location_list}")
        return location_list

    @classmethod
    def _build_world_map_from_location_list(
        cls,
        location_names: List[str],
        initial_scene: str,
        graph_id: str,
        llm: LLMClient,
    ) -> Dict:
        """
        根据预提取的地点名单构建世界地图拓扑（邻接关系）。
        复用 world_map_build prompt，专注于拓扑推理而非地点发现。

        包含截断检测：如果 LLM 输出被截断导致地点数远少于输入，
        会自动重试（缩小输入列表 + 提高 max_tokens）。
        """
        if not location_names:
            return {}

        # 从 FalkorDB 获取地点背景信息
        location_facts = []
        try:
            from falkordb import FalkorDB
            db = FalkorDB(
                host=Config.FALKORDB_HOST,
                port=Config.FALKORDB_PORT,
                password=Config.FALKORDB_PASSWORD or None,
            )
            graph = db.select_graph(graph_id)
            for loc in location_names:
                try:
                    result = graph.query(
                        "MATCH (n:Entity) WHERE n.name = $name OR n.name CONTAINS $name "
                        "RETURN n.name, n.summary LIMIT 2",
                        {"name": loc}
                    )
                    if result.result_set:
                        for row in result.result_set:
                            name_val, summary = row[0], row[1]
                            if summary:
                                location_facts.append(f"- {name_val}: {str(summary)[:120]}")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"查询地点图谱信息失败（非致命）: {e}")

        facts_str = "\n".join(location_facts) if location_facts else "（无额外地点信息）"

        # ── 过滤过于模糊的地点名（单字、纯方位词等） ──
        _vague = {'屋', '室', '房', '门', '厅', '院', '楼', '阁', '处', '宫',
                  '里间', '正房', '堂屋', '后门', '二门', '北边', '卧室', '里头'}
        filtered_names = [n for n in location_names if n not in _vague and len(n) >= 2]
        if not filtered_names:
            filtered_names = location_names  # 全被过滤掉就用原始列表

        # ── 最多尝试 2 次，第 2 次缩减列表并提高 max_tokens ──
        MIN_EXPECTED = 15  # 合理地图的最少地点数
        best_map: Dict = {}

        for attempt in range(2):
            if attempt == 0:
                use_names = filtered_names
            else:
                # 第 2 次：只保留在图谱中有 summary 的地点（更可靠的核心地点）
                names_with_facts = {f.split(":")[0].lstrip("- ").strip()
                                    for f in (location_facts or [])}
                use_names = [n for n in filtered_names if n in names_with_facts]
                if len(use_names) < MIN_EXPECTED:
                    use_names = filtered_names[:60]  # 兜底：取前 60 个
                logger.info(f"地图重试: 缩减地点列表至 {len(use_names)} 个")

            locations_str = "\n".join(f"- {loc}" for loc in use_names)
            prompt = safe_render(get_template('world_map_build'), {
                'initial_scene': initial_scene or "一个虚构的叙事世界",
                'known_locations': locations_str,
                'location_facts': facts_str,
            })

            try:
                _p = get_llm_params('world_map_build')
                # 第 2 次尝试提高 max_tokens 以减少截断风险
                max_tok = _p['max_tokens'] if attempt == 0 else max(_p['max_tokens'], 16384)
                result = get_client_for_prompt('world_map_build').chat_json(
                    messages=[
                        {"role": "system", "content": get_system('world_map_build')},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_p['temperature'],
                    max_tokens=max_tok,
                )
                world_map = result.get("locations", result)
                if isinstance(world_map, dict) and world_map:
                    world_map = cls._normalize_world_map(world_map)
                    logger.info(
                        f"地点列表地图构建完成 (attempt {attempt+1}): "
                        f"{len(world_map)} 个地点: {list(world_map.keys())}"
                    )
                    # 截断检测：输入 > 30 个地点但输出 < MIN_EXPECTED，判定为截断
                    if len(use_names) > 30 and len(world_map) < MIN_EXPECTED:
                        logger.warning(
                            f"地图疑似被截断: 输入 {len(use_names)} 个地点，"
                            f"仅输出 {len(world_map)} 个（< {MIN_EXPECTED}），"
                            f"{'将重试' if attempt == 0 else '已用最佳结果'}"
                        )
                        # 保留当前结果作为兜底，继续重试
                        if len(world_map) > len(best_map):
                            best_map = world_map
                        if attempt == 0:
                            continue  # 重试
                    return world_map
            except Exception as e:
                logger.error(f"地点列表地图构建失败 (attempt {attempt+1}): {e}")

        # 所有尝试都不理想，返回最佳结果
        if best_map:
            logger.warning(f"地图构建使用截断后的最佳结果: {len(best_map)} 个地点")
        return best_map

    @staticmethod
    def _normalize_world_map(raw: Dict) -> Dict:
        """
        清洗 LLM 返回的 world_map：
        1. strip 所有地点名的空白字符
        2. 合并同名（strip 后相同）地点
        3. adjacent 数组去重、去自引用、去不存在的节点
        4. 确保邻接关系对称
        """
        # 第一遍：strip key，合并重复
        merged: Dict[str, Dict] = {}
        for loc, data in raw.items():
            key = loc.strip()
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "description": (data.get("description") or "").strip(),
                    "adjacent": []
                }
            # 合并 adjacent（先收集，后清洗）
            for a in data.get("adjacent", []):
                a = a.strip()
                if a and a not in merged[key]["adjacent"]:
                    merged[key]["adjacent"].append(a)

        all_locs = set(merged.keys())

        # 第二遍：清洗 adjacent（只保留存在的节点，去自引用，去重）
        for loc, data in merged.items():
            seen = set()
            clean = []
            for a in data["adjacent"]:
                if a in all_locs and a != loc and a not in seen:
                    seen.add(a)
                    clean.append(a)
            data["adjacent"] = clean

        # 第三遍：补全对称性（A→B 则 B→A）
        for loc, data in merged.items():
            for a in data["adjacent"]:
                if loc not in merged[a]["adjacent"]:
                    merged[a]["adjacent"].append(loc)

        return merged

    @classmethod
    def _build_world_map(
        cls,
        state: 'NarrativeState',
        profiles: List[Dict],
        llm: LLMClient
    ) -> Dict:
        """
        从角色位置和 FalkorDB 图谱构建世界地图（邻接关系）。
        在 prepare 阶段调用一次，结果存入 state.world_map。
        """
        # 收集所有已知地点
        known_locations: set = set()
        for loc in state.agent_locations.values():
            if loc and loc not in ("未知", "unknown"):
                known_locations.add(loc)
        for p in profiles:
            loc = p.get("current_location", "")
            if loc and loc not in ("未知", "unknown"):
                known_locations.add(loc)

        if not known_locations:
            logger.info("未发现已知地点，跳过世界地图构建")
            return {}

        # 从 FalkorDB 获取地点相关背景信息
        location_facts = []
        try:
            from falkordb import FalkorDB
            db = FalkorDB(
                host=Config.FALKORDB_HOST,
                port=Config.FALKORDB_PORT,
                password=Config.FALKORDB_PASSWORD or None,
            )
            graph = db.select_graph(state.graph_id)
            for loc in list(known_locations)[:12]:
                try:
                    result = graph.query(
                        "MATCH (n:Entity) WHERE n.name = $name OR n.name CONTAINS $name "
                        "RETURN n.name, n.summary LIMIT 2",
                        {"name": loc}
                    )
                    if result.result_set:
                        for row in result.result_set:
                            name_val, summary = row[0], row[1]
                            if summary:
                                location_facts.append(f"- {name_val}: {str(summary)[:120]}")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"查询地点图谱信息失败（非致命）: {e}")

        locations_str = "\n".join(f"- {loc}" for loc in sorted(known_locations))
        facts_str = "\n".join(location_facts) if location_facts else "（无额外地点信息）"

        prompt = safe_render(get_template('world_map_build'), {
            'initial_scene': state.initial_scene or "一个虚构的叙事世界",
            'known_locations': locations_str,
            'location_facts': facts_str,
        })

        try:
            _p = get_llm_params('world_map_build')
            result = get_client_for_prompt('world_map_build').chat_json(
                messages=[
                    {"role": "system", "content": get_system('world_map_build')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )
            world_map = result.get("locations", result)
            if isinstance(world_map, dict) and world_map:
                world_map = cls._normalize_world_map(world_map)
                logger.info(f"世界地图构建完成: {len(world_map)} 个地点, "
                            f"地点: {list(world_map.keys())}")
                return world_map
        except Exception as e:
            logger.error(f"世界地图 LLM 生成失败: {e}")

        # 降级：全连接地图（所有已知地点互相邻接）
        loc_list = sorted(loc.strip() for loc in known_locations if loc.strip())
        loc_list = list(dict.fromkeys(loc_list))  # 去重保序
        simple_map = {
            loc: {"description": "", "adjacent": [l for l in loc_list if l != loc]}
            for loc in loc_list
        }
        logger.info(f"使用降级全连接地图: {len(simple_map)} 个地点")
        return simple_map

    @staticmethod
    def _find_adjacent_toward(world_map: Dict, current: str, target: str) -> Optional[str]:
        """
        BFS 找出从 current 到 target 的第一步邻接节点。
        返回 None 表示无路可走（或地图不完整）。
        """
        if not world_map or current not in world_map:
            return None
        adj = world_map[current].get("adjacent", [])
        if target in adj:
            return target

        from collections import deque
        queue = deque([(current, [])])
        visited = {current}
        while queue:
            node, path = queue.popleft()
            for neighbor in world_map.get(node, {}).get("adjacent", []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                new_path = path + [neighbor]
                if neighbor == target:
                    return new_path[0]  # 第一步
                queue.append((neighbor, new_path))
        return None

    # ---- 判断是否该玩家行动 ----

    @classmethod
    def _should_player_act(cls, state: NarrativeState) -> bool:
        """判断是否需要玩家行动"""
        # 强制规则：NPC 回合数达到上限
        if state.npc_turns_since_player >= state.max_npc_turns_between_player:
            return True
        # 第一回合：开场叙事已生成，让玩家做出初始决定
        if state.current_turn == 1 and state.narrative_segments:
            return True
        return False

    # ---- NPC 回合处理 ----

    @classmethod
    def _select_agents_for_turn(
        cls,
        state: NarrativeState,
        profiles: List[Dict]
    ) -> tuple:
        """选择本回合行动的 NPC 及本回合推进的游戏内时间（分钟）。
        返回 (selected_agents: List[Dict], time_minutes: int)
        优先使用剧情规划的 scheduled_turns，否则回退到公平轮转。
        """
        npc_profiles = [p for p in profiles if not p.get("is_player")]
        if not npc_profiles:
            return [], 0

        current_turn_num = state.npc_turns_since_player + 1  # 1-based

        # ---- 优先：从 scheduled_turns 中查找匹配当前回合的计划 ----
        if state.plot_plan and state.plot_plan.get("scheduled_turns"):
            scheduled = state.plot_plan["scheduled_turns"]
            for i, st in enumerate(scheduled):
                if st.get("turn_offset") == current_turn_num:
                    time_minutes = max(1, int(st.get("time_minutes_since_last", 10)))
                    agent_plans = st.get("agents", [])
                    selected = []
                    for ap in agent_plans:
                        match = next(
                            (p for p in npc_profiles if p["entity_uuid"] == ap.get("entity_uuid")),
                            None
                        )
                        if match:
                            # 把剧情规划的 directive 临时附到 profile 上，供 NPC action 参考
                            if ap.get("directive"):
                                match = dict(match)  # 浅拷贝避免污染原 profile
                                match["_directive"] = ap["directive"]
                            selected.append(match)
                    # 消费掉这个已执行的计划回合
                    state.plot_plan["scheduled_turns"].pop(i)
                    if not state.plot_plan["scheduled_turns"]:
                        state.plot_plan = None
                    if selected:
                        logger.debug(f"计划调度(回合{current_turn_num}, +{time_minutes}min): {[p['name'] for p in selected]}")
                        return selected, time_minutes
                    break  # 计划存在但没找到对应角色，落入轮转

        # ---- 回退：基于公平轮转 + 随机，默认推进10分钟 ----
        sorted_npcs = sorted(npc_profiles, key=lambda p: state.agent_last_acted.get(p["entity_uuid"], -1))
        num_agents = min(random.randint(2, 8), len(sorted_npcs))
        top_candidates = sorted_npcs[:max(num_agents * 2, 4)]
        selected = random.sample(top_candidates, min(num_agents, len(top_candidates)))
        return selected, 10

    @classmethod
    def _get_npc_graph_context(
        cls,
        state: NarrativeState,
        agent_name: str,
    ) -> str:
        """查询 FalkorDB 图谱获取NPC的关系和背景事实，同session同agent复用缓存"""
        cache_key = state.session_id
        if cache_key in cls._npc_graph_cache and agent_name in cls._npc_graph_cache[cache_key]:
            return cls._npc_graph_cache[cache_key][agent_name]

        try:
            facts = search_entity_facts_by_name(
                group_id=state.graph_id,
                entity_name=agent_name,
                limit=6,
            )
            context = "\n".join(f"- {f}" for f in facts) if facts else ""

            # 写入缓存
            if cache_key not in cls._npc_graph_cache:
                cls._npc_graph_cache[cache_key] = {}
            cls._npc_graph_cache[cache_key][agent_name] = context
            return context

        except Exception as e:
            logger.warning(f"NPC图谱查询失败 ({agent_name}): {e}")
            return ""

    @classmethod
    def _recall_memory(
        cls,
        state: NarrativeState,
        agent: Dict,
        personality: str,
        goals_str: str,
        location: str,
        current_world_time: str,
        same_loc_str: str,
        recent_text: str,
        directive_str: str,
    ) -> str:
        """
        记忆检索（两轮调用的第一轮）：
        根据角色的 known_nodes 和当前场景，让 LLM 选出此刻最相关的记忆节点，
        然后从 FalkorDB 查询这些节点的详情，返回格式化的记忆文本。
        """
        agent_name = agent.get("name", "NPC")
        known_nodes = agent.get("known_nodes", [])
        if not known_nodes:
            return "（无额外记忆）"

        # 构建已知节点目录（用于 LLM 选择）
        # 先尝试从缓存取全部节点信息，避免反复查库
        all_nodes_cache_key = f"_all_nodes_{state.graph_id}"
        all_nodes_map = getattr(cls, all_nodes_cache_key, None)
        if all_nodes_map is None:
            try:
                from .falkordb_entity_reader import read_all_nodes_directory
                all_nodes_list = read_all_nodes_directory(group_id=state.graph_id)
                all_nodes_map = {n["uuid"]: n for n in all_nodes_list}
                setattr(cls, all_nodes_cache_key, all_nodes_map)
            except Exception as e:
                logger.warning(f"记忆检索：获取节点目录失败: {e}")
                return "（无额外记忆）"

        # 只列出角色已知的节点
        dir_lines = []
        for uuid in known_nodes:
            nd = all_nodes_map.get(uuid)
            if nd:
                n_labels = [l for l in nd.get("labels", []) if l not in ("Entity", "Node")]
                type_str = n_labels[0] if n_labels else "未分类"
                summary_short = (nd.get("summary", "") or "")[:50]
                dir_lines.append(f"- [{uuid}] {nd['name']}（{type_str}）：{summary_short}")
        if not dir_lines:
            return "（无额外记忆）"

        known_nodes_directory = "\n".join(dir_lines)

        # 第一轮 LLM 调用：选择要召回的记忆
        recall_prompt = safe_render(get_template('memory_recall'), {
            'agent_name': agent_name,
            'personality': personality,
            'goals': goals_str or '无明确目标',
            'location': location,
            'temperament': agent.get('temperament', '平和'),
            'world_time': current_world_time,
            'same_loc_agents': same_loc_str,
            'recent_text': recent_text or '（暂无事件）',
            'directive': directive_str,
            'known_nodes_directory': known_nodes_directory,
        })

        try:
            _p = get_llm_params('memory_recall')
            recall_result = get_client_for_prompt('memory_recall').chat_json(
                messages=[
                    {"role": "system", "content": get_system('memory_recall')},
                    {"role": "user", "content": recall_prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )
        except Exception as e:
            logger.warning(f"记忆检索LLM调用失败 ({agent_name}): {e}")
            return "（无额外记忆）"

        recalled_uuids = recall_result.get("recalled_node_uuids", [])
        recall_reason = recall_result.get("recall_reason", "")
        if recall_reason:
            logger.debug(f"记忆检索 ({agent_name}): {recall_reason}")

        if not recalled_uuids:
            return "（无额外记忆）"

        # 验证 UUID 有效性：只保留确实在 known_nodes 中的
        valid_recalled = [u for u in recalled_uuids if u in known_nodes][:8]
        if not valid_recalled:
            return "（无额外记忆）"

        # 查询召回节点的详细信息
        try:
            recalled_nodes = read_nodes_by_uuids(
                group_id=state.graph_id,
                uuids=valid_recalled,
            )
        except Exception as e:
            logger.warning(f"记忆检索：查询节点详情失败: {e}")
            return "（无额外记忆）"

        # 格式化为记忆文本
        memory_parts = []
        for nd in recalled_nodes:
            nd_name = nd.get("name", "")
            nd_summary = nd.get("summary", "")
            nd_facts = nd.get("related_facts", [])
            part = f"【{nd_name}】{nd_summary}"
            if nd_facts:
                part += "\n" + "\n".join(f"  - {f}" for f in nd_facts[:4])
            memory_parts.append(part)

        return "\n\n".join(memory_parts) if memory_parts else "（无额外记忆）"

    @classmethod
    def _process_npc_turn(
        cls,
        state: NarrativeState,
        agent: Dict,
        all_profiles: List[Dict],
        llm: LLMClient,
        zep_client: Optional[Zep],
        current_world_time: str = ""
    ):
        """处理单个 NPC 的回合。current_world_time 由调用方在回合开始时统一推进后传入。"""
        agent_name = agent.get("name", "NPC")
        agent_uuid = agent.get("entity_uuid", "")
        location = state.agent_locations.get(agent_uuid, "未知")

        # 若调用方未传入时间（兼容旧调用路径），回退到当前时间字符串
        if not current_world_time:
            current_world_time = _world_time_str(state.world_day, state.world_hour)

        # 构建上下文：最近全局事件
        npc_global_count = get_setting('npc_global_events_count')
        recent_events = state.all_events[-npc_global_count:] if state.all_events else []
        recent_text = "\n".join(_format_event_line(e) for e in recent_events)

        # 构建 NPC 自身行动历史
        npc_own_count = get_setting('npc_own_actions_count')
        my_actions = [e for e in state.all_events if e.get("agent_uuid") == agent_uuid][-npc_own_count:]
        my_recent_actions_text = "\n".join(_format_event_line(e) for e in my_actions) if my_actions else "（暂无行动记录）"

        # 空间感知：区分同地/异地角色
        same_loc_agents = []
        other_loc_agents = []
        for p in all_profiles:
            if p["entity_uuid"] == agent_uuid:
                continue
            p_loc = state.agent_locations.get(p["entity_uuid"], "未知")
            if p_loc == location:
                same_loc_agents.append(p["name"])
            else:
                other_loc_agents.append(f"{p['name']}（{p_loc}）")

        same_loc_str = "、".join(same_loc_agents) if same_loc_agents else "无"
        other_loc_str = "、".join(other_loc_agents) if other_loc_agents else "无"

        # 从世界地图获取当前位置的邻接地点
        adjacent_locs = []
        if state.world_map and location in state.world_map:
            adjacent_locs = state.world_map[location].get("adjacent", [])
        adjacent_str = "、".join(adjacent_locs) if adjacent_locs else "（地图未知，可自行判断）"

        # 图谱上下文（查询本 NPC，FalkorDB summary 已在构建时用 entity_database 充实）
        graph_context = cls._get_npc_graph_context(state, agent_name)

        personality = agent.get('personality') or agent.get('persona') or '未知'
        backstory = (agent.get('bio') or agent.get('backstory') or '')[:200]
        goals_raw = agent.get('goals') or agent.get('interested_topics') or []
        goals_str = ', '.join(goals_raw) if isinstance(goals_raw, list) else str(goals_raw)
        directive_str = (
            f"（剧情规划建议：{agent.get('_directive')}。仅供参考，可根据角色性格���情境自由发挥）"
            if agent.get('_directive') else '（无特别提示，自由行动）'
        )

        # ====== 第一轮：记忆检索 ======
        recalled_memory_text = "（无额外记忆）"
        known_nodes = agent.get('known_nodes', [])
        if known_nodes:
            recalled_memory_text = cls._recall_memory(
                state=state,
                agent=agent,
                personality=personality,
                goals_str=goals_str,
                location=location,
                current_world_time=current_world_time,
                same_loc_str=same_loc_str,
                recent_text=recent_text,
                directive_str=directive_str,
            )

        # ====== ���二轮：���动生成（注入召回的记忆） ======
        prompt = safe_render(get_template('npc_action'), {
            'agent_name': agent_name,
            'world_time': current_world_time,
            'personality': personality,
            'backstory': backstory or '（无背景信息）',
            'goals': goals_str or '无明确目标',
            'location': location,
            'speech_style': agent.get('speech_style', '普通'),
            'temperament': agent.get('temperament', '平和'),
            'same_loc_agents': same_loc_str,
            'adjacent_locations': adjacent_str,
            'other_loc_agents': other_loc_str,
            'my_recent_actions': my_recent_actions_text,
            'recent_text': recent_text or '（暂无事件）',
            'graph_context': graph_context or '（无图谱信息）',
            'recalled_memory': recalled_memory_text,
            'directive': directive_str,
        })

        try:
            _p = get_llm_params('npc_action')
            action_text = get_client_for_prompt('npc_action').chat(
                messages=[
                    {"role": "system", "content": get_system('npc_action')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            ).strip()
        except Exception as e:
            logger.error(f"NPC行动生成失败 ({agent_name}): {e}")
            action_text = f"{agent_name}安静地待在原地，若有所思。"

        # 检测位置变化（含邻接验证）
        if "[移动到:" in action_text:
            try:
                new_loc = action_text.split("[移动到:")[1].split("]")[0].strip()
                # 邻接验证：如果世界地图已构建，检查目标是否可直达
                if state.world_map and location in state.world_map and adjacent_locs:
                    if new_loc not in adjacent_locs:
                        # 目标不邻接，尝试路径规划（移动一步）
                        step = cls._find_adjacent_toward(state.world_map, location, new_loc)
                        if step and step != new_loc:
                            logger.info(
                                f"路径规划: {agent_name} 无法直达 {new_loc}，"
                                f"先移动到 {step}（从 {location}）"
                            )
                            action_text = action_text.replace(
                                f"[移动到: {new_loc}]", f"[移动到: {step}]"
                            )
                            new_loc = step
                        elif not step:
                            logger.warning(
                                f"{agent_name} 移动到 {new_loc} 无路可走，保持原位"
                            )
                            action_text = action_text.split("[移动到:")[0].strip()
                            new_loc = location
                state.agent_locations[agent_uuid] = new_loc
                # 同步回 profile dict，保持一致性
                _sync_profile_location(all_profiles, agent_uuid, new_loc)
                action_text = action_text.split("[移动到:")[0].strip()
            except (IndexError, ValueError):
                pass

        # 评估事件重要性 + 知识更新 + 性格变化
        eval_result = cls._rate_event_importance(
            action_text, llm, agent_name=agent_name,
            agent_known_nodes=known_nodes,
            graph_id=state.graph_id,
        )
        importance = eval_result["importance"]

        event = NarrativeEvent(
            turn_number=state.current_turn,
            agent_name=agent_name,
            agent_uuid=agent_uuid,
            action_type="npc_action",
            action_description=action_text,
            location=location,
            importance=importance,
            is_player=False,
            visible_to_player=True
        )
        event_dict = event.to_dict()
        event_dict["world_time"] = current_world_time

        state.all_events.append(event_dict)
        state.agent_last_acted[agent_uuid] = state.current_turn

        # 高重要性事件：写入图谱 + 更新角色记忆和 profile
        if importance >= Config.NARRATIVE_IMPORTANCE_THRESHOLD:
            if zep_client:
                cls._write_event_to_graph(event, state.graph_id, zep_client)

            # 更新角色已知节点（new_knowledge）
            new_knowledge = eval_result.get("new_knowledge", [])
            if new_knowledge and known_nodes is not None:
                existing_set = set(known_nodes)
                for nk_uuid in new_knowledge:
                    if nk_uuid not in existing_set:
                        known_nodes.append(nk_uuid)
                        existing_set.add(nk_uuid)
                agent['known_nodes'] = known_nodes
                logger.debug(f"记忆更新 ({agent_name}): +{len(new_knowledge)} 节点")

            # 更新角色 profile（profile_change）
            profile_change = eval_result.get("profile_change")
            if profile_change and isinstance(profile_change, dict):
                for field_name, new_value in profile_change.items():
                    if field_name in ('goals', 'temperament', 'personality', 'speech_style'):
                        agent[field_name] = new_value
                        logger.info(f"角色演化 ({agent_name}): {field_name} → {new_value}")

        logger.debug(f"NPC行动: {agent_name} (重要性={importance:.2f}): {action_text[:80]}")

    @classmethod
    def _rate_event_importance(
        cls,
        action_text: str,
        llm: LLMClient,
        agent_name: str = "",
        agent_known_nodes: Optional[List[str]] = None,
        graph_id: str = "",
    ) -> Dict[str, Any]:
        """
        评估事件重要性 (0-1)，同时判断新知识获取和角色性格变化。

        Returns:
            {"importance": float, "new_knowledge": [str], "profile_change": dict|None}
        """
        default = {"importance": 0.5, "new_knowledge": [], "profile_change": None}

        # 构建 unknown_nodes_nearby：角色尚未知道的节点
        unknown_nodes_text = "（无）"
        known_set = set(agent_known_nodes or [])
        if graph_id and known_set:
            try:
                all_nodes_cache_key = f"_all_nodes_{graph_id}"
                all_nodes_map = getattr(cls, all_nodes_cache_key, None)
                if all_nodes_map is None:
                    from .falkordb_entity_reader import read_all_nodes_directory
                    all_nodes_list = read_all_nodes_directory(group_id=graph_id)
                    all_nodes_map = {n["uuid"]: n for n in all_nodes_list}
                    setattr(cls, all_nodes_cache_key, all_nodes_map)

                unknown_lines = []
                for uid, nd in all_nodes_map.items():
                    if uid not in known_set:
                        n_name = nd.get("name", "")
                        n_summary = (nd.get("summary", "") or "")[:40]
                        unknown_lines.append(f"- [{uid}] {n_name}：{n_summary}")
                if unknown_lines:
                    unknown_nodes_text = "\n".join(unknown_lines[:30])
            except Exception as e:
                logger.debug(f"构建未知节点列表失败: {e}")

        try:
            _p = get_llm_params('event_importance')
            result = get_client_for_prompt('event_importance').chat_json(
                messages=[
                    {"role": "system", "content": get_system('event_importance')},
                    {"role": "user", "content": safe_render(get_template('event_importance'), {
                        "action_text": action_text,
                        "agent_name": agent_name or "未知",
                        "agent_known_nodes": ", ".join(agent_known_nodes[:20]) if agent_known_nodes else "（无）",
                        "unknown_nodes_nearby": unknown_nodes_text,
                    })}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )
            importance = max(0.0, min(1.0, float(result.get("importance", 0.5))))
            new_knowledge = result.get("new_knowledge", [])
            # 验证 new_knowledge 中的 UUID 确实在 unknown 节点中
            if new_knowledge and known_set:
                new_knowledge = [u for u in new_knowledge if u not in known_set]
            profile_change = result.get("profile_change")
            return {
                "importance": importance,
                "new_knowledge": new_knowledge,
                "profile_change": profile_change,
            }
        except Exception:
            return default

    @classmethod
    def _write_event_to_graph(cls, event: NarrativeEvent, graph_id: str, zep_client: Optional[Zep]):
        """将高重要性事件写入图谱（FalkorDB 为主，Zep 为辅）"""
        # 写入 FalkorDB：将事件作为边 fact 写入参与者节点之间
        try:
            from falkordb import FalkorDB
            db = FalkorDB(
                host=Config.FALKORDB_HOST,
                port=Config.FALKORDB_PORT,
                password=Config.FALKORDB_PASSWORD or None,
            )
            graph = db.select_graph(graph_id)
            fact_text = f"[回合{event.turn_number}] {event.agent_name}: {event.action_description}"
            # 更新该 agent 节点的 summary（追加事件）
            graph.query(
                "MATCH (n:Entity {uuid: $uuid}) "
                "SET n.summary = CASE WHEN n.summary IS NULL THEN $fact "
                "ELSE n.summary + '\\n' + $fact END",
                {"uuid": event.agent_uuid, "fact": fact_text[:300]}
            )
        except Exception as e:
            logger.debug(f"FalkorDB 事件写入失败（非致命）: {e}")

        # 回退写入 Zep Cloud
        if zep_client:
            try:
                zep_client.graph.episode.add(
                    graph_id=graph_id,
                    episodes=[{
                        "content": event.to_episode_text(),
                        "source": "narrative_engine",
                        "source_description": f"叙事引擎 - 回合{event.turn_number}"
                    }]
                )
            except Exception as e:
                logger.debug(f"Zep 事件写入失败（非致命）: {e}")

    # ---- 玩家回合处理 ----

    @classmethod
    def _prepare_player_turn(
        cls,
        state: NarrativeState,
        profiles: List[Dict],
        llm: LLMClient,
        zep_client: Optional[Zep]
    ):
        """准备玩家回合：生成叙事文本 + 选项"""
        player_profile = next((p for p in profiles if p.get("is_player")), None)
        if not player_profile:
            logger.error("找不到玩家角色档案")
            return

        player_location = state.agent_locations.get(state.player_entity_uuid, "未知")

        # 收集自上次玩家回合以来的事件
        events_count = get_setting('events_text_count')
        recent_events = []
        for e in state.all_events:
            if e.get("visible_to_player", True):
                recent_events.append(e)
        # 只取最近的事件
        recent_events = recent_events[-events_count:]

        # 搜索 FalkorDB 图谱获取玩家角色上下文
        # （FalkorDB summary 已在构建时用 entity_database 充实，无需额外注入）
        graph_context = ""
        try:
            graph_context = search_entity_context(
                group_id=state.graph_id,
                entity_name=player_profile['name'],
                limit=8,
            )
        except Exception as e:
            logger.warning(f"FalkorDB 图谱搜索失败: {e}")

        # 附近角色
        nearby = [
            p["name"] for p in profiles
            if not p.get("is_player")
            and state.agent_locations.get(p["entity_uuid"], "") == player_location
        ]

        # 从世界地图获取玩家当前位置的邻接地点
        player_adjacent_locs = []
        if state.world_map and player_location in state.world_map:
            player_adjacent_locs = state.world_map[player_location].get("adjacent", [])
        player_adjacent_str = "、".join(player_adjacent_locs) if player_adjacent_locs else "（地图未知）"

        events_text = "\n".join(
            f"- {_format_event_line(e)}"
            for e in recent_events
        )

        # 收集最近叙事正文，用于延续叙事风格和情节
        prev_count = get_setting('previous_narrative_count')
        prev_max_chars = get_setting('previous_narrative_max_chars')
        prev_segments = [s for s in state.narrative_segments
                         if s.get("type") in ("player_scene", "opening")][-prev_count:]
        previous_narrative = "\n\n---\n\n".join(
            s["text"] for s in prev_segments if s.get("text")
        )
        if len(previous_narrative) > prev_max_chars:
            previous_narrative = previous_narrative[-prev_max_chars:]

        # 当前世界时间（不推进，player_scene 是对当前时刻的描写）
        current_world_time = _world_time_str(state.world_day, state.world_hour)

        # 生成叙事文本
        player_name = player_profile['name']
        personality = player_profile.get('personality') or player_profile.get('persona') or ''
        nearby_str = ', '.join(nearby) if nearby else '无人在附近'
        events_text_val = events_text or '（一切平静）'
        graph_context_val = graph_context or '（无额外信息）'
        previous_narrative_val = previous_narrative or '（这是故事的开始）'

        # 开场后的第一个玩家回合：直接用开场叙事作为选项上下文，不再生成额外正文
        is_opening_turn = state.current_turn == 1 and _has_segment(state, "opening", 0)

        if is_opening_turn:
            opening_seg = next((s for s in state.narrative_segments if s.get("type") == "opening"), None)
            narrative_text = opening_seg["text"] if opening_seg else previous_narrative_val
        else:
            narrative_prompt = safe_render(get_template('player_scene'), {
                "player_name": player_name,
                "personality": personality,
                "player_location": player_location,
                "world_time": current_world_time,
                "nearby": nearby_str,
                "adjacent_locations": player_adjacent_str,
                "events_text": events_text_val,
                "graph_context": graph_context_val,
                "previous_narrative": previous_narrative_val,
            })

            try:
                _p = get_llm_params('player_scene')
                narrative_text = get_client_for_prompt('player_scene').chat(
                    messages=[
                        {"role": "system", "content": get_system('player_scene')},
                        {"role": "user", "content": narrative_prompt}
                    ],
                    temperature=_p['temperature'],
                    max_tokens=_p['max_tokens']
                ).strip()
            except Exception as e:
                logger.error(f"生成玩家叙事失败: {e}")
                narrative_text = "你环顾四周，一切似乎正在发生变化。你感到此刻需要做出一个选择。"

        # 生成选项
        choices = cls._generate_player_choices(state, narrative_text, player_profile, llm, previous_narrative_val)

        # 设置 player_turn_data
        ptd = PlayerTurnData(
            turn_number=state.current_turn,
            narrative_text=narrative_text,
            choices=choices,
            scene_description=f"位置: {player_location}" + (f" | 附近: {', '.join(nearby)}" if nearby else ""),
            current_location=player_location
        )

        state.player_turn_data = ptd.to_dict()
        # 开场回合不新增 player_scene 段落，开场文本已经展示
        if not is_opening_turn and not _has_segment(state, "player_scene", state.current_turn):
            state.narrative_segments.append({
                "text": narrative_text,
                "type": "player_scene",
                "turn_number": state.current_turn,
                "world_time": current_world_time,
                "location": player_location,
                "timestamp": datetime.now().isoformat()
            })
        state.status = NarrativeStatus.AWAITING_PLAYER.value
        state.updated_at = datetime.now().isoformat()

    @classmethod
    def _generate_player_choices(
        cls,
        state: NarrativeState,
        narrative_text: str,
        player_profile: Dict,
        llm: LLMClient,
        previous_narrative: str = ""
    ) -> List[PlayerChoice]:
        """生成4个玩家选项"""
        player_name = player_profile.get('name', '')
        personality = player_profile.get('personality', '')

        prompt = safe_render(get_template('player_choices'), {
            "narrative_text": narrative_text,
            "player_name": player_name,
            "personality": personality,
            "previous_narrative": previous_narrative or "（这是故事的开始）",
        })

        try:
            _p = get_llm_params('player_choices')
            result = get_client_for_prompt('player_choices').chat_json(
                messages=[
                    {"role": "system", "content": get_system('player_choices')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )

            choices = []
            for c in result.get("choices", []):
                choices.append(PlayerChoice(
                    id=str(c.get("id", str(len(choices) + 1))),
                    label=c.get("label", f"选项{len(choices) + 1}"),
                    description=c.get("description", ""),
                    risk_level=c.get("risk_level", "moderate")
                ))

            # 确保至少有4个选项
            while len(choices) < 4:
                choices.append(PlayerChoice(
                    id=str(len(choices) + 1),
                    label=f"选项{len(choices) + 1}",
                    description="继续观察局势",
                    risk_level="safe"
                ))

            return choices[:4]

        except Exception as e:
            logger.error(f"生成选项失败: {e}")
            return [
                PlayerChoice(id="1", label="观望等待", description="继续观察周围的情况", risk_level="safe"),
                PlayerChoice(id="2", label="向前推进", description="朝着目标方向前进", risk_level="moderate"),
                PlayerChoice(id="3", label="四处探索", description="探索周围未知的区域", risk_level="exploratory"),
                PlayerChoice(id="4", label="冒险行动", description="采取大胆的行动", risk_level="risky"),
            ]

    # ---- 玩家输入处理 ----

    @classmethod
    def _process_player_action(
        cls,
        state: NarrativeState,
        player_input: Dict,
        profiles: List[Dict],
        llm: LLMClient,
        zep_client: Optional[Zep]
    ):
        """处理玩家输入后的逻辑"""
        # 每5个玩家回合清空NPC图谱缓存
        if state.current_turn % 5 == 0:
            cls._npc_graph_cache.pop(state.session_id, None)

        player_profile = next((p for p in profiles if p.get("is_player")), None)
        if not player_profile:
            return

        choice_id = player_input.get("choice_id")
        free_text = player_input.get("free_text")

        # 确定玩家实际行动
        player_action = ""
        if free_text:
            player_action = free_text
        elif choice_id and state.player_turn_data:
            choices = state.player_turn_data.get("choices", [])
            selected = next((c for c in choices if str(c.get("id")) == str(choice_id)), None)
            if selected:
                player_action = f"{selected.get('label', '')}: {selected.get('description', '')}"

        if not player_action:
            player_action = "观望等待"

        # 行动前推进世界时间（与 NPC 行动等量）
        current_world_time = _advance_world_time(state)

        # 玩家行动作为普通事件，与 NPC 事件无区别
        event = NarrativeEvent(
            turn_number=state.current_turn,
            agent_name=player_profile["name"],
            agent_uuid=state.player_entity_uuid,
            action_type="player_action",
            action_description=player_action,
            location=state.agent_locations.get(state.player_entity_uuid, "未知"),
            importance=0.8,
            is_player=True,
            visible_to_player=True
        )
        event_dict = event.to_dict()
        event_dict["world_time"] = current_world_time
        state.all_events.append(event_dict)

        # 写入图谱
        if zep_client:
            cls._write_event_to_graph(event, state.graph_id, zep_client)

        # 检测并应用玩家移动（问题9：玩家位置之前从不更新）
        cls._detect_player_movement(state, player_action)

        # 剧情规划（指导后续 NPC 如何反应）
        cls._plot_planning(state, player_action, player_profile, profiles, llm, zep_client)

        # 将玩家所选行动作为独立段落存入 narrative_segments，显示在正文流中
        state.narrative_segments.append({
            "text": player_action,
            "type": "player_choice",
            "turn_number": state.current_turn,
            "world_time": current_world_time,
            "timestamp": datetime.now().isoformat()
        })

        logger.info(f"玩家行动已记录为事件: [{current_world_time}] {player_action[:60]}")

    @classmethod
    def _detect_player_movement(cls, state: NarrativeState, player_action: str):
        """
        检测玩家行动文本中的移动意图并更新位置。
        优先识别显式标记 [移动到: xxx]（兼容中英文冒号），
        其次识别自然语言中的移动动词 + 地图已知地点名。
        """
        import re
        if not state.world_map:
            return

        current_loc = state.agent_locations.get(state.player_entity_uuid, "未知")
        new_loc = None

        # 1. 显式标记（兼容全角/半角冒号）
        m = re.search(r'\[移动到[：:]\s*([^\]]+)\]', player_action)
        if m:
            new_loc = m.group(1).strip()
        else:
            # 2. 自然语言：行动中包含移动动词 + 地图中存在的地点名
            move_verbs = ['前往', '去到', '走向', '走去', '走到', '来到', '赶往', '奔向', '返回', '回到', '移动到', '去']
            has_move_verb = any(v in player_action for v in move_verbs)
            if has_move_verb:
                # 找到行动文本中出现的地图地点（排除当前位置）
                new_loc = next(
                    (loc for loc in state.world_map if loc in player_action and loc != current_loc),
                    None
                )

        if not new_loc or new_loc not in state.world_map:
            return

        # 3. 邻接验证：直接相邻则移动，否则走一步
        adj = state.world_map.get(current_loc, {}).get("adjacent", [])
        if new_loc in adj:
            state.agent_locations[state.player_entity_uuid] = new_loc
            _sync_profile_location(cls._agent_profiles.get(state.session_id, []), state.player_entity_uuid, new_loc)
            logger.info(f"玩家移动: {current_loc} → {new_loc}")
        else:
            step = cls._find_adjacent_toward(state.world_map, current_loc, new_loc)
            if step:
                state.agent_locations[state.player_entity_uuid] = step
                _sync_profile_location(cls._agent_profiles.get(state.session_id, []), state.player_entity_uuid, step)
                logger.info(f"玩家移动（路径规划）: {current_loc} → {step}（目标: {new_loc}）")

    @classmethod
    def _generate_action_result(
        cls,
        state: NarrativeState,
        player_action: str,
        player_profile: Dict,
        llm: LLMClient
    ) -> str:
        """生成玩家行动的结果叙事"""
        player_name = player_profile['name']
        player_location = state.agent_locations.get(state.player_entity_uuid, "未知")

        # 取最近一段 player_scene 正文作为当前场景
        current_scene = ""
        for seg in reversed(state.narrative_segments):
            if seg.get("type") == "player_scene" and seg.get("text"):
                current_scene = seg["text"][:800]
                break

        # 取最近5条事件
        recent_events = state.all_events[-5:] if state.all_events else []
        recent_events_text = "\n".join(
            f"- {_format_event_line(e)}" for e in recent_events
        )

        prompt = safe_render(get_template('action_result'), {
            "player_name": player_name,
            "player_action": player_action,
            "player_location": player_location,
            "current_scene": current_scene or "（无当前场景）",
            "recent_events_text": recent_events_text or "（无近期事件）",
        })

        try:
            _p = get_llm_params('action_result')
            text = get_client_for_prompt('action_result').chat(
                messages=[
                    {"role": "system", "content": get_system('action_result')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            ).strip()
            return text
        except Exception as e:
            logger.error(f"生成行动结果失败: {e}")
            return ""

    @classmethod
    def _plot_planning(
        cls,
        state: NarrativeState,
        player_action: str,
        player_profile: Dict,
        all_profiles: List[Dict],
        llm: LLMClient,
        zep_client: Optional[Zep]
    ):
        """剧情规划：智能调度 NPC 反应、引入/退场角色、场景转换"""
        player_location = state.agent_locations.get(state.player_entity_uuid, '未知')

        recent_events_text = "\n".join(
            f"- {_format_event_line(e)}"
            for e in state.all_events[-10:]
        )

        npc_profiles = [p for p in all_profiles if not p.get("is_player")]
        npc_list_text = "\n".join(
            f"- {p['name']} (uuid: {p['entity_uuid']}) | "
            f"位于: {state.agent_locations.get(p['entity_uuid'], '未知')} | "
            f"性格: {str(p.get('personality', '未知'))[:30]} | "
            f"目标: {', '.join(p.get('goals', ['无'])[:2])}"
            for p in npc_profiles
        )

        player_name = player_profile['name']
        recent_events_val = recent_events_text or '（无）'
        npc_list_val = npc_list_text or '（无NPC）'

        prompt = safe_render(get_template('plot_planning'), {
            "player_action": player_action,
            "player_name": player_name,
            "player_location": player_location,
            "recent_events_text": recent_events_val,
            "npc_list_text": npc_list_val,
        })

        try:
            _p = get_llm_params('plot_planning')
            result = get_client_for_prompt('plot_planning').chat_json(
                messages=[
                    {"role": "system", "content": get_system('plot_planning')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )

            # 保存规划结果供后续 NPC 回合使用
            state.plot_plan = result

            # 处理场景转换
            if result.get("scene_transition") and result.get("new_location"):
                new_loc = result["new_location"]
                state.agent_locations[state.player_entity_uuid] = new_loc
                _sync_profile_location(profiles, state.player_entity_uuid, new_loc)
                logger.info(f"场景转换: → {new_loc}")

            # 处理新实体引入（角色/物品/地点/事件，专用AI生成完整档案）
            new_entities = result.get("new_entities", [])
            for ent_hint in new_entities:
                if isinstance(ent_hint, dict) and ent_hint.get("name"):
                    cls._create_new_entity(state, ent_hint, all_profiles, llm, zep_client)

            # 处理角色退场
            for exit_char in result.get("exit_characters", []):
                exit_uuid = exit_char.get("entity_uuid")
                if exit_uuid:
                    exit_name = next(
                        (p['name'] for p in all_profiles if p.get('entity_uuid') == exit_uuid),
                        '未知角色'
                    )
                    reason = exit_char.get("reason", "退场")
                    cls.delete_profile(state.session_id, exit_uuid)
                    logger.info(f"角色退场: {exit_name} ({exit_uuid}) - {reason}")
                    # 记录退场事件
                    state.all_events.append(NarrativeEvent(
                        turn_number=state.current_turn,
                        agent_name=exit_name,
                        agent_uuid=exit_uuid,
                        action_type="exit",
                        action_description=f"离开了场景（{reason}）",
                        location=state.agent_locations.get(exit_uuid, '未知'),
                        importance=0.7,
                        is_player=False,
                        visible_to_player=True
                    ).to_dict())

            total_planned_agents = sum(len(st.get("agents", [])) for st in result.get("scheduled_turns", []))
            logger.info(f"剧情规划完成: {len(result.get('scheduled_turns', []))}个计划回合/{result.get('total_npc_turns', '?')}总回合, {total_planned_agents}个NPC有计划行动, "
                        f"新实体={len(new_entities)}个, "
                        f"退场={len(result.get('exit_characters', []))}人")

        except Exception as e:
            logger.error(f"剧情规划失败: {e}")
            state.plot_plan = None

    @classmethod
    def _create_new_entity(
        cls,
        state: NarrativeState,
        entity_hint: Dict,
        all_profiles: List[Dict],
        llm: LLMClient,
        zep_client: Optional[Zep]
    ):
        """创建新实体：专用AI生成完整档案（特征+关系），写入图谱，同步引擎状态"""
        entity_type = entity_hint.get("entity_type", "character")
        entity_name = entity_hint.get("name", "未知实体")
        brief_description = entity_hint.get("brief_description", "")
        role_in_plot = entity_hint.get("role_in_plot", "")
        related_existing_nodes = entity_hint.get("related_existing_nodes", [])

        entity_uuid = str(uuid.uuid4())
        player_location = state.agent_locations.get(state.player_entity_uuid, '未知')

        # 构建场景上下文
        scene_context = (
            f"当前场景: {state.initial_scene or '（未知）'}\n"
            f"玩家所在位置: {player_location}\n"
            f"世界时间: {_world_time_str(state.world_day, state.world_hour)}"
        )

        # 构建已有相关实体信息文本
        related_info = []
        for node_name in related_existing_nodes:
            match_profile = next((p for p in all_profiles if p.get("name") == node_name), None)
            if match_profile:
                related_info.append(
                    f"- {node_name}（角色, uuid: {match_profile.get('entity_uuid', '?')}, "
                    f"位置: {state.agent_locations.get(match_profile.get('entity_uuid', ''), '未知')}）"
                )
            elif node_name in state.world_map:
                related_info.append(f"- {node_name}（地点）")
            elif node_name in state.world_items:
                item_info = state.world_items[node_name]
                related_info.append(f"- {node_name}（物品, 位于: {item_info.get('location', '未知')}）")
            else:
                related_info.append(f"- {node_name}")
        related_nodes_text = "\n".join(related_info) if related_info else "（无特别关联的已有实体）"

        valid_locations = list(state.world_map.keys()) if state.world_map else [player_location]

        # === 调用专用实体生成AI ===
        entity_data = {}
        try:
            gen_prompt = safe_render(get_template('entity_generation'), {
                "entity_type": entity_type,
                "entity_name": entity_name,
                "brief_description": brief_description,
                "role_in_plot": role_in_plot,
                "scene_context": scene_context,
                "related_nodes_text": related_nodes_text,
                "valid_locations": "、".join(valid_locations) if valid_locations else player_location,
                "current_location": player_location,
            })
            _p = get_llm_params('entity_generation')
            entity_data = get_client_for_prompt('entity_generation').chat_json(
                messages=[
                    {"role": "system", "content": get_system('entity_generation')},
                    {"role": "user", "content": gen_prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )
            logger.info(f"实体生成AI完成: [{entity_type}] {entity_name}")
        except Exception as e:
            logger.error(f"实体生成AI失败 ({entity_name}): {e}")
            entity_data = {"description": brief_description or role_in_plot}

        # === 根据实体类型同步引擎状态 ===
        if entity_type == "character":
            # 新角色的 known_nodes：默认知道自己 + 关联的已有实体
            new_char_known = [entity_uuid]
            for node_name in related_existing_nodes:
                match_p = next((p for p in all_profiles if p.get("name") == node_name), None)
                if match_p:
                    new_char_known.append(match_p.get("entity_uuid", ""))
            new_char_known = [u for u in new_char_known if u]

            profile_dict = {
                "entity_uuid": entity_uuid,
                "name": entity_name,
                "personality": entity_data.get("personality", ""),
                "goals": entity_data.get("goals", []),
                "speech_style": entity_data.get("speech_style", "普通"),
                "temperament": entity_data.get("temperament", "平和"),
                "current_location": entity_data.get("current_location", player_location),
                "backstory": entity_data.get("backstory", entity_data.get("description", "")),
                "relationships": entity_data.get("relationships", []),
                "abilities": entity_data.get("abilities", []),
                "is_player": False,
                "known_nodes": new_char_known,
            }
            cls.add_profile(state.session_id, profile_dict)
            state.agent_locations[entity_uuid] = profile_dict["current_location"]
            state.agent_last_acted[entity_uuid] = -1
            state.all_events.append(NarrativeEvent(
                turn_number=state.current_turn,
                agent_name=entity_name,
                agent_uuid=entity_uuid,
                action_type="appear",
                action_description=f"出现在了{profile_dict['current_location']}",
                location=profile_dict["current_location"],
                importance=0.8,
                is_player=False,
                visible_to_player=True
            ).to_dict())

        elif entity_type == "item":
            item_location = entity_data.get("location", player_location)
            state.world_items[entity_name] = {
                "uuid": entity_uuid,
                "name": entity_name,
                "description": entity_data.get("description", brief_description),
                "location": item_location,
                "owner": entity_data.get("owner", ""),
                "properties": entity_data.get("properties", ""),
            }
            state.all_events.append(NarrativeEvent(
                turn_number=state.current_turn,
                agent_name=entity_name,
                agent_uuid=entity_uuid,
                action_type="item_appear",
                action_description=f"【物品】{entity_name}出现在{item_location}：{entity_data.get('description', brief_description)[:80]}",
                location=item_location,
                importance=0.6,
                is_player=False,
                visible_to_player=True
            ).to_dict())

        elif entity_type == "location":
            loc_dict = {
                "description": entity_data.get("description", brief_description),
                "adjacent": entity_data.get("adjacent", []),
                "atmosphere": entity_data.get("atmosphere", ""),
                "notable_features": entity_data.get("notable_features", []),
            }
            state.world_map[entity_name] = loc_dict
            # 双向连接：将新地点加入相邻地点的邻接列表
            for adj_loc in loc_dict["adjacent"]:
                if adj_loc in state.world_map:
                    existing_adj = state.world_map[adj_loc].get("adjacent", [])
                    if entity_name not in existing_adj:
                        state.world_map[adj_loc]["adjacent"] = existing_adj + [entity_name]
            state.all_events.append(NarrativeEvent(
                turn_number=state.current_turn,
                agent_name=entity_name,
                agent_uuid=entity_uuid,
                action_type="location_reveal",
                action_description=f"【地点】发现了新地点「{entity_name}」：{entity_data.get('description', brief_description)[:80]}",
                location=entity_name,
                importance=0.6,
                is_player=False,
                visible_to_player=True
            ).to_dict())

        elif entity_type == "event":
            state.all_events.append(NarrativeEvent(
                turn_number=state.current_turn,
                agent_name=entity_name,
                agent_uuid=entity_uuid,
                action_type="event_occur",
                action_description=f"【事件】{entity_name}：{entity_data.get('description', brief_description)[:120]}",
                location=player_location,
                importance=0.9,
                is_player=False,
                visible_to_player=True
            ).to_dict())

        else:
            state.all_events.append(NarrativeEvent(
                turn_number=state.current_turn,
                agent_name=entity_name,
                agent_uuid=entity_uuid,
                action_type="entity_appear",
                action_description=f"【{entity_type}】{entity_name}：{entity_data.get('description', brief_description)[:80]}",
                location=player_location,
                importance=0.6,
                is_player=False,
                visible_to_player=True
            ).to_dict())

        # === 写入 FalkorDB 图谱 ===
        type_label_map = {
            "character": "Person",
            "item": "Item",
            "location": "Location",
            "event": "Event",
        }
        type_label = type_label_map.get(entity_type, "Entity")
        node_summary = (entity_data.get("description") or entity_data.get("backstory") or brief_description or "")

        try:
            from falkordb import FalkorDB
            db = FalkorDB(
                host=Config.FALKORDB_HOST,
                port=Config.FALKORDB_PORT,
                password=Config.FALKORDB_PASSWORD or None,
            )
            graph = db.select_graph(state.graph_id)

            # 创建节点（双标签: Entity + 类型标签）
            graph.query(
                f"CREATE (n:Entity:{type_label} {{uuid: $uuid, name: $name, summary: $summary, entity_type: $etype}})",
                {
                    "uuid": entity_uuid,
                    "name": entity_name,
                    "summary": str(node_summary)[:500],
                    "etype": entity_type,
                }
            )

            # 写入AI生成的关系边
            written_targets = set()
            for rel in entity_data.get("relationships", []):
                target_name = rel.get("target_name", "")
                relation = rel.get("relation", "")
                edge_type = rel.get("edge_type", "RELATES_TO").upper().replace(" ", "_")
                if not target_name or not relation:
                    continue
                try:
                    find_result = graph.query(
                        "MATCH (t:Entity) WHERE t.name = $name RETURN t.uuid LIMIT 1",
                        {"name": target_name}
                    )
                    if find_result.result_set:
                        target_uuid = find_result.result_set[0][0]
                        graph.query(
                            "MATCH (s:Entity {uuid: $s_uuid}), (t:Entity {uuid: $t_uuid}) "
                            "MERGE (s)-[r:RELATES_TO]->(t) "
                            "SET r.fact = $fact, r.name = $edge_name",
                            {
                                "s_uuid": entity_uuid,
                                "t_uuid": target_uuid,
                                "fact": relation,
                                "edge_name": edge_type[:50],
                            }
                        )
                        written_targets.add(target_name)
                except Exception:
                    pass

            # 补充：若玩家未被AI覆盖，补写与玩家的关联边
            player_profile = next((p for p in all_profiles if p.get("is_player")), None)
            if player_profile and player_profile.get("name") not in written_targets:
                try:
                    graph.query(
                        "MATCH (s:Entity {uuid: $s_uuid}), (t:Entity {uuid: $t_uuid}) "
                        "MERGE (s)-[r:RELATES_TO]->(t) "
                        "SET r.fact = $fact, r.name = $edge_name",
                        {
                            "s_uuid": entity_uuid,
                            "t_uuid": player_profile.get("entity_uuid", ""),
                            "fact": f"{entity_name}（{entity_type}）在{player_location}出现，与{player_profile.get('name', '玩家')}相遇",
                            "edge_name": "ENCOUNTERED",
                        }
                    )
                except Exception:
                    pass

            logger.info(f"新实体已写入 FalkorDB: [{entity_type}] {entity_name} ({entity_uuid})")
        except Exception as e:
            logger.warning(f"新实体写入 FalkorDB 失败: {e}")

        # === 写入 Zep Cloud（如果可用）===
        if zep_client:
            try:
                episode_text = (
                    f"新{entity_type}「{entity_name}」出现: "
                    f"{entity_data.get('description', brief_description) or role_in_plot}"
                )
                zep_client.graph.episode.add(
                    graph_id=state.graph_id,
                    episodes=[{
                        "content": episode_text,
                        "source": "narrative_engine",
                        "source_description": f"叙事引擎 - 新实体引入({entity_type}) - 回合{state.current_turn}"
                    }]
                )
            except Exception:
                pass

        # === 更新记忆系统 ===
        # 1. 使节点目录缓存失效（新节点已写入 FalkorDB）
        all_nodes_cache_key = f"_all_nodes_{state.graph_id}"
        if hasattr(cls, all_nodes_cache_key):
            delattr(cls, all_nodes_cache_key)

        # 2. 同地点角色 + 玩家自动获知新实体
        new_entity_location = (
            entity_data.get("current_location", player_location) if entity_type == "character"
            else entity_data.get("location", player_location) if entity_type == "item"
            else player_location
        )
        for p in all_profiles:
            p_uuid = p.get("entity_uuid", "")
            p_loc = state.agent_locations.get(p_uuid, "")
            should_know = (
                p.get("is_player")  # 玩家始终知道
                or p_loc == new_entity_location  # 同地点角色知道
                or p_uuid in [r.get("entity_uuid", "") for r in entity_data.get("relationships", []) if isinstance(r, dict)]
            )
            if should_know:
                p_known = p.get("known_nodes", [])
                if entity_uuid not in p_known:
                    p_known.append(entity_uuid)
                    p["known_nodes"] = p_known

        logger.info(f"新实体已加入引擎: [{entity_type}] {entity_name} ({entity_uuid})")

    # ---- 持久化 ----

    @classmethod
    def _save_state(cls, state: NarrativeState):
        """保存会话状态 + 角色档案到 JSON 文件"""
        try:
            data_dir = os.path.join(Config.NARRATIVE_DATA_DIR, state.session_id)
            os.makedirs(data_dir, exist_ok=True)

            state_file = os.path.join(data_dir, "narrative_state.json")
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

            # 同步保存角色档案
            profiles = cls._agent_profiles.get(state.session_id, [])
            if profiles:
                profiles_file = os.path.join(data_dir, "profiles.json")
                with open(profiles_file, 'w', encoding='utf-8') as f:
                    json.dump(profiles, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")

    @classmethod
    def _load_state(cls, session_id: str) -> Optional[NarrativeState]:
        """从 JSON 文件加载会话状态"""
        try:
            state_file = os.path.join(Config.NARRATIVE_DATA_DIR, session_id, "narrative_state.json")
            if not os.path.exists(state_file):
                return None
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return NarrativeState.from_dict(data)
        except Exception as e:
            logger.error(f"加载状态失败: {e}")
            return None

    @classmethod
    def _load_profiles(cls, session_id: str) -> List[Dict]:
        """从 JSON 文件加载角色档案"""
        try:
            profiles_file = os.path.join(Config.NARRATIVE_DATA_DIR, session_id, "profiles.json")
            if not os.path.exists(profiles_file):
                return []
            with open(profiles_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载角色档案失败: {e}")
            return []

    # ---- 存档快照 ----

    @classmethod
    def create_checkpoint(cls, session_id: str) -> str:
        """创建存档快照，返回 save_id"""
        import shutil as _shutil
        state = cls.get_session(session_id)  # 内存优先，自动回退到磁盘
        if not state:
            raise ValueError(f"会话不存在: {session_id}")

        save_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        saves_dir = os.path.join(Config.NARRATIVE_DATA_DIR, session_id, "saves")
        save_dir = os.path.join(saves_dir, save_id)
        os.makedirs(save_dir, exist_ok=True)

        with open(os.path.join(save_dir, "state.json"), 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

        # 内存中有就用内存，否则从磁盘读
        profiles = cls._agent_profiles.get(session_id) or cls._load_profiles(session_id)
        with open(os.path.join(save_dir, "profiles.json"), 'w', encoding='utf-8') as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)

        if state.current_turn == 0:
            desc = "初始状态"
        elif state.status == NarrativeStatus.AWAITING_PLAYER.value:
            desc = f"回合{state.current_turn} - 等待玩家输入"
        else:
            desc = f"回合{state.current_turn}"

        meta = {
            "save_id": save_id,
            "save_time": datetime.now().isoformat(),
            "turn": state.current_turn,
            "segments_count": len(state.narrative_segments),
            "events_count": len(state.all_events),
            "status": state.status,
            "description": desc
        }
        with open(os.path.join(save_dir, "meta.json"), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"存档快照已创建: session={session_id}, save_id={save_id}, turn={state.current_turn}")
        return save_id

    @classmethod
    def list_checkpoints(cls, session_id: str) -> List[Dict]:
        """列出会话的所有存档"""
        saves_dir = os.path.join(Config.NARRATIVE_DATA_DIR, session_id, "saves")
        if not os.path.exists(saves_dir):
            return []
        result = []
        for save_id in os.listdir(saves_dir):
            meta_file = os.path.join(saves_dir, save_id, "meta.json")
            if os.path.isfile(meta_file):
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    result.append(meta)
                except Exception:
                    pass
        result.sort(key=lambda x: x.get("save_time", ""), reverse=True)
        return result

    @classmethod
    def load_checkpoint(cls, session_id: str, save_id: str) -> 'NarrativeState':
        """从存档快照恢复状态并重启引擎"""
        saves_dir = os.path.join(Config.NARRATIVE_DATA_DIR, session_id, "saves")
        save_dir = os.path.join(saves_dir, save_id)
        state_file = os.path.join(save_dir, "state.json")
        profiles_file = os.path.join(save_dir, "profiles.json")

        if not os.path.isfile(state_file):
            raise ValueError(f"存档不存在: {save_id}")

        # 停止当前引擎
        cls._stop_flags.get(session_id, threading.Event()).set()
        cls._player_input_events.get(session_id, threading.Event()).set()
        thread = cls._engine_threads.get(session_id)
        if thread and thread.is_alive():
            thread.join(timeout=5)

        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        state = NarrativeState.from_dict(data)

        profiles = []
        if os.path.isfile(profiles_file):
            with open(profiles_file, 'r', encoding='utf-8') as f:
                profiles = json.load(f)

        # 恢复 awaiting_player 状态，其他状态重置为 running
        if state.status != NarrativeStatus.AWAITING_PLAYER.value:
            state.status = NarrativeStatus.RUNNING.value
        state.updated_at = datetime.now().isoformat()

        cls._sessions[session_id] = state
        cls._agent_profiles[session_id] = profiles
        cls._locks.setdefault(session_id, threading.Lock())
        cls._stop_flags[session_id] = threading.Event()
        cls._player_input_events[session_id] = threading.Event()

        cls._save_state(state)

        thread = threading.Thread(
            target=cls._engine_loop,
            args=(session_id,),
            daemon=True,
            name=f"NarrativeEngine-{session_id[:8]}"
        )
        thread.start()
        cls._engine_threads[session_id] = thread

        logger.info(f"已从存档恢复: session={session_id}, save_id={save_id}, turn={state.current_turn}")
        return state

    @classmethod
    def delete_checkpoint(cls, session_id: str, save_id: str) -> bool:
        """删除指定存档"""
        import shutil as _shutil
        save_dir = os.path.join(Config.NARRATIVE_DATA_DIR, session_id, "saves", save_id)
        if not os.path.exists(save_dir):
            return False
        _shutil.rmtree(save_dir)
        logger.info(f"存档已删除: session={session_id}, save_id={save_id}")
        return True

    # ---- Profile CRUD ----

    @classmethod
    def update_profile(cls, session_id: str, entity_uuid: str, updates: Dict[str, Any]) -> Optional[Dict]:
        """线程安全更新 profile + state"""
        state = cls._sessions.get(session_id)
        if not state:
            return None

        lock = cls._locks.get(session_id)
        if not lock:
            return None

        with lock:
            profiles = cls._agent_profiles.get(session_id, [])
            target = None
            for p in profiles:
                if p.get('entity_uuid') == entity_uuid:
                    target = p
                    break
            if not target:
                return None

            # 记录旧位置
            old_location = target.get('current_location')

            # 应用更新
            for key, value in updates.items():
                if key != 'entity_uuid':  # 不允许修改 uuid
                    target[key] = value

            # 如果 current_location 变更，同步更新 state
            new_location = target.get('current_location')
            if new_location and new_location != old_location:
                state.agent_locations[entity_uuid] = new_location

            state.updated_at = datetime.now().isoformat()
            cls._save_state(state)

            return dict(target)

    @classmethod
    def add_profile(cls, session_id: str, profile_dict: Dict[str, Any]) -> Optional[Dict]:
        """线程安全添加 profile + 初始化 state 跟踪"""
        state = cls._sessions.get(session_id)
        if not state:
            return None

        lock = cls._locks.get(session_id)
        if not lock:
            return None

        with lock:
            if session_id not in cls._agent_profiles:
                cls._agent_profiles[session_id] = []

            cls._agent_profiles[session_id].append(profile_dict)

            entity_uuid = profile_dict.get('entity_uuid', '')
            if entity_uuid:
                state.agent_locations[entity_uuid] = profile_dict.get('current_location', '未知')
                state.agent_last_acted[entity_uuid] = -1

            state.updated_at = datetime.now().isoformat()
            cls._save_state(state)

            return dict(profile_dict)

    @classmethod
    def delete_profile(cls, session_id: str, entity_uuid: str) -> bool:
        """线程安全删除 profile + 清理 state"""
        state = cls._sessions.get(session_id)
        if not state:
            return False

        lock = cls._locks.get(session_id)
        if not lock:
            return False

        with lock:
            profiles = cls._agent_profiles.get(session_id, [])
            original_len = len(profiles)
            cls._agent_profiles[session_id] = [
                p for p in profiles if p.get('entity_uuid') != entity_uuid
            ]
            if len(cls._agent_profiles[session_id]) == original_len:
                return False  # not found

            state.agent_locations.pop(entity_uuid, None)
            state.agent_last_acted.pop(entity_uuid, None)
            state.updated_at = datetime.now().isoformat()
            cls._save_state(state)
            return True

    # ---- 清理 ----

    @classmethod
    def register_cleanup(cls):
        """注册退出清理"""
        atexit.register(cls._cleanup_all)

    @classmethod
    def _cleanup_all(cls):
        """停止所有运行中的会话"""
        for sid in list(cls._sessions.keys()):
            try:
                cls.stop_session(sid)
            except Exception:
                pass
