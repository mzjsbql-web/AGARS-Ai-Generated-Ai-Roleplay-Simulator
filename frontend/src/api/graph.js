import service, { requestWithRetry } from './index'

/**
 * 生成本体（上传文档和模拟需求）
 * @param {Object} data - 包含files, simulation_requirement, project_name等
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return requestWithRetry(() => 
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * 构建图谱
 * @param {Object} data - 包含project_id, graph_name等
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * 查询任务状态
 * @param {String} taskId - 任务ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * 获取图谱数据
 * @param {String} graphId - 图谱ID
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * 获取项目信息
 * @param {String} projectId - 项目ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}

/**
 * 获取实体在图谱中的边（出边+入边）
 * @param {String} graphId - 图谱ID
 * @param {String} entityUuid - 实体UUID
 */
export function getEntityEdges(graphId, entityUuid) {
  return service({
    url: `/api/graph/entity-edges/${graphId}/${entityUuid}`,
    method: 'get'
  })
}

/**
 * 更新图谱中实体节点的属性
 * @param {String} graphId - 图谱ID
 * @param {String} entityUuid - 实体UUID
 * @param {Object} data - { name?, summary?, label? }
 */
export function updateEntityNode(graphId, entityUuid, data) {
  return requestWithRetry(() =>
    service({
      url: `/api/graph/entity-node/${graphId}/${entityUuid}`,
      method: 'put',
      data
    })
  )
}

/**
 * 在图谱中创建实体节点及关系边
 * @param {String} graphId - 图谱ID
 * @param {Object} data - { name, entity_type?, summary?, relationships?: [{name, relation}] }
 */
export function createEntityNode(graphId, data) {
  return requestWithRetry(() =>
    service({
      url: `/api/graph/entity-node/${graphId}`,
      method: 'post',
      data
    })
  )
}

/**
 * 更新实体在图谱中的关系边
 * @param {String} graphId - 图谱ID
 * @param {String} entityUuid - 实体UUID
 * @param {Object} data - { relationships: [{name, relation}] }
 */
export function updateEntityEdges(graphId, entityUuid, data) {
  return requestWithRetry(() =>
    service({
      url: `/api/graph/entity-edges/${graphId}/${entityUuid}`,
      method: 'put',
      data
    })
  )
}

/**
 * 删除图谱中的实体节点及其所有关联边
 * @param {String} graphId - 图谱ID
 * @param {String} entityUuid - 实体UUID
 */
export function deleteEntityNode(graphId, entityUuid) {
  return service({
    url: `/api/graph/entity-node/${graphId}/${entityUuid}`,
    method: 'delete'
  })
}

/**
 * 更新图谱中单条边的属性
 * @param {String} graphId - 图谱ID
 * @param {String} edgeUuid - 边UUID
 * @param {Object} data - { name?, fact? }
 */
export function updateEdge(graphId, edgeUuid, data) {
  return requestWithRetry(() =>
    service({
      url: `/api/graph/edge/${graphId}/${edgeUuid}`,
      method: 'put',
      data
    })
  )
}

/**
 * 手动合并节点
 * @param {String} graphId - 图谱ID
 * @param {Array<String>} uuids - 要合并的节点 UUID 列表（至少 2 个）
 * @param {String|null} canonicalUuid - 保留的规范节点 UUID，不填则自动选 summary 最长的
 */
export function mergeEntities(graphId, uuids, canonicalUuid = null) {
  return service({
    url: `/api/graph/merge-entities/${graphId}`,
    method: 'post',
    data: { uuids, canonical_uuid: canonicalUuid || undefined }
  })
}

/**
 * 列出所有项目（用于历史记录展示）
 * @param {number} limit
 */
export function listProjects(limit = 30) {
  return service({ url: '/api/graph/project/list', method: 'get', params: { limit } })
}

/**
 * 更新项目的自定义标题
 * @param {string} projectId
 * @param {string} customTitle
 */
export function renameProject(projectId, customTitle) {
  return service({ url: `/api/graph/project/${projectId}/rename`, method: 'patch', data: { custom_title: customTitle } })
}

/**
 * 删除项目
 * @param {string} projectId
 */
export function deleteProject(projectId) {
  return service({ url: `/api/graph/project/${projectId}`, method: 'delete' })
}
