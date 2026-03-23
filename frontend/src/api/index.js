import axios from 'axios'
import { addHttpEntry } from '../store/monitorStore'

let _clientIdCounter = 0

// 创建axios实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000, // 5分钟超时（本体生成可能需要较长时间）
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
service.interceptors.request.use(
  config => {
    try {
      config._monitorStartTime = Date.now()
      config._monitorId = `http_${++_clientIdCounter}`
      addHttpEntry({
        _clientId: config._monitorId,
        type: 'http_request',
        timestamp: Date.now() / 1000,
        method: config.method?.toUpperCase(),
        url: (config.baseURL || '') + (config.url || ''),
        requestData: config.data,
      })
    } catch { /* monitor must not break normal flow */ }
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器（容错重试机制）
service.interceptors.response.use(
  response => {
    try {
      const duration = response.config._monitorStartTime
        ? Date.now() - response.config._monitorStartTime
        : null
      addHttpEntry({
        _clientId: `http_${++_clientIdCounter}`,
        type: 'http_response',
        timestamp: Date.now() / 1000,
        method: response.config.method?.toUpperCase(),
        url: (response.config.baseURL || '') + (response.config.url || ''),
        status: response.status,
        duration_ms: duration,
        responseData: response.data,
      })
    } catch { /* monitor must not break normal flow */ }

    const res = response.data

    // 如果返回的状态码不是success，则抛出错误
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }

    return res
  },
  error => {
    try {
      const config = error.config || {}
      const duration = config._monitorStartTime
        ? Date.now() - config._monitorStartTime
        : null
      addHttpEntry({
        _clientId: `http_${++_clientIdCounter}`,
        type: 'http_error',
        timestamp: Date.now() / 1000,
        method: config.method?.toUpperCase(),
        url: (config.baseURL || '') + (config.url || ''),
        status: error.response?.status,
        duration_ms: duration,
        error: error.message,
      })
    } catch { /* monitor must not break normal flow */ }

    console.error('Response error:', error)

    // 处理超时
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }

    // 处理网络错误
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }

    return Promise.reject(error)
  }
)

// 带重试的请求函数
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error

      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
