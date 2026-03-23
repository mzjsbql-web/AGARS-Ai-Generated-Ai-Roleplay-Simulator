<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')"><span style="color:#FF4500">A</span>GARS</div>
      </div>

      <div class="header-center">
        <div class="view-switcher">
          <button
            v-for="mode in ['graph', 'split', 'narrative']"
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: '图谱', split: '双栏', narrative: '叙事' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Narrative</span>
          <span class="step-name">叙事模式</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
        <button class="gear-btn" @click="showSettings = true" title="设置">
          <svg class="gear-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 设置弹窗 -->
    <SettingsModal :visible="showSettings" @close="showSettings = false" />

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="3"
          :isSimulating="isActive"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Narrative Player -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <NarrativePlayer
          :sessionId="currentSessionId"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import NarrativePlayer from '../components/NarrativePlayer.vue'
import SettingsModal from '../components/SettingsModal.vue'
import { getProject, getGraphData } from '../api/graph'
import { getNarrativeSession, stopNarrative, prepareNarrative, getPrepareStatus, startNarrative, resumeNarrative, loadNarrativeSave } from '../api/narrative'

const route = useRoute()
const router = useRouter()

const props = defineProps({
  sessionId: String
})

// 设置弹窗
const showSettings = ref(false)

// Layout
const viewMode = ref('split')

// Data
const currentSessionId = ref(route.params.sessionId)
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error

// --- Computed Layout ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'narrative') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '30%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'narrative') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '70%', opacity: 1, transform: 'translateX(0)' }
})

const statusClass = computed(() => currentStatus.value)

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  return 'Running'
})

const isActive = computed(() => currentStatus.value === 'processing')

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) systemLogs.value.shift()
}

const updateStatus = (status) => {
  currentStatus.value = status
}

const toggleMaximize = (target) => {
  viewMode.value = viewMode.value === target ? 'split' : target
}

