import service, { requestWithRetry } from './index'

/**
 * 上传小说文件，生成前文摘要（续写模式）
 * @param {File} file - pdf/txt/md 文件对象
 */
export const summarizeFile = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return service.post('/api/narrative/summarize_file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000  // 摘要生成可能较慢，5 分钟
  })
}

/**
 * 创建叙事会话
 * @param {Object} data - { project_id, graph_id, player_entity_uuid, initial_scene?, opening_text?, prior_summary?, max_npc_turns? }
 */
export const createNarrative = (data) => {
  return requestWithRetry(() => service.post('/api/narrative/create', data), 3, 1000)
}

/**
 * 准备叙事会话（异步：读取实体、生成角色档案）
 * @param {Object} data - { session_id, entity_types?, parallel_count? }
 */
export const prepareNarrative = (data) => {
  return requestWithRetry(() => service.post('/api/narrative/prepare', data), 3, 1000)
}

/**
 * 查询准备任务进度
 * @param {Object} data - { task_id? | session_id? }
 */
export const getPrepareStatus = (data) => {
  return service.post('/api/narrative/prepare/status', data)
}

/**
 * 获取完整会话状态
 * @param {string} sessionId
 */
export const getNarrativeSession = (sessionId) => {
  return service.get(`/api/narrative/${sessionId}`)
}

/**
 * 获取角色档案列表
 * @param {string} sessionId
 */
export const getNarrativeProfiles = (sessionId) => {
  return service.get(`/api/narrative/${sessionId}/profiles`)
}

/**
 * 获取会话状态（轮询用）
 * @param {string} sessionId
 */
export const getNarrativeStatus = (sessionId) => {
  return service.get(`/api/narrative/${sessionId}/status`)
}

/**
 * 获取叙事文本段落（增量）
 * @param {string} sessionId
 * @param {number} fromSegment - 从第 N 段开始
 */
export const getNarrativeText = (sessionId, fromSegment = 0) => {
  return service.get(`/api/narrative/${sessionId}/narrative`, {
    params: { from_segment: fromSegment }
  })
}

/**
 * 获取背景事件列表（增量）
 * @param {string} sessionId
 * @param {number} fromTurn - 从第 N 回合开始
 */
export const getNarrativeEvents = (sessionId, fromTurn = 0) => {
  return service.get(`/api/narrative/${sessionId}/events`, {
    params: { from_turn: fromTurn }
  })
}

/**
 * 更新叙事会话基本信息（player_entity_uuid, initial_scene, opening_text）
 * @param {string} sessionId
 * @param {Object} data - { player_entity_uuid?, initial_scene?, opening_text? }
 */
export const updateNarrativeSession = (sessionId, data) => {
  return service.patch(`/api/narrative/${sessionId}/update`, data)
}

/**
 * 更新存档的自定义标题
 * @param {string} sessionId
 * @param {string} saveId
 * @param {string} customTitle
 */
export const renameNarrativeSave = (sessionId, saveId, customTitle) => {
  return service.patch(`/api/narrative/${sessionId}/saves/${saveId}/rename`, { custom_title: customTitle })
}

/**
 * 启动叙事引擎
 * @param {Object} data - { session_id }
 */
export const startNarrative = (data) => {
  return requestWithRetry(() => service.post('/api/narrative/start', data), 3, 1000)
}

/**
 * 停止叙事引擎
 * @param {Object} data - { session_id }
 */
export const stopNarrative = (data) => {
  return service.post('/api/narrative/stop', data)
}

/**
 * 提交玩家输入
 * @param {Object} data - { session_id, choice_id?, free_text? }
 */
export const submitPlayerInput = (data) => {
  return requestWithRetry(() => service.post('/api/narrative/player-input', data), 3, 1000)
}

/**
 * 获取叙事历史列表
 * @param {number} limit - 最大数量
 */
export const getNarrativeHistory = (limit = 20) => {
  return service.get('/api/narrative/history', { params: { limit } })
}

/**
 * 删除叙事会话
 * @param {string} sessionId
 */
export const deleteNarrativeSession = (sessionId) => {
  return service.delete(`/api/narrative/${sessionId}`)
}

/**
 * 恢复叙事会话（从存档加载 + 重启引擎）
 * @param {Object} data - { session_id }
 */
export const resumeNarrative = (data) => {
  return requestWithRetry(() => service.post('/api/narrative/resume', data), 3, 1000)
}

/**
 * 手动存档（创建新存档快照）
 * @param {string} sessionId
 */
export const saveNarrative = (sessionId) => {
  return service.post(`/api/narrative/${sessionId}/save`)
}

/**
 * 获取存档列表
 * @param {string} sessionId
 */
export const listNarrativeSaves = (sessionId) => {
  return service.get(`/api/narrative/${sessionId}/saves`)
}

/**
 * 从指定存档读取
 * @param {string} sessionId
 * @param {string} saveId
 */
export const loadNarrativeSave = (sessionId, saveId) => {
  return service.post(`/api/narrative/${sessionId}/saves/${saveId}/load`)
}

/**
 * 删除指定存档
 * @param {string} sessionId
 * @param {string} saveId
 */
export const deleteNarrativeSave = (sessionId, saveId) => {
  return service.delete(`/api/narrative/${sessionId}/saves/${saveId}`)
}

/**
 * 更新角色档案
 * @param {string} sessionId
 * @param {string} entityUuid
 * @param {Object} data - 要更新的字段
 */
export const updateNarrativeProfile = (sessionId, entityUuid, data) => {
  return requestWithRetry(() => service.put(`/api/narrative/${sessionId}/profiles/${entityUuid}`, data), 3, 1000)
}

/**
 * 添加新角色
 * @param {string} sessionId
 * @param {Object} data - 角色信息
 */
export const addNarrativeProfile = (sessionId, data) => {
  return requestWithRetry(() => service.post(`/api/narrative/${sessionId}/profiles`, data), 3, 1000)
}

export const deleteNarrativeProfile = (sessionId, entityUuid) => {
  return service.delete(`/api/narrative/${sessionId}/profiles/${entityUuid}`)
}
