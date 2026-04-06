"""
图谱构建服务
使用 Graphiti + FalkorDB 本地构建知识图谱（替代 Zep Cloud 图谱构建）

Graphiti 是 Zep 的开源图谱引擎，使用 add_episode_bulk 批量添加数据时
不会执行边失效检测（edge invalidation），从而保留所有边。

搜索、实体读取、模拟更新仍使用 Zep Cloud。
"""

import asyncio
import logging
import os
import time as _time
import uuid
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from .compat_llm_client import CompatOpenAIClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from .dashscope_embedder import DashScopeEmbedder
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.utils.bulk_utils import RawEpisode
from graphiti_core.nodes import EpisodeType

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from .text_processor import TextProcessor

logger = logging.getLogger('agars.build')


# Graphiti 使用的保留属性名，不能作为自定义实体属性
RESERVED_ATTR_NAMES = {
    'uuid', 'name', 'group_id', 'labels', 'created_at',
    'summary', 'attributes', 'name_embedding',
    # 'title' 与 JSON Schema 顶层关键词同名，会导致 Gemini API 报 INVALID_ARGUMENT
    'title',
}


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


def _safe_attr_name(attr_name: str) -> str:
    """将保留名称转换为安全名称"""
    if attr_name.lower() in RESERVED_ATTR_NAMES:
        return f"entity_{attr_name}"
    return attr_name


def _build_entity_types(ontology: Dict[str, Any]) -> Dict[str, type]:
    """
    将本体中的 entity_types 转换为 Graphiti 需要的 Pydantic BaseModel 字典。

    输入格式（来自 ontology_generator.py）:
    {
        "entity_types": [
            {"name": "Person", "description": "...", "attributes": [{"name": "age", "description": "..."}]}
        ]
    }

    输出格式: {"Person": PersonModel, ...}
    """
    entity_types = {}
    for entity_def in ontology.get("entity_types", []):
        name = entity_def["name"]
        description = entity_def.get("description", f"A {name} entity.")

        attrs = {"__doc__": description}
        annotations = {}

        for attr_def in entity_def.get("attributes", []):
            attr_name = _safe_attr_name(attr_def["name"])
            attr_desc = attr_def.get("description", attr_name)
            attrs[attr_name] = Field(default=None, description=attr_desc)
            annotations[attr_name] = Optional[str]

        attrs["__annotations__"] = annotations

        entity_class = type(name, (BaseModel,), attrs)
        entity_class.__doc__ = description
        entity_types[name] = entity_class

    return entity_types


def _build_edge_types(ontology: Dict[str, Any]) -> tuple:
    """
    将本体中的 edge_types 转换为 Graphiti 需要的格式。

    返回:
        (edge_types, edge_type_map)
        edge_types: {"KNOWS": KnowsModel, ...}
        edge_type_map: {("Person", "Person"): ["KNOWS"], ...}
    """
    edge_types = {}
    edge_type_map = {}

    for edge_def in ontology.get("edge_types", []):
        name = edge_def["name"]
        description = edge_def.get("description", f"A {name} relationship.")

        attrs = {"__doc__": description}
        annotations = {}

        for attr_def in edge_def.get("attributes", []):
            attr_name = _safe_attr_name(attr_def["name"])
            attr_desc = attr_def.get("description", attr_name)
            attrs[attr_name] = Field(default=None, description=attr_desc)
            annotations[attr_name] = Optional[str]

        attrs["__annotations__"] = annotations

        # 类名使用 PascalCase
        class_name = ''.join(word.capitalize() for word in name.split('_'))
        edge_class = type(class_name, (BaseModel,), attrs)
        edge_class.__doc__ = description
        edge_types[name] = edge_class

        # 构建 edge_type_map
        for st in edge_def.get("source_targets", []):
            source = st.get("source", "Entity")
            target = st.get("target", "Entity")
            key = (source, target)
            if key not in edge_type_map:
                edge_type_map[key] = []
            if name not in edge_type_map[key]:
                edge_type_map[key].append(name)

    return edge_types, edge_type_map


