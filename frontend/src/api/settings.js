/**
 * Settings API - Prompt 配置管理
 */
import service from './index'

/** 获取所有 prompt 配置 */
export const getPrompts = () => {
  return service({ url: '/api/settings/prompts', method: 'get' })
}

/** 获取 Prompt 变量参考表 */
export const getPromptVariables = () => {
  return service({ url: '/api/settings/prompt-variables', method: 'get' })
}

/** 更新单个 prompt */
export const updatePrompt = (key, data) => {
  return service({ url: `/api/settings/prompts/${key}`, method: 'put', data })
}

/** 重置 prompt（传 key 重置单个，不传重置全部） */
export const resetPrompt = (key = null) => {
  return service({ url: '/api/settings/prompts/reset', method: 'post', data: { key } })
}

// ============================================================
// 叙事引擎配置
// ============================================================

/** 获取叙事引擎所有配置 */
export const getNarrativeEngineSettings = () => {
  return service({ url: '/api/settings/narrative-engine', method: 'get' })
}

/** 更新单个叙事引擎配置 */
export const updateNarrativeEngineSetting = (key, value) => {
  return service({ url: `/api/settings/narrative-engine/${key}`, method: 'put', data: { value } })
}

/** 重置叙事引擎配置（传 key 重置单个，不传重置全部） */
export const resetNarrativeEngineSetting = (key = null) => {
  return service({ url: '/api/settings/narrative-engine/reset', method: 'post', data: { key } })
}

/** 获取所有可用 LLM profile（从 .env 读取） */
export const getLlmProfiles = () => {
  return service({ url: '/api/settings/llm-profiles', method: 'get' })
}

// ============================================================
// 全局 API 配置（直接对应 .env）
// ============================================================

/** 获取 .env 中的基础 API 配置 */
export const getEnvConfig = () => {
  return service({ url: '/api/settings/env-config', method: 'get' })
}

/** 保存基础 API 配置到 .env */
export const updateEnvConfig = (data) => {
  return service({ url: '/api/settings/env-config', method: 'post', data })
}

/** 通过 base_url + api_key 拉取可用模型列表 */
export const fetchModels = (data) => {
  return service({ url: '/api/settings/fetch-models', method: 'post', data })
}
