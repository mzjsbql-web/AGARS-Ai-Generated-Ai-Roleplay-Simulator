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
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: '图谱', split: '双栏', workbench: '工作台' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step 2/5</span>
          <span class="step-name">环境搭建</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
        <button
          v-if="currentSimulationId"
          class="header-save-btn"
          :class="{ 'save-success': saveSuccess }"
          @click="handleSave"
          :disabled="saving"
        >
          {{ saveSuccess ? '已存档 ✓' : (saving ? '...' : '存档') }}
        </button>

        <!-- 存档通知 -->
        <Transition name="notif-fade">
          <div v-if="saveNotification" class="save-notification">
            <span class="notif-icon">✓</span>
            <span class="notif-text">{{ saveNotification }}</span>
          </div>
        </Transition>
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
          :currentPhase="2"
          :highlightNodeId="highlightedNodeId"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step2 环境搭建 -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <Step2EnvSetup
          :simulationId="currentSimulationId"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          :narrativeMode="isNarrativeMode"
          :narrativeSessionId="narrativeSessionIdFromRoute"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
          @highlight-graph-node="handleHighlightNode"
          @narrative-session-created="onNarrativeSessionCreated"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import SettingsModal from '../components/SettingsModal.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation, stopSimulation, getEnvStatus, closeSimulationEnv } from '../api/simulation'
import { createNarrative, updateNarrativeSession, saveNarrative } from '../api/narrative'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  simulationId: String
})

// 设置弹窗
const showSettings = ref(false)

// 存档
const saving = ref(false)
const saveSuccess = ref(false)
const saveNotification = ref('')
let saveTimer = null
let saveNotifTimer = null

const handleSave = async () => {
  if (saving.value) return
  saving.value = true
  saveSuccess.value = false

  // narrative 模式：调用叙事存档 API，创建独立存档条目
  if (isNarrativeMode.value && effectiveNarrativeSessionId.value) {
    try {
      const res = await saveNarrative(effectiveNarrativeSessionId.value)
      if (res.success) {
        addLog(`存档成功（回合${res.data?.turn ?? 0}）`)
        saveNotification.value = `存档已创建 · 主页历史记录可查看`
      } else {
        addLog(`存档失败: ${res.error || '未知错误'}`)
        saveNotification.value = `存档失败`
      }
    } catch (err) {
      addLog(`存档失败: ${err.message}`)
      saveNotification.value = `存档失败`
    }
  } else {
    // 非 narrative 模式：原有逻辑（URL 复制到剪贴板）
    try {
      await navigator.clipboard.writeText(window.location.href)
    } catch { /* clipboard may fail on http */ }
    const shortId = currentSimulationId.value?.slice(0, 8) ?? ''
    saveNotification.value = `环境已保存（ID: ${shortId}…）· 返回主页可在历史记录中找到此项目`
    addLog(`存档成功：模拟 ${currentSimulationId.value}`)
  }

  saveSuccess.value = true
  if (saveTimer) clearTimeout(saveTimer)
  if (saveNotifTimer) clearTimeout(saveNotifTimer)
  saveTimer = setTimeout(() => { saveSuccess.value = false }, 2000)
  saveNotifTimer = setTimeout(() => { saveNotification.value = '' }, 5000)
  saving.value = false
}

// Layout State
const viewMode = ref('split')

// Data State
const currentSimulationId = ref(route.params.simulationId)
const isNarrativeMode = computed(() => route.query.mode === 'narrative')
const narrativeSessionIdFromRoute = computed(() => route.query.sessionId || null)
const localNarrativeSessionId = ref(null)  // step2 期间由子组件创建的 session id
const effectiveNarrativeSessionId = computed(
  () => localNarrativeSessionId.value || narrativeSessionIdFromRoute.value || null
)

const onNarrativeSessionCreated = (sessionId) => {
  localNarrativeSessionId.value = sessionId
}
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error
const highlightedNodeId = ref(null)

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Ready'
  return 'Preparing'
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

