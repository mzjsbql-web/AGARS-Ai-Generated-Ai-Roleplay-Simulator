"""
从 FalkorDB 本地图谱读取实体（替代 ZepEntityReader）
轻量级读取，不需要初始化 Graphiti 客户端
"""

from typing import Dict, Any, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('agars.falkordb_reader')

# 非 agent 关键词（出现在 labels 或 summary 中时倾向判为非 agent）
_NON_AGENT_KEYWORDS = [
    '物品', '道具', '武器', '装备', '药品', '食物', '工具', '材料', '宝物', '书籍', '文献', '信件',
    '地点', '场所', '建筑', '城市', '村庄', '房间', '区域', '山', '河', '森林', '洞穴', '遗迹',
    '事件', '战役', '灾难', '仪式', '节日', '历史',
    '概念', '技能', '魔法', '法术', '阵法',
    'item', 'weapon', 'location', 'place', 'event', 'concept', 'skill',
]
# agent 关键词（出现在 labels 或 summary 中时倾向判为 agent）
_AGENT_KEYWORDS = [
    '人物', '角色', '人', '族', '组织', '势力', '团体', '门派', '帮派', '家族', '王国', '帝国',
    '军队', '商会', '教会', '公会',
    'character', 'person', 'organization', 'faction', 'group',
]


def _classify_is_agent(
    custom_labels: List[str],
    summary: str,
    agent_types: Optional[List[str]] = None,
) -> bool:
    """
    判断实体是否为 agent（能自主行动的实体）。
    优先级：
    1. 如果实体标签命中 agent_types 列表（ontology 提供），直接判为 agent
    2. 如果实体标签命中非 agent 关键词，判为非 agent
    3. 如果实体标签命中 agent 关键词，判为 agent
    4. 根据 summary 内容做启发式判断
    5. 兜底：有标签但无法判断时 → False（保守策略）；无标签 → True（可能是未分类的重要角色）
    """
    labels_lower = [l.lower() for l in custom_labels]
    labels_joined = " ".join(custom_labels).lower()

    # 1. ontology 显式标记
    if agent_types and custom_labels:
        if any(l in agent_types for l in custom_labels):
            return True
        # 有标签但不在 agent_types 中，大概率不是 agent
        # 但还需检查是否是 ontology 中遗漏 is_agent 的类型，继续往下判断

    # 2. 标签关键词匹配
    for kw in _NON_AGENT_KEYWORDS:
        if kw in labels_joined:
            return False
    for kw in _AGENT_KEYWORDS:
        if kw in labels_joined:
            return True

    # 3. summary 启发式判断
    summary_lower = (summary or "").lower()[:200]
    if summary_lower:
        non_agent_hits = sum(1 for kw in _NON_AGENT_KEYWORDS if kw in summary_lower)
        agent_hits = sum(1 for kw in _AGENT_KEYWORDS if kw in summary_lower)
        if non_agent_hits > agent_hits:
            return False
        if agent_hits > non_agent_hits:
            return True

    # 4. 兜底
    if custom_labels:
        # 有标签但无法确定 → 保守判为非 agent
        return False
    # 无标签的实体可能是 Graphiti 未分配本体类型的重要角色
    return True


