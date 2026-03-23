"""
叙事角色档案生成器
为知识图谱中的实体生成叙事角色档案（替代 oasis_profile_generator 用于叙事模式）
"""

import json
import time
import concurrent.futures
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Callable

from zep_cloud.client import Zep

from ..config import Config
from ..utils.llm_client import LLMClient, get_client_for_prompt
from ..utils.logger import get_logger
from .prompt_config import get_system, get_template, safe_render, get_llm_params

logger = get_logger('agars.narrative_profile')


@dataclass
class NarrativeCharacterProfile:
    """叙事角色档案"""
    entity_uuid: str
    entity_type: str
    name: str
    is_player: bool = False
    profession: str = ""
    personality: str = ""
    goals: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    backstory: str = ""
    current_location: str = ""
    relationships: List[Dict[str, str]] = field(default_factory=list)
    speech_style: str = ""
    temperament: str = ""
    raw_graph_context: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NarrativeCharacterProfile':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class NarrativeProfileGenerator:
    """叙事角色档案生成器"""

    def __init__(
        self,
        graph_id: str,
        zep_api_key: Optional[str] = None,
        llm_client: Optional[LLMClient] = None
    ):
        self.graph_id = graph_id
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self._zep_edges_cache = None  # 全图边缓存，避免每个实体重复拉取
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Zep 客户端初始化失败（将跳过 Zep 搜索）: {e}")
        self.llm = llm_client or LLMClient()

    def _get_zep_all_edges(self):
        """懒加载并缓存图谱全部边（整个 generate 流程只拉取一次）"""
        if self._zep_edges_cache is None:
            try:
                raw = self.zep_client.graph.edge.get_by_graph_id(graph_id=self.graph_id)
                self._zep_edges_cache = raw or []
                logger.debug(f"Zep全图边缓存已建立: {len(self._zep_edges_cache)} 条边")
            except Exception as e:
                logger.warning(f"获取Zep全图边失败，跳过直连边检索: {e}")
                self._zep_edges_cache = []
        return self._zep_edges_cache

    def _search_zep_for_entity(self, entity_name: str) -> Dict[str, Any]:
        """
        使用 Zep 混合搜索为实体获取上下文信息
        复用 OasisProfileGenerator._search_zep_for_entity 的模式
        """
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}

        def search_edges():
            max_retries = 3
            delay = 2.0
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=f"关于{entity_name}的所有信息、活动、事件、关系和背景",
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"边搜索失败，重试... ({attempt + 1}): {e}")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.warning(f"边搜索最终失败: {e}")
                        return None

        def search_nodes():
            max_retries = 3
            delay = 2.0
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=f"{entity_name} 的特征、能力、性格和身份",
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"节点搜索失败，重试... ({attempt + 1}): {e}")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.warning(f"节点搜索最终失败: {e}")
                        return None

        # 并行搜索
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            edge_future = executor.submit(search_edges)
            node_future = executor.submit(search_nodes)

            edge_result = edge_future.result(timeout=30)
            node_result = node_future.result(timeout=30)

        # 只保留明确提及目标实体名称的事实（语义搜索过滤）
        entity_name_lower = entity_name.lower()
        facts = set()
        if edge_result and edge_result.edges:
            for edge in edge_result.edges:
                if edge.fact and entity_name_lower in edge.fact.lower():
                    facts.add(edge.fact)

        # 只保留目标实体本身节点的摘要；同时提取匹配节点 UUID 用于结构性边检索
        summaries = set()
        entity_node_uuid = None
        if node_result and node_result.nodes:
            for node in node_result.nodes:
                node_name = getattr(node, 'name', '') or ''
                if node_name.lower() == entity_name_lower:
                    if node.summary:
                        summaries.add(node.summary)
                    if entity_node_uuid is None:
                        entity_node_uuid = getattr(node, 'uuid', None)

        # 补充直连边（结构性检索）：source_node_uuid 或 target_node_uuid == entity_node_uuid
        # UUID 匹配保证与该实体直接相关，无需名称过滤
        if entity_node_uuid:
            for raw_edge in self._get_zep_all_edges():
                src = getattr(raw_edge, 'source_node_uuid', '') or ''
                tgt = getattr(raw_edge, 'target_node_uuid', '') or ''
                if src == entity_node_uuid or tgt == entity_node_uuid:
                    fact = getattr(raw_edge, 'fact', '') or ''
                    if fact:
                        facts.add(fact)

        context_parts = []
        if facts:
            context_parts.append("【相关事实】\n" + "\n".join(f"- {f}" for f in facts))
        if summaries:
            context_parts.append("【相关实体摘要】\n" + "\n".join(f"- {s}" for s in summaries))

        return {
            "facts": list(facts),
            "node_summaries": list(summaries),
            "context": "\n\n".join(context_parts)
        }

    @staticmethod
    def _extract_relationships_from_edges(
        related_edges: List[Dict[str, Any]],
        related_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """从图谱边直接提取结构化关系，每条标记 source=graph"""
        node_map = {n.get("uuid", ""): n.get("name", "") for n in related_nodes}
        relationships = []
        seen = set()

        for edge in related_edges:
            # 确定对方名字
            other_uuid = edge.get("target_node_uuid") or edge.get("source_node_uuid") or edge.get("other_uuid", "")
            other_name = edge.get("other_name") or node_map.get(other_uuid, "")
            if not other_name:
                continue

            edge_name = edge.get("edge_name", "")
            fact = edge.get("fact", "")
            relation = fact if fact else edge_name

            dedup_key = (other_name, relation)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            relationships.append({
                "name": other_name,
                "relation": relation,
                "source": "graph",
            })

        return relationships

    def generate_profile_from_entity(
        self,
        entity: Dict[str, Any],
        is_player: bool = False,
        valid_locations: Optional[List[str]] = None,
        entity_database: Optional[Dict[str, Any]] = None,
    ) -> NarrativeCharacterProfile:
        """
        从图谱实体生成叙事角色档案

        Args:
            entity: 实体数据 (uuid, name, labels, summary, related_edges 等)
            is_player: 是否为玩家角色
        """
        entity_uuid = entity.get("uuid", "")
        entity_name = entity.get("name", "未知")
        labels = entity.get("labels", [])
        entity_type = next((l for l in labels if l not in ["Entity", "Node"]), "角色")
        summary = entity.get("summary", "")
        related_edges = entity.get("related_edges", [])
        related_nodes = entity.get("related_nodes", [])

        # 搜索 Zep 获取更丰富的上下文
        zep_context = self._search_zep_for_entity(entity_name)

        # 构建上下文信息
        context_parts = []

        # 【最高优先级】预提取实体数据库（方案C）
        if entity_database:
            from .text_enricher import TextEnricher
            db_entry = TextEnricher.lookup_entity(entity_database, entity_name)
            if db_entry:
                db_parts = []
                if db_entry.get('description'):
                    db_parts.append(f"【预提取描述】{db_entry['description']}")
                if db_entry.get('key_facts'):
                    facts_str = '\n'.join(f"- {f}" for f in db_entry['key_facts'])
                    db_parts.append(f"【预提取事实】\n{facts_str}")
                if db_entry.get('relationships'):
                    rels_str = '\n'.join(
                        f"- {r['target']}：{r['relation']}"
                        for r in db_entry['relationships']
                    )
                    db_parts.append(f"【预提取关系】\n{rels_str}")
                if db_entry.get('aliases'):
                    db_parts.append(f"【别名/称谓】{'、'.join(db_entry['aliases'])}")
                if db_parts:
                    context_parts.append('\n\n'.join(db_parts))

        if summary:
            context_parts.append(f"【实体摘要】{summary}")
        if related_edges:
            edge_texts = []
            for e in related_edges[:15]:
                if e.get("fact"):
                    edge_texts.append(f"- {e['fact']}")
            if edge_texts:
                context_parts.append("【关系事实】\n" + "\n".join(edge_texts))
        if related_nodes:
            node_texts = [f"- {n.get('name', '?')} ({n.get('type', '?')})" for n in related_nodes[:10]]
            context_parts.append("【相关实体】\n" + "\n".join(node_texts))
        if zep_context.get("context"):
            context_parts.append(zep_context["context"])

        full_context = "\n\n".join(context_parts) or "无额外上下文信息"

        # 使用 LLM 生成角色档案
        is_player_status = "是（第一人称视角角色）" if is_player else "否（NPC）"
        if valid_locations:
            locs_str = "\n".join(f"- {loc}" for loc in valid_locations)
        else:
            locs_str = "（未指定，请从上下文推断）"
        prompt = safe_render(get_template('narrative_profile'), {
            'entity_name': entity_name,
            'entity_type': entity_type,
            'is_player_status': is_player_status,
            'valid_locations': locs_str,
            'full_context': full_context,
        })

        try:
            _p = get_llm_params('narrative_profile')
            result = get_client_for_prompt('narrative_profile').chat_json(
                messages=[
                    {"role": "system", "content": get_system('narrative_profile')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens']
            )

            # Normalize current_location against valid_locations
            raw_loc = result.get("current_location", "")
            if valid_locations and raw_loc:
                raw_loc = raw_loc.strip()
                if raw_loc not in valid_locations:
                    # 1. 子串匹配
                    matched = next(
                        (loc for loc in valid_locations if loc in raw_loc or raw_loc in loc),
                        None
                    )
                    if matched is None:
                        # 2. 字符重叠相似度（避免全部 fallback 到第一个地点，问题C）
                        def _char_overlap(a: str, b: str) -> float:
                            if not a or not b:
                                return 0.0
                            common = sum(1 for c in a if c in b)
                            return common / max(len(a), len(b))
                        best = max(valid_locations, key=lambda loc: _char_overlap(raw_loc, loc))
                        matched = best if _char_overlap(raw_loc, best) > 0 else valid_locations[0]
                    logger.debug(f"位置修正: {entity_name} '{raw_loc}' → '{matched}'")
                    raw_loc = matched
            elif valid_locations and not raw_loc:
                raw_loc = valid_locations[0]
            normalized_location = raw_loc

            # 合并图谱关系与LLM推断关系（图谱优先，去重）
            graph_rels = self._extract_relationships_from_edges(related_edges, related_nodes)
            llm_rels = result.get("relationships", [])

            # 用图谱关系名称去重LLM关系
            graph_names = {r["name"] for r in graph_rels}
            merged_rels = list(graph_rels)
            for lr in llm_rels:
                if lr.get("name") not in graph_names:
                    lr["source"] = "llm"
                    merged_rels.append(lr)

            profile = NarrativeCharacterProfile(
                entity_uuid=entity_uuid,
                entity_type=entity_type,
                name=entity_name,
                is_player=is_player,
                # profession 优先用 LLM 输出，否则 fallback 到 entity_type（问题A）
                profession=result.get("profession", "") or entity_type,
                personality=result.get("personality", ""),
                goals=result.get("goals", []),
                abilities=result.get("abilities", []),
                backstory=result.get("backstory", ""),
                current_location=normalized_location or "未知",
                relationships=merged_rels,
                speech_style=result.get("speech_style", ""),
                temperament=result.get("temperament", ""),
                raw_graph_context=full_context[:2000]
            )

            logger.info(f"角色档案生成成功: {entity_name} (is_player={is_player}), "
                         f"关系: {len(graph_rels)} 图谱 + {len(merged_rels) - len(graph_rels)} LLM")
            return profile

        except Exception as e:
            logger.error(f"角色档案生成失败 ({entity_name}): {e}")
            # 返回最小化的档案
            return NarrativeCharacterProfile(
                entity_uuid=entity_uuid,
                entity_type=entity_type,
                name=entity_name,
                is_player=is_player,
                personality="（档案生成失败，使用默认性格）",
                backstory=summary or "（无背景信息）",
                raw_graph_context=full_context[:2000]
            )

    def generate_profiles_batch(
        self,
        entities: List[Dict[str, Any]],
        player_uuid: str,
        max_workers: int = 3,
        progress_callback: Optional[Callable] = None,
        valid_locations: Optional[List[str]] = None,
        entity_database: Optional[Dict[str, Any]] = None,
    ) -> List[NarrativeCharacterProfile]:
        """
        批量生成角色档案

        Args:
            entities: 实体列表
            player_uuid: 玩家角色的 UUID
            max_workers: 最大并行数
            progress_callback: 进度回调 (message, progress_percent)
        """
        profiles = []
        total = len(entities)

        if total == 0:
            return profiles

        def generate_one(idx_entity):
            idx, entity = idx_entity
            is_player = entity.get("uuid", "") == player_uuid
            return self.generate_profile_from_entity(
                entity,
                is_player=is_player,
                valid_locations=valid_locations,
                entity_database=entity_database,
            )

        completed = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(generate_one, (i, e)): i
                for i, e in enumerate(entities)
            }

            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    profile = future.result(timeout=60)
                    profiles.append(profile)
                except Exception as e:
                    entity = entities[idx]
                    logger.error(f"批量生成失败 ({entity.get('name', '?')}): {e}")
                    # 使用最小化档案
                    profiles.append(NarrativeCharacterProfile(
                        entity_uuid=entity.get("uuid", ""),
                        entity_type="角色",
                        name=entity.get("name", "未知"),
                        is_player=entity.get("uuid", "") == player_uuid
                    ))

                completed += 1
                if progress_callback:
                    progress_callback(
                        f"已生成 {completed}/{total} 个角色档案",
                        completed / total
                    )

        # 按原始顺序排序（玩家角色排第一）
        profiles.sort(key=lambda p: (not p.is_player, p.name))

        logger.info(f"批量角色档案生成完成: {len(profiles)}/{total}")
        return profiles

    def assign_initial_locations(
        self,
        profiles: List['NarrativeCharacterProfile'],
        initial_scene: str,
        valid_locations: List[str],
        world_map: Optional[Dict[str, Any]] = None,
        prior_summary: str = "",
        entity_database: Optional[Dict[str, Any]] = None,
        opening_text: str = "",
    ) -> Dict[str, str]:
        """
        整体布局：一次 LLM 调用，为全体角色分配初始位置。

        Args:
            profiles: 所有角色档案（已生成，含 current_location 作为参考建议）
            initial_scene: 初始场景描述
            valid_locations: 可用地点列表
            world_map: 世界地图（可选，含地点描述和邻接信息）
            prior_summary: 前文摘要（续写模式下角色最新位置的权威来源）
            entity_database: 预提取实体数据库（key_facts 可能含位置线索）
            opening_text: 用户提供的开篇正文（最高优先级，明确描述了角色当前位置）

        Returns:
            dict: {entity_uuid: location_name}
        """
        if not valid_locations:
            logger.warning("assign_initial_locations: 无可用地点，跳过整体布局")
            return {}

        # 构建地点描述
        loc_lines = []
        for loc in valid_locations:
            if world_map and loc in world_map:
                adj = world_map[loc].get("adjacent", [])
                desc = world_map[loc].get("description", "")
                adj_str = f"（邻接：{'、'.join(adj)}）" if adj else ""
                desc_str = f"：{desc}" if desc else ""
                loc_lines.append(f"- {loc}{desc_str}{adj_str}")
            else:
                loc_lines.append(f"- {loc}")
        locations_info = "\n".join(loc_lines)

        # 构建角色信息（附带 profile 推理的位置建议 + entity_database 位置线索）
        char_lines = []
        for p in profiles:
            role_tag = "【玩家角色】" if p.is_player else ""
            goals_str = "；".join(p.goals[:2]) if p.goals else ""
            rels = []
            for r in p.relationships[:4]:
                name = r.get("name", "")
                if not name:
                    continue
                relation = r.get("relation", "").strip()
                rels.append(f"{name}（{relation}）" if relation else name)
            rels_str = f"，关联：{'、'.join(rels)}" if rels else ""

            # profile 已推理的位置建议
            suggested_loc = p.current_location or ""
            loc_hint = f"，建议位置：{suggested_loc}" if suggested_loc and suggested_loc != "未知" else ""

            # entity_database 中的位置线索
            db_loc_hints = ""
            if entity_database:
                from .text_enricher import TextEnricher
                entry = TextEnricher.lookup_entity(entity_database, p.name)
                if entry:
                    # 从 key_facts 中筛选可能包含位置信息的条目
                    loc_keywords = ('位于', '住在', '居住', '驻守', '目前在', '现在在',
                                    '来到', '抵达', '所在', '定居', '常驻', '出没')
                    loc_facts = [f for f in entry.get('key_facts', [])
                                 if f and any(kw in f for kw in loc_keywords)]
                    if loc_facts:
                        db_loc_hints = f"，原文位置线索：{'；'.join(loc_facts[:3])}"

            line = (
                f"- {p.name}{role_tag}（职业：{p.profession or p.entity_type}）"
                f"：{p.personality[:40] if p.personality else '无性格描述'}"
                f"{('；目标：' + goals_str) if goals_str else ''}"
                f"{rels_str}{loc_hint}{db_loc_hints}"
            )
            char_lines.append(line)
        characters_info = "\n".join(char_lines)

        prompt = safe_render(get_template('narrative_location_assignment'), {
            'initial_scene': initial_scene or "（无场景描述）",
            'prior_summary': prior_summary or "",
            'opening_text': opening_text[:2000] if opening_text else "",
            'locations_info': locations_info,
            'characters_info': characters_info,
        })

        try:
            _p = get_llm_params('narrative_location_assignment')
            raw = get_client_for_prompt('narrative_location_assignment').chat_json(
                messages=[
                    {"role": "system", "content": get_system('narrative_location_assignment')},
                    {"role": "user", "content": prompt}
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens'],
            )
        except Exception as e:
            logger.error(f"整体位置分配 LLM 调用失败: {e}")
            return {}

        # raw 的格式为 {"角色名": "地点名", ...}
        # 建立 name→uuid 映射，并做位置规范化
        name_to_uuid = {p.name: p.entity_uuid for p in profiles}
        result: Dict[str, str] = {}

        def _normalize(raw_loc: str) -> str:
            raw_loc = raw_loc.strip()
            if raw_loc in valid_locations:
                return raw_loc
            matched = next(
                (loc for loc in valid_locations if loc in raw_loc or raw_loc in loc),
                None
            )
            if matched is None:
                def _overlap(a, b):
                    if not a or not b:
                        return 0.0
                    return sum(1 for c in a if c in b) / max(len(a), len(b))
                best = max(valid_locations, key=lambda loc: _overlap(raw_loc, loc))
                matched = best if _overlap(raw_loc, best) > 0 else valid_locations[0]
            return matched

        for name, loc in raw.items():
            uuid = name_to_uuid.get(name)
            if uuid is None:
                # 尝试模糊匹配角色名
                uuid = next(
                    (p.entity_uuid for p in profiles if p.name in name or name in p.name),
                    None
                )
            if uuid is None:
                logger.debug(f"整体布局：未能匹配角色名 '{name}'，跳过")
                continue
            normalized = _normalize(str(loc))
            result[uuid] = normalized
            logger.debug(f"整体布局: {name} → {normalized}")

        logger.info(f"整体位置分配完成: {len(result)}/{len(profiles)} 个角色已分配")
        return result
