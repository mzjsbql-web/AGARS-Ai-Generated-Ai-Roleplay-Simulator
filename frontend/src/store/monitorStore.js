/**
 * AI Monitor Store — SSE 连接管理、消息存储、过滤
 */
import { reactive } from 'vue'

const MAX_ENTRIES = 500

const state = reactive({
  isOpen: false,
  entries: [],
  filter: 'all', // 'all' | 'llm' | 'http'
  connected: false,
  autoScroll: true,
})

let eventSource = null

function toggleMonitor() {
  state.isOpen ? closeMonitor() : openMonitor()
}

function openMonitor() {
  state.isOpen = true
  connectSSE()
}

function closeMonitor() {
  state.isOpen = false
  disconnectSSE()
}

function connectSSE() {
  if (eventSource) return
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'
  eventSource = new EventSource(`${baseURL}/api/monitor/stream`)

  eventSource.onopen = () => {
    state.connected = true
  }

  eventSource.onmessage = (event) => {
    try {
      const entry = JSON.parse(event.data)
      pushEntry(entry)
    } catch {
      // ignore parse errors
    }
  }

  eventSource.onerror = () => {
    state.connected = false
    // browser will auto-reconnect EventSource
  }
}

function disconnectSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  state.connected = false
}

function pushEntry(entry) {
  state.entries.push(entry)
  if (state.entries.length > MAX_ENTRIES) {
    state.entries.splice(0, state.entries.length - MAX_ENTRIES)
  }
}

function addHttpEntry(entry) {
  pushEntry(entry)
}

function setFilter(f) {
  state.filter = f
}

function clearEntries() {
  state.entries.splice(0, state.entries.length)
  // also clear server-side
  const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'
  fetch(`${baseURL}/api/monitor/clear`, { method: 'POST' }).catch(() => {})
}

export {
  state,
  toggleMonitor,
  openMonitor,
  closeMonitor,
  addHttpEntry,
  setFilter,
  clearEntries,
}