def read_entities_from_falkordb(
    group_id: str,
    entity_types: Optional[List[str]] = None,
    required_uuids: Optional[List[str]] = None,
    agent_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    从 FalkorDB 读取实体及其关系信息

    Args:
        group_id: 图谱分区ID（即 project.graph_id）
        entity_types: 筛选的实体类型（可选）
        agent_types: 被视为 agent 的实体类型名称列表（可选）。
                     若提供，每个返回的实体会带 is_agent 字段；
                     无标签实体根据 summary 启发式判断。

    Returns:
        实体列表，每个实体包含 uuid, name, labels, summary, related_edges, related_nodes, is_agent
    """
    from falkordb import FalkorDB

    db = FalkorDB(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
    )
    graph = db.select_graph(group_id)

    # 查询所有 Entity 节点
    nodes_result = graph.query("MATCH (n:Entity) RETURN n")
    nodes = []
    node_map = {}
    for record in nodes_result.result_set:
        node = record[0]
        props = node.properties
        node_name = (props.get("name") or "").strip()
        node_data = {
            "uuid": props.get("uuid", ""),
            "name": node_name,
            "labels": list(node.labels) if hasattr(node, 'labels') else [],
            "summary": props.get("summary", ""),
        }
        node_map[node_data["uuid"]] = node_data  # 边查找需要完整的 map
        if not node_name:
            continue  # 空白节点不参与实体处理
        nodes.append(node_data)

    # 查询所有 Entity->Entity 边
    edges_result = graph.query(
        "MATCH (s:Entity)-[r]->(t:Entity) RETURN s.uuid, r, t.uuid"
    )
    edges = []
    for record in edges_result.result_set:
        s_uuid = record[0]
        rel = record[1]
        t_uuid = record[2]
        r_props = rel.properties
        edges.append({
            "source_node_uuid": s_uuid,
            "target_node_uuid": t_uuid,
            "name": r_props.get("name", ""),
            "fact": r_props.get("fact", ""),
        })

    # 筛选并丰富实体
    entities = []
    for node_data in nodes:
        labels = node_data.get("labels", [])
        custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
        # required_uuids（如玩家实体）不受任何标签过滤
        is_required = bool(required_uuids and node_data["uuid"] in required_uuids)
        # 无自定义标签但有 summary 或有关联边的实体不再跳过——
        # Graphiti 可能未给它分配本体类型，但它仍可能是重要角色
        if not custom_labels and not is_required:
            has_summary = bool((node_data.get("summary") or "").strip())
            has_edges = any(
                e["source_node_uuid"] == node_data["uuid"] or e["target_node_uuid"] == node_data["uuid"]
                for e in edges
            )
            if not has_summary and not has_edges:
                continue  # 真正的空白节点才跳过
        if entity_types and not is_required:
            # 有自定义标签时按类型过滤；无自定义标签的实体保留（兜底）
            if custom_labels and not any(l in entity_types for l in custom_labels):
                continue

        related_edges = []
        related_node_uuids = set()
        for edge in edges:
            if edge["source_node_uuid"] == node_data["uuid"]:
                related_edges.append({
                    "direction": "outgoing",
                    "edge_name": edge["name"],
                    "fact": edge["fact"],
                    "target_node_uuid": edge["target_node_uuid"],
                })
                related_node_uuids.add(edge["target_node_uuid"])
            elif edge["target_node_uuid"] == node_data["uuid"]:
                related_edges.append({
                    "direction": "incoming",
                    "edge_name": edge["name"],
                    "fact": edge["fact"],
                    "source_node_uuid": edge["source_node_uuid"],
                })
                related_node_uuids.add(edge["source_node_uuid"])

        related_nodes = []
        for ruuid in related_node_uuids:
            if ruuid in node_map:
                rn = node_map[ruuid]
                related_nodes.append({
                    "uuid": rn["uuid"],
                    "name": rn.get("name", ""),
                    "labels": rn.get("labels", []),
                    "summary": rn.get("summary", ""),
                })

        # 判断 is_agent：基于实体自身标签和 summary
        is_agent = _classify_is_agent(custom_labels, node_data.get("summary", ""), agent_types)

        entities.append({
            "uuid": node_data["uuid"],
            "name": node_data.get("name", ""),
            "labels": labels,
            "summary": node_data.get("summary", ""),
            "related_edges": related_edges,
            "related_nodes": related_nodes,
            "is_agent": is_agent,
        })

    logger.info(f"从 FalkorDB 读取实体: group_id={group_id}, 总节点={len(nodes)}, 筛选后={len(entities)}, "
                f"agents={sum(1 for e in entities if e.get('is_agent'))}")
    return entities


def read_all_nodes_directory(
    group_id: str,
) -> List[Dict[str, Any]]:
    """
    读取图谱中所有节点的精简目录（uuid, name, labels, summary），
    用于记忆系统 known_nodes 判断。不做类型过滤。

    Returns:
        [{"uuid", "name", "labels", "summary"}]
    """
    from falkordb import FalkorDB

    db = FalkorDB(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
    )
    graph = db.select_graph(group_id)

    nodes = []
    try:
        result = graph.query("MATCH (n:Entity) RETURN n")
        for record in result.result_set:
            node = record[0]
            props = node.properties
            name = (props.get("name") or "").strip()
            if not name:
                continue
            nodes.append({
                "uuid": props.get("uuid", ""),
                "name": name,
                "labels": list(node.labels) if hasattr(node, 'labels') else [],
                "summary": props.get("summary", ""),
            })
    except Exception as e:
        logger.warning(f"读取全部节点目录失败: {e}")

    logger.debug(f"全部节点目录: group_id={group_id}, count={len(nodes)}")
    return nodes


def read_nodes_by_uuids(
    group_id: str,
    uuids: List[str],
) -> List[Dict[str, Any]]:
    """
    按 UUID 列表批量读取节点详情（含 summary）及其关联的边。
    用于记忆检索后获取召回节点的完整信息。

    Returns:
        [{"uuid", "name", "labels", "summary", "related_facts": [str]}]
    """
    if not uuids:
        return []

    from falkordb import FalkorDB

    db = FalkorDB(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
    )
    graph = db.select_graph(group_id)

    nodes = []
    try:
        # 批量查询节点
        result = graph.query(
            "MATCH (n:Entity) WHERE n.uuid IN $uuids RETURN n",
            {"uuids": uuids}
        )
        node_map = {}
        for record in result.result_set:
            node = record[0]
            props = node.properties
            node_uuid = props.get("uuid", "")
            node_map[node_uuid] = {
                "uuid": node_uuid,
                "name": (props.get("name") or "").strip(),
                "labels": list(node.labels) if hasattr(node, 'labels') else [],
                "summary": props.get("summary", ""),
                "related_facts": [],
            }

        # 查询这些节点的关联边 facts
        if node_map:
            edges_result = graph.query(
                "MATCH (s:Entity)-[r]->(t:Entity) "
                "WHERE s.uuid IN $uuids OR t.uuid IN $uuids "
                "RETURN s.uuid, r.fact, t.uuid, s.name, t.name",
                {"uuids": uuids}
            )
            for record in edges_result.result_set:
                s_uuid, fact, t_uuid, s_name, t_name = record
                if not fact:
                    continue
                # 将 fact 添加到相关节点
                if s_uuid in node_map:
                    node_map[s_uuid]["related_facts"].append(fact)
                if t_uuid in node_map and t_uuid != s_uuid:
                    node_map[t_uuid]["related_facts"].append(fact)

        # 去重 facts 并返回
        for nd in node_map.values():
            nd["related_facts"] = list(dict.fromkeys(nd["related_facts"]))
            nodes.append(nd)

    except Exception as e:
        logger.warning(f"按UUID批量读取节点失败: {e}")

    return nodes


def read_entity_edges(
    group_id: str,
    entity_uuid: str,
) -> List[Dict[str, Any]]:
    """
    读取指定实体的所有图谱边（出边+入边）

    Returns:
        [{"direction", "edge_name", "fact", "other_name", "other_uuid"}]
    """
    from falkordb import FalkorDB

    db = FalkorDB(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
    )
    graph = db.select_graph(group_id)

    edges = []

    # 出边
    # Graphiti 在 FalkorDB 中统一用 RELATES_TO 作为 Cypher 关系类型
    # 语义类型（如 MEMBER_OF）存在 r.name 属性中，r.fact 存描述文本
    try:
        out_result = graph.query(
            "MATCH (s:Entity {uuid: $uuid})-[r]->(t:Entity) "
            "RETURN r.name AS edge_name, r.fact AS fact, "
            "t.name AS other_name, t.uuid AS other_uuid",
            {"uuid": entity_uuid}
        )
        for record in out_result.result_set:
            edges.append({
                "direction": "outgoing",
                "rel_type": record[0] or "",
                "fact": record[1] or "",
                "other_name": record[2] or "",
                "other_uuid": record[3] or "",
            })
    except Exception as e:
        logger.warning(f"读取出边失败 ({entity_uuid}): {e}")

    # 入边
    try:
        in_result = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity {uuid: $uuid}) "
            "RETURN r.name AS edge_name, r.fact AS fact, "
            "s.name AS other_name, s.uuid AS other_uuid",
            {"uuid": entity_uuid}
        )
        for record in in_result.result_set:
            edges.append({
                "direction": "incoming",
                "rel_type": record[0] or "",
                "fact": record[1] or "",
                "other_name": record[2] or "",
                "other_uuid": record[3] or "",
            })
    except Exception as e:
        logger.warning(f"读取入边失败 ({entity_uuid}): {e}")

    logger.debug(f"实体边读取: uuid={entity_uuid}, edges={len(edges)}")
    return edges


def search_entity_facts_by_name(
    group_id: str,
    entity_name: str,
    limit: int = 8,
) -> List[str]:
    """
    按实体名称在 FalkorDB 中搜索其相关 facts（边的 fact 属性）

    Returns:
        fact 字符串列表
    """
    from falkordb import FalkorDB

    db = FalkorDB(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
    )
    graph = db.select_graph(group_id)

    facts = []
    try:
        # 出边 facts
        result = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity) "
            "WHERE s.name = $name "
            "RETURN r.fact, t.name "
            "LIMIT $limit",
            {"name": entity_name, "limit": limit}
        )
        for record in result.result_set:
            fact = record[0]
            if fact:
                facts.append(fact)

        # 入边 facts
        result2 = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity) "
            "WHERE t.name = $name "
            "RETURN r.fact, s.name "
            "LIMIT $limit",
            {"name": entity_name, "limit": limit}
        )
        for record in result2.result_set:
            fact = record[0]
            if fact:
                facts.append(fact)

    except Exception as e:
        logger.warning(f"按名称搜索实体 facts 失败 ({entity_name}): {e}")

    # 去重保序
    seen = set()
    unique = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique[:limit]


def search_entity_context(
    group_id: str,
    entity_name: str,
    limit: int = 10,
) -> str:
    """
    获取实体的综合图谱上下文（summary + 相关 facts），返回格式化文本
    """
    from falkordb import FalkorDB

    db = FalkorDB(
        host=Config.FALKORDB_HOST,
        port=Config.FALKORDB_PORT,
        password=Config.FALKORDB_PASSWORD or None,
    )
    graph = db.select_graph(group_id)

    parts = []

    # 获取实体 summary
    try:
        node_result = graph.query(
            "MATCH (n:Entity) WHERE n.name = $name RETURN n.summary LIMIT 1",
            {"name": entity_name}
        )
        if node_result.result_set and node_result.result_set[0][0]:
            parts.append(f"- {node_result.result_set[0][0]}")
    except Exception:
        pass

    # 获取相关 facts
    facts = search_entity_facts_by_name(group_id, entity_name, limit=limit)
    for f in facts:
        parts.append(f"- {f}")

    return "\n".join(parts)