// --- Data Loading ---
const loadSessionData = async () => {
  try {
    addLog(`加载叙事会话: ${currentSessionId.value}`)

    // 若携带存档 ID，先恢复存档快照
    const saveId = route.query.saveId
    if (saveId) {
      addLog(`读取存档: ${saveId}`)
      try {
        const loadRes = await loadNarrativeSave(currentSessionId.value, saveId)
        if (loadRes.success) {
          addLog(`存档已恢复，当前回合: ${loadRes.data?.current_turn ?? '?'}`)
        } else {
          addLog(`存档读取失败: ${loadRes.error || '未知错误'}，将直接恢复会话`)
        }
      } catch (loadErr) {
        addLog(`存档读取异常: ${loadErr.message}，将直接恢复会话`)
      }
    }

    const res = await getNarrativeSession(currentSessionId.value)
    if (res.success && res.data) {
      const sessionData = res.data
      if (sessionData.project_id) {
        const projRes = await getProject(sessionData.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          if (projRes.data.graph_id) {
            await loadGraph(projRes.data.graph_id)
          }
        }
      }

      // 如果玩家角色尚未选择（step2 阶段创建的临时会话），自动返回主页
      if (sessionData.player_entity_uuid === 'pending') {
        addLog('叙事会话尚未完成配置（未选择玩家角色），正在返回主页...')
        router.push('/')
        return
      }

      // 若已通过存档恢复，跳过 prepare/start 流程直接返回
      if (saveId) return

      // 根据会话状态决定启动方式
      if (sessionData.status === 'prepared') {
        // 已完成 prepare（Step 2 生成过角色档案），直接启动引擎
        addLog('角色档案已就绪，启动叙事引擎...')
        const startRes = await startNarrative({ session_id: currentSessionId.value })
        if (startRes.success) {
          addLog('叙事引擎已启动')
        } else {
          addLog(`启动引擎失败: ${startRes.error || '未知错误'}`)
          currentStatus.value = 'error'
        }
      } else if (sessionData.status === 'idle') {
        // 新会话：prepare → start 流程
        addLog('开始准备叙事环境...')

        // Step 1: prepare
        const prepRes = await prepareNarrative({ session_id: currentSessionId.value })
        if (!prepRes.success) {
          addLog(`准备失败: ${prepRes.error || '未知错误'}`)
          currentStatus.value = 'error'
          return
        }

        const taskId = prepRes.data.task_id
        addLog(`准备任务已提交: ${taskId}`)

        // Step 2: poll prepare status
        await new Promise((resolve, reject) => {
          const poll = setInterval(async () => {
            try {
              const statusRes = await getPrepareStatus({ task_id: taskId })
              if (statusRes.success && statusRes.data) {
                if (statusRes.data.message) {
                  addLog(`准备进度: ${statusRes.data.message}`)
                }
                if (statusRes.data.status === 'completed') {
                  clearInterval(poll)
                  resolve()
                } else if (statusRes.data.status === 'failed') {
                  clearInterval(poll)
                  reject(new Error(statusRes.data.error || '准备失败'))
                }
              }
            } catch (pollErr) {
              clearInterval(poll)
              reject(pollErr)
            }
          }, 2000)
        })

        addLog('角色档案准备完成，启动叙事引擎...')

        // Step 3: start engine
        const startRes = await startNarrative({ session_id: currentSessionId.value })
        if (startRes.success) {
          addLog('叙事引擎已启动')
        } else {
          addLog(`启动引擎失败: ${startRes.error || '未知错误'}`)
          currentStatus.value = 'error'
        }
      } else if (['completed', 'failed', 'running', 'awaiting_player'].includes(sessionData.status)) {
        // 已结束或运行中的会话：调用 resume（引擎会判断是否需要重启线程）
        const turnInfo = sessionData.current_turn > 0 ? `（回合 ${sessionData.current_turn}）` : ''
        addLog(`恢复叙事引擎${turnInfo}...`)
        try {
          const resumeRes = await resumeNarrative({ session_id: currentSessionId.value })
          if (resumeRes.success) {
            addLog(`叙事引擎已恢复，当前回合: ${resumeRes.data?.current_turn ?? sessionData.current_turn}`)
          }
        } catch (resumeErr) {
          // resume 失败不影响现有内容的显示，只记录日志
          addLog(`恢复引擎失败（不影响已有内容）: ${resumeErr.message}`)
        }
      }
    }
  } catch (err) {
    addLog(`加载异常: ${err.message}`)
    currentStatus.value = 'error'
  }
}

const loadGraph = async (graphId) => {
  if (!isActive.value) graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (res.success) graphData.value = res.data
  } catch (err) {
    addLog(`图谱加载失败: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) loadGraph(projectData.value.graph_id)
}

// --- Auto Graph Refresh ---
let graphRefreshTimer = null

const startGraphRefresh = () => {
  if (graphRefreshTimer) return
  graphRefreshTimer = setInterval(refreshGraph, 30000)
}

const stopGraphRefresh = () => {
  if (graphRefreshTimer) {
    clearInterval(graphRefreshTimer)
    graphRefreshTimer = null
  }
}

watch(isActive, (val) => {
  if (val) startGraphRefresh()
  else stopGraphRefresh()
}, { immediate: true })

onMounted(() => {
  addLog('NarrativeView 初始化')
  loadSessionData()
})

onUnmounted(() => {
  stopGraphRefresh()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

.header-save-btn {
  margin-left: 8px;
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #1565C0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.header-save-btn:hover:not(:disabled) { background: #E3F2FD; border-color: #1565C0; }
.header-save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.header-save-btn.save-success { background: #E8F5E9; color: #2E7D32; border-color: #4CAF50; }

.gear-btn {
  width: 30px;
  height: 30px;
  border: 1px solid #E0E0E0;
  background: #FFF;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  transition: all 0.2s;
  padding: 0;
}
.gear-btn:hover { border-color: #999; color: #000; }
.gear-icon { width: 15px; height: 15px; }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid #EAEAEA;
}
</style>
