"""
图谱相关API路由
采用项目上下文机制，服务端持久化状态
"""

import os
import re
import traceback
import threading
from typing import List
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..services.zep_graph_sync import ZepGraphSync

# 获取日志器
logger = get_logger('agars.api')


def _parse_text_sections(combined_text: str) -> List[tuple]:
    """
    将合并文本按 '=== filename ===' 分隔符拆回各文件的 (filename, text) 列表。
    若无分隔符，整体作为一个匿名文档返回。
    """
    pattern = re.compile(r'^=== (.+?) ===\s*$', re.MULTILINE)
    matches = list(pattern.finditer(combined_text))
    if not matches:
        return [("document", combined_text)]

    sections = []
    for idx, match in enumerate(matches):
        filename = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(combined_text)
        section_text = combined_text[start:end].strip()
        if section_text:
            sections.append((filename, section_text))
    return sections


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== 项目管理接口 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    获取项目详情
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"项目不存在: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所有项目
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    删除项目
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"项目不存在或删除失败: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"项目已删除: {project_id}"
    })


@graph_bp.route('/project/<project_id>/rename', methods=['PATCH'])
def rename_project(project_id: str):
    """更新项目的自定义标题"""
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": "项目不存在"}), 404

    data = request.get_json()
    custom_title = data.get('custom_title', '')
    project.name = custom_title if custom_title else project.name
    ProjectManager.save_project(project)
    return jsonify({"success": True})


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置项目状态（用于重新构建图谱）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"项目不存在: {project_id}"
        }), 404
    
    # 重置到本体已生成状态
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": f"项目已重置: {project_id}",
        "data": project.to_dict()
    })


