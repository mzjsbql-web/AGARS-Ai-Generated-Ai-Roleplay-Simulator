"""
从 FalkorDB 本地图谱读取实体（替代 ZepEntityReader）
轻量级读取，不需要初始化 Graphiti 客户端
"""

from typing import Dict, Any, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('agars.falkordb_reader')


def read_entities_from_falkordb(
    group_id: str,
    entity_types: Optional[List[str]] = None,
    required_uuids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    从 FalkorDB 读取实体及其关系信息

    Args:
        group_id: 图谱分区ID（即 project.graph_id）
        entity_types: 筛选的实体类型（可选）

    Returns:
        实体列表，每个实体包含 uuid, name, labels, summary, related_edges, related_nodes
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

        entities.append({
            "uuid": node_data["uuid"],
            "name": node_data.get("name", ""),
            "labels": labels,
            "summary": node_data.get("summary", ""),
            "related_edges": related_edges,
            "related_nodes": related_nodes,
        })

    logger.info(f"从 FalkorDB 读取实体: group_id={group_id}, 总节点={len(nodes)}, 筛选后={len(entities)}")
    return entities


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
