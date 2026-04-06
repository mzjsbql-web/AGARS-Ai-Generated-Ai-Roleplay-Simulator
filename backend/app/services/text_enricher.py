"""
文本实体预提取器（TextEnricher）

在图谱构建前对原始文本做分段结构化提取，结果用于三个用途：
  A: 为 graphiti chunk 注入实体上下文头，改善跨块实体解析
  B: 图谱构建后补全空 summary，直接写回 FalkorDB
  C: profile 生成时的第一优先级信息源

兼容任意文档类型（小说、设定集、剧本、历史文献等），不依赖文档结构假设。
"""

import re
import concurrent.futures
from typing import Any, Callable, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient, get_client_for_prompt
from ..utils.logger import get_logger
from .prompt_config import get_llm_params, get_system, get_template, safe_render

logger = get_logger('agars.text_enricher')

# 每段目标字符数（超大文件也可处理：1M字 ÷ 10000 ≈ 100段）
SECTION_TARGET_SIZE = 10000
# 并行提取的最大线程数
MAX_SECTION_WORKERS = 5
# FalkorDB summary 写回的最大长度
# 500→800：给关键事实更多空间，同步到 Zep 后也能提供更丰富的搜索上下文
MAX_SUMMARY_WRITE = 800


class TextEnricher:
    """文本分段实体预提取器，支持任意文档类型"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    # ──────────────────────────────────────────────────────────────
    # 1. 分段：按结构边界切分，不依赖文档类型
    # ──────────────────────────────────────────────────────────────

    def split_into_sections(
        self,
        text: str,
        target_size: int = SECTION_TARGET_SIZE,
    ) -> List[str]:
        """
        将文本按章节标题或段落边界切成约 target_size 字的段落。
        无需预知文档类型：先尝试识别章节标题，找不到则按段落切分。
        """
        chapter_pattern = re.compile(
            r'(?m)^(?:'
            r'第[零一二三四五六七八九十百千万\d]+[章节卷幕回篇部]'   # 中文章节
            r'|Chapter\s+\d+'                                        # 英文 Chapter
            r'|CHAPTER\s+\d+'
            r'|#{1,3}\s+\S'                                          # Markdown 标题
            r'|【[^】]{1,20}】'                                       # 【标题】格式
            r'|\d+\.\s+\S'                                           # 1. 标题
            r')'
        )
        boundaries = [0] + [m.start() for m in chapter_pattern.finditer(text)] + [len(text)]
        raw_sections = [
            text[boundaries[i]:boundaries[i + 1]].strip()
            for i in range(len(boundaries) - 1)
            if text[boundaries[i]:boundaries[i + 1]].strip()
        ]

        # 没识别到章节结构，降级为段落切分
        if len(raw_sections) <= 1:
            raw_sections = self._split_by_paragraphs(text, target_size)

        return self._normalize_sections(raw_sections, target_size)

    def _split_by_paragraphs(self, text: str, target_size: int) -> List[str]:
        """按双换行切段落，再合并到 target_size"""
        paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
        sections: List[str] = []
        buf: List[str] = []
        buf_len = 0
        for p in paragraphs:
            if buf_len + len(p) > target_size and buf:
                sections.append('\n\n'.join(buf))
                buf, buf_len = [], 0
            buf.append(p)
            buf_len += len(p)
        if buf:
            sections.append('\n\n'.join(buf))
        return sections or [text]

    def _normalize_sections(self, sections: List[str], target_size: int) -> List[str]:
        """把过大段落再切分，把过小段落合并"""
        expanded: List[str] = []
        for sec in sections:
            if len(sec) > target_size * 2:
                expanded.extend(self._split_by_paragraphs(sec, target_size))
            else:
                expanded.append(sec)

        merged: List[str] = []
        buf: List[str] = []
        buf_len = 0
        for sec in expanded:
            if buf_len + len(sec) <= target_size or not buf:
                buf.append(sec)
                buf_len += len(sec)
            else:
                merged.append('\n\n'.join(buf))
                buf, buf_len = [sec], len(sec)
        if buf:
            merged.append('\n\n'.join(buf))
        return merged

    # ──────────────────────────────────────────────────────────────
    # 2. 单段提取（两步 LLM 调用）
    # ──────────────────────────────────────────────────────────────

    def _extract_entities_one_section(self, section: str, section_idx: int) -> List[Dict[str, Any]]:
        """Step 1: 对单个段落调用 LLM 只提取实体（不含关系），降低认知负担"""
        prompt = safe_render(get_template('section_entity_extraction'), {
            'section_text': section[:12000],
        })
        try:
            _p = get_llm_params('section_entity_extraction')
            result = get_client_for_prompt('section_entity_extraction').chat_json(
                messages=[
                    {'role': 'system', 'content': get_system('section_entity_extraction')},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens'],
            )
            entities = result.get('entities', [])
            if not isinstance(entities, list):
                entities = []
            logger.debug(f"段落 {section_idx}: 提取到 {len(entities)} 个实体")
            return entities
        except Exception as e:
            logger.warning(f"段落 {section_idx} 实体提取失败: {e}")
            return []

    def _extract_relations_one_section(
        self, section: str, section_idx: int, entity_names: List[str],
    ) -> List[Dict[str, Any]]:
        """Step 2: 给定全局实体列表，从段落中提取关系"""
        entity_list_str = '\n'.join(f'- {name}' for name in entity_names)
        prompt = safe_render(get_template('section_relation_extraction'), {
            'section_text': section[:12000],
            'entity_list': entity_list_str,
        })
        try:
            _p = get_llm_params('section_relation_extraction')
            result = get_client_for_prompt('section_relation_extraction').chat_json(
                messages=[
                    {'role': 'system', 'content': get_system('section_relation_extraction')},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens'],
            )
            relationships = result.get('relationships', [])
            if not isinstance(relationships, list):
                relationships = []
            logger.debug(f"段落 {section_idx}: 提取到 {len(relationships)} 条关系")
            return relationships
        except Exception as e:
            logger.warning(f"段落 {section_idx} 关系提取失败: {e}")
            return []

    # 保留旧接口供向后兼容（如有外部调用）
    def _extract_one_section(self, section: str, section_idx: int) -> List[Dict[str, Any]]:
        """旧版一体式提取（已弃用，保留向后兼容）"""
        prompt = safe_render(get_template('section_extraction'), {
            'section_text': section[:12000],
        })
        try:
            _p = get_llm_params('section_extraction')
            result = get_client_for_prompt('section_extraction').chat_json(
                messages=[
                    {'role': 'system', 'content': get_system('section_extraction')},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=_p['temperature'],
                max_tokens=_p['max_tokens'],
            )
            entities = result.get('entities', [])
            if not isinstance(entities, list):
                entities = []
            return entities
        except Exception as e:
            logger.warning(f"段落 {section_idx} 实体提取失败: {e}")
            return []

    # ──────────────────────────────────────────────────────────────
    # 3. 全文两步提取
    # ──────────────────────────────────────────────────────────────

    def extract_all_sections(
        self,
        text: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        target_size: int = SECTION_TARGET_SIZE,
    ) -> Dict[str, Any]:
        """
        两步提取：先并行提取实体，合并后再并行提取关系。

        Step 1（并行）：每段独立提取实体（name, type, aliases, description, key_facts）
        Step 2（并行）：基于全局实体列表，每段独立提取关系

        分步提取降低了单次 LLM 调用的认知负担，使实体和关系的提取都更准确。
        关系提取时拥有全局实体列表作为上下文，能更好地识别跨段引用。

        entity_database 格式：
        {
          canonical_name: {
            "type": str,
            "aliases": [str, ...],
            "description": str,
            "key_facts": [str, ...],
            "relationships": [{"target": str, "relation": str}, ...]
          },
          ...
        }
        """
        sections = self.split_into_sections(text, target_size)
        total = len(sections)
        logger.info(f"文本分为 {total} 个段落，开始两步提取...")

        # ── Step 1: 并行提取实体 ────────────────────────────────
        if progress_callback:
            progress_callback(f"第一步：提取实体（共 {total} 段）...", 0.0)

        section_entities: List[List[Dict]] = [[] for _ in range(total)]
        completed = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SECTION_WORKERS) as executor:
            future_to_idx = {
                executor.submit(self._extract_entities_one_section, sec, i): i
                for i, sec in enumerate(sections)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    section_entities[idx] = future.result()
                except Exception as e:
                    logger.warning(f"段落 {idx} 实体提取异常: {e}")
                completed += 1
                if progress_callback:
                    progress_callback(
                        f"实体提取: {completed}/{total}",
                        completed / total * 0.5,  # 前 50% 进度给实体提取
                    )

        # 合并实体（此时无 relationships）
        entity_database = self._merge_entity_lists(section_entities)
        logger.info(f"Step 1 完成: {len(entity_database)} 个实体")

        # ── Step 2: 并行提取关系（携带全局实体列表） ──────────────
        if progress_callback:
            progress_callback(f"第二步：提取关系（{len(entity_database)} 个已知实体）...", 0.5)

        # 构建全局实体名称列表（含别名），供关系提取 prompt 使用
        all_entity_names = self.get_all_names(entity_database)

        section_relations: List[List[Dict]] = [[] for _ in range(total)]
        completed = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SECTION_WORKERS) as executor:
            future_to_idx = {
                executor.submit(
                    self._extract_relations_one_section, sec, i, all_entity_names
                ): i
                for i, sec in enumerate(sections)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    section_relations[idx] = future.result()
                except Exception as e:
                    logger.warning(f"段落 {idx} 关系提取异常: {e}")
                completed += 1
                if progress_callback:
                    progress_callback(
                        f"关系提取: {completed}/{total}",
                        0.5 + completed / total * 0.5,  # 后 50% 进度给关系提取
                    )

        # 将关系合并到 entity_database
        self._merge_relations_into_database(entity_database, section_relations)
        total_rels = sum(len(e.get('relationships', [])) for e in entity_database.values())
        logger.info(f"Step 2 完成: {total_rels} 条关系")
        logger.info(f"实体数据库构建完成: {len(entity_database)} 个实体, {total_rels} 条关系")
        return entity_database

    # ──────────────────────────────────────────────────────────────
    # 4. 跨段合并
    # ──────────────────────────────────────────────────────────────

    def _merge_entity_lists(
        self,
        all_section_entities: List[List[Dict]],
    ) -> Dict[str, Any]:
        """
        把多个段落的 entities 列表合并成一个 entity_database。
        相同实体通过 name/aliases 交叉匹配识别，合并时取并集。
        """
        db: Dict[str, Dict[str, Any]] = {}        # canonical_name → entry
        alias_index: Dict[str, str] = {}           # 任意称谓 → canonical_name

        for section_entities in all_section_entities:
            for ent in section_entities:
                name = (ent.get('name') or '').strip()
                if not name:
                    continue
                aliases = [a.strip() for a in ent.get('aliases', []) if isinstance(a, str) and a.strip()]
                all_names = [name] + aliases

                # 找到已有条目（通过任意称谓匹配）
                canonical: Optional[str] = None
                for n in all_names:
                    if n in alias_index:
                        canonical = alias_index[n]
                        break

                if canonical is None:
                    # 新实体：以首次出现的 name 作为 canonical key
                    canonical = name
                    db[canonical] = {
                        'type': ent.get('type', '其他'),
                        'aliases': [],
                        'description': '',
                        'key_facts': [],
                        'relationships': [],
                    }

                entry = db[canonical]
                # 注册所有称谓到 alias_index
                for n in all_names:
                    alias_index[n] = canonical
                    if n != canonical and n not in entry['aliases']:
                        entry['aliases'].append(n)

                # 合并 type（非"其他"时才覆盖）
                new_type = (ent.get('type') or '').strip()
                if new_type and new_type != '其他' and entry['type'] == '其他':
                    entry['type'] = new_type

                # 合并 description：保留最新非空描述（后面段落反映最新情节状态）
                new_desc = (ent.get('description') or '').strip()
                if new_desc:
                    entry['description'] = new_desc

                # 合并 key_facts（去重）
                existing_facts: set = set(entry['key_facts'])
                for f in ent.get('key_facts', []):
                    f = (f or '').strip()
                    if f and f not in existing_facts:
                        entry['key_facts'].append(f)
                        existing_facts.add(f)

                # 合并 relationships（按 target+relation 去重）
                existing_rels: set = {
                    (r['target'], r['relation']) for r in entry['relationships']
                }
                for r in ent.get('relationships', []):
                    if not isinstance(r, dict):
                        continue
                    target = (r.get('target') or '').strip()
                    relation = (r.get('relation') or '').strip()
                    if target and relation and (target, relation) not in existing_rels:
                        entry['relationships'].append({'target': target, 'relation': relation})
                        existing_rels.add((target, relation))

        return db

    def _merge_relations_into_database(
        self,
        entity_database: Dict[str, Any],
        all_section_relations: List[List[Dict]],
    ) -> None:
        """
        将 Step 2 提取的关系合并到已有的 entity_database 中。

        关系的 source/target 通过别名反查表映射到 canonical name，
        按 (source_canonical, target_canonical, relation) 去重。
        """
        # 构建别名反查表
        alias_to_canonical: Dict[str, str] = {}
        for canonical, entry in entity_database.items():
            alias_to_canonical[canonical] = canonical
            for alias in entry.get('aliases', []):
                alias_to_canonical[alias] = canonical

        for section_rels in all_section_relations:
            for rel in section_rels:
                if not isinstance(rel, dict):
                    continue
                source = (rel.get('source') or '').strip()
                target = (rel.get('target') or '').strip()
                relation = (rel.get('relation') or '').strip()
                if not source or not target or not relation:
                    continue

                # 将 source 映射到 canonical name
                source_canonical = alias_to_canonical.get(source)
                if not source_canonical:
                    continue
                target_canonical = alias_to_canonical.get(target, target)

                entry = entity_database.get(source_canonical)
                if not entry:
                    continue

                # 按 (target, relation) 去重
                existing_rels = {
                    (r['target'], r['relation']) for r in entry['relationships']
                }
                if (target_canonical, relation) not in existing_rels:
                    entry['relationships'].append({
                        'target': target_canonical,
                        'relation': relation,
                    })

    # ──────────────────────────────────────────────────────────────
    # 5. B：补全 FalkorDB 空 summary
    # ──────────────────────────────────────────────────────────────

    def enrich_graph_summaries(
        self,
        group_id: str,
        entity_database: Dict[str, Any],
    ) -> int:
        """
        用 entity_database 的预提取信息**仅填充空 summary 节点**。

        Graphiti 会在逐 chunk 处理时增量构建 summary（每次把已有 summary + 新 chunk
        一起交给 LLM 生成更新版本），其质量优于 entity_database 从 10K 段落一次性
        提取的描述。因此只在 Graphiti 未能生成 summary 时才用 entity_database 兜底。

        返回更新的节点数量。
        """
        if not entity_database:
            return 0

        from falkordb import FalkorDB
        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(group_id)

        # 只查空 summary 的节点
        result = graph.query(
            "MATCH (n:Entity) WHERE n.name IS NOT NULL AND n.name <> '' "
            "AND (n.summary IS NULL OR n.summary = '') "
            "RETURN n.uuid, n.name"
        )
        empty_nodes = [
            (row[0], row[1])
            for row in result.result_set
            if row[0] and row[1]
        ]
        if not empty_nodes:
            logger.info("enrich_graph_summaries: 无空 summary 节点，跳过")
            return 0

        # 构建别名反查表
        alias_to_canonical: Dict[str, str] = {}
        for canonical, entry in entity_database.items():
            alias_to_canonical[canonical] = canonical
            for alias in entry.get('aliases', []):
                alias_to_canonical[alias] = canonical

        enriched = 0
        for node_uuid, node_name in empty_nodes:
            canonical = alias_to_canonical.get(node_name)
            if not canonical:
                continue
            entry = entity_database.get(canonical, {})
            db_summary = self._build_summary_from_entry(entry)
            if not db_summary:
                continue

            try:
                graph.query(
                    "MATCH (n:Entity {uuid: $uuid}) SET n.summary = $summary",
                    {'uuid': node_uuid, 'summary': db_summary[:MAX_SUMMARY_WRITE]},
                )
                enriched += 1
            except Exception as e:
                logger.warning(f"写回 summary 失败 ({node_name}): {e}")

        logger.info(f"enrich_graph_summaries: 填充 {enriched}/{len(empty_nodes)} 个空 summary 节点")
        return enriched

    def _build_summary_from_entry(self, entry: Dict[str, Any]) -> str:
        """把 entity_database 条目的 description + key_facts 拼成 summary 字符串。
        不再硬编码条数限制，由 MAX_SUMMARY_WRITE 自然截断，尽量填满可用空间。
        key_facts 倒序拼接，优先保留最新情节的事实。
        """
        parts: List[str] = []
        if entry.get('description'):
            parts.append(entry['description'].strip())
        if entry.get('key_facts'):
            # 倒序：最新的事实先拼入，截断时丢的是最早的
            reversed_facts = list(reversed(entry['key_facts']))
            parts.append('；'.join(f.strip() for f in reversed_facts if f))
        return '。'.join(parts)[:MAX_SUMMARY_WRITE]

    # ──────────────────────────────────────────────────────────────
    # 6. 补建缺失的图谱边
    # ──────────────────────────────────────────────────────────────

    def supplement_missing_edges(
        self,
        group_id: str,
        entity_database: Dict[str, Any],
    ) -> int:
        """
        用 entity_database 的 relationships 补建图谱中缺失的边。

        Graphiti 的 node extraction 和 edge extraction 是两次独立 LLM 调用，
        有时关系信息只出现在 summary 里而没有生成 edge。
        entity_database 的 relationships 是从原文 10K 段落提取的结构化关系，
        可以用来补回缺失的边。

        Returns:
            新建的边数量
        """
        if not entity_database:
            return 0

        import uuid as _uuid
        from falkordb import FalkorDB
        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(group_id)

        # 1. 读取所有节点 name → uuid 映射
        result = graph.query(
            "MATCH (n:Entity) WHERE n.name IS NOT NULL AND n.name <> '' "
            "RETURN n.uuid, n.name"
        )
        name_to_uuid: Dict[str, str] = {}
        for row in result.result_set:
            if row[0] and row[1]:
                name_to_uuid[row[1].strip()] = row[0]
        graph_names = list(name_to_uuid.keys())

        # 构建 任意名称 → uuid 的综合反查表
        # 三层匹配：精确 → 别名 → 子串模糊
        alias_to_uuid: Dict[str, str] = dict(name_to_uuid)

        def _fuzzy_match_graph_node(name: str) -> Optional[str]:
            """模糊匹配：子串包含（较长名包含较短名，或反之）"""
            if not name:
                return None
            # 精确匹配
            if name in alias_to_uuid:
                return alias_to_uuid[name]
            # 子串匹配：图谱节点名包含查询名，或查询名包含节点名
            for gn in graph_names:
                if len(name) >= 2 and len(gn) >= 2:
                    if name in gn or gn in name:
                        return name_to_uuid[gn]
            return None

        # 用 entity_database 的别名扩展反查表
        for canonical, entry in entity_database.items():
            all_names = [canonical] + entry.get('aliases', [])
            # 找到这组名称中任何一个能匹配到图谱节点的 uuid
            resolved_uuid = None
            for n in all_names:
                resolved_uuid = _fuzzy_match_graph_node(n)
                if resolved_uuid:
                    break
            if resolved_uuid:
                # 将所有名称都指向这个 uuid
                for n in all_names:
                    if n not in alias_to_uuid:
                        alias_to_uuid[n] = resolved_uuid

        # 2. 读取已有边的 fact 集合，用于内容级去重
        # 两个实体之间可能有多种关系（师父、盟友），只按实体对去重会丢失关系
        edges_result = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity) RETURN s.uuid, t.uuid, r.fact"
        )
        existing_edge_facts: set = set()  # (source_uuid, target_uuid, fact_key)
        existing_edge_pairs: set = set()  # (source_uuid, target_uuid) 快速判断是否有任何边
        for row in edges_result.result_set:
            if row[0] and row[1]:
                existing_edge_pairs.add((row[0], row[1]))
                fact = (row[2] or '').strip()
                if fact:
                    existing_edge_facts.add((row[0], row[1], fact))

        # 3. 遍历 entity_database 的 relationships，补建缺失边
        created = 0
        for canonical, entry in entity_database.items():
            source_uuid = alias_to_uuid.get(canonical) or _fuzzy_match_graph_node(canonical)
            if not source_uuid:
                continue
            for rel in entry.get('relationships', []):
                target_name = (rel.get('target') or '').strip()
                relation = (rel.get('relation') or '').strip()
                if not target_name or not relation:
                    continue
                target_uuid = alias_to_uuid.get(target_name) or _fuzzy_match_graph_node(target_name)
                if not target_uuid:
                    continue
                if source_uuid == target_uuid:
                    continue  # 跳过自环

                new_fact = f"{canonical}{relation}{target_name}"

                # 内容级去重：检查已有边中是否有包含相同关键词的 fact
                # 如果 A→B 或 B→A 已有边且 fact 中包含 relation 的关键内容，跳过
                already_covered = False
                for s, t, f in existing_edge_facts:
                    if (s == source_uuid and t == target_uuid) or (s == target_uuid and t == source_uuid):
                        # 关系关键词出现在已有 fact 中，视为重复
                        if relation in f or f in new_fact:
                            already_covered = True
                            break
                if already_covered:
                    continue

                try:
                    graph.query(
                        "MATCH (a:Entity {uuid: $a}), (b:Entity {uuid: $b}) "
                        "CREATE (a)-[r:RELATES_TO]->(b) "
                        "SET r.name = $name, r.fact = $fact, r.uuid = $ruuid",
                        {
                            "a": source_uuid, "b": target_uuid,
                            "name": "RELATES_TO",
                            "fact": new_fact,
                            "ruuid": str(_uuid.uuid4()),
                        }
                    )
                    existing_edge_facts.add((source_uuid, target_uuid, new_fact))
                    created += 1
                except Exception as e:
                    logger.debug(f"补建边失败 ({canonical}→{target_name}): {e}")

        if created:
            logger.info(f"supplement_missing_edges: 补建 {created} 条边 (group_id={group_id})")
        return created

    # ──────────────────────────────────────────────────────────────
    # 7. 工具方法
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def lookup_entity(
        entity_database: Dict[str, Any],
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """按名称（含别名）在 entity_database 中查找条目，找不到返回 None"""
        if not entity_database or not name:
            return None
        if name in entity_database:
            return entity_database[name]
        for entry in entity_database.values():
            if name in entry.get('aliases', []):
                return entry
        return None

    @staticmethod
    def get_all_names(entity_database: Dict[str, Any]) -> List[str]:
        """返回 entity_database 中所有实体名称和别名的列表（用于 chunk header 注入）"""
        names: List[str] = []
        for canonical, entry in entity_database.items():
            names.append(canonical)
            names.extend(entry.get('aliases', []))
        # 去重，按长度降序（让更长的名字优先匹配，避免短名覆盖长名）
        seen: set = set()
        result: List[str] = []
        for n in sorted(names, key=len, reverse=True):
            if n and n not in seen:
                result.append(n)
                seen.add(n)
        return result