const handleHighlightNode = (nodeId) => {
  highlightedNodeId.value = nodeId
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleGoBack = () => {
  // 返回到 process 页面
  if (projectData.value?.project_id) {
    router.push({ name: 'Process', params: { projectId: projectData.value.project_id } })
  } else {
    router.push('/')
  }
}

const handleNextStep = async (params = {}) => {
  // Narrative 分支：更新已有会话或创建新会话，然后跳转
  if (params.narrativeMode && params.playerEntityUuid) {
    try {
      let sessionId = params.narrativeSessionId

      if (sessionId) {
        // 会话已在 step2 阶段创建，更新 player_entity_uuid 和开篇设定
        addLog('正在更新叙事会话设定...')
        const updatePayload = {
          player_entity_uuid: params.playerEntityUuid,
          initial_scene: params.initialScene || '一个充满未知与冒险的世界'
        }
        if (params.openingText) {
          updatePayload.opening_text = params.openingText
        }
        if (params.priorSummary) {
          updatePayload.prior_summary = params.priorSummary
        }
        await updateNarrativeSession(sessionId, updatePayload)
        addLog(`Narrative 会话已更新: ${sessionId}`)
      } else {
        // 兜底：如果没有现成的会话，仍然创建新的
        addLog('进入叙事模式，创建 Narrative 会话...')
        const payload = {
          project_id: projectData.value?.project_id,
          graph_id: projectData.value?.graph_id,
          player_entity_uuid: params.playerEntityUuid,
          initial_scene: params.initialScene || '一个充满未知与冒险的世界'
        }
        if (params.openingText) {
          payload.opening_text = params.openingText
        }
        if (params.priorSummary) {
          payload.prior_summary = params.priorSummary
        }
        const res = await createNarrative(payload)
        if (res.success && res.data?.session_id) {
          sessionId = res.data.session_id
          addLog(`Narrative 会话已创建: ${sessionId}`)
        } else {
          addLog(`创建叙事会话失败: ${res.error || '未知错误'}`)
          alert('创建叙事会话失败: ' + (res.error || '未知错误'))
          return
        }
      }

      router.push({ name: 'Narrative', params: { sessionId: sessionId } })
    } catch (err) {
      addLog(`叙事会话异常: ${err.message}`)
      alert('叙事会话异常: ' + err.message)
    }
    return
  }

  // OASIS 分支：跳转到 SimulationRun
  addLog('进入 Step 3: 开始模拟')

  if (params.maxRounds) {
    addLog(`自定义模拟轮数: ${params.maxRounds} 轮`)
  } else {
    addLog('使用自动配置的模拟轮数')
  }

  const routeParams = {
    name: 'SimulationRun',
    params: { simulationId: currentSimulationId.value }
  }

  if (params.maxRounds) {
    routeParams.query = { maxRounds: params.maxRounds }
  }

  router.push(routeParams)
}

// --- Data Logic ---

/**
 * 检查并关闭正在运行的模拟
 * 当用户从 Step 3 返回到 Step 2 时，默认用户要退出模拟
 */
const checkAndStopRunningSimulation = async () => {
  if (!currentSimulationId.value) return
  
  try {
    // 先检查模拟环境是否存活
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      addLog('检测到模拟环境正在运行，正在关闭...')
      
      // 尝试优雅关闭模拟环境
      try {
        const closeRes = await closeSimulationEnv({ 
          simulation_id: currentSimulationId.value,
          timeout: 10  // 10秒超时
        })
        
        if (closeRes.success) {
          addLog('✓ 模拟环境已关闭')
        } else {
          addLog(`关闭模拟环境失败: ${closeRes.error || '未知错误'}`)
          // 如果优雅关闭失败，尝试强制停止
          await forceStopSimulation()
        }
      } catch (closeErr) {
        addLog(`关闭模拟环境异常: ${closeErr.message}`)
        // 如果优雅关闭异常，尝试强制停止
        await forceStopSimulation()
      }
    } else {
      // 环境未运行，但可能进程还在，检查模拟状态
      const simRes = await getSimulation(currentSimulationId.value)
      if (simRes.success && simRes.data?.status === 'running') {
        addLog('检测到模拟状态为运行中，正在停止...')
        await forceStopSimulation()
      }
    }
  } catch (err) {
    // 检查环境状态失败不影响后续流程
    console.warn('检查模拟状态失败:', err)
  }
}

/**
 * 强制停止模拟
 */
const forceStopSimulation = async () => {
  try {
    const stopRes = await stopSimulation({ simulation_id: currentSimulationId.value })
    if (stopRes.success) {
      addLog('✓ 模拟已强制停止')
    } else {
      addLog(`强制停止模拟失败: ${stopRes.error || '未知错误'}`)
    }
  } catch (err) {
    addLog(`强制停止模拟异常: ${err.message}`)
  }
}

const loadSimulationData = async () => {
  try {
    addLog(`加载模拟数据: ${currentSimulationId.value}`)
    
    // 获取 simulation 信息
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      const simData = simRes.data
      
      // 获取 project 信息
      if (simData.project_id) {
        const projRes = await getProject(simData.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          addLog(`项目加载成功: ${projRes.data.project_id}`)
          
          // 获取 graph 数据
          if (projRes.data.graph_id) {
            await loadGraph(projRes.data.graph_id)
          }
        }
      }
    } else {
      addLog(`加载模拟数据失败: ${simRes.error || '未知错误'}`)
    }
  } catch (err) {
    addLog(`加载异常: ${err.message}`)
  }
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      addLog('图谱数据加载成功')
    }
  } catch (err) {
    addLog(`图谱加载失败: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    loadGraph(projectData.value.graph_id)
  }
}

onMounted(async () => {
  addLog('SimulationView 初始化')
  
  // 检查并关闭正在运行的模拟（用户从 Step 3 返回时）
  await checkAndStopRunningSimulation()
  
  // 加载模拟数据
  loadSimulationData()
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

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
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

.header-save-btn {
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

.save-notification {
  position: fixed;
  top: 68px;
  right: 20px;
  background: #1B5E20;
  color: #fff;
  padding: 10px 18px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  z-index: 2000;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 380px;
}
.notif-icon { font-size: 15px; flex-shrink: 0; }
.notif-text { line-height: 1.4; }
.notif-fade-enter-active, .notif-fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.notif-fade-enter-from { opacity: 0; transform: translateY(-8px); }
.notif-fade-leave-to { opacity: 0; transform: translateY(-8px); }
</style>

