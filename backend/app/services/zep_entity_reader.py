"""
实体读取与过滤服务
从 FalkorDB 本地图谱读取节点，筛选出符合预定义实体类型的节点

注意：原先使用 Zep Cloud API，现已改为直接查询 FalkorDB，
因为图谱是通过 Graphiti + FalkorDB 在本地构建的。
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('agars.zep_entity_reader')


@dataclass
class EntityNode:
    """实体节点数据结构"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # 相关的边信息
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # 相关的其他节点信息
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """获取实体类型（排除默认的Entity标签）"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """过滤后的实体集合"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    实体读取与过滤服务（FalkorDB 本地版）

    主要功能：
    1. 从 FalkorDB 本地图谱读取所有节点
    2. 筛选出符合预定义实体类型的节点（Labels不只是Entity的节点）
    3. 获取每个实体的相关边和关联节点信息

    注意：构造函数保留 api_key 参数以兼容现有调用，但不再使用。
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key 参数保留以兼容现有调用，不再使用
        self._host = Config.FALKORDB_HOST
        self._port = Config.FALKORDB_PORT
        self._password = Config.FALKORDB_PASSWORD or None

    def _get_graph(self, graph_id: str):
        """获取 FalkorDB graph 对象"""
        from falkordb import FalkorDB
        db = FalkorDB(
            host=self._host,
            port=self._port,
            password=self._password,
        )
        return db.select_graph(graph_id)

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        获取图谱的所有节点

        Args:
            graph_id: 图谱ID（FalkorDB graph 名称）

        Returns:
            节点列表
        """
        logger.info(f"从 FalkorDB 获取图谱 {graph_id} 的所有节点...")

        graph = self._get_graph(graph_id)
        result = graph.query("MATCH (n:Entity) RETURN n")

        nodes_data = []
        for record in result.result_set:
            node = record[0]
            props = node.properties
            nodes_data.append({
                "uuid": props.get("uuid", ""),
                "name": props.get("name", ""),
                "labels": list(node.labels) if hasattr(node, 'labels') else [],
                "summary": props.get("summary", ""),
                "attributes": {},
            })

        logger.info(f"共获取 {len(nodes_data)} 个节点")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        获取图谱的所有边

        Args:
            graph_id: 图谱ID（FalkorDB graph 名称）

        Returns:
            边列表
        """
        logger.info(f"从 FalkorDB 获取图谱 {graph_id} 的所有边...")

        graph = self._get_graph(graph_id)
        result = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity) RETURN s.uuid, r, t.uuid"
        )

        edges_data = []
        for record in result.result_set:
            s_uuid = record[0]
            rel = record[1]
            t_uuid = record[2]
            r_props = rel.properties
            edges_data.append({
                "uuid": r_props.get("uuid", ""),
                "name": r_props.get("name", ""),
                "fact": r_props.get("fact", ""),
                "source_node_uuid": s_uuid,
                "target_node_uuid": t_uuid,
                "attributes": {},
            })

        logger.info(f"共获取 {len(edges_data)} 条边")
        return edges_data

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[Dict[str, Any]]:
        """
        获取指定节点的所有相关边

        Args:
            graph_id: 图谱ID
            node_uuid: 节点UUID

        Returns:
            边列表
        """
        try:
            graph = self._get_graph(graph_id)
            result = graph.query(
                "MATCH (n:Entity {uuid: $uuid})-[r]-(m:Entity) "
                "RETURN n.uuid, r, m.uuid",
                params={"uuid": node_uuid}
            )

            edges_data = []
            for record in result.result_set:
                n_uuid = record[0]
                rel = record[1]
                m_uuid = record[2]
                r_props = rel.properties

                # 判断边的方向
                src = r_props.get("source_node_uuid", n_uuid)
                tgt = r_props.get("target_node_uuid", m_uuid)

                edges_data.append({
                    "uuid": r_props.get("uuid", ""),
                    "name": r_props.get("name", ""),
                    "fact": r_props.get("fact", ""),
                    "source_node_uuid": src,
                    "target_node_uuid": tgt,
                    "attributes": {},
                })

            return edges_data
        except Exception as e:
            logger.warning(f"获取节点 {node_uuid} 的边失败: {str(e)}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        筛选出符合预定义实体类型的节点

        筛选逻辑：
        - 如果节点的Labels只有一个"Entity"，说明这个实体不符合我们预定义的类型，跳过
        - 如果节点的Labels包含除"Entity"和"Node"之外的标签，说明符合预定义类型，保留

        Args:
            graph_id: 图谱ID
            defined_entity_types: 预定义的实体类型列表（可选，如果提供则只保留这些类型）
            enrich_with_edges: 是否获取每个实体的相关边信息

        Returns:
            FilteredEntities: 过滤后的实体集合
        """
        logger.info(f"开始筛选图谱 {graph_id} 的实体...")

        # 获取所有节点
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        # 获取所有边（用于后续关联查找）
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        # 构建节点UUID到节点数据的映射
        node_map = {n["uuid"]: n for n in all_nodes}

        # 筛选符合条件的实体
        filtered_entities = []
        entity_types_found = set()

        for node in all_nodes:
            labels = node.get("labels", [])

            # 筛选逻辑：Labels必须包含除"Entity"和"Node"之外的标签
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]

            if not custom_labels:
                # 只有默认标签，跳过
                continue

            # 如果指定了预定义类型，检查是否匹配
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            # 创建实体节点对象
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            # 获取相关边和节点
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                # 获取关联节点的基本信息
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(f"筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, "
                   f"实体类型: {entity_types_found}")

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        获取单个实体及其完整上下文（边和关联节点）

        Args:
            graph_id: 图谱ID
            entity_uuid: 实体UUID

        Returns:
            EntityNode或None
        """
        try:
            graph = self._get_graph(graph_id)
            result = graph.query(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n",
                params={"uuid": entity_uuid}
            )

            if not result.result_set:
                return None

            node = result.result_set[0][0]
            props = node.properties

            # 获取节点的边
            edges = self.get_node_edges(graph_id, entity_uuid)

            # 获取所有节点用于关联查找
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            # 处理相关边和节点
            related_edges = []
            related_node_uuids = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            # 获取关联节点信息
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })

            return EntityNode(
                uuid=props.get("uuid", ""),
                name=props.get("name", ""),
                labels=list(node.labels) if hasattr(node, 'labels') else [],
                summary=props.get("summary", ""),
                attributes={},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )

        except Exception as e:
            logger.error(f"获取实体 {entity_uuid} 失败: {str(e)}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        获取指定类型的所有实体

        Args:
            graph_id: 图谱ID
            entity_type: 实体类型（如 "Student", "PublicFigure" 等）
            enrich_with_edges: 是否获取相关边信息

        Returns:
            实体列表
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