class GraphBuilderService:
    """
    图谱构建服务
    使用 Graphiti + FalkorDB 本地构建知识图谱
    """

    def __init__(self):
        # 创建独立的 event loop（Flask 同步线程中运行 async Graphiti）
        # 必须 set_event_loop 使其成为当前线程的默认 loop，
        # 否则 redis.asyncio / httpx 等库内部 get_event_loop() 拿不到正确的 loop。
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # 初始化 FalkorDB driver
        password = Config.FALKORDB_PASSWORD or None
        self._driver = FalkorDriver(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=password,
            database="graphiti",
        )

        # 初始化 Graphiti LLM 客户端（使用项目统一的 OpenAI 兼容 API）
        llm_config = LLMConfig(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL,
            model=Config.LLM_MODEL_NAME,
        )
        llm_client = CompatOpenAIClient(config=llm_config)

        # Embedder 使用独立的 Embedding API 配置
        embedder_config = OpenAIEmbedderConfig(
            api_key=Config.EMBEDDING_API_KEY,
            base_url=Config.EMBEDDING_BASE_URL,
            embedding_model=Config.EMBEDDING_MODEL_NAME,
        )
        # 阿里云 DashScope 限制单次 embedding 请求最多 10 条，需要自动分批
        if 'dashscope' in (Config.EMBEDDING_BASE_URL or ''):
            embedder = DashScopeEmbedder(config=embedder_config)
        else:
            embedder = OpenAIEmbedder(config=embedder_config)

        # Cross-encoder / reranker（复用同一套 LLM 配置）
        cross_encoder = OpenAIRerankerClient(config=llm_config)

        # 初始化 Graphiti
        self._graphiti = Graphiti(
            graph_driver=self._driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

        # ── Monkey-patch Graphiti 内部参数 ──
        # Graphiti 默认为聊天场景设计，summary 限制过紧，不适合长篇叙事文本。
        # 在运行时覆盖关键常量，无需修改库文件。
        self._patch_graphiti_defaults()

        self.task_manager = TaskManager()

    @staticmethod
    def _patch_graphiti_defaults():
        """
        覆盖 Graphiti 内部默认值和 prompt 以适应中文长篇叙事文本场景。

        Graphiti 设计初衷是英文聊天/对话场景，默认 prompt 对中文小说/剧本不适配：
        - summary 限制 250 字符、示例全是英文用户行为
        - node 提取指导过于笼统
        - edge 提取要求"clearly stated"，对中文叙事的隐含关系过于保守

        这里通过 monkey-patch 在运行时覆盖，不修改库文件。
        使用"包装原函数追加内容"而非"替换函数"，降低库升级的兼容风险。
        """
        try:
            # ── 1. 常量调整 ──────────────────────────────────────────
            import graphiti_core.utils.maintenance.node_operations as _node_ops
            _node_ops.MAX_SUMMARY_CHARS = 800

            import graphiti_core.utils.maintenance.graph_data_operations as _gdo
            _gdo.EPISODE_WINDOW_LEN = 5

            # ── 2. Summary prompt：替换为中文叙事适配版本 ────────────
            import graphiti_core.prompts.snippets as _snippets
            _snippets.summary_instructions = """Guidelines:
1. Output only factual content. Never explain what you're doing or mention limitations.
2. Only use the provided messages and entity context to set attribute values.
3. Keep the summary concise. STATE FACTS DIRECTLY IN UNDER 800 CHARACTERS.
4. For Chinese text: write the summary in Chinese.

WHAT BELONGS IN A SUMMARY (实体描述性信息):
- Identity: who/what the entity is (身份、类型、所属)
- Stable traits: personality, abilities, appearance (性格、能力、外貌)
- Current status: latest known state, location, condition (当前状态、位置、处境)
- Key background: origin, history that defines the entity (背景、经历)

WHAT DOES NOT BELONG IN A SUMMARY (应作为 edge/fact 提取的信息):
- Specific events between two entities → these should be edges
- Temporal actions (who did what to whom when) → these should be edges
- Relationships with other entities (ally, enemy, mentor) → these should be edges

Example summaries:
BAD: "张三在第三章中与李四战斗并获胜。后来他与王五结盟对抗魔王。" (these are events/relationships, not summary)
GOOD: "张三，年轻武士，性格沉默寡言，擅长剑术和火系魔法。目前身受重伤，隐居山中疗养。曾是皇家军团成员，后脱离独行。"
GOOD: "皇家军团，帝国最精锐的军事力量，驻守王都北门。兵力约三千人，纪律严明，以重骑兵著称。近年因连续征战实力有所下降。"
"""

            # ── 3. Node 提取 prompt：追加中文叙事指导 ────────────────
            import graphiti_core.prompts.extract_nodes as _extract_nodes
            _orig_extract_text = _extract_nodes.versions['extract_text']

            def _patched_extract_text(context):
                messages = _orig_extract_text(context)
                messages[-1] = type(messages[-1])(
                    role=messages[-1].role,
                    content=messages[-1].content + """

ADDITIONAL GUIDELINES FOR NARRATIVE TEXT (中文叙事文本补充规则):
- The text may contain a header like [本段涉及实体：...已知关系：...] at the beginning. These are pre-extracted entities — use them to identify and resolve entity references in the text.
- For Chinese names: a character may be referred to by full name (张三丰), surname (张), title (掌门), or nickname (老张). Extract using the most complete/formal name.
- Extract ALL named characters, organizations, locations, and significant items — not just "main" entities. Minor characters are also important for the knowledge graph.
- If a pronoun clearly refers to a known entity, resolve it to that entity's name.

Example: Given text "老张拔剑迎向敌人，身旁的小李紧随其后。二人冲入了皇城大门。"
→ Extract: "张三" (if header says 老张=张三), "李四" (if header says 小李=李四), "皇城"
→ Do NOT extract: "敌人" (too vague), "大门" (not significant)
""",
                )
                return messages
            _extract_nodes.versions['extract_text'] = _patched_extract_text

            # ── 4. Edge 提取 prompt：利用预提取关系 + 中文叙事适配 ──
            import graphiti_core.prompts.extract_edges as _extract_edges
            _orig_edge = _extract_edges.versions['edge']

            def _patched_edge(context):
                messages = _orig_edge(context)
                messages[-1] = type(messages[-1])(
                    role=messages[-1].role,
                    content=messages[-1].content + """

ADDITIONAL RULES FOR NARRATIVE TEXT (中文叙事文本补充规则):

1. PRE-EXTRACTED RELATIONSHIPS:
   The text may start with a header like [本段涉及实体：...已知关系：...].
   The "已知关系" section lists relationships pre-extracted from a broader context window.
   - You MUST extract these relationships as edges if they are supported by the current text.
   - Use them as strong hints — they tell you WHAT relationships exist; your job is to find the textual evidence and extract with proper detail (fact description, temporal info).
   - If a pre-extracted relationship is not supported by the current text, skip it.

2. IMPLICIT RELATIONSHIPS IN NARRATIVE:
   In narrative text, relationships are often implied through actions rather than stated directly.
   Examples:
   · "二人并肩走过长街" → COMPANION or ALLIED_WITH
   · "他想起师父曾说的话" → MENTORED_BY
   · "她将信物交给了他" → ENTRUSTED or GAVE_TO
   Extract these as edges. When the relationship type is ambiguous, use INTERACTS_WITH as a fallback relation_type.

3. ENTITY NAME RESOLUTION:
   Use the entity descriptions and aliases from the [本段涉及实体：...] header to correctly match character references to their full names in the ENTITIES list.

4. SINGLE-ENTITY FACTS:
   Facts about a single entity (e.g., "张三擅长剑术") cannot be edges — those belong in the entity summary. Only extract facts that involve TWO distinct entities.

5. EXAMPLE:
   Text: "张三拔剑挡在李四面前，替他挡下了魔王的致命一击。"
   Header says: 已知关系：张三 → 师从 → 李四
   Expected edges:
   - source=张三, target=李四, relation_type=PROTECTED, fact="张三替李四挡下了魔王的致命一击"
   - source=张三, target=魔王, relation_type=FOUGHT_AGAINST, fact="张三与魔王交战，挡下其致命一击"
   - source=张三, target=李四, relation_type=MENTORED_BY, fact="张三师从李四" (from pre-extracted relationship, supported by the protective act implying a close mentor-student bond)
""",
                )
                return messages
            _extract_edges.versions['edge'] = _patched_edge

            logger.info(
                "[Graphiti patch] Applied: MAX_SUMMARY_CHARS=800, "
                "EPISODE_WINDOW_LEN=5, Chinese narrative prompts for summary/node/edge"
            )
        except Exception as e:
            logger.warning(f"[Graphiti patch] 部分覆盖失败（不影响构建）: {e}")

    def _run(self, coro):
        """在独立的 event loop 中同步执行 async 协程"""
        return self._loop.run_until_complete(coro)

    def close(self):
        """关闭资源"""
        try:
            self._run(self._graphiti.close())
        except Exception:
            pass
        try:
            self._loop.close()
        except Exception:
            pass

    def create_graph(self, name: str) -> str:
        """
        创建图谱（生成 group_id，初始化索引）

        Graphiti 使用 group_id 分区数据，无需显式创建图。
        返回生成的 group_id，存入 project.graph_id 字段。
        """
        group_id = f"mf_{uuid.uuid4().hex[:16]}"

        # 确保索引和约束已创建
        self._run(self._graphiti.build_indices_and_constraints())

        return group_id

    def set_ontology(self, group_id: str, ontology: Dict[str, Any]):
        """
        解析本体定义，转换为 Graphiti 的 entity_types 和 edge_types。

        注意：Graphiti 不需要单独"设置"本体，而是在 add_episode 时传入。
        这里只做预处理和缓存。
        """
        self._entity_types = _build_entity_types(ontology)
        self._edge_types, self._edge_type_map = _build_edge_types(ontology)

    def add_text_batches(
        self,
        group_id: str,
        chunks: List[str],
        batch_size: int = 10,
        progress_callback: Optional[Callable] = None,
        source_description: str = "AGARS document import"
    ) -> int:
        """
        使用 Graphiti add_episode_bulk 批量添加文本到图谱。

        add_episode_bulk 不执行边失效检测，所有边都会被保留。

        Args:
            group_id: 图谱分区ID
            chunks: 文本块列表
            batch_size: 每批大小（传给 add_episode_bulk 的 bulk_episodes 列表长度）
            progress_callback: 进度回调 (message, progress_ratio)

        Returns:
            处理的 episode 数量
        """
        total_chunks = len(chunks)
        processed_count = 0

        # 获取本体类型（如果已通过 set_ontology 设置）
        entity_types = getattr(self, '_entity_types', None) or None
        edge_types = getattr(self, '_edge_types', None) or None
        edge_type_map = getattr(self, '_edge_type_map', None) or None

        # 跨批次节点上下文注入：处理完每批后更新，供下批使用
        _known_graph_nodes: List[Dict[str, str]] = []

        # 记录失败批次，容忍部分失败
        failed_batches: List[Dict[str, Any]] = []

        # 分批处理
        for i in range(0, total_chunks, batch_size):
            batch_chunks = list(chunks[i:i + batch_size])
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"发送第 {batch_num}/{total_batches} 批数据 ({len(batch_chunks)} 块)...",
                    progress
                )

            # 将上一批产生的图谱节点注入到本批的 chunk 头部
            # 帮助 Graphiti 将新文本中的实体引用解析到已有节点而非创建重复节点
            if _known_graph_nodes:
                batch_chunks = self._inject_graph_node_context(batch_chunks, _known_graph_nodes)
                logger.debug(f"[batch {batch_num}] 注入 {len(_known_graph_nodes)} 个已知节点上下文")

            # 构建 RawEpisode 列表
            episodes = []
            for j, chunk in enumerate(batch_chunks):
                episodes.append(RawEpisode(
                    name=f"chunk_{i + j + 1}",
                    content=chunk,
                    source=EpisodeType.text,
                    source_description=source_description,
                    reference_time=datetime.now(),
                ))

            # 调用 Graphiti bulk API（不触发 edge invalidation）
            # 注意：compat_llm_client 内部已有 3 次 LLM 级重试；
            # 这里在 batch 级别再做最多 BATCH_MAX_RETRIES 次重试，
            # 覆盖 LLM 重试也无法恢复的瞬时故障（如 API 网关超时）。
            BATCH_MAX_RETRIES = 2
            batch_success = False
            for batch_attempt in range(BATCH_MAX_RETRIES):
                try:
                    attempt_label = f" (重试 {batch_attempt})" if batch_attempt > 0 else ""
                    logger.info(
                        f"[batch {batch_num}/{total_batches}]{attempt_label} "
                        f"开始 add_episode_bulk ({len(episodes)} episodes)..."
                    )
                    self._run(self._graphiti.add_episode_bulk(
                        bulk_episodes=episodes,
                        group_id=group_id,
                        entity_types=entity_types if entity_types else None,
                        edge_types=edge_types if edge_types else None,
                        edge_type_map=edge_type_map if edge_type_map else None,
                        custom_extraction_instructions=(
                            "重要提取规则（必须遵守）：\n"
                            "1. 时间标记：如文本提及时间（'一年前'、'三个月后'、'幼年时'、'last year'等），"
                            "必须在 fact 字段中原文保留。例：'（一年前）角色A从商人处购买了一把剑'\n"
                            "2. 实体摘要：尽量详细，包含身份、职业、关键关系、能力特长、当前状态。"
                            "不要过度压缩——500字符以内即可，不必追求极简\n"
                            "3. 中文别名：同一人物的姓名、称号、外号、代称（如'那位老人'的真名）"
                            "应识别为同一实体，使用最完整的名称作为实体名\n"
                            "4. 保留具体细节：不要将具体事件、地点、物品泛化为笼统描述\n"
                            "5. 如果文本开头的 [本段涉及实体] 提供了实体描述，"
                            "利用它来更准确地识别和关联实体，但以正文内容为准\n"
                            "6. 关系必须生成独立的 edge：两个实体之间的每种关系都应提取为独立的 fact triple，"
                            "不要仅写在实体 summary 中。即使关系是隐含的（如叙述暗示A是B的师父），"
                            "也应提取为 edge"
                        ),
                    ))
                    logger.info(f"[batch {batch_num}/{total_batches}] add_episode_bulk 完成")
                    processed_count += len(batch_chunks)
                    batch_success = True

                    # 当前批次处理完后，查询图谱中已有节点，供下批注入使用
                    if i + batch_size < total_chunks:
                        try:
                            _known_graph_nodes = self._get_current_nodes_brief(group_id)
                        except Exception as _qe:
                            logger.warning(f"[batch {batch_num}] 查询已知节点失败，跳过下批注入: {_qe}")
                            _known_graph_nodes = []
                    break  # 成功，跳出重试循环

                except Exception as e:
                    if batch_attempt < BATCH_MAX_RETRIES - 1:
                        wait = 30 * (batch_attempt + 1)
                        logger.warning(
                            f"[batch {batch_num}/{total_batches}] add_episode_bulk 失败，"
                            f"{wait}s 后重试 ({batch_attempt+1}/{BATCH_MAX_RETRIES}): {e}"
                        )
                        if progress_callback:
                            progress_callback(
                                f"批次 {batch_num} 失败，{wait}s 后重试...", 0
                            )
                        _time.sleep(wait)
                    else:
                        # 重试用尽，记录失败并继续后续批次
                        logger.error(
                            f"[batch {batch_num}/{total_batches}] add_episode_bulk "
                            f"重试 {BATCH_MAX_RETRIES} 次后仍失败，跳过此批次: {e}",
                            exc_info=True,
                        )
                        failed_batches.append({"batch": batch_num, "error": str(e)})
                        if progress_callback:
                            progress_callback(
                                f"批次 {batch_num} 重试后仍失败，已跳过: {str(e)[:80]}", 0
                            )

        # 汇总结果
        if failed_batches:
            total_batches = (total_chunks + batch_size - 1) // batch_size
            logger.warning(
                f"图谱构建部分批次失败: {len(failed_batches)}/{total_batches} 批失败，"
                f"{processed_count}/{total_chunks} 块成功处理"
            )
            if processed_count == 0:
                # 全部失败：抛出最后一个错误
                raise RuntimeError(
                    f"图谱构建失败: 全部 {len(failed_batches)} 个批次均失败。"
                    f"最后错误: {failed_batches[-1]['error']}"
                )

        return processed_count

    def get_graph_data(self, group_id: str) -> Dict[str, Any]:
        """
        通过 FalkorDB Cypher 查询获取完整图谱数据。

        Args:
            group_id: 图谱分区ID（即 project.graph_id）

        Returns:
            包含 nodes 和 edges 的字典
        """
        from falkordb import FalkorDB

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        # Graphiti 用 group_id 作为 FalkorDB 的 graph 名称（不是 "graphiti"）
        graph = db.select_graph(group_id)

        # 查询节点（同一个 graph 内的所有 Entity 都属于该 group）
        nodes_result = graph.query(
            "MATCH (n:Entity) RETURN n"
        )

        nodes_data = []
        node_name_map = {}  # uuid -> name

        for record in nodes_result.result_set:
            node = record[0]
            props = node.properties

            node_uuid = props.get("uuid", "")
            node_name = (props.get("name") or "").strip()
            node_name_map[node_uuid] = node_name  # 边查找需要完整的 map
            if not node_name:
                continue  # 不展示空白节点

            # 提取标签
            labels = list(node.labels) if hasattr(node, 'labels') else []

            nodes_data.append({
                "uuid": node_uuid,
                "name": node_name,
                "labels": labels,
                "summary": props.get("summary", ""),
                "attributes": {},
                "created_at": props.get("created_at", None),
            })

        # 查询边
        edges_result = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity) RETURN s, r, t"
        )

        edges_data = []
        for record in edges_result.result_set:
            source_node = record[0]
            rel = record[1]
            target_node = record[2]

            s_props = source_node.properties
            r_props = rel.properties
            t_props = target_node.properties

            source_uuid = s_props.get("uuid", "")
            target_uuid = t_props.get("uuid", "")

            edges_data.append({
                "uuid": r_props.get("uuid", ""),
                "name": r_props.get("name", ""),
                "fact": r_props.get("fact", ""),
                "fact_type": r_props.get("fact_type", r_props.get("name", "")),
                "source_node_uuid": source_uuid,
                "target_node_uuid": target_uuid,
                "source_node_name": node_name_map.get(source_uuid, s_props.get("name", "")),
                "target_node_name": node_name_map.get(target_uuid, t_props.get("name", "")),
                "attributes": {},
                "created_at": r_props.get("created_at", None),
                "valid_at": r_props.get("valid_at", None),
                "invalid_at": r_props.get("invalid_at", None),
                "expired_at": r_props.get("expired_at", None),
                "episodes": [],
            })

        return {
            "graph_id": group_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def _get_graph_info(self, group_id: str) -> GraphInfo:
        """获取图谱摘要信息"""
        data = self.get_graph_data(group_id)

        entity_types = set()
        for node in data["nodes"]:
            for label in node.get("labels", []):
                if label not in ("Entity", "Node"):
                    entity_types.add(label)

        return GraphInfo(
            graph_id=group_id,
            node_count=data["node_count"],
            edge_count=data["edge_count"],
            entity_types=list(entity_types)
        )

    def resolve_duplicate_entities(
        self,
        group_id: str,
        progress_callback: Optional[Callable] = None,
        entity_database: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        LLM 辅助实体去重：识别名称不同但实指同一实体的节点，并在图谱中合并。

        步骤：
        1. 从 FalkorDB 读取所有实体的 uuid/name/summary
        2. 调用 LLM 识别别名/同义实体组（处理称谓、外号、缩写等场景）
        3. 在 FalkorDB 中合并：将重复节点的所有边转移到规范节点，删除重复节点

        Returns:
            {"merged": int, "groups": [[uuid, ...], ...]}
        """
        from falkordb import FalkorDB
        from ..utils.llm_client import LLMClient, get_client_for_prompt
        from ..utils.llm_monitor import monitor

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(group_id)

        # 1. 读取所有实体及其边数（边数多的是规范节点）
        result = graph.query("MATCH (n:Entity) RETURN n.uuid, n.name, n.summary")
        entities = []
        for record in result.result_set:
            uid, name, summary = record[0], record[1] or "", record[2] or ""
            if uid and name:
                entities.append({"uuid": uid, "name": name, "summary": summary})

        logger.info(f"实体去重: group_id={group_id}, 实体数={len(entities)}")
        monitor.log_full(
            source="Dedup",
            model="—",
            messages=[{"role": "system", "content": f"[去重开始] graph={group_id}, 共 {len(entities)} 个实体"}],
            response=", ".join(f'{e["name"]}({e["uuid"][:8]})' for e in entities[:30]),
        )

        if len(entities) < 2:
            return {"merged": 0, "groups": []}

        edge_counts = self._get_entity_edge_counts(graph, entities)

        merged_count = 0
        all_groups = []
        absorbed = set()  # 已被合并掉的 uuid，不再参与后续步骤

        # 阶段0：利用 entity_database 的别名信息直接合并已知别名节点
        # entity_database 由预提取阶段通过 LLM 识别，包含最可靠的别名对应关系
        if entity_database:
            if progress_callback:
                progress_callback("利用预提取别名数据执行第0阶段去重...", 0.05)
            alias_groups = self._find_alias_groups_from_entity_db(entities, entity_database)
            for group in alias_groups:
                canonical_uuid = max(group, key=lambda u: edge_counts.get(u, 0))
                duplicates = [u for u in group if u != canonical_uuid and u not in absorbed]
                for dup_uuid in duplicates:
                    try:
                        self._merge_entity_into(graph, canonical_uuid, dup_uuid)
                        absorbed.add(dup_uuid)
                        merged_count += 1
                        logger.info(f"[别名预合并] 合并: {dup_uuid} -> {canonical_uuid}")
                    except Exception as e:
                        logger.error(f"别名预合并失败 ({dup_uuid} -> {canonical_uuid}): {e}")
                if duplicates:
                    all_groups.append(group)
            if alias_groups:
                logger.info(f"[别名预合并] 共合并 {sum(len(g)-1 for g in alias_groups)} 个节点")
            # 刷新 edge_counts（合并后边数变化）
            remaining_after_alias = [e for e in entities if e["uuid"] not in absorbed]
            if remaining_after_alias:
                edge_counts = self._get_entity_edge_counts(graph, remaining_after_alias)

        # 阶段1：字符串预筛选：精确名称匹配
        #    这类情况信号明确，直接合并，无需 LLM
        if progress_callback:
            progress_callback(f"读取到 {len(entities)} 个实体，执行字符串预筛选...", 0.1)

        name_groups = self._find_name_based_groups(entities, edge_counts)
        for group in name_groups:
            # 规范节点 = 边数最多的
            canonical_uuid = max(group, key=lambda u: edge_counts.get(u, 0))
            duplicates = [u for u in group if u != canonical_uuid and u not in absorbed]
            for dup_uuid in duplicates:
                try:
                    self._merge_entity_into(graph, canonical_uuid, dup_uuid)
                    absorbed.add(dup_uuid)
                    merged_count += 1
                    logger.info(f"[字符串匹配] 合并: {dup_uuid} -> {canonical_uuid}")
                except Exception as e:
                    logger.error(f"合并失败 ({dup_uuid} -> {canonical_uuid}): {e}")
            if duplicates:
                all_groups.append(group)

        # 3. LLM 兜底：对尚未处理的实体做语义去重（别名、称谓等复杂场景）
        remaining = [e for e in entities if e["uuid"] not in absorbed]
        if len(remaining) >= 2:
            if progress_callback:
                progress_callback(f"字符串预筛选完成，对剩余 {len(remaining)} 个实体进行 Embedding 预筛选...", 0.4)

            llm = get_client_for_prompt('graph_dedup')

            # 用 embedding 余弦相似度找候选组，避免大图谱跨批次漏检
            candidate_groups = self._find_dedup_candidates_by_embedding(remaining)
            if candidate_groups is None:
                # embedding 调用失败，回退到旧的全量批次策略
                logger.warning("[Embedding去重] 回退到全量批次LLM策略")
                llm_groups = self._llm_find_duplicate_entities(llm, remaining, graph)
            elif len(candidate_groups) == 0:
                logger.info("[Embedding去重] 未找到相似度足够高的候选组，跳过LLM")
                llm_groups = []
            else:
                total_candidates = sum(len(g) for g in candidate_groups)
                if progress_callback:
                    progress_callback(
                        f"Embedding预筛选找到 {len(candidate_groups)} 个候选组（共 {total_candidates} 个实体），逐组LLM确认...",
                        0.5
                    )
                llm_groups = []
                for cg in candidate_groups:
                    llm_groups.extend(self._llm_find_duplicates_batch(llm, cg, graph))

            for group in llm_groups:
                canonical_uuid = max(group, key=lambda u: edge_counts.get(u, 0))
                duplicates = [u for u in group if u != canonical_uuid and u not in absorbed]
                for dup_uuid in duplicates:
                    try:
                        self._merge_entity_into(graph, canonical_uuid, dup_uuid)
                        absorbed.add(dup_uuid)
                        merged_count += 1
                        logger.info(f"[LLM] 合并: {dup_uuid} -> {canonical_uuid}")
                    except Exception as e:
                        logger.error(f"合并失败 ({dup_uuid} -> {canonical_uuid}): {e}")
                if duplicates:
                    all_groups.append(group)

        if progress_callback:
            progress_callback(f"去重完成，共合并 {merged_count} 个节点", 1.0)

        logger.info(f"实体去重完成: merged={merged_count}")
        monitor.log_full(
            source="Dedup",
            model="—",
            messages=[{"role": "system", "content": f"[去重完成] graph={group_id}"}],
            response=f"merged={merged_count}, groups={all_groups}",
        )
        return {"merged": merged_count, "groups": all_groups}

    def _get_entity_edge_counts(self, graph, entities: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量获取各实体的出边+入边总数。"""
        counts: Dict[str, int] = {e["uuid"]: 0 for e in entities}
        try:
            # 出边计数
            out = graph.query(
                "MATCH (n:Entity)-[r]->(:Entity) RETURN n.uuid, count(r)"
            )
            for row in out.result_set:
                uid = row[0]
                if uid in counts:
                    counts[uid] += row[1]
        except Exception as e:
            logger.warning(f"查询出边数失败: {e}")
        try:
            # 入边计数
            in_ = graph.query(
                "MATCH (:Entity)-[r]->(n:Entity) RETURN n.uuid, count(r)"
            )
            for row in in_.result_set:
                uid = row[0]
                if uid in counts:
                    counts[uid] += row[1]
        except Exception as e:
            logger.warning(f"查询入边数失败: {e}")
        return counts

    def _find_name_based_groups(
        self,
        entities: List[Dict[str, Any]],
        edge_counts: Dict[str, int]
    ) -> List[List[str]]:
        """
        通过字符串精确匹配找出重复实体组：仅合并名称完全相同的节点。
        其他情况（别名、称谓、名字出现在summary中等）全部交给 LLM 判断。
        返回 [[uuid1, uuid2, ...], ...]，每组内包含所有重复节点。
        """
        parent: Dict[str, str] = {e["uuid"]: e["uuid"] for e in entities}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str):
            parent[find(a)] = find(b)

        for i, e1 in enumerate(entities):
            for j, e2 in enumerate(entities):
                if i >= j:
                    continue
                # 只合并名称完全相同的节点
                if e1["name"] == e2["name"]:
                    union(e1["uuid"], e2["uuid"])

        # 按根节点分组
        groups: Dict[str, List[str]] = {}
        for e in entities:
            root = find(e["uuid"])
            groups.setdefault(root, []).append(e["uuid"])

        return [g for g in groups.values() if len(g) >= 2]

    def _llm_find_duplicate_entities(
        self,
        llm,
        entities: List[Dict[str, Any]],
        graph,
        batch_size: int = 80
    ) -> List[List[str]]:
        """
        调用 LLM 识别别名/重复实体组。
        entities 超过 batch_size 时分批处理。
        """
        all_groups: List[List[str]] = []

        for i in range(0, len(entities), batch_size):
            batch = entities[i:i + batch_size]
            groups = self._llm_find_duplicates_batch(llm, batch, graph)
            all_groups.extend(groups)

        return all_groups

    def _query_entity_edges_brief(self, graph, entity_uuid: str, limit: int = 5) -> List[str]:
        """查询实体的关系边，返回简短描述列表，用于丰富去重上下文。"""
        facts = []
        try:
            # 出边：该实体 -> 其他实体（FalkorDB 不支持参数化 LIMIT，用 f-string）
            out = graph.query(
                f"MATCH (n:Entity {{uuid: $uuid}})-[r]->(t:Entity) "
                f"RETURN t.name, r.fact LIMIT {limit}",
                {"uuid": entity_uuid}
            )
            for row in out.result_set:
                t_name, fact = row[0] or "", row[1] or ""
                if fact:
                    facts.append(f"→{t_name}: {fact[:80]}")
                elif t_name:
                    facts.append(f"→{t_name}")
        except Exception as e:
            logger.debug(f"查询出边失败 ({entity_uuid[:8]}): {e}")
        try:
            # 入边：其他实体 -> 该实体
            in_ = graph.query(
                f"MATCH (s:Entity)-[r]->(n:Entity {{uuid: $uuid}}) "
                f"RETURN s.name, r.fact LIMIT {limit}",
                {"uuid": entity_uuid}
            )
            for row in in_.result_set:
                s_name, fact = row[0] or "", row[1] or ""
                if fact:
                    facts.append(f"←{s_name}: {fact[:80]}")
                elif s_name:
                    facts.append(f"←{s_name}")
        except Exception as e:
            logger.debug(f"查询入边失败 ({entity_uuid[:8]}): {e}")
        return facts

    def _llm_find_duplicates_batch(
        self,
        llm,
        entities: List[Dict[str, Any]],
        graph
    ) -> List[List[str]]:
        """对单批实体调用 LLM 识别重复组，附带关系边上下文。"""
        lines = []
        for e in entities:
            summary_short = e["summary"][:500] if e["summary"] else "（无摘要）"
            edge_facts = self._query_entity_edges_brief(graph, e["uuid"], limit=5)
            edges_str = "；".join(edge_facts) if edge_facts else "（无关系边）"
            lines.append(
                f'- UUID={e["uuid"]}\n'
                f'  名称: {e["name"]}\n'
                f'  摘要: {summary_short}\n'
                f'  关系: {edges_str}'
            )

        entity_text = "\n".join(lines)

        prompt = f"""以下是知识图谱中的实体列表（每条含UUID、名称、摘要、关系边）：

{entity_text}

任务：找出名称不同但实指同一实体（同一人物/组织）的节点组，将它们的UUID放入 merge_groups。

重点关注以下场景（按优先级）：
1. 【摘要揭示真名】节点名称是称谓/代称（如"小姐"、"仕女"、"那人"），但摘要中写明了真实姓名，且多个节点的摘要指向同一个真实姓名 → 应合并
2. 【关系边重叠】两节点与相同的第三方节点有相似关系 → 强信号
3. 【别名变体】名称是外号、缩写、不同译名等

输出规则：
- 只在有充分依据时合并，模糊情况宁可不合并
- 每组至少 2 个 UUID
- 没有发现重复时 merge_groups 返回 []

只返回如下 JSON，不要任何其他文字：
{{"merge_groups": [["uuid_a", "uuid_b"], ["uuid_c", "uuid_d"]]}}"""

        from .prompt_config import get_system as _get_system
        logger.info(f"[LLM去重] 发送 {len(entities)} 个实体到LLM识别重复...")
        try:
            result = llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": _get_system('graph_dedup')
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=8192
            )
            logger.info(f"[LLM去重] 原始返回: {result}")

            merge_groups = result.get("merge_groups", [])
            logger.info(f"[LLM去重] 识别到 {len(merge_groups)} 个重复组: {merge_groups}")

            valid_uuids = {e["uuid"] for e in entities}
            validated = [
                [u for u in group if u in valid_uuids]
                for group in merge_groups
                if isinstance(group, list)
            ]
            validated = [g for g in validated if len(g) >= 2]
            logger.info(f"[LLM去重] 验证后有效组: {validated}")
            return validated

        except Exception as e:
            logger.warning(f"[LLM去重] 调用失败: {e}", exc_info=True)
            return []

    def _get_entity_embeddings(self, entities: List[Dict[str, Any]]) -> List[List[float]]:
        """为实体列表生成 embedding（name + summary 前300字拼接）。失败返回空列表。"""
        texts = [
            e["name"] + ("\n" + e["summary"][:300] if e.get("summary") else "")
            for e in entities
        ]
        try:
            return self._run(self._graphiti.embedder.create_batch(texts))
        except Exception as ex:
            logger.warning(f"[Embedding去重] 生成embedding失败: {ex}")
            return []

    def _find_dedup_candidates_by_embedding(
        self,
        entities: List[Dict[str, Any]],
        threshold: float = 0.75,
        max_group_size: int = 20,
    ) -> Optional[List[List[Dict[str, Any]]]]:
        """
        用 embedding 余弦相似度预筛选潜在重复实体候选组。

        步骤：
        1. 生成所有实体的向量
        2. 计算两两余弦相似度矩阵
        3. similarity >= threshold 的实体对用 Union-Find 合并成候选组
        4. 候选组超过 max_group_size 时，取组内平均相似度最高的前 max_group_size 个实体

        Returns:
            候选组列表（每组为实体 dict 的列表，组大小 >= 2）；
            embedding 调用失败时返回 None（供调用方回退）。
        """
        import numpy as np

        if len(entities) < 2:
            return []

        embeddings = self._get_entity_embeddings(entities)
        if not embeddings:
            return None  # 明确区分"失败"和"无候选"
        if len(embeddings) != len(entities):
            logger.warning("[Embedding去重] embedding数量与实体数不匹配，跳过")
            return None

        # 归一化为单位向量，计算余弦相似度矩阵
        mat = np.array(embeddings, dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat /= norms
        sim_matrix = mat @ mat.T  # shape (n, n)

        n = len(entities)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int):
            parent[find(a)] = find(b)

        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= threshold:
                    union(i, j)

        # 按根节点分组
        groups: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        result: List[List[Dict[str, Any]]] = []
        for root, indices in groups.items():
            if len(indices) < 2:
                continue

            if len(indices) > max_group_size:
                # 取组内对其他成员平均相似度最高的前 max_group_size 个实体
                sub_sim = sim_matrix[np.ix_(indices, indices)]
                avg_sim = (sub_sim.sum(axis=1) - 1.0) / (len(indices) - 1)
                top_pos = np.argsort(avg_sim)[::-1][:max_group_size]
                indices = [indices[int(k)] for k in top_pos]
                logger.warning(
                    f"[Embedding去重] 候选组过大，已截取 top {max_group_size} 个实体"
                )

            result.append([entities[i] for i in indices])

        logger.info(
            f"[Embedding去重] threshold={threshold}，发现 {len(result)} 个候选组，"
            f"共 {sum(len(g) for g in result)} 个候选实体（原始 {n} 个）"
        )
        return result

    def _merge_entity_into(self, graph, canonical_uuid: str, dup_uuid: str):
        """
        将 dup 节点的所有边转移到 canonical 节点，然后 DETACH DELETE dup。
        自环（canonical <-> dup 之间的边）直接跳过。
        如果 canonical 的 summary 为空而 dup 有 summary，将其保留到 canonical 上。
        """
        # 保留 summary：canonical 为空时继承 dup 的 summary，避免信息丢失
        try:
            sr = graph.query(
                "MATCH (c:Entity {uuid: $can}), (d:Entity {uuid: $dup}) "
                "RETURN c.summary, d.summary",
                {"can": canonical_uuid, "dup": dup_uuid}
            )
            if sr.result_set:
                can_summary = (sr.result_set[0][0] or '').strip()
                dup_summary = (sr.result_set[0][1] or '').strip()
                if not can_summary and dup_summary:
                    graph.query(
                        "MATCH (c:Entity {uuid: $can}) SET c.summary = $summary",
                        {"can": canonical_uuid, "summary": dup_summary}
                    )
        except Exception as e:
            logger.warning(f"合并summary失败 ({dup_uuid} -> {canonical_uuid}): {e}")

        # 转移出边：dup -> t  变为  canonical -> t
        out_result = graph.query(
            "MATCH (d:Entity {uuid: $dup})-[r]->(t:Entity) "
            "RETURN r.name, r.fact, t.uuid",
            {"dup": dup_uuid}
        )
        for record in out_result.result_set:
            edge_name = record[0] or ""
            edge_fact = record[1] or ""
            target_uuid = record[2]
            if target_uuid == canonical_uuid:
                continue
            try:
                graph.query(
                    "MATCH (a:Entity {uuid: $a}), (t:Entity {uuid: $t}) "
                    "CREATE (a)-[r:RELATES_TO]->(t) "
                    "SET r.name = $name, r.fact = $fact, r.uuid = $ruuid",
                    {
                        "a": canonical_uuid, "t": target_uuid,
                        "name": edge_name, "fact": edge_fact,
                        "ruuid": str(uuid.uuid4())
                    }
                )
            except Exception as e:
                logger.warning(f"转移出边失败 ({dup_uuid}->{target_uuid}): {e}")

        # 转移入边：s -> dup  变为  s -> canonical
        in_result = graph.query(
            "MATCH (s:Entity)-[r]->(d:Entity {uuid: $dup}) "
            "RETURN r.name, r.fact, s.uuid",
            {"dup": dup_uuid}
        )
        for record in in_result.result_set:
            edge_name = record[0] or ""
            edge_fact = record[1] or ""
            source_uuid = record[2]
            if source_uuid == canonical_uuid:
                continue
            try:
                graph.query(
                    "MATCH (s:Entity {uuid: $s}), (a:Entity {uuid: $a}) "
                    "CREATE (s)-[r:RELATES_TO]->(a) "
                    "SET r.name = $name, r.fact = $fact, r.uuid = $ruuid",
                    {
                        "s": source_uuid, "a": canonical_uuid,
                        "name": edge_name, "fact": edge_fact,
                        "ruuid": str(uuid.uuid4())
                    }
                )
            except Exception as e:
                logger.warning(f"转移入边失败 ({source_uuid}->{dup_uuid}): {e}")

        # 删除重复节点（DETACH DELETE 同时删除其残余边）
        graph.query(
            "MATCH (d:Entity {uuid: $dup}) DETACH DELETE d",
            {"dup": dup_uuid}
        )

    def cleanup_empty_nodes(self, group_id: str) -> int:
        """
        删除没有 summary 且没有任何 Entity 间边（RELATES_TO）的孤立空节点。
        这类节点是 graphiti 提取时顺带产生的无效实体，对叙事引擎毫无价值。
        DETACH DELETE 会同时删除该节点的 episodic edge。

        Returns:
            删除的节点数量
        """
        from falkordb import FalkorDB

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(group_id)

        # 先查出数量
        count_result = graph.query(
            "MATCH (n:Entity) "
            "WHERE (n.summary IS NULL OR n.summary = '') "
            "AND NOT (n)-[:RELATES_TO]->(:Entity) "
            "AND NOT (:Entity)-[:RELATES_TO]->(n) "
            "RETURN count(n)"
        )
        count = count_result.result_set[0][0] if count_result.result_set else 0

        if count > 0:
            graph.query(
                "MATCH (n:Entity) "
                "WHERE (n.summary IS NULL OR n.summary = '') "
                "AND NOT (n)-[:RELATES_TO]->(:Entity) "
                "AND NOT (:Entity)-[:RELATES_TO]->(n) "
                "DETACH DELETE n"
            )
            logger.info(f"cleanup_empty_nodes: 删除 {count} 个空节点 (group_id={group_id})")

        return count

    def _get_current_nodes_brief(self, group_id: str) -> List[Dict[str, str]]:
        """
        查询图谱中已有的节点（name + summary 前120字），用于跨批次上下文注入。
        限制最多500个节点，避免对大图谱产生性能影响。
        """
        from falkordb import FalkorDB
        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(group_id)
        result = graph.query(
            "MATCH (n:Entity) WHERE n.name IS NOT NULL AND n.name <> '' "
            "RETURN n.name, n.summary LIMIT 500"
        )
        nodes = []
        for row in result.result_set:
            name = (row[0] or '').strip()
            summary = (row[1] or '').strip()[:120]
            if name:
                nodes.append({'name': name, 'summary': summary})
        return nodes

    def _inject_graph_node_context(
        self,
        chunks: List[str],
        known_nodes: List[Dict[str, str]],
        max_nodes_per_chunk: int = 5,
    ) -> List[str]:
        """
        将图谱中已有节点的信息注入到每个 chunk 的头部。
        只注入在 chunk 文本中出现的节点名称，避免信息噪声。

        帮助 Graphiti 将当前 chunk 中提到的实体解析到已有节点，
        而非重复创建新节点。
        """
        import re as _re
        if not known_nodes:
            return chunks
        # 按名称长度降序，保证长名先匹配（避免短名截断长名）
        sorted_nodes = sorted(known_nodes, key=lambda n: len(n['name']), reverse=True)
        names = [n['name'] for n in sorted_nodes]
        name_to_summary = {n['name']: n['summary'] for n in sorted_nodes}
        try:
            pattern = _re.compile('|'.join(_re.escape(nm) for nm in names))
        except Exception:
            return chunks

        result = []
        for chunk in chunks:
            found = list(dict.fromkeys(pattern.findall(chunk)))[:max_nodes_per_chunk]
            if found:
                lines = []
                for nm in found:
                    summary = name_to_summary.get(nm, '')
                    lines.append(f"  {nm}：{summary}" if summary else f"  {nm}")
                header = "[图谱中已有相关实体：\n" + "\n".join(lines) + "\n]\n"
                result.append(header + chunk)
            else:
                result.append(chunk)
        return result

    def _find_alias_groups_from_entity_db(
        self,
        entities: List[Dict[str, Any]],
        entity_database: Dict[str, Any],
    ) -> List[List[str]]:
        """
        利用 entity_database 中预提取的别名信息，在图谱节点中找出对应同一实体的 UUID 组。

        entity_database 由 TextEnricher 的 LLM 提取阶段生成，包含
        canonical_name → {aliases: [...]} 映射，可信度高。

        返回 [[uuid1, uuid2, ...], ...]，每组至少 2 个 UUID。
        """
        # name → uuid 反查表（图谱中的节点）
        name_to_uuid: Dict[str, str] = {e['name']: e['uuid'] for e in entities}
        valid_uuids: set = {e['uuid'] for e in entities}

        groups: List[List[str]] = []
        for canonical, entry in entity_database.items():
            aliases = entry.get('aliases', [])
            all_names = [canonical] + aliases
            matching_uuids = list(dict.fromkeys(
                name_to_uuid[n] for n in all_names if n in name_to_uuid
            ))
            # 过滤掉已不在图谱中的 uuid（可能被先前阶段删除）
            matching_uuids = [u for u in matching_uuids if u in valid_uuids]
            if len(matching_uuids) >= 2:
                groups.append(matching_uuids)

        return groups

    def delete_graph(self, group_id: str):
        """
        删除指定 group_id 的所有图谱数据。
        Graphiti 用 group_id 作为 FalkorDB 的 graph 名称，直接删除整个 graph。
        """
        from falkordb import FalkorDB

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(group_id)

        # 删除整个 graph
        graph.delete()