# ============== 接口1：上传文件并生成本体 ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    接口1：上传文件，分析生成本体定义
    
    请求方式：multipart/form-data
    
    参数：
        files: 上传的文件（PDF/MD/TXT），可多个
        simulation_requirement: 模拟需求描述（必填）
        project_name: 项目名称（可选）
        additional_context: 额外说明（可选）
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== 开始生成本体定义 ===")
        
        # 获取参数
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(f"项目名称: {project_name}")
        logger.debug(f"模拟需求: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "请提供模拟需求描述 (simulation_requirement)"
            }), 400
        
        # 获取上传的文件
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "请至少上传一个文档文件"
            }), 400
        
        # 创建项目
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"创建项目: {project.project_id}")
        
        # 保存文件并提取文本
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # 保存文件到项目目录
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                # 提取文本
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "没有成功处理任何文档，请检查文件格式"
            }), 400
        
        # 保存提取的文本
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文本提取完成，共 {len(all_text)} 字符")
        
        # 生成本体
        logger.info("调用 LLM 生成本体定义...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        # 保存本体到项目
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"本体生成完成: {entity_count} 个实体类型, {edge_count} 个关系类型")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        logger.error(f"本体生成失败: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 接口2：构建图谱 ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    接口2：根据project_id构建图谱
    
    请求（JSON）：
        {
            "project_id": "proj_xxxx",  // 必填，来自接口1
            "graph_name": "图谱名称",    // 可选
            "chunk_size": 1500,         // 可选，默认1500
            "chunk_overlap": 50,        // 可选，默认50
            "batch_size": 10            // 可选，默认10
        }
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "图谱构建任务已启动"
            }
        }
    """
    try:
        logger.info("=== 开始构建图谱 ===")
        
        # 检查配置
        errors = []
        if not Config.LLM_API_KEY:
            errors.append("LLM_API_KEY未配置")
        if errors:
            logger.error(f"配置错误: {errors}")
            return jsonify({
                "success": False,
                "error": "配置错误: " + "; ".join(errors)
            }), 500
        
        # 解析请求
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"请求参数: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "请提供 project_id"
            }), 400
        
        # 获取项目
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"项目不存在: {project_id}"
            }), 404
        
        # 检查项目状态
        force = data.get('force', False)  # 强制重新构建
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "项目尚未生成本体，请先调用 /ontology/generate"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "图谱正在构建中，请勿重复提交。如需强制重建，请添加 force: true",
                "task_id": project.graph_build_task_id
            }), 400
        
        # 如果强制重建，重置状态
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        # 获取配置
        graph_name = data.get('graph_name', project.name or 'AGARS Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        batch_size = data.get('batch_size', project.batch_size or Config.DEFAULT_BATCH_SIZE)

        # 更新项目配置
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        project.batch_size = batch_size
        
        # 获取提取的文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "未找到提取的文本内容"
            }), 400
        
        # 获取本体
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "未找到本体定义"
            }), 400
        
        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {graph_name}")
        logger.info(f"创建图谱构建任务: task_id={task_id}, project_id={project_id}")
        
        # 更新项目状态
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        # 启动后台任务
        def build_task():
            import re as _re
            import time as _time
            build_logger = get_logger('agars.build')
            try:
                phase_start = _time.time()
                build_logger.info(f"[{task_id}] 开始构建图谱...")
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    message="初始化图谱构建服务..."
                )

                # 创建图谱构建服务（Graphiti + FalkorDB）
                builder = GraphBuilderService()
                build_logger.info(f"[{task_id}] [计时] GraphBuilderService初始化: {_time.time()-phase_start:.1f}s")

                # 按文件分块（保留来源信息）
                phase_start = _time.time()
                task_manager.update_task(
                    task_id,
                    message="文本分块中...",
                    progress=5
                )
                file_sections = _parse_text_sections(text)
                file_chunks = [
                    (filename, TextProcessor.split_text(section_text, chunk_size=chunk_size, overlap=chunk_overlap))
                    for filename, section_text in file_sections
                ]

                # ── 方案C：分段结构化实体预提取 ──────────────────────────────
                phase_start = _time.time()
                task_manager.update_task(
                    task_id,
                    message="预提取实体信息（分段并行）...",
                    progress=7
                )
                from ..utils.llm_client import LLMClient
                from ..services.text_enricher import TextEnricher
                from ..models.project import ProjectManager as _PM

                entity_database: dict = {}
                try:
                    enricher = TextEnricher(LLMClient())

                    def _enrich_progress(msg, ratio):
                        task_manager.update_task(
                            task_id,
                            message=f"[实体预提取] {msg}",
                            progress=7 + int(ratio * 6),   # 7% → 13%
                        )

                    entity_database = enricher.extract_all_sections(
                        text,
                        progress_callback=_enrich_progress,
                    )
                    _PM.save_entity_database(project_id, entity_database)
                    build_logger.info(
                        f"[{task_id}] [计时] 实体预提取({len(entity_database)}个实体): "
                        f"{_time.time()-phase_start:.1f}s"
                    )
                except Exception as _enrich_err:
                    build_logger.warning(
                        f"[{task_id}] 实体预提取失败（不影响图谱构建）: {_enrich_err}"
                    )

                # ── 方案A：为 chunk 注入实体上下文头 ────────────────────────
                if entity_database:
                    entity_names = TextEnricher.get_all_names(entity_database)
                    if entity_names:
                        # 构建多模式正则，按名称长度降序（长名先匹配）
                        _pattern = _re.compile(
                            '|'.join(_re.escape(n) for n in entity_names)
                        )

                        def _inject_headers(chunks):
                            result = []
                            for chunk in chunks:
                                matches = list(dict.fromkeys(_pattern.findall(chunk)))[:6]
                                if matches:
                                    # 注入实体描述（不只是名字），给 Graphiti 更多上下文
                                    lines = []
                                    for m in matches:
                                        entry = TextEnricher.lookup_entity(entity_database, m)
                                        if entry and entry.get('description'):
                                            lines.append(f"  {m}：{entry['description'][:80]}")
                                        else:
                                            lines.append(f"  {m}")
                                    header = "[本段涉及实体：\n" + "\n".join(lines) + "\n]\n"
                                    result.append(header + chunk)
                                else:
                                    result.append(chunk)
                            return result

                        file_chunks = [
                            (fn, _inject_headers(chunks))
                            for fn, chunks in file_chunks
                        ]
                        build_logger.info(
                            f"[{task_id}] 实体上下文头注入完成（{len(entity_names)} 个实体名）"
                        )
                total_chunks = sum(len(c) for _, c in file_chunks)
                build_logger.info(
                    f"[{task_id}] [计时] 文本分块({len(file_sections)}个文件, {total_chunks}块): {_time.time()-phase_start:.1f}s"
                )

                # 创建图谱（生成 group_id，初始化索引）
                phase_start = _time.time()
                task_manager.update_task(
                    task_id,
                    message="初始化FalkorDB图谱...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                build_logger.info(f"[{task_id}] [计时] create_graph+索引: {_time.time()-phase_start:.1f}s")

                # 更新项目的graph_id（实际存储的是 group_id）
                project.graph_id = graph_id
                ProjectManager.save_project(project)

                # 解析本体定义
                task_manager.update_task(
                    task_id,
                    message="解析本体定义...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)

                # 按文件逐个写入图谱（Graphiti add_episode_bulk，无边失效）
                task_manager.update_task(
                    task_id,
                    message=f"开始添加 {total_chunks} 个文本块（{len(file_chunks)} 个文件）...",
                    progress=15
                )

                phase_start = _time.time()
                processed_so_far = 0
                for file_idx, (filename, chunks) in enumerate(file_chunks):
                    def add_progress_callback(msg, progress_ratio, _fi=file_idx, _fn=filename):
                        # 整体进度 = 15%~88%，按已处理块数比例计算
                        file_done = sum(len(c) for _, c in file_chunks[:_fi])
                        overall = (file_done + progress_ratio * len(file_chunks[_fi][1])) / total_chunks
                        progress = 15 + int(overall * 73)
                        task_manager.update_task(
                            task_id,
                            message=f"[{_fn}] {msg}",
                            progress=progress
                        )

                    builder.add_text_batches(
                        graph_id,
                        chunks,
                        batch_size=batch_size,
                        progress_callback=add_progress_callback,
                        source_description=filename,
                    )
                    processed_so_far += len(chunks)
                    build_logger.info(
                        f"[{task_id}] 文件 {file_idx+1}/{len(file_chunks)} 写入完成: {filename} ({len(chunks)} 块)"
                    )

                build_logger.info(f"[{task_id}] [计时] add_text_batches({total_chunks}块): {_time.time()-phase_start:.1f}s")

                # ── 先用预提取数据充实所有节点 summary ───────────────────
                # 必须在去重之前：去重用 embedding(name+summary) 做相似度，
                # summary 越完整去重质量越高
                if entity_database:
                    try:
                        enriched_count = enricher.enrich_graph_summaries(graph_id, entity_database)
                        if enriched_count:
                            build_logger.info(f"[{task_id}] summary 充实: {enriched_count} 个节点")
                    except Exception as _enrich_b_err:
                        build_logger.warning(f"[{task_id}] summary 充实失败（不影响图谱）: {_enrich_b_err}")

                    # 补建缺失的边（entity_database 有结构化关系但 Graphiti 可能没生成 edge）
                    # 在去重之前：去重用 edge count 选择规范节点，边越完整去重越准
                    try:
                        new_edges = enricher.supplement_missing_edges(graph_id, entity_database)
                        if new_edges:
                            build_logger.info(f"[{task_id}] 补建缺失边: {new_edges} 条")
                    except Exception as _edge_err:
                        build_logger.warning(f"[{task_id}] 补建缺失边失败（不影响图谱）: {_edge_err}")

                # 实体去重（LLM 语义去重）
                phase_start = _time.time()
                task_manager.update_task(
                    task_id,
                    message="执行实体去重...",
                    progress=89
                )
                try:
                    def dedup_progress(msg, ratio):
                        task_manager.update_task(
                            task_id,
                            message=f"去重: {msg}",
                            progress=89
                        )
                    dedup_result = builder.resolve_duplicate_entities(
                        graph_id,
                        progress_callback=dedup_progress,
                        entity_database=entity_database if entity_database else None,
                    )
                    build_logger.info(
                        f"[{task_id}] 实体去重完成: merged={dedup_result['merged']}"
                    )
                except Exception as dedup_err:
                    build_logger.warning(f"[{task_id}] 实体去重失败（不影响图谱）: {dedup_err}")

                # 清理空节点（无 summary 且无 Entity 间边）
                try:
                    deleted = builder.cleanup_empty_nodes(graph_id)
                    if deleted:
                        build_logger.info(f"[{task_id}] 清理空节点: 删除 {deleted} 个")
                except Exception as cleanup_err:
                    build_logger.warning(f"[{task_id}] 清理空节点失败（不影响图谱）: {cleanup_err}")

                # 同步到 Zep Cloud（带超时保护）
                import time as _time
                task_manager.update_task(
                    task_id,
                    message="同步图谱到 Zep Cloud...",
                    progress=90
                )
                zep_sync_start = _time.time()
                try:
                    syncer = ZepGraphSync()

                    def sync_progress_callback(msg, ratio):
                        progress = 90 + int(ratio * 5)
                        task_manager.update_task(
                            task_id,
                            message=f"Zep Cloud 同步: {msg}",
                            progress=progress
                        )

                    sync_result = syncer.sync_graph(
                        graph_id,
                        progress_callback=sync_progress_callback
                    )
                    zep_sync_elapsed = _time.time() - zep_sync_start
                    build_logger.info(
                        f"[{task_id}] Zep Cloud 同步完成 ({zep_sync_elapsed:.1f}s): "
                        f"edges={sync_result['synced_edges']}, "
                        f"nodes={sync_result['synced_nodes']}, "
                        f"errors={len(sync_result['errors'])}"
                    )
                    if sync_result["errors"]:
                        build_logger.warning(
                            f"[{task_id}] Zep Cloud 同步有 {len(sync_result['errors'])} 个错误"
                        )
                except Exception as sync_err:
                    zep_sync_elapsed = _time.time() - zep_sync_start
                    build_logger.warning(
                        f"[{task_id}] Zep Cloud 同步失败 ({zep_sync_elapsed:.1f}s，不影响本地图谱）: {sync_err}"
                    )

                # 获取图谱数据
                task_manager.update_task(
                    task_id,
                    message="获取图谱数据...",
                    progress=96
                )
                graph_data = builder.get_graph_data(graph_id)
                
                # 更新项目状态
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}")
                
                # 关闭 Graphiti 资源
                builder.close()

                # 完成
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="图谱构建完成",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )

            except Exception as e:
                # 清理资源
                try:
                    builder.close()
                except Exception:
                    pass

                # 更新项目状态为失败
                build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")
                build_logger.debug(traceback.format_exc())

                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"构建失败: {str(e)}",
                    error=traceback.format_exc()
                )
        
        # 启动后台线程
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "图谱构建任务已启动，请通过 /task/{task_id} 查询进度"
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 任务查询接口 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    查询任务状态
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": f"任务不存在: {task_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    列出所有任务
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== 图谱数据接口 ==============

@graph_bp.route('/merge-entities/<graph_id>', methods=['POST'])
def merge_entities(graph_id: str):
    """
    手动合并指定节点。

    请求（JSON）：
        {
            "uuids": ["uuid_a", "uuid_b", "uuid_c"],  // 必填，至少 2 个
            "canonical_uuid": "uuid_a"                 // 可选，指定规范节点；
                                                       // 不填则自动选 summary 最长的
        }

    返回：
        {
            "success": true,
            "data": {
                "canonical_uuid": "uuid_a",
                "merged": 2
            }
        }
    """
    try:
        data = request.get_json() or {}
        uuids = data.get("uuids", [])

        if len(uuids) < 2:
            return jsonify({"success": False, "error": "至少提供 2 个 uuid"}), 400

        from falkordb import FalkorDB
        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(graph_id)

        # 确认所有 UUID 存在
        result = graph.query(
            "MATCH (n:Entity) WHERE n.uuid IN $uuids RETURN n.uuid, n.summary",
            {"uuids": uuids}
        )
        found = {row[0]: (row[1] or "") for row in result.result_set}
        missing = [u for u in uuids if u not in found]
        if missing:
            return jsonify({"success": False, "error": f"以下 UUID 不存在: {missing}"}), 404

        # 确定规范节点
        canonical_uuid = data.get("canonical_uuid")
        if canonical_uuid:
            if canonical_uuid not in found:
                return jsonify({"success": False, "error": f"canonical_uuid 不存在: {canonical_uuid}"}), 404
        else:
            canonical_uuid = max(uuids, key=lambda u: len(found[u]))

        # 合并
        builder = GraphBuilderService()
        duplicates = [u for u in uuids if u != canonical_uuid]
        merged = 0
        for dup_uuid in duplicates:
            builder._merge_entity_into(graph, canonical_uuid, dup_uuid)
            merged += 1
        builder.close()

        logger.info(f"手动合并: graph={graph_id}, canonical={canonical_uuid}, merged={merged}")
        return jsonify({
            "success": True,
            "data": {"canonical_uuid": canonical_uuid, "merged": merged}
        })

    except Exception as e:
        logger.error(f"手动合并失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/resolve-duplicates/<graph_id>', methods=['POST'])
def resolve_duplicate_entities(graph_id: str):
    """
    对已构建的图谱执行 LLM 语义去重。

    识别名称不同但实指同一实体的节点（别名、称谓、外号等），
    将重复节点的边转移到规范节点后删除重复节点。

    返回：
        {
            "success": true,
            "data": {
                "merged": 3,
                "groups": [["uuid1", "uuid2"], ...]
            }
        }
    """
    try:
        builder = GraphBuilderService()
        result = builder.resolve_duplicate_entities(graph_id)
        builder.close()

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"实体去重失败: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    获取图谱数据（节点和边）
    """
    try:
        builder = GraphBuilderService()
        graph_data = builder.get_graph_data(graph_id)
        builder.close()

        return jsonify({
            "success": True,
            "data": graph_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    删除图谱（从FalkorDB中删除指定group_id的所有数据）
    """
    try:
        builder = GraphBuilderService()
        builder.delete_graph(graph_id)
        builder.close()

        return jsonify({
            "success": True,
            "message": f"图谱已删除: {graph_id}"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============================================================
# 实体节点/边 直接操作（无需叙事 session）
# ============================================================

@graph_bp.route('/entity-edges/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_edges(graph_id: str, entity_uuid: str):
    """
    获取实体在 FalkorDB 中的所有边（出边+入边）+ 节点基本信息
    不依赖叙事 session，直接按 graph_id 查询
    """
    try:
        from ..services.falkordb_entity_reader import read_entity_edges
        edges = read_entity_edges(group_id=graph_id, entity_uuid=entity_uuid)

        # 同时返回节点基本信息
        node_info = {}
        try:
            from falkordb import FalkorDB
            db = FalkorDB(
                host=Config.FALKORDB_HOST,
                port=Config.FALKORDB_PORT,
                password=Config.FALKORDB_PASSWORD or None,
            )
            graph = db.select_graph(graph_id)
            result = graph.query(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n.name, n.summary, labels(n)",
                {"uuid": entity_uuid}
            )
            if result.result_set:
                row = result.result_set[0]
                all_labels = row[2] if row[2] else []
                custom_label = next((l for l in all_labels if l not in ('Entity', 'Node')), '')
                node_info = {
                    "name": row[0] or "",
                    "summary": row[1] or "",
                    "label": custom_label,
                    "labels": all_labels,
                }
        except Exception as node_err:
            logger.warning(f"获取节点信息失败: {node_err}")

        return jsonify({"success": True, "data": {"edges": edges, "count": len(edges), "node": node_info}})
    except Exception as e:
        logger.error(f"获取实体边失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@graph_bp.route('/entity-node/<graph_id>', methods=['POST'])
def create_entity_node(graph_id: str):
    """
    在 FalkorDB 中创建实体节点及关系边
    Request body: { name, entity_type?, summary?, relationships?: [{name, relation}] }
    """
    try:
        import uuid as uuid_mod
        from falkordb import FalkorDB

        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({"success": False, "error": "缺少必要字段 name"}), 400

        name = data['name']
        entity_type = data.get('entity_type', 'Person')
        summary = data.get('summary', '')

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(graph_id)

        entity_uuid = str(uuid_mod.uuid4())
        label = entity_type if entity_type and entity_type not in ('角色', '') else 'Person'

        graph.query(
            f"CREATE (n:Entity:{label} {{uuid: $uuid, name: $name, summary: $summary}})",
            {"uuid": entity_uuid, "name": name, "summary": summary[:500]}
        )
        logger.info(f"FalkorDB 节点已创建: {name} ({entity_uuid}) in {graph_id}")

        created_edges = []
        for rel in data.get('relationships', []):
            target_name = rel.get('name', '')
            fact_text = rel.get('relation', '')
            rel_type = rel.get('rel_type', 'RELATES_TO') or 'RELATES_TO'
            if not target_name or not fact_text:
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
                        "CREATE (s)-[r:RELATES_TO]->(t) "
                        "SET r.name = $edge_name, r.fact = $fact",
                        {
                            "s_uuid": entity_uuid,
                            "t_uuid": target_uuid,
                            "edge_name": rel_type,
                            "fact": fact_text,
                        }
                    )
                    created_edges.append({"target": target_name, "relation": fact_text})
            except Exception as edge_err:
                logger.warning(f"创建关系边失败 ({target_name}): {edge_err}")

        return jsonify({
            "success": True,
            "data": {
                "entity_uuid": entity_uuid,
                "name": name,
                "label": label,
                "edges_created": len(created_edges)
            }
        })

    except Exception as e:
        logger.error(f"创建实体节点失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@graph_bp.route('/entity-node/<graph_id>/<entity_uuid>', methods=['PUT'])
def update_entity_node(graph_id: str, entity_uuid: str):
    """
    更新 FalkorDB 中实体节点的属性
    Request body: { name?, summary?, label? }
    """
    try:
        from falkordb import FalkorDB

        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "缺少请求体"}), 400

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(graph_id)

        set_parts = []
        params = {'uuid': entity_uuid}

        if 'name' in data:
            set_parts.append("n.name = $name")
            params['name'] = data['name']
        if 'summary' in data:
            set_parts.append("n.summary = $summary")
            params['summary'] = data['summary']

        if set_parts:
            graph.query(
                f"MATCH (n:Entity {{uuid: $uuid}}) SET {', '.join(set_parts)}",
                params
            )

        # 更新 label（需要先移除旧的自定义 label，再添加新的）
        if 'label' in data and data['label']:
            new_label = data['label']
            # 获取当前 labels
            try:
                result = graph.query(
                    "MATCH (n:Entity {uuid: $uuid}) RETURN labels(n)",
                    {"uuid": entity_uuid}
                )
                if result.result_set:
                    current_labels = result.result_set[0][0]
                    for lbl in current_labels:
                        if lbl not in ('Entity', 'Node', new_label):
                            graph.query(
                                f"MATCH (n:Entity {{uuid: $uuid}}) REMOVE n:{lbl}",
                                {"uuid": entity_uuid}
                            )
                    if new_label not in current_labels:
                        graph.query(
                            f"MATCH (n:Entity {{uuid: $uuid}}) SET n:{new_label}",
                            {"uuid": entity_uuid}
                        )
            except Exception as label_err:
                logger.warning(f"更新 label 失败: {label_err}")

        logger.info(f"FalkorDB 节点已更新: {entity_uuid}")
        return jsonify({"success": True, "data": {"message": "节点已更新"}})

    except Exception as e:
        logger.error(f"更新实体节点失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@graph_bp.route('/entity-node/<graph_id>/<entity_uuid>', methods=['DELETE'])
def delete_entity_node(graph_id: str, entity_uuid: str):
    """
    删除 FalkorDB 中的实体节点及其所有关联边（出边+入边）
    """
    try:
        from falkordb import FalkorDB

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(graph_id)

        # 先删除所有关联边（出边+入边）
        graph.query(
            "MATCH (n:Entity {uuid: $uuid})-[r]-() DELETE r",
            {"uuid": entity_uuid}
        )
        # 再删除节点本身
        graph.query(
            "MATCH (n:Entity {uuid: $uuid}) DELETE n",
            {"uuid": entity_uuid}
        )

        logger.info(f"FalkorDB 节点及关联边已删除: {entity_uuid} in {graph_id}")
        return jsonify({"success": True, "data": {"message": "节点及关联边已删除"}})

    except Exception as e:
        logger.error(f"删除实体节点失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@graph_bp.route('/entity-edges/<graph_id>/<entity_uuid>', methods=['PUT'])
def update_entity_edges(graph_id: str, entity_uuid: str):
    """
    更新实体在 FalkorDB 中的关系边
    Request body: { relationships: [{name, relation}] }
    对比现有边：新增不存在的，删除已移除的
    """
    try:
        from falkordb import FalkorDB

        data = request.get_json()
        if not data or 'relationships' not in data:
            return jsonify({"success": False, "error": "缺少 relationships 字段"}), 400

        new_rels = [r for r in data['relationships'] if r.get('name') and r.get('relation')]

        db = FalkorDB(
            host=Config.FALKORDB_HOST,
            port=Config.FALKORDB_PORT,
            password=Config.FALKORDB_PASSWORD or None,
        )
        graph = db.select_graph(graph_id)

        # 读现有出边
        try:
            existing = graph.query(
                "MATCH (s:Entity {uuid: $uuid})-[r]->(t:Entity) "
                "RETURN t.name, id(r)",
                {"uuid": entity_uuid}
            )
            existing_targets = {rec[0]: rec[1] for rec in existing.result_set} if existing.result_set else {}
        except Exception:
            existing_targets = {}

        new_target_names = {r['name'] for r in new_rels}

        # 删除不再存在的边
        for tname, rid in existing_targets.items():
            if tname not in new_target_names:
                try:
                    graph.query(
                        "MATCH (s:Entity {uuid: $uuid})-[r]->(t:Entity {name: $tname}) DELETE r",
                        {"uuid": entity_uuid, "tname": tname}
                    )
                except Exception as e:
                    logger.warning(f"删除边失败 ({tname}): {e}")

        # 新增或更新边
        # Graphiti 约定：Cypher 类型统一为 RELATES_TO，r.name 存语义类型（如 MEMBER_OF），r.fact 存描述文本
        for rel in new_rels:
            target_name = rel['name']
            fact_text = rel['relation']
            rel_type = rel.get('rel_type', 'RELATES_TO') or 'RELATES_TO'
            try:
                find_result = graph.query(
                    "MATCH (t:Entity) WHERE t.name = $name RETURN t.uuid LIMIT 1",
                    {"name": target_name}
                )
                if find_result.result_set:
                    target_uuid = find_result.result_set[0][0]
                    # 先删除已有的旧边
                    graph.query(
                        "MATCH (s:Entity {uuid: $s_uuid})-[r]->(t:Entity {uuid: $t_uuid}) DELETE r",
                        {"s_uuid": entity_uuid, "t_uuid": target_uuid}
                    )
                    graph.query(
                        "MATCH (s:Entity {uuid: $s_uuid}), (t:Entity {uuid: $t_uuid}) "
                        "CREATE (s)-[r:RELATES_TO]->(t) "
                        "SET r.name = $edge_name, r.fact = $fact",
                        {
                            "s_uuid": entity_uuid,
                            "t_uuid": target_uuid,
                            "edge_name": rel_type,
                            "fact": fact_text,
                        }
                    )
            except Exception as e:
                logger.warning(f"创建/更新边失败 ({target_name}): {e}")

        return jsonify({"success": True, "data": {"message": "关系已更新"}})

    except Exception as e:
        logger.error(f"更新实体边失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
