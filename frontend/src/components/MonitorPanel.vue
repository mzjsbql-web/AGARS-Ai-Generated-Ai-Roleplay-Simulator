<template>
  <Teleport to="body">
    <Transition name="slide">
      <div v-if="store.isOpen" class="monitor-overlay" @click.self="closeMonitor">
        <div class="monitor-panel">
          <!-- Header -->
          <div class="monitor-header">
            <div class="header-left">
              <span class="header-title">AI Monitor</span>
              <span :class="['status-dot', store.connected ? 'connected' : 'disconnected']"></span>
            </div>
            <div class="header-right">
              <button class="header-btn" @click="clearEntries" title="Clear">Clear</button>
              <button class="header-btn close-btn" @click="closeMonitor" title="Close">&times;</button>
            </div>
          </div>

          <!-- Filter tabs -->
          <div class="filter-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.value"
              :class="['tab-btn', { active: store.filter === tab.value }]"
              @click="setFilter(tab.value)"
            >
              {{ tab.label }}
              <span class="tab-count">{{ countByFilter(tab.value) }}</span>
            </button>
          </div>

          <!-- Entry list -->
          <div class="entry-list" ref="entryList">
            <div
              v-for="entry in filteredEntries"
              :key="entry.id || entry._clientId"
              :class="['entry-item', entry.type]"
              @click="toggleExpand(entry)"
            >
              <div class="entry-summary">
                <span class="entry-badge" :class="entry.type">{{ badgeText(entry) }}</span>
                <span class="entry-source">{{ entry.source || entry.method || '' }}</span>
                <span class="entry-model" v-if="entry.model">{{ entry.model }}</span>
                <span class="entry-url" v-if="entry.url">{{ truncate(entry.url, 40) }}</span>
                <span class="entry-status" v-if="entry.status" :class="statusClass(entry.status)">{{ entry.status }}</span>
                <span class="entry-duration" v-if="entry.duration_ms">{{ Math.round(entry.duration_ms) }}ms</span>
                <span class="entry-error" v-if="entry.error">ERR</span>
                <span class="entry-time">{{ formatTime(entry.timestamp) }}</span>
              </div>

              <!-- Collapsed preview -->
              <div class="entry-preview" v-if="!isExpanded(entry)">
                {{ previewText(entry) }}
              </div>

              <!-- Expanded content -->
              <div class="entry-detail" v-if="isExpanded(entry)" @click.stop>
                <!-- LLM entry -->
                <template v-if="entry.type === 'llm'">
                  <div class="detail-section" v-if="entry.messages">
                    <div class="detail-label">Messages</div>
                    <pre class="detail-content">{{ formatJSON(entry.messages) }}</pre>
                  </div>
                  <div class="detail-section" v-if="entry.response">
                    <div class="detail-label">Response</div>
                    <pre class="detail-content">{{ entry.response }}</pre>
                  </div>
                  <div class="detail-section" v-if="entry.tokens">
                    <div class="detail-label">Tokens</div>
                    <pre class="detail-content">{{ formatJSON(entry.tokens) }}</pre>
                  </div>
                  <div class="detail-section" v-if="entry.error">
                    <div class="detail-label">Error</div>
                    <pre class="detail-content error-text">{{ entry.error }}</pre>
                  </div>
                </template>

                <!-- HTTP entry -->
                <template v-else>
                  <div class="detail-section" v-if="entry.url">
                    <div class="detail-label">URL</div>
                    <pre class="detail-content">{{ entry.method }} {{ entry.url }}</pre>
                  </div>
                  <div class="detail-section" v-if="entry.requestData">
                    <div class="detail-label">Request</div>
                    <pre class="detail-content">{{ formatJSON(entry.requestData) }}</pre>
                  </div>
                  <div class="detail-section" v-if="entry.responseData">
                    <div class="detail-label">Response</div>
                    <pre class="detail-content">{{ formatJSON(entry.responseData) }}</pre>
                  </div>
                  <div class="detail-section" v-if="entry.error">
                    <div class="detail-label">Error</div>
                    <pre class="detail-content error-text">{{ entry.error }}</pre>
                  </div>
                </template>
              </div>
            </div>

            <div class="empty-state" v-if="filteredEntries.length === 0">
              No entries yet. Trigger an AI operation to see traffic here.
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { state as store, closeMonitor, setFilter, clearEntries } from '../store/monitorStore'

const tabs = [
  { label: 'All', value: 'all' },
  { label: 'LLM Calls', value: 'llm' },
  { label: 'HTTP', value: 'http' },
]

const expandedIds = ref(new Set())
const entryList = ref(null)

const filteredEntries = computed(() => {
  if (store.filter === 'all') return store.entries
  return store.entries.filter(e => {
    if (store.filter === 'llm') return e.type === 'llm'
    if (store.filter === 'http') return e.type?.startsWith('http')
    return true
  })
})

