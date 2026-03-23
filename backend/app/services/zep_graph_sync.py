"""
Zep Cloud 图谱同步工具

将 FalkorDB 本地构建的图谱数据同步到 Zep Cloud，
使运行时（narrative_engine、zep_tools 等）能通过 Zep Cloud API 访问图谱。

同步方式：使用 zep_client.graph.add_fact_triple() 逐条上传边（含源/目标节点）。
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable, Dict, Any

from falkordb import FalkorDB
from zep_cloud.client import Zep

from ..config import Config

logger = logging.getLogger('agars.sync')


class ZepGraphSync:
    """将 FalkorDB 本地图谱同步到 Zep Cloud"""

    def __init__(self, zep_api_key: Optional[str] = None):
        api_key = zep_api_key or Config.ZEP_API_KEY
        if not api_key:
            raise ValueError("ZEP_API_KEY 未配置，无法同步到 Zep Cloud")
        self.zep_client = Zep(api_key=api_key)

    def sync_graph(
        self,
        graph_id: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        将 FalkorDB 本地图谱同步到 Zep Cloud。

        流程:
        1. 在 Zep Cloud 创建图谱（graph.create）
        2. 从 FalkorDB 读取所有边（含端点节点）
        3. 并发调用 graph.add_fact_triple() 上传每条边
        4. 报告进度

        Args:
            graph_id: FalkorDB 中的 group_id（即 project.graph_id）
            progress_callback: 进度回调 (message, progress_ratio)

        Returns:
            {"synced_edges": int, "synced_nodes": int, "errors": list}
        """
        result = {"synced_edges": 0, "synced_nodes": 0, "errors": []}

        # Step 1: 在 Zep Cloud 创建图谱
        if progress_callback:
            progress_callback("在 Zep Cloud 创建图谱...", 0.0)

        try:
            self.zep_client.graph.create(
                graph_id=graph_id,
                name=graph_id,
                description="AGARS graph synced from FalkorDB",
            )
            logger.info(f"Zep Cloud 图谱已创建: {graph_id}")
        except Exception as e:
            error_msg = str(e)
            # 如果图谱已存在，忽略错误继续同步
            if "already exists" in error_msg.lower() or "409" in error_msg:
                logger.info(f"Zep Cloud 图谱已存在，继续同步: {graph_id}")
            else:
                logger.warning(f"创建 Zep Cloud 图谱失败: {e}")
                result["errors"].append(f"创建图谱失败: {error_msg}")
                return result

        # Step 2: 从 FalkorDB 读取所有边
        if progress_callback:
            progress_callback("从 FalkorDB 读取图谱数据...", 0.05)

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(graph_id)

        edges_result = graph.query(
            "MATCH (s:Entity)-[r]->(t:Entity) RETURN s, r, t"
        )

        edges = []
        seen_nodes = set()
        for record in edges_result.result_set:
            source_node = record[0]
            rel = record[1]
            target_node = record[2]

            s_props = source_node.properties
            r_props = rel.properties
            t_props = target_node.properties

            source_name = s_props.get("name", "")
            target_name = t_props.get("name", "")

            edges.append({
                "fact": r_props.get("fact", ""),
                "fact_name": r_props.get("name", "RELATED_TO"),
                "source_node_name": source_name,
                "target_node_name": target_name,
                "source_node_summary": s_props.get("summary", ""),
                "target_node_summary": t_props.get("summary", ""),
            })

            seen_nodes.add(source_name)
            seen_nodes.add(target_name)

        total_edges = len(edges)
        logger.info(f"从 FalkorDB 读取到 {total_edges} 条边, {len(seen_nodes)} 个节点")

        if total_edges == 0:
            if progress_callback:
                progress_callback("图谱无边数据，跳过同步", 1.0)
            result["synced_nodes"] = len(seen_nodes)
            return result

        # Step 3: 并发上传边到 Zep Cloud
        if progress_callback:
            progress_callback(f"开始同步 {total_edges} 条边到 Zep Cloud...", 0.1)

        synced_count = 0
        error_count = 0

        def upload_edge(edge_data: dict) -> Optional[str]:
            """上传单条边，成功返回 None，失败返回错误信息"""
            try:
                self.zep_client.graph.add_fact_triple(
                    fact=edge_data["fact"],
                    fact_name=edge_data["fact_name"],
                    source_node_name=edge_data["source_node_name"],
                    target_node_name=edge_data["target_node_name"],
                    source_node_summary=edge_data["source_node_summary"],
                    target_node_summary=edge_data["target_node_summary"],
                    graph_id=graph_id,
                )
                return None
            except Exception as e:
                return f"[{edge_data['source_node_name']}]->{edge_data['target_node_name']}: {e}"

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(upload_edge, edge): i for i, edge in enumerate(edges)}

            for future in as_completed(futures):
                idx = futures[future]
                error = future.result()
                if error is None:
                    synced_count += 1
                else:
                    error_count += 1
                    result["errors"].append(error)
                    logger.warning(f"同步边失败: {error}")

                # 更新进度 (10% - 100%)
                done = synced_count + error_count
                if progress_callback and done % max(1, total_edges // 20) == 0:
                    ratio = 0.1 + 0.9 * (done / total_edges)
                    progress_callback(
                        f"已同步 {synced_count}/{total_edges} 条边"
                        + (f" ({error_count} 失败)" if error_count else ""),
                        ratio,
                    )

        result["synced_edges"] = synced_count
        result["synced_nodes"] = len(seen_nodes)

        if progress_callback:
            progress_callback(
                f"同步完成: {synced_count} 条边, {len(seen_nodes)} 个节点"
                + (f", {error_count} 个错误" if error_count else ""),
                1.0,
            )

        logger.info(
            f"Zep Cloud 同步完成: graph_id={graph_id}, "
            f"edges={synced_count}/{total_edges}, nodes={len(seen_nodes)}, "
            f"errors={error_count}"
        )

        return result
