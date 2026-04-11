"""
叙事引擎 API 路由
"""

import os
import json
import shutil
import threading
from flask import request, jsonify

from . import narrative_bp
from ..config import Config
from ..utils.logger import get_logger
from ..services.narrative_engine import NarrativeEngine, NarrativeStatus
from ..services.narrative_profile_generator import NarrativeProfileGenerator
from ..services.falkordb_entity_reader import read_entities_from_falkordb, read_entity_edges, read_all_nodes_directory

logger = get_logger('agars.api.narrative')

# 异步准备任务状态
_prepare_tasks = {}
_prepare_lock = threading.Lock()


# ============================================================
# 会话管理
# ============================================================

@narrative_bp.route('/create', methods=['POST'])
def create_narrative():
    """
    创建叙事会话
    Request body: { project_id, graph_id, player_entity_uuid, initial_scene?, max_npc_turns? }
    """
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        graph_id = data.get('graph_id')
        player_entity_uuid = data.get('player_entity_uuid')

        if not all([project_id, graph_id, player_entity_uuid]):
            return jsonify({"success": False, "error": "缺少必要参数: project_id, graph_id, player_entity_uuid"}), 400

        initial_scene = data.get('initial_scene', '')
        opening_text = data.get('opening_text', '')
        prior_summary = data.get('prior_summary', '')
        max_npc_turns = data.get('max_npc_turns', Config.NARRATIVE_MAX_NPC_TURNS)
        simulation_id = data.get('simulation_id', '')

        # 先创建一个空的会话（角色档案在 prepare 步骤生成）
        # 使用临时空档案列表，在 prepare 中填充
        from ..services.narrative_profile_generator import NarrativeCharacterProfile
        state = NarrativeEngine.create_session(
            graph_id=graph_id,
            project_id=project_id,
            player_entity_uuid=player_entity_uuid,
            agent_profiles=[],  # 在 prepare 中填充
            initial_scene=initial_scene,
            opening_text=opening_text,
            prior_summary=prior_summary,
            max_npc_turns=max_npc_turns,
            simulation_id=simulation_id
        )

        return jsonify({
            "success": True,
            "data": {
                "session_id": state.session_id,
                "status": state.status
            }
        })

    except Exception as e:
        logger.error(f"创建叙事会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/prepare', methods=['POST'])
def prepare_narrative():
    """
    异步准备叙事会话（读取实体、生成角色档案）
    Request body: { session_id, entity_types?, parallel_count? }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({"success": False, "error": "缺少 session_id"}), 400

        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": f"会话不存在: {session_id}"}), 404

        entity_types = data.get('entity_types')
        parallel_count = data.get('parallel_count', 3)

        # 启动异步准备
        task_id = f"prepare_{session_id}"
        with _prepare_lock:
            _prepare_tasks[task_id] = {
                "status": "running",
                "progress": 0.0,
                "message": "正在读取实体...",
                "profiles_count": 0,
                "error": None
            }

        thread = threading.Thread(
            target=_run_prepare,
            args=(session_id, state.graph_id, state.player_entity_uuid,
                  entity_types, parallel_count, task_id),
            daemon=True
        )
        thread.start()

        return jsonify({
            "success": True,
            "data": {"task_id": task_id}
        })

    except Exception as e:
        logger.error(f"准备叙事会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


def _run_prepare(session_id, graph_id, player_uuid, entity_types, parallel_count, task_id):
    """异步准备任务"""
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            raise ValueError(f"会话不存在: {session_id}")

        # Step 1: 读取实体
        with _prepare_lock:
            _prepare_tasks[task_id]["message"] = "正在从图谱读取实体..."
            _prepare_tasks[task_id]["progress"] = 0.05

        if entity_types:
            entity_types_list = [t.strip() for t in entity_types.split(',')]
        else:
            entity_types_list = None

        # 从 ontology 获取 agent 类型列表（作为参考，非唯一判断依据）
        ontology_agent_types = None
        try:
            from ..models.project import ProjectManager
            project = ProjectManager.get_project(state.project_id)
            if project and project.ontology:
                ontology_agent_types = [
                    et["name"] for et in project.ontology.get("entity_types", [])
                    if et.get("is_agent")  # 不再默认 True，缺失 is_agent 的类型不纳入
                ]
                if not entity_types_list and ontology_agent_types:
                    entity_types_list = ontology_agent_types
                    logger.info(f"从本体自动推导 agent 类型: {ontology_agent_types}")
        except Exception as e:
            logger.warning(f"推导 agent 类型失败，将使用全部实体: {e}")

        # 读取实体，同时让 reader 根据标签+summary 判断 is_agent
        entities = read_entities_from_falkordb(
            group_id=graph_id,
            entity_types=entity_types_list,
            required_uuids=[player_uuid] if player_uuid else None,
            agent_types=ontology_agent_types,
        )

        # 使用实体自身的 is_agent 字段过滤，仅保留 agent 实体（required_uuids 始终保留）
        required_set = set([player_uuid] if player_uuid else [])
        agent_entities = [
            e for e in entities
            if e.get("is_agent") or e["uuid"] in required_set
        ]
        non_agent_names = [e["name"] for e in entities if not e.get("is_agent") and e["uuid"] not in required_set]
        if non_agent_names:
            logger.info(f"过滤非 agent 实体: {non_agent_names}")
        entities = agent_entities

        # 获取全部节点目录（含非 agent 类型），用于记忆系统 known_nodes 判断
        all_nodes_for_memory = read_all_nodes_directory(group_id=graph_id)

        # Step 2: 先生成世界地图（规范地名）
        with _prepare_lock:
            _prepare_tasks[task_id]["message"] = "正在生成世界地图（规范地点名称）..."
            _prepare_tasks[task_id]["progress"] = 0.15

        from ..utils.llm_client import LLMClient
        from ..models.project import ProjectManager
        llm = LLMClient()

        # 从项目原始文件读取全文，两步走构建世界地图：
        # 第一步：全文分块提取地点名单；第二步：根据名单构建拓扑
        raw_text = ""
        try:
            raw_text = ProjectManager.get_extracted_text(state.project_id) or ""
        except Exception as e:
            logger.warning(f"读取项目文本失败（不影响流程）: {e}")

        world_map = {}
        try:
            if raw_text:
                location_names = NarrativeEngine._extract_locations_from_text(raw_text, llm)
                if location_names:
                    world_map = NarrativeEngine._build_world_map_from_location_list(
                        location_names, state.initial_scene, state.graph_id, llm
                    )
            if not world_map:
                # fallback：仅凭初始场景 + 前 8000 字推断
                source_text = raw_text[:8000] if raw_text else ""
                world_map = NarrativeEngine._build_world_map_from_scene(
                    state.initial_scene, llm, source_text=source_text
                )
            if world_map:
                state.world_map = world_map
                NarrativeEngine._save_state(state)
                logger.info(f"规范地图已建立: {list(world_map.keys())}")
        except Exception as map_err:
            logger.warning(f"世界地图预生成失败（将在角色档案后重试）: {map_err}")

        valid_locations = list(world_map.keys()) if world_map else None

        # Step 3: 生成角色档案，传入规范地名约束
        with _prepare_lock:
            _prepare_tasks[task_id]["message"] = f"已读取 {len(entities)} 个实体，正在生成角色档案..."
            _prepare_tasks[task_id]["progress"] = 0.25

        generator = NarrativeProfileGenerator(graph_id=graph_id, llm_client=llm)

        # 加载预提取实体数据库（方案C，图谱构建时生成）
        entity_database: dict = {}
        try:
            from ..models.project import ProjectManager
            if state.project_id:
                entity_database = ProjectManager.get_entity_database(state.project_id) or {}
                if entity_database:
                    logger.info(f"加载实体数据库: {len(entity_database)} 个实体")
        except Exception as _edb_err:
            logger.warning(f"加载实体数据库失败（不影响 profile 生成）: {_edb_err}")

        def progress_cb(msg, pct):
            with _prepare_lock:
                _prepare_tasks[task_id]["message"] = msg
                _prepare_tasks[task_id]["progress"] = 0.25 + pct * 0.65

        profiles = generator.generate_profiles_batch(
            entities=entities,
            player_uuid=player_uuid,
            max_workers=parallel_count,
            progress_callback=progress_cb,
            valid_locations=valid_locations,
            entity_database=entity_database or None,
            all_nodes=all_nodes_for_memory or None,
        )

        # Step 3.5: 整体位置分配（一次 LLM 调用，全局视角）
        if valid_locations:
            with _prepare_lock:
                _prepare_tasks[task_id]["message"] = "正在进行角色初始位置整体布局..."
                _prepare_tasks[task_id]["progress"] = 0.88
            try:
                location_assignments = generator.assign_initial_locations(
                    profiles=profiles,
                    initial_scene=state.initial_scene if state else "",
                    valid_locations=valid_locations,
                    world_map=world_map if world_map else None,
                    prior_summary=state.prior_summary if state else "",
                    entity_database=entity_database or None,
                    opening_text=state.opening_text if state else "",
                )
            except Exception as loc_err:
                logger.warning(f"整体位置分配失败，将使用角色档案中的位置: {loc_err}")
                location_assignments = {}
        else:
            location_assignments = {}

        # Step 4: 更新状态
        state = NarrativeEngine.get_session(session_id)
        if state:
            profile_dicts = [p.to_dict() for p in profiles]
            NarrativeEngine._agent_profiles[session_id] = profile_dicts
            for p in profiles:
                # 优先使用整体布局结果，其次 fallback 到档案中的位置
                assigned = location_assignments.get(p.entity_uuid)
                state.agent_locations[p.entity_uuid] = assigned or p.current_location or "未知"
                state.agent_last_acted[p.entity_uuid] = -1

            # Step 5: 如果预生成地图失败，用角色位置兜底；否则用已有地图补充 FalkorDB facts
            if not state.world_map:
                try:
                    state.world_map = NarrativeEngine._build_world_map(state, profile_dicts, llm)
                except Exception as e:
                    logger.warning(f"兜底地图构建失败: {e}")
            # 标记为已准备完成（避免 NarrativeView 重复调用 prepare）
            from ..services.narrative_engine import NarrativeStatus
            state.status = NarrativeStatus.PREPARED.value
            # 无论如何保存
            NarrativeEngine._save_state(state)

        with _prepare_lock:
            _prepare_tasks[task_id]["status"] = "completed"
            _prepare_tasks[task_id]["progress"] = 1.0
            _prepare_tasks[task_id]["message"] = f"准备完成，共 {len(profiles)} 个角色，{len(state.world_map if state else {})} 个地点"
            _prepare_tasks[task_id]["profiles_count"] = len(profiles)

        logger.info(f"叙事准备完成: session={session_id}, profiles={len(profiles)}")

    except Exception as e:
        logger.error(f"准备任务失败: {e}", exc_info=True)
        with _prepare_lock:
            _prepare_tasks[task_id]["status"] = "failed"
            _prepare_tasks[task_id]["error"] = str(e)
            _prepare_tasks[task_id]["message"] = f"准备失败: {e}"


@narrative_bp.route('/prepare/status', methods=['POST'])
def prepare_status():
    """查询准备任务进度"""
    try:
        data = request.get_json()
        task_id = data.get('task_id')
        if not task_id:
            # 尝试从 session_id 构造
            session_id = data.get('session_id')
            if session_id:
                task_id = f"prepare_{session_id}"
            else:
                return jsonify({"success": False, "error": "缺少 task_id 或 session_id"}), 400

        with _prepare_lock:
            task = _prepare_tasks.get(task_id)

        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        return jsonify({"success": True, "data": task})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 会话状态查询
# ============================================================

@narrative_bp.route('/<session_id>', methods=['GET'])
def get_narrative_session(session_id):
    """获取完整会话状态"""
    state = NarrativeEngine.get_session(session_id)
    if not state:
        return jsonify({"success": False, "error": "会话不存在"}), 404

    return jsonify({
        "success": True,
        "data": state.to_dict()
    })


@narrative_bp.route('/<session_id>/profiles', methods=['GET'])
def get_narrative_profiles(session_id):
    """获取角色档案列表"""
    profiles = NarrativeEngine.get_profiles(session_id)
    return jsonify({
        "success": True,
        "data": {"profiles": profiles}
    })


@narrative_bp.route('/<session_id>/status', methods=['GET'])
def get_narrative_status(session_id):
    """获取会话状态（轮询用）"""
    state = NarrativeEngine.get_session(session_id)
    if not state:
        return jsonify({"success": False, "error": "会话不存在"}), 404

    return jsonify({
        "success": True,
        "data": {
            "status": state.status,
            "current_turn": state.current_turn,
            "npc_turns_since_player": state.npc_turns_since_player,
            "events_count": len(state.all_events),
            "segments_count": len(state.narrative_segments),
            "player_turn_data": state.player_turn_data,
            "error_message": state.error_message,
            "agent_locations": state.agent_locations,
            "player_entity_uuid": state.player_entity_uuid,
        }
    })


@narrative_bp.route('/<session_id>/narrative', methods=['GET'])
def get_narrative_text(session_id):
    """
    获取叙事文本段落（增量）
    Query params: from_segment=N (从第 N 段开始)
    """
    state = NarrativeEngine.get_session(session_id)
    if not state:
        return jsonify({"success": False, "error": "会话不存在"}), 404

    from_segment = request.args.get('from_segment', 0, type=int)
    segments = state.narrative_segments[from_segment:]

    return jsonify({
        "success": True,
        "data": {
            "segments": segments,
            "from_segment": from_segment,
            "total_segments": len(state.narrative_segments)
        }
    })


@narrative_bp.route('/<session_id>/events', methods=['GET'])
def get_narrative_events(session_id):
    """
    获取背景事件列表（增量）
    Query params: from_turn=N (从第 N 回合开始)
    """
    state = NarrativeEngine.get_session(session_id)
    if not state:
        return jsonify({"success": False, "error": "会话不存在"}), 404

    from_turn = request.args.get('from_turn', 0, type=int)
    events = [e for e in state.all_events if e.get("turn_number", 0) >= from_turn]

    return jsonify({
        "success": True,
        "data": {
            "events": events,
            "from_turn": from_turn,
            "total_events": len(state.all_events)
        }
    })


# ============================================================
# Profile CRUD
# ============================================================

@narrative_bp.route('/<session_id>/profiles/<entity_uuid>', methods=['PUT'])
def update_narrative_profile(session_id, entity_uuid):
    """更新角色档案"""
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        # 状态校验：running / processing_player 时拒绝编辑
        if state.status in (NarrativeStatus.RUNNING.value, NarrativeStatus.PROCESSING_PLAYER.value):
            return jsonify({"success": False, "error": f"当前状态 {state.status} 不允许编辑"}), 409

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "缺少请求体"}), 400

        updated = NarrativeEngine.update_profile(session_id, entity_uuid, data)
        if not updated:
            return jsonify({"success": False, "error": "角色不存在"}), 404

        # 异步同步 Zep 图谱
        _async_sync_zep_profile(state.graph_id, updated, data)

        return jsonify({"success": True, "data": updated})

    except Exception as e:
        logger.error(f"更新角色档案失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/profiles', methods=['POST'])
def add_narrative_profile(session_id):
    """添加新角色"""
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        if state.status in (NarrativeStatus.RUNNING.value, NarrativeStatus.PROCESSING_PLAYER.value):
            return jsonify({"success": False, "error": f"当前状态 {state.status} 不允许添加角色"}), 409

        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({"success": False, "error": "缺少必要字段 name"}), 400

        graph_id = state.graph_id
        import uuid as uuid_mod

        # 如果前端已创建 FalkorDB 节点并传了 entity_uuid，直接复用，不重复创建
        entity_uuid = data.get('entity_uuid')
        if not entity_uuid:
            # 兜底：后端自行创建 FalkorDB 节点
            name = data['name']
            entity_type = data.get('entity_type', '角色')
            summary = data.get('backstory', '') or data.get('personality', '') or ''
            try:
                from falkordb import FalkorDB
                db = FalkorDB(
                    host=Config.FALKORDB_HOST,
                    port=Config.FALKORDB_PORT,
                    password=Config.FALKORDB_PASSWORD or None,
                )
                graph = db.select_graph(graph_id)
                entity_uuid = str(uuid_mod.uuid4())
                label = entity_type if entity_type and entity_type != '角色' else 'Person'
                graph.query(
                    f"CREATE (n:Entity:{label} {{uuid: $uuid, name: $name, summary: $summary}})",
                    {"uuid": entity_uuid, "name": name, "summary": summary[:500]}
                )
                logger.info(f"FalkorDB 节点已创建: {name} ({entity_uuid})")
            except Exception as e:
                logger.error(f"FalkorDB 节点创建失败: {e}", exc_info=True)
                entity_uuid = None

        # 构建 profile dict
        profile_dict = {
            "entity_uuid": entity_uuid or f"custom_{uuid_mod.uuid4().hex[:12]}",
            "entity_type": data.get('entity_type', '角色'),
            "name": data['name'],
            "username": data.get('username', data['name']),
            "personality": data.get('personality', ''),
            "backstory": data.get('backstory', ''),
            "goals": data.get('goals', []),
            "speech_style": data.get('speech_style', ''),
            "temperament": data.get('temperament', '平和'),
            "current_location": data.get('current_location', '未知'),
            "relationships": data.get('relationships', []),
            "profession": data.get('profession', ''),
            "age": data.get('age'),
            "gender": data.get('gender', ''),
            "mbti": data.get('mbti', ''),
            "bio": data.get('bio', ''),
            "persona": data.get('persona', ''),
            "interested_topics": data.get('interested_topics', []),
            "is_player": False,
            "source_entity_uuid": None
        }

        added = NarrativeEngine.add_profile(session_id, profile_dict)
        if not added:
            return jsonify({"success": False, "error": "添加失败"}), 500

        return jsonify({"success": True, "data": added})

    except Exception as e:
        logger.error(f"添加角色失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/profiles/<entity_uuid>', methods=['DELETE'])
def delete_narrative_profile(session_id, entity_uuid):
    """删除角色（可选是否同时清理 FalkorDB 节点及关联边）"""
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        if state.status in (NarrativeStatus.RUNNING.value, NarrativeStatus.PROCESSING_PLAYER.value):
            return jsonify({"success": False, "error": f"当前状态 {state.status} 不允许删除角色"}), 409

        success = NarrativeEngine.delete_profile(session_id, entity_uuid)
        if not success:
            return jsonify({"success": False, "error": "角色不存在"}), 404

        # keep_node=1 时仅删 profile，保留图谱节点
        keep_node = request.args.get('keep_node', '0') == '1'

        if not keep_node:
            # 同时删除 FalkorDB 中的节点及关联边
            graph_id = state.graph_id
            if graph_id and entity_uuid and not entity_uuid.startswith('custom_'):
                try:
                    from falkordb import FalkorDB
                    db = FalkorDB(
                        host=Config.FALKORDB_HOST,
                        port=Config.FALKORDB_PORT,
                        password=Config.FALKORDB_PASSWORD or None,
                    )
                    graph = db.select_graph(graph_id)
                    graph.query(
                        "MATCH (n:Entity {uuid: $uuid})-[r]-() DELETE r",
                        {"uuid": entity_uuid}
                    )
                    graph.query(
                        "MATCH (n:Entity {uuid: $uuid}) DELETE n",
                        {"uuid": entity_uuid}
                    )
                    logger.info(f"FalkorDB 节点及关联边已删除: {entity_uuid}")
                except Exception as graph_err:
                    logger.warning(f"FalkorDB 清理失败（不影响角色删除）: {graph_err}")

        msg = "角色已删除" + ("（保留图谱节点）" if keep_node else "（含图谱节点）")
        return jsonify({"success": True, "data": {"message": msg}})

    except Exception as e:
        logger.error(f"删除角色失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/profiles/<entity_uuid>/graph-relationships', methods=['GET'])
def get_graph_relationships(session_id, entity_uuid):
    """获取实体在图谱中的真实边关系"""
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        edges = read_entity_edges(
            group_id=state.graph_id,
            entity_uuid=entity_uuid,
        )

        return jsonify({
            "success": True,
            "data": {"edges": edges, "count": len(edges)}
        })

    except Exception as e:
        logger.error(f"获取图谱关系失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


def _get_zep_client():
    """获取 Zep 客户端"""
    if not Config.ZEP_API_KEY:
        return None
    try:
        from zep_cloud.client import Zep
        return Zep(api_key=Config.ZEP_API_KEY)
    except Exception:
        return None


def _async_sync_zep_profile(graph_id, profile, changes):
    """后台线程异步同步 Zep + FalkorDB 图谱"""
    def _sync():
        name = profile.get('name', 'Unknown')

        # ---- 1. Zep: 将所有变更写为自然语言 episode ----
        try:
            zep_client = _get_zep_client()
            if zep_client:
                field_map = {
                    'name': lambda v: f"角色更名为「{v}」",
                    'personality': lambda v: f"{name}的性格特点：{v}",
                    'backstory': lambda v: f"{name}的背景故事：{v}",
                    'goals': lambda v: f"{name}的目标：{', '.join(v) if isinstance(v, list) else v}",
                    'speech_style': lambda v: f"{name}的说话风格：{v}",
                    'temperament': lambda v: f"{name}的气质：{v}",
                    'abilities': lambda v: f"{name}的能力：{', '.join(v) if isinstance(v, list) else v}",
                    'current_location': lambda v: f"{name}当前位于{v}",
                    'relationships': lambda v: f"{name}的人际关系：{'; '.join(r.get('name','')+'('+r.get('relation','')+')' for r in v) if isinstance(v, list) else v}",
                }
                desc_parts = []
                for field, formatter in field_map.items():
                    if field in changes and changes[field]:
                        desc_parts.append(formatter(changes[field]))

                if desc_parts:
                    zep_client.graph.episode.add(
                        graph_id=graph_id,
                        episodes=[{
                            "content": "。".join(desc_parts),
                            "source": "narrative_engine",
                            "source_description": f"角色档案更新 - {name}"
                        }]
                    )
        except Exception as e:
            logger.warning(f"Zep 同步失败: {e}")

        # ---- 2. FalkorDB: 更新本地图谱节点属性 ----
        try:
            entity_uuid = profile.get('entity_uuid') or profile.get('source_entity_uuid')
            if entity_uuid and graph_id:
                from falkordb import FalkorDB
                db = FalkorDB(
                    host=Config.FALKORDB_HOST,
                    port=Config.FALKORDB_PORT,
                    password=Config.FALKORDB_PASSWORD or None,
                )
                graph = db.select_graph(graph_id)

                # 更新 summary（将关键属性拼接为摘要）
                summary_parts = []
                for field in ('personality', 'backstory', 'goals', 'abilities'):
                    val = profile.get(field)
                    if val:
                        if isinstance(val, list):
                            summary_parts.append(', '.join(val))
                        else:
                            summary_parts.append(str(val))
                new_summary = '。'.join(summary_parts) if summary_parts else None

                updates = []
                if 'name' in changes:
                    updates.append(f"n.name = $name")
                if new_summary:
                    updates.append(f"n.summary = $summary")

                if updates:
                    query = f"MATCH (n:Entity {{uuid: $uuid}}) SET {', '.join(updates)}"
                    params = {'uuid': entity_uuid}
                    if 'name' in changes:
                        params['name'] = changes['name']
                    if new_summary:
                        params['summary'] = new_summary
                    graph.query(query, params)
                    logger.debug(f"FalkorDB 实体已更新: {entity_uuid}")
        except Exception as e:
            logger.warning(f"FalkorDB 同步失败: {e}")

        # ---- 3. FalkorDB: 关系编辑回写图谱边 ----
        if 'relationships' in changes and isinstance(changes['relationships'], list):
            try:
                entity_uuid = profile.get('entity_uuid') or profile.get('source_entity_uuid')
                if entity_uuid and graph_id and not entity_uuid.startswith('custom_'):
                    from falkordb import FalkorDB as FDB
                    db2 = FDB(
                        host=Config.FALKORDB_HOST,
                        port=Config.FALKORDB_PORT,
                        password=Config.FALKORDB_PASSWORD or None,
                    )
                    graph2 = db2.select_graph(graph_id)

                    # 读取当前出边，用于对比删除
                    try:
                        existing = graph2.query(
                            "MATCH (s:Entity {uuid: $uuid})-[r]->(t:Entity) "
                            "RETURN t.name, id(r)",
                            {"uuid": entity_uuid}
                        )
                        existing_targets = {rec[0]: rec[1] for rec in existing.result_set} if existing.result_set else {}
                    except Exception:
                        existing_targets = {}

                    new_target_names = set()
                    for rel in changes['relationships']:
                        target_name = rel.get('name', '')
                        relation = rel.get('relation', '')
                        if not target_name or not relation:
                            continue
                        new_target_names.add(target_name)

                        try:
                            find_result = graph2.query(
                                "MATCH (t:Entity) WHERE t.name = $name RETURN t.uuid LIMIT 1",
                                {"name": target_name}
                            )
                            if find_result.result_set:
                                target_uuid = find_result.result_set[0][0]
                                graph2.query(
                                    "MATCH (s:Entity {uuid: $s_uuid}), (t:Entity {uuid: $t_uuid}) "
                                    "MERGE (s)-[r:RELATES_TO]->(t) "
                                    "SET r.fact = $fact, r.name = $edge_name",
                                    {
                                        "s_uuid": entity_uuid,
                                        "t_uuid": target_uuid,
                                        "fact": relation,
                                        "edge_name": relation[:50],
                                    }
                                )
                                logger.debug(f"FalkorDB 边已写入: {name} -> {target_name}")
                        except Exception as edge_err:
                            logger.warning(f"写入关系边失败 ({target_name}): {edge_err}")

                    # 删除用户移除的关系边
                    for old_name, edge_id in existing_targets.items():
                        if old_name not in new_target_names:
                            try:
                                graph2.query(
                                    "MATCH (s:Entity {uuid: $uuid})-[r]->(t:Entity {name: $tname}) DELETE r",
                                    {"uuid": entity_uuid, "tname": old_name}
                                )
                                logger.debug(f"FalkorDB 边已删除: {name} -> {old_name}")
                            except Exception:
                                pass

            except Exception as e:
                logger.warning(f"FalkorDB 关系回写失败: {e}")

    thread = threading.Thread(target=_sync, daemon=True)
    thread.start()


# ============================================================
# 引擎控制
# ============================================================

@narrative_bp.route('/<session_id>/update', methods=['PATCH'])
def update_narrative_session(session_id):
    """
    更新叙事会话基本信息（player_entity_uuid, initial_scene, opening_text, prior_summary）
    """
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": f"会话不存在: {session_id}"}), 404

        data = request.get_json()
        if 'player_entity_uuid' in data:
            state.player_entity_uuid = data['player_entity_uuid']
        if 'initial_scene' in data:
            state.initial_scene = data['initial_scene']
        if 'opening_text' in data:
            state.opening_text = data['opening_text']
        if 'prior_summary' in data:
            state.prior_summary = data['prior_summary']
        if 'custom_title' in data:
            state.custom_title = data['custom_title']

        NarrativeEngine._save_state(state)
        return jsonify({"success": True, "data": {"session_id": session_id}})

    except Exception as e:
        logger.error(f"更新叙事会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/start', methods=['POST'])
def start_narrative():
    """启动叙事引擎"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({"success": False, "error": "缺少 session_id"}), 400

        state = NarrativeEngine.start_session(session_id)
        return jsonify({
            "success": True,
            "data": {"session_id": session_id, "status": state.status}
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"启动叙事引擎失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/stop', methods=['POST'])
def stop_narrative():
    """停止叙事引擎"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({"success": False, "error": "缺少 session_id"}), 400

        state = NarrativeEngine.stop_session(session_id)
        return jsonify({
            "success": True,
            "data": {"session_id": session_id, "status": state.status}
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"停止叙事引擎失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/resume', methods=['POST'])
def resume_narrative():
    """
    恢复叙事会话（从磁盘加载状态 + 重启引擎循环）
    Request body: { session_id }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({"success": False, "error": "缺少 session_id"}), 400

        state = NarrativeEngine.resume_session(session_id)
        return jsonify({
            "success": True,
            "data": {
                "session_id": session_id,
                "status": state.status,
                "current_turn": state.current_turn,
                "segments_count": len(state.narrative_segments),
                "events_count": len(state.all_events)
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"恢复叙事会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/player-input', methods=['POST'])
def submit_player_input():
    """
    提交玩家输入
    Request body: { session_id, choice_id?, free_text? }
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        choice_id = data.get('choice_id')
        free_text = data.get('free_text')

        if not session_id:
            return jsonify({"success": False, "error": "缺少 session_id"}), 400

        if not choice_id and not free_text:
            return jsonify({"success": False, "error": "需要 choice_id 或 free_text"}), 400

        success = NarrativeEngine.submit_player_input(
            session_id=session_id,
            choice_id=choice_id,
            free_text=free_text
        )

        if not success:
            return jsonify({"success": False, "error": "当前无法接受玩家输入（状态不是 awaiting_player）"}), 400

        return jsonify({
            "success": True,
            "data": {"message": "玩家输入已提交"}
        })

    except Exception as e:
        logger.error(f"提交玩家输入失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 存档/检查点
# ============================================================

@narrative_bp.route('/<session_id>/save', methods=['POST'])
def save_narrative_checkpoint(session_id):
    """
    手动存档：创建存档快照
    """
    try:
        state = NarrativeEngine.get_session(session_id)
        if not state:
            return jsonify({"success": False, "error": "会话不存在"}), 404

        disallowed = (NarrativeStatus.PROCESSING_PLAYER.value,)
        if state.status in disallowed:
            return jsonify({
                "success": False,
                "error": f"当前状态 {state.status} 正在处理中，请稍后再存档"
            }), 409

        save_id = NarrativeEngine.create_checkpoint(session_id)
        saves = NarrativeEngine.list_checkpoints(session_id)
        save_meta = next((s for s in saves if s["save_id"] == save_id), {"save_id": save_id})

        return jsonify({"success": True, "data": save_meta})

    except Exception as e:
        logger.error(f"叙事存档失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/saves', methods=['GET'])
def list_narrative_saves(session_id):
    """列出会话的所有存档"""
    try:
        saves = NarrativeEngine.list_checkpoints(session_id)
        return jsonify({"success": True, "data": saves})
    except Exception as e:
        logger.error(f"获取存档列表失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/saves/<save_id>/load', methods=['POST'])
def load_narrative_save(session_id, save_id):
    """从指定存档恢复"""
    try:
        state = NarrativeEngine.load_checkpoint(session_id, save_id)
        return jsonify({
            "success": True,
            "data": {
                "session_id": session_id,
                "save_id": save_id,
                "status": state.status,
                "current_turn": state.current_turn
            }
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"读取存档失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/saves/<save_id>', methods=['DELETE'])
def delete_narrative_save(session_id, save_id):
    """删除指定存档"""
    try:
        deleted = NarrativeEngine.delete_checkpoint(session_id, save_id)
        if not deleted:
            return jsonify({"success": False, "error": "存档不存在"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"删除存档失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>/saves/<save_id>/rename', methods=['PATCH'])
def rename_narrative_save(session_id, save_id):
    """更新存档的自定义标题"""
    try:
        data = request.get_json()
        custom_title = data.get('custom_title', '')

        narratives_dir = Config.NARRATIVE_DATA_DIR
        meta_file = os.path.join(narratives_dir, session_id, "saves", save_id, "meta.json")
        if not os.path.isfile(meta_file):
            return jsonify({"success": False, "error": "存档不存在"}), 404

        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        meta['custom_title'] = custom_title
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"更新存档标题失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 历史记录
# ============================================================

@narrative_bp.route('/history', methods=['GET'])
def get_narrative_history():
    """
    获取叙事会话历史列表。
    - 若会话有存档快照：每个存档独立作为一条记录
    - 若会话无存档快照：会话本身作为一条记录（兼容旧逻辑）
    Query params: limit=N (默认20)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        narratives_dir = Config.NARRATIVE_DATA_DIR

        if not os.path.exists(narratives_dir):
            return jsonify({"success": True, "data": [], "count": 0})

        results = []
        for session_id in os.listdir(narratives_dir):
            state_file = os.path.join(narratives_dir, session_id, "narrative_state.json")
            if not os.path.isfile(state_file):
                continue
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 从 state.json 提取会话级别的公共字段
                base = {
                    "session_id": data.get("session_id", session_id),
                    "record_type": "narrative",
                    "initial_scene": data.get("initial_scene", ""),
                    "project_id": data.get("project_id", ""),
                    "player_entity_uuid": data.get("player_entity_uuid", ""),
                    "simulation_id": data.get("simulation_id", ""),
                    "session_created_at": data.get("created_at", ""),
                    "custom_title": data.get("custom_title", ""),
                }

                # 检查是否有存档快照
                saves_dir = os.path.join(narratives_dir, session_id, "saves")
                save_metas = []
                if os.path.isdir(saves_dir):
                    for save_id in os.listdir(saves_dir):
                        meta_file = os.path.join(saves_dir, save_id, "meta.json")
                        if os.path.isfile(meta_file):
                            try:
                                with open(meta_file, 'r', encoding='utf-8') as mf:
                                    save_metas.append(json.load(mf))
                            except Exception:
                                pass

                if save_metas:
                    # 有存档：每个存档作为独立记录
                    for meta in save_metas:
                        record = {
                            **base,
                            "save_id": meta.get("save_id"),
                            "status": meta.get("status", "completed"),
                            "can_resume": True,
                            "current_turn": meta.get("turn", 0),
                            "segments_count": meta.get("segments_count", 0),
                            "events_count": meta.get("events_count", 0),
                            "description": meta.get("description", ""),
                            "created_at": meta.get("save_time", base["session_created_at"]),
                            "custom_title": meta.get("custom_title", base.get("custom_title", "")),
                        }
                        results.append(record)
                else:
                    # 无存档：会话本身作为记录（保留旧逻辑）
                    raw_status = data.get("status", "unknown")
                    has_profiles = os.path.isfile(
                        os.path.join(narratives_dir, session_id, "profiles.json")
                    )
                    can_resume = (
                        raw_status in ("completed", "awaiting_player", "failed")
                        and data.get("current_turn", 0) > 0
                        and has_profiles
                    )
                    live_state = NarrativeEngine._sessions.get(session_id)
                    display_status = live_state.status if live_state else raw_status
                    record = {
                        **base,
                        "save_id": None,
                        "status": display_status,
                        "can_resume": can_resume,
                        "current_turn": data.get("current_turn", 0),
                        "segments_count": len(data.get("narrative_segments", [])),
                        "events_count": len(data.get("all_events", [])),
                        "description": "",
                        "created_at": data.get("created_at", ""),
                    }
                    results.append(record)

            except Exception as e:
                logger.warning(f"读取叙事状态失败 ({session_id}): {e}")
                continue

        # 按 created_at 降序
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        results = results[:limit]

        return jsonify({"success": True, "data": results, "count": len(results)})

    except Exception as e:
        logger.error(f"获取叙事历史失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@narrative_bp.route('/<session_id>', methods=['DELETE'])
def delete_narrative_session(session_id):
    """删除叙事会话（停止运行 + 删除文件）"""
    try:
        # 尝试停止运行中的会话
        state = NarrativeEngine.get_session(session_id)
        if state and state.status in (NarrativeStatus.RUNNING.value, NarrativeStatus.AWAITING_PLAYER.value):
            NarrativeEngine.stop_session(session_id)

        # 清理内存中的会话
        NarrativeEngine._sessions.pop(session_id, None)
        NarrativeEngine._agent_profiles.pop(session_id, None)
        NarrativeEngine._locks.pop(session_id, None)
        NarrativeEngine._player_input_events.pop(session_id, None)
        NarrativeEngine._player_inputs.pop(session_id, None)
        NarrativeEngine._stop_flags.pop(session_id, None)
        NarrativeEngine._engine_threads.pop(session_id, None)

        # 删除磁盘文件
        session_dir = os.path.join(Config.NARRATIVE_DATA_DIR, session_id)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)

        return jsonify({"success": True, "data": {"message": f"叙事会话 {session_id} 已删除"}})

    except Exception as e:
        logger.error(f"删除叙事会话失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 文件摘要（续写模式）
# ============================================================

@narrative_bp.route('/summarize_file', methods=['POST'])
def summarize_file():
    """
    上传小说文件，分块后生成前文摘要供续写模式使用。
    Request: multipart/form-data, 字段 'file'（pdf/txt/md）
    Response: { success, data: { summary, chunk_count } }
    """
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "缺少文件"}), 400

        f = request.files['file']
        if not f.filename:
            return jsonify({"success": False, "error": "文件名为空"}), 400

        ext = f.filename.rsplit('.', 1)[-1].lower()
        if ext not in ('pdf', 'txt', 'md', 'markdown'):
            return jsonify({"success": False, "error": "仅支持 pdf / txt / md 格式"}), 400

        # 保存到临时目录
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
            tmp_path = tmp.name
            f.save(tmp_path)

        try:
            from ..utils.file_parser import FileParser
            from ..services.text_processor import TextProcessor
            from ..utils.llm_client import LLMClient, get_client_for_prompt
            from ..services.prompt_config import get_system, get_template, safe_render, get_llm_params

            # 1. 提取文本
            raw_text = FileParser.extract_text(tmp_path)
            if not raw_text or not raw_text.strip():
                return jsonify({"success": False, "error": "文件内容为空或无法提取"}), 400

            # 2. 分块（每块约 2000 字，重叠 100 字）
            chunks = TextProcessor.split_text(raw_text, chunk_size=2000, overlap=100)
            if not chunks:
                return jsonify({"success": False, "error": "文本分块失败"}), 400

            llm = LLMClient()

            # 3. 逐块生成摘要（最多处理 20 块，避免过长）
            MAX_CHUNKS = 20
            sampled = chunks if len(chunks) <= MAX_CHUNKS else _sample_chunks(chunks, MAX_CHUNKS)

            chunk_summaries = []
            chunk_tmpl = get_template('novel_chunk_summary')
            chunk_sys = get_system('novel_chunk_summary')
            for idx, chunk in enumerate(sampled):
                prompt = safe_render(chunk_tmpl, {'chunk_text': chunk})
                # 最后一块包含最新情节，要求 LLM 详细保留所有角色最新状态
                if idx == len(sampled) - 1:
                    prompt += (
                        "\n\n【重要】这是故事的最新段落（最后一段），"
                        "请特别详细地记录所有人物的最新状态、位置、关系变化和未解决的冲突。"
                    )
                try:
                    _p = get_llm_params('novel_chunk_summary')
                    s = get_client_for_prompt('novel_chunk_summary').chat(
                        messages=[
                            {"role": "system", "content": chunk_sys},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=_p['temperature'],
                        max_tokens=_p['max_tokens']
                    )
                    chunk_summaries.append(s.strip())
                except Exception as e:
                    logger.warning(f"分块摘要失败，跳过: {e}")

            if not chunk_summaries:
                return jsonify({"success": False, "error": "摘要生成失败"}), 500

            # 4. 合并所有分块摘要为一份前文摘要
            if len(chunk_summaries) == 1:
                final_summary = chunk_summaries[0]
            else:
                numbered = "\n\n".join(
                    f"【第{i+1}段】{s}" for i, s in enumerate(chunk_summaries)
                )
                merge_prompt = safe_render(get_template('novel_summary_merge'), {'chunk_summaries': numbered})
                _p = get_llm_params('novel_summary_merge')
                final_summary = get_client_for_prompt('novel_summary_merge').chat(
                    messages=[
                        {"role": "system", "content": get_system('novel_summary_merge')},
                        {"role": "user", "content": merge_prompt}
                    ],
                    temperature=_p['temperature'],
                    max_tokens=_p['max_tokens']
                ).strip()

            return jsonify({
                "success": True,
                "data": {
                    "summary": final_summary,
                    "chunk_count": len(chunks),
                    "sampled_count": len(sampled)
                }
            })

        finally:
            import os as _os
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"文件摘要生成失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


def _sample_chunks(chunks: list, n: int) -> list:
    """均匀抽样 n 个分块，确保首尾一定包含（最后的块含最新情节，不可遗漏）"""
    if len(chunks) <= n:
        return chunks
    step = len(chunks) / n
    indices = [int(i * step) for i in range(n)]
    # 确保最后一块（最新情节）一定被包含
    if indices[-1] != len(chunks) - 1:
        indices[-1] = len(chunks) - 1
    return [chunks[i] for i in indices]