function countByFilter(f) {
  if (f === 'all') return store.entries.length
  return store.entries.filter(e => {
    if (f === 'llm') return e.type === 'llm'
    if (f === 'http') return e.type?.startsWith('http')
    return true
  }).length
}

function toggleExpand(entry) {
  const id = entry.id || entry._clientId
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

function isExpanded(entry) {
  return expandedIds.value.has(entry.id || entry._clientId)
}

function badgeText(entry) {
  if (entry.type === 'llm') return 'LLM'
  if (entry.type === 'http_request') return 'REQ'
  if (entry.type === 'http_response') return 'RES'
  if (entry.type === 'http_error') return 'ERR'
  return entry.type?.toUpperCase() || '?'
}

function statusClass(status) {
  if (status >= 200 && status < 300) return 'status-ok'
  if (status >= 400) return 'status-err'
  return ''
}

function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

function previewText(entry) {
  if (entry.type === 'llm') {
    if (entry.error) return `Error: ${truncate(entry.error, 200)}`
    return truncate(entry.response || '', 200)
  }
  if (entry.responseData) return truncate(JSON.stringify(entry.responseData), 200)
  if (entry.requestData) return truncate(JSON.stringify(entry.requestData), 200)
  return ''
}

function formatJSON(obj) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts)
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// Auto-scroll when new entries arrive
watch(
  () => store.entries.length,
  () => {
    if (store.autoScroll && entryList.value) {
      nextTick(() => {
        entryList.value.scrollTop = entryList.value.scrollHeight
      })
    }
  }
)
</script>

<style scoped>
.monitor-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(0, 0, 0, 0.3);
}

.monitor-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 480px;
  background: #111;
  color: #e0e0e0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.5);
}

/* Header */
.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #333;
  background: #1a1a1a;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-title {
  font-size: 14px;
  font-weight: 700;
  color: #fff;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.connected {
  background: #4caf50;
}
.status-dot.disconnected {
  background: #666;
}
.header-right {
  display: flex;
  gap: 8px;
}
.header-btn {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
}
.header-btn:hover {
  color: #fff;
  border-color: #666;
}
.close-btn {
  font-size: 18px;
  line-height: 1;
  padding: 2px 8px;
}

/* Filter tabs */
.filter-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #333;
  background: #1a1a1a;
  flex-shrink: 0;
}
.tab-btn {
  flex: 1;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: #888;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
  transition: color 0.2s, border-color 0.2s;
}
.tab-btn:hover {
  color: #ccc;
}
.tab-btn.active {
  color: #fff;
  border-bottom-color: #ff6b00;
}
.tab-count {
  margin-left: 4px;
  opacity: 0.5;
}

/* Entry list */
.entry-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.entry-item {
  border-bottom: 1px solid #222;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.entry-item:hover {
  background: #1a1a1a;
}

.entry-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.entry-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}
.entry-badge.llm {
  background: #2d1f5e;
  color: #b39ddb;
}
.entry-badge.http_request {
  background: #1a3a1a;
  color: #81c784;
}
.entry-badge.http_response {
  background: #1a2a3a;
  color: #64b5f6;
}
.entry-badge.http_error {
  background: #3a1a1a;
  color: #e57373;
}

.entry-source {
  color: #aaa;
  font-size: 11px;
}
.entry-model {
  color: #ff9800;
  font-size: 11px;
}
.entry-url {
  color: #888;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry-status.status-ok {
  color: #4caf50;
}
.entry-status.status-err {
  color: #e57373;
}
.entry-duration {
  color: #666;
  font-size: 10px;
  margin-left: auto;
}
.entry-error {
  color: #e57373;
  font-size: 10px;
  font-weight: 700;
}
.entry-time {
  color: #555;
  font-size: 10px;
  margin-left: auto;
  flex-shrink: 0;
}

.entry-preview {
  color: #666;
  font-size: 11px;
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* Detail */
.entry-detail {
  margin-top: 8px;
}
.detail-section {
  margin-bottom: 8px;
}
.detail-label {
  color: #888;
  font-size: 10px;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.detail-content {
  background: #0a0a0a;
  border: 1px solid #222;
  border-radius: 4px;
  padding: 8px;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 400px;
  overflow-y: auto;
  color: #ccc;
  margin: 0;
  font-family: inherit;
}
.error-text {
  color: #e57373;
}

.empty-state {
  color: #555;
  text-align: center;
  padding: 40px 20px;
  font-size: 12px;
}

/* Slide transition */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.25s ease;
}
.slide-enter-from .monitor-panel,
.slide-leave-to .monitor-panel {
  transform: translateX(100%);
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
}

/* Scrollbar inside panel */
.entry-list::-webkit-scrollbar {
  width: 6px;
}
.entry-list::-webkit-scrollbar-track {
  background: #111;
}
.entry-list::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 3px;
}
.detail-content::-webkit-scrollbar {
  width: 4px;
}
.detail-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}
</style>
