<template>
  <div 
    class="history-database"
    :class="{ 'no-projects': projects.length === 0 && !loading }"
    ref="historyContainer"
  >
    <!-- 背景装饰：技术网格线（只在有项目时显示） -->
    <div v-if="projects.length > 0 || loading" class="tech-grid-bg">
      <div class="grid-pattern"></div>
      <div class="gradient-overlay"></div>
    </div>

    <!-- 标题区域 -->
    <div class="section-header" ref="sectionHeader">
      <div class="section-line"></div>
      <span class="section-title">推演记录 <span v-if="projects.length > 0" class="record-count">{{ projects.length }}</span></span>
      <div class="section-line"></div>
    </div>

    <!-- 卡片容器（只在有项目时显示） -->
    <div v-if="projects.length > 0" class="cards-container" :class="{ expanded: isExpanded }" :style="containerStyle">
      <div 
        v-for="(project, index) in projects" 
        :key="project.record_type === 'narrative' ? (project.session_id + '_' + (project.save_id || 'session')) : (project.simulation_id || project.session_id || project.project_id)"
        class="project-card"
        :class="{ expanded: isExpanded, hovering: hoveringCard === index }"
        :style="getCardStyle(index)"
        @mouseenter="hoveringCard = index"
        @mouseleave="hoveringCard = null"
        @click="navigateToProject(project)"
      >
        <!-- 卡片头部：ID 和 状态 -->
        <div class="card-header">
          <span class="card-id">{{ formatRecordId(project) }}</span>
          <!-- 仿真模式：功能状态图标 -->
          <div class="card-status-icons" v-if="project.record_type !== 'narrative'">
            <span
              class="status-icon"
              :class="{ available: project.project_id, unavailable: !project.project_id }"
              title="图谱构建"
            >◇</span>
            <span
              class="status-icon"
              :class="{ available: project.record_type !== 'project_only', unavailable: project.record_type === 'project_only' }"
              title="环境搭建"
            >◈</span>
            <span
              class="status-icon"
              :class="{ available: project.report_id, unavailable: !project.report_id }"
              title="分析报告"
            >◆</span>
          </div>
          <!-- 叙事模式：状态标签 -->
          <span v-else class="card-narrative-status" :class="[project.status, { resumable: project.can_resume }]">
            {{ project.save_id ? '存档' : (project.can_resume ? '可恢复' : narrativeStatusLabel(project.status)) }}
          </span>
        </div>

        <!-- 中间区域 -->
        <div class="card-files-wrapper">
          <!-- 角落装饰 - 取景框风格 -->
          <div class="corner-mark top-left-only"></div>

          <!-- 仿真模式：文件列表 -->
          <template v-if="project.record_type !== 'narrative'">
            <div class="files-list" v-if="project.files && project.files.length > 0">
              <div
                v-for="(file, fileIndex) in project.files.slice(0, 3)"
                :key="fileIndex"
                class="file-item"
              >
                <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                <span class="file-name">{{ truncateFilename(file.filename, 20) }}</span>
              </div>
              <div v-if="project.files.length > 3" class="files-more">
                +{{ project.files.length - 3 }} 个文件
              </div>
            </div>
            <div class="files-empty" v-else>
              <span class="empty-file-icon">◇</span>
              <span class="empty-file-text">暂无文件</span>
            </div>
          </template>

          <!-- 叙事模式：统计信息 -->
          <div class="narrative-stats" v-else>
            <div class="stat-row">
              <span class="stat-label">回合</span>
              <span class="stat-value">{{ project.current_turn || 0 }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">段落</span>
              <span class="stat-value">{{ project.segments_count || 0 }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">事件</span>
              <span class="stat-value">{{ project.events_count || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- 卡片标题 -->
        <h3 class="card-title">{{ getCardTitle(project) }}</h3>

        <!-- 卡片描述 -->
        <p class="card-desc">{{ getCardDesc(project) }}</p>

        <!-- 卡片底部 -->
        <div class="card-footer">
          <div class="card-datetime">
            <span class="card-date">{{ formatDate(project.created_at) }}</span>
            <span class="card-time">{{ formatTime(project.created_at) }}</span>
          </div>
          <template v-if="project.record_type !== 'narrative'">
            <span v-if="project.total_rounds > 0" class="card-progress" :class="getProgressClass(project)">
              <span class="status-dot">●</span> {{ formatRounds(project) }}
            </span>
            <span v-else-if="project.record_type === 'project_only'" class="card-progress not-started">图谱就绪</span>
            <span v-else class="card-progress not-started">未开始</span>
          </template>
          <span v-else class="card-mode-tag narrative">{{ project.save_id ? '存档 · ' : '叙事模式 · ' }}{{ project.current_turn || 0 }} 回合</span>
        </div>

        <!-- 删除按钮 -->
        <button
          class="card-delete-btn"
          @click.stop="confirmDelete(project, index)"
          title="删除记录"
        >×</button>
        
        <!-- 底部装饰线 (hover时展开) -->
        <div class="card-bottom-line"></div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span>
      <span class="loading-text">加载中...</span>
    </div>

    <!-- 历史回放详情弹窗 -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="selectedProject" class="modal-overlay" @click.self="closeModal">
          <div class="modal-content">
            <!-- 弹窗头部 -->
            <div class="modal-header">
              <div class="modal-title-section">
                <span class="modal-id">{{ formatRecordId(selectedProject) }}</span>
                <template v-if="selectedProject.record_type !== 'narrative' && selectedProject.record_type !== 'project_only'">
                  <span v-if="selectedProject.total_rounds > 0" class="modal-progress" :class="getProgressClass(selectedProject)">
                    <span class="status-dot">●</span> {{ formatRounds(selectedProject) }}
                  </span>
                  <span v-else class="modal-mode-tag">未开始</span>
                </template>
                <span v-else-if="selectedProject.record_type === 'project_only'" class="modal-mode-tag">图谱就绪</span>
                <span v-else class="modal-mode-tag narrative">叙事模式</span>
                <span class="modal-create-time">{{ formatDate(selectedProject.created_at) }} {{ formatTime(selectedProject.created_at) }}</span>
              </div>
              <button class="modal-close" @click="closeModal">×</button>
            </div>

            <!-- 标题编辑区域 -->
            <div class="modal-title-edit-section">
              <div class="modal-label">标题</div>
              <div v-if="!isEditingTitle" class="modal-title-display" @click="startEditTitle">
                <span class="modal-title-text">{{ getFullTitle(selectedProject) }}</span>
                <span class="modal-title-edit-icon" title="编辑标题">✎</span>
              </div>
              <div v-else class="modal-title-edit-form">
                <input
                  v-model="editTitleValue"
                  class="modal-title-input"
                  maxlength="50"
                  @keyup.enter="saveTitle"
                  @keyup.escape="cancelEditTitle"
                  ref="titleInputRef"
                />
                <div class="modal-title-edit-actions">
                  <button class="title-btn save" @click="saveTitle" :disabled="savingTitle || !editTitleValue.trim()">
                    {{ savingTitle ? '保存中...' : '保存' }}
                  </button>
                  <button class="title-btn cancel" @click="cancelEditTitle" :disabled="savingTitle">取消</button>
                </div>
              </div>
            </div>

            <!-- 弹窗内容 -->
            <div class="modal-body">
              <!-- 模拟需求 / 叙事场景 -->
              <div class="modal-section">
                <div class="modal-label">{{ selectedProject.record_type === 'narrative' ? '叙事场景' : '模拟需求' }}</div>
                <div class="modal-requirement">
                  {{ selectedProject.record_type === 'narrative'
                    ? (selectedProject.initial_scene || '无')
                    : (selectedProject.simulation_requirement || '无') }}
                </div>
              </div>

              <!-- 文件列表（仿真/图谱记录） -->
              <div class="modal-section" v-if="selectedProject.record_type !== 'narrative'">
                <div class="modal-label">关联文件</div>
                <div class="modal-files" v-if="selectedProject.files && selectedProject.files.length > 0">
                  <div v-for="(file, index) in selectedProject.files" :key="index" class="modal-file-item">
                    <span class="file-tag" :class="getFileType(file.filename)">{{ getFileTypeLabel(file.filename) }}</span>
                    <span class="modal-file-name">{{ file.filename }}</span>
                  </div>
                </div>
                <div class="modal-empty" v-else>暂无关联文件</div>
              </div>

              <!-- 叙事进度（叙事记录） -->
              <div class="modal-section" v-else>
                <div class="modal-label">叙事进度</div>
                <div class="modal-requirement">
                  {{ selectedProject.current_turn || 0 }} 回合 · {{ selectedProject.segments_count || 0 }} 段落 · {{ selectedProject.events_count || 0 }} 事件
                </div>
              </div>
            </div>

            <!-- 推演回放分割线 -->
            <div class="modal-divider">
              <span class="divider-line"></span>
              <span class="divider-text">{{ selectedProject.record_type === 'narrative' ? (selectedProject.save_id ? '读取存档' : ((selectedProject.player_entity_uuid === 'pending' || (selectedProject.current_turn || 0) === 0) ? '继续配置' : '继续叙事')) : '推演回放' }}</span>
              <span class="divider-line"></span>
            </div>

            <!-- 导航按钮 -->
            <div class="modal-actions">
              <!-- 叙事模式：继续叙事 或 返回配置（pending会话） -->
              <template v-if="selectedProject.record_type === 'narrative'">
                <button
                  v-if="selectedProject.player_entity_uuid === 'pending' || (selectedProject.current_turn || 0) === 0"
                  class="modal-btn btn-simulation"
                  @click="goToProjectForNarrative"
                >
                  <span class="btn-step">Step2</span>
                  <span class="btn-icon">◈</span>
                  <span class="btn-text">环境配置</span>
                </button>
                <button v-else class="modal-btn btn-simulation" @click="goToNarrative">
                  <span class="btn-icon">▶</span>
                  <span class="btn-text">{{ selectedProject.save_id ? '读取存档' : '继续叙事' }}</span>
                </button>
              </template>
              <!-- 仿真/图谱模式：Step1/Step2/Step4 -->
              <template v-else>
                <button
                  class="modal-btn btn-project"
                  @click="goToProject"
                  :disabled="!selectedProject.project_id"
                >
                  <span class="btn-step">Step1</span>
                  <span class="btn-icon">◇</span>
                  <span class="btn-text">图谱构建</span>
                </button>
                <button
                  class="modal-btn btn-simulation"
                  @click="goToSimulation"
                  :disabled="!selectedProject.simulation_id"
                >
                  <span class="btn-step">Step2</span>
                  <span class="btn-icon">◈</span>
                  <span class="btn-text">环境搭建</span>
                </button>
                <button
                  class="modal-btn btn-report"
                  @click="goToReport"
                  :disabled="!selectedProject.report_id"
                >
                  <span class="btn-step">Step4</span>
                  <span class="btn-icon">◆</span>
                  <span class="btn-text">分析报告</span>
                </button>
              </template>
            </div>
            <!-- 不可回放提示（仅仿真/图谱模式） -->
            <div class="modal-playback-hint" v-if="selectedProject.record_type !== 'narrative'">
              <span class="hint-text">Step3「开始模拟」与 Step5「深度互动」需在运行中启动，不支持历史回放</span>
            </div>

            <!-- 删除按钮 -->
            <div class="modal-delete-section">
              <button class="modal-delete-btn" @click="confirmDeleteFromModal">删除此记录</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="deleteTarget" class="modal-overlay" @click.self="cancelDelete">
          <div class="confirm-dialog">
            <p class="confirm-text">确认删除该推演记录？此操作不可撤回。</p>
            <div class="confirm-actions">
              <button class="confirm-btn cancel" @click="cancelDelete">取消</button>
              <button class="confirm-btn danger" @click="executeDelete" :disabled="deleting">
                {{ deleting ? '删除中...' : '确认删除' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSimulationHistory, deleteSimulation, renameSimulation } from '../api/simulation'
import { getNarrativeHistory, deleteNarrativeSession, deleteNarrativeSave, updateNarrativeSession, renameNarrativeSave } from '../api/narrative'
import { listProjects, deleteProject, renameProject } from '../api/graph'

const router = useRouter()
const route = useRoute()

// 状态
const projects = ref([])
const loading = ref(true)
const isExpanded = ref(false)
const hoveringCard = ref(null)
const historyContainer = ref(null)
const sectionHeader = ref(null)
const selectedProject = ref(null)  // 当前选中的项目（用于弹窗）
const isEditingTitle = ref(false)
const editTitleValue = ref('')
const savingTitle = ref(false)
const titleInputRef = ref(null)
let scrollHandler = null
let expandDebounceTimer = null  // 防抖定时器

// 卡片布局配置 - 调整为更宽的比例
const CARDS_PER_ROW = 4
const CARD_WIDTH = 280  
const CARD_HEIGHT = 280 
const CARD_GAP = 24

// 动态计算容器高度样式
const containerStyle = computed(() => {
  if (!isExpanded.value) {
    // 折叠态：固定高度
    return { minHeight: '420px' }
  }
  
  // 展开态：根据卡片数量动态计算高度
  const total = projects.value.length
  if (total === 0) {
    return { minHeight: '280px' }
  }
  
  const rows = Math.ceil(total / CARDS_PER_ROW)
  // 计算实际需要的高度：行数 * 卡片高度 + (行数-1) * 间距 + 少量底部间距
  const expandedHeight = rows * CARD_HEIGHT + (rows - 1) * CARD_GAP + 10
  
  return { minHeight: `${expandedHeight}px` }
})

// 获取卡片样式
const getCardStyle = (index) => {
  const total = projects.value.length
  
  if (isExpanded.value) {
    // 展开态：网格布局
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'

    const col = index % CARDS_PER_ROW
    const row = Math.floor(index / CARDS_PER_ROW)
    
    // 计算当前行的卡片数量，确保每行居中
    const currentRowStart = row * CARDS_PER_ROW
    const currentRowCards = Math.min(CARDS_PER_ROW, total - currentRowStart)
    
    const rowWidth = currentRowCards * CARD_WIDTH + (currentRowCards - 1) * CARD_GAP
    
    const startX = -(rowWidth / 2) + (CARD_WIDTH / 2)
    const colInRow = index % CARDS_PER_ROW
    const x = startX + colInRow * (CARD_WIDTH + CARD_GAP)
    
    // 向下展开，增加与标题的间距
    const y = 20 + row * (CARD_HEIGHT + CARD_GAP)

    return {
      transform: `translate(${x}px, ${y}px) rotate(0deg) scale(1)`,
      zIndex: 100 + index,
      opacity: 1,
      transition: transition
    }
  } else {
    // 折叠态：扇形堆叠
    const transition = 'transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease, border-color 0.3s ease'

    const centerIndex = (total - 1) / 2
    const offset = index - centerIndex
    
    const x = offset * 35
    // 调整起始位置，靠近标题但保持适当间距
    const y = 25 + Math.abs(offset) * 8
    const r = offset * 3
    const s = 0.95 - Math.abs(offset) * 0.05
    
    return {
      transform: `translate(${x}px, ${y}px) rotate(${r}deg) scale(${s})`,
      zIndex: 10 + index,
      opacity: 1,
      transition: transition
    }
  }
}

// 根据轮数进度获取样式类
const getProgressClass = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  
  if (total === 0 || current === 0) {
    // 未开始
    return 'not-started'
  } else if (current >= total) {
    // 已完成
    return 'completed'
  } else {
    // 进行中
    return 'in-progress'
  }
}

// 格式化日期（只显示日期部分）
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toISOString().slice(0, 10)
  } catch {
    return dateStr?.slice(0, 10) || ''
  }
}

// 格式化时间（显示时:分）
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const hours = date.getHours().toString().padStart(2, '0')
    const minutes = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${minutes}`
  } catch {
    return ''
  }
}

// 截断文本
const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.slice(0, maxLength) + '...' : text
}

// 从模拟需求生成标题（取前20字）
const getSimulationTitle = (requirement) => {
  if (!requirement) return '未命名模拟'
  const title = requirement.slice(0, 20)
  return requirement.length > 20 ? title + '...' : title
}

// 格式化 simulation_id 显示（截取前6位）
const formatSimulationId = (simulationId) => {
  if (!simulationId) return 'SIM_UNKNOWN'
  const prefix = simulationId.replace('sim_', '').slice(0, 6)
  return `SIM_${prefix.toUpperCase()}`
}

// 格式化记录 ID（根据 record_type）
const formatRecordId = (project) => {
  if (project.record_type === 'narrative') {
    const id = (project.session_id || '').slice(0, 6).toUpperCase()
    if (project.save_id) return `SAV_${id}`
    return `NAR_${id || 'UNKNOWN'}`
  }
  if (project.record_type === 'project_only') {
    const id = (project.project_id || '').replace('proj_', '').slice(0, 6).toUpperCase()
    return `PROJ_${id || 'UNKNOWN'}`
  }
  return formatSimulationId(project.simulation_id)
}

// 获取完整标题（不截断，用于弹窗编辑）
const getFullTitle = (project) => {
  if (project.custom_title) return project.custom_title
  if (project.record_type === 'narrative') return project.initial_scene || '叙事世界'
  if (project.record_type === 'project_only') return project.name || '未命名项目'
  return project.simulation_requirement || '未命名模拟'
}

// 卡片标题（根据 record_type，优先使用自定义标题）
const getCardTitle = (project) => {
  if (project.custom_title) {
    return getSimulationTitle(project.custom_title)
  }
  if (project.record_type === 'narrative') {
    return getSimulationTitle(project.initial_scene || '叙事世界')
  }
  if (project.record_type === 'project_only') {
    return getSimulationTitle(project.name || '未命名项目')
  }
  return getSimulationTitle(project.simulation_requirement)
}

// 卡片描述（根据 record_type）
const getCardDesc = (project) => {
  if (project.record_type === 'narrative') {
    if (project.save_id && project.description) return truncateText(project.description, 55)
    return truncateText(project.initial_scene || '叙事世界', 55)
  }
  return truncateText(project.simulation_requirement, 55)
}

// 叙事状态标签
const narrativeStatusLabel = (status) => {
  const map = {
    idle: '待机',
    running: '进行中',
    awaiting_player: '等待玩家',
    processing_player: '处理中',
    completed: '已结束',
    failed: '出错'
  }
  return map[status] || status || '未知'
}

// 格式化轮数显示（当前轮/总轮数）
const formatRounds = (simulation) => {
  const current = simulation.current_round || 0
  const total = simulation.total_rounds || 0
  if (total === 0) return '未开始'
  return `${current}/${total} 轮`
}

// 获取文件类型（用于样式）
const getFileType = (filename) => {
  if (!filename) return 'other'
  const ext = filename.split('.').pop()?.toLowerCase()
  const typeMap = {
    'pdf': 'pdf',
    'doc': 'doc', 'docx': 'doc',
    'xls': 'xls', 'xlsx': 'xls', 'csv': 'xls',
    'ppt': 'ppt', 'pptx': 'ppt',
    'txt': 'txt', 'md': 'txt', 'json': 'code',
    'jpg': 'img', 'jpeg': 'img', 'png': 'img', 'gif': 'img',
    'zip': 'zip', 'rar': 'zip', '7z': 'zip'
  }
  return typeMap[ext] || 'other'
}

// 获取文件类型标签文本
const getFileTypeLabel = (filename) => {
  if (!filename) return 'FILE'
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

// 截断文件名（保留扩展名）
const truncateFilename = (filename, maxLength) => {
  if (!filename) return '未知文件'
  if (filename.length <= maxLength) return filename
  
  const ext = filename.includes('.') ? '.' + filename.split('.').pop() : ''
  const nameWithoutExt = filename.slice(0, filename.length - ext.length)
  const truncatedName = nameWithoutExt.slice(0, maxLength - ext.length - 3) + '...'
  return truncatedName + ext
}

// 打开项目详情弹窗
const navigateToProject = (record) => {
  selectedProject.value = record
}

// 关闭弹窗
const closeModal = () => {
  selectedProject.value = null
  isEditingTitle.value = false
  editTitleValue.value = ''
}

// 导航到图谱构建页面（Project）
const goToProject = () => {
  if (selectedProject.value?.project_id) {
    router.push({
      name: 'Process',
      params: { projectId: selectedProject.value.project_id }
    })
    closeModal()
  }
}

// 导航到环境配置页面（Simulation）
const goToSimulation = () => {
  if (selectedProject.value?.simulation_id) {
    // 如果是 narrative 模式，带上 mode=narrative query 参数
    const query = selectedProject.value.mode === 'narrative' ? { mode: 'narrative' } : {}
    router.push({
      name: 'Simulation',
      params: { simulationId: selectedProject.value.simulation_id },
      query
    })
    closeModal()
  }
}

// 导航到分析报告页面（Report）
const goToReport = () => {
  if (selectedProject.value?.report_id) {
    router.push({
      name: 'Report',
      params: { reportId: selectedProject.value.report_id }
    })
    closeModal()
  }
}

// 导航到叙事页面（继续叙事 或 读取存档）
const goToNarrative = () => {
  if (selectedProject.value?.session_id) {
    const query = selectedProject.value.save_id ? { saveId: selectedProject.value.save_id } : {}
    router.push({ name: 'Narrative', params: { sessionId: selectedProject.value.session_id }, query })
    closeModal()
  }
}

// 叙事会话未完成配置（pending），跳转至 Step2 环境配置页继续操作
const goToProjectForNarrative = () => {
  const proj = selectedProject.value
  if (!proj) return
  if (proj.simulation_id) {
    // 有 simulation_id，直接进入 Step2（narrative 模式）
    router.push({
      name: 'Simulation',
      params: { simulationId: proj.simulation_id },
      query: { mode: 'narrative', sessionId: proj.session_id }
    })
  } else {
    // 无 simulation_id，fallback 回图谱页让用户重新走流程
    router.push({ name: 'Process', params: { projectId: proj.project_id } })
  }
  closeModal()
}

// 标题编辑
const startEditTitle = () => {
  if (!selectedProject.value) return
  editTitleValue.value = getFullTitle(selectedProject.value)
  isEditingTitle.value = true
}

const cancelEditTitle = () => {
  isEditingTitle.value = false
  editTitleValue.value = ''
}

const saveTitle = async () => {
  if (!selectedProject.value || savingTitle.value) return
  const newTitle = editTitleValue.value.trim()
  if (!newTitle) return

  savingTitle.value = true
  try {
    const p = selectedProject.value
    const recordType = p.record_type

    if (recordType === 'narrative' && p.save_id) {
      // 叙事存档
      await renameNarrativeSave(p.session_id, p.save_id, newTitle)
    } else if (recordType === 'narrative') {
      // 叙事会话（无存档）
      await updateNarrativeSession(p.session_id, { custom_title: newTitle })
    } else if (recordType === 'project_only') {
      // 仅图谱项目
      await renameProject(p.project_id, newTitle)
    } else {
      // 仿真记录
      await renameSimulation(p.simulation_id, newTitle)
    }

    // 更新本地数据
    p.custom_title = newTitle
    if (recordType === 'project_only') {
      p.name = newTitle
    }

    // 同步 projects 列表中的数据
    const target = projects.value.find(item => {
      if (recordType === 'narrative') {
        return item.session_id === p.session_id && (item.save_id || null) === (p.save_id || null)
      }
      if (recordType === 'project_only') {
        return item.project_id === p.project_id
      }
      return item.simulation_id === p.simulation_id
    })
    if (target) {
      target.custom_title = newTitle
      if (recordType === 'project_only') target.name = newTitle
    }

    isEditingTitle.value = false
  } catch (e) {
    console.error('保存标题失败:', e)
  } finally {
    savingTitle.value = false
  }
}

// 删除相关状态
const deleteTarget = ref(null)  // { simulation_id, index }
const deleting = ref(false)

// 从卡片触发删除确认
const confirmDelete = (project, index) => {
  const record_type = project.record_type || 'simulation'
  // 叙事记录必须用 session_id，simulation_id 是来源仿真的 ID，不能用于叙事 API 路径
  const id = record_type === 'narrative'
    ? project.session_id
    : (project.simulation_id || project.session_id || project.project_id)
  deleteTarget.value = {
    id,
    record_type,
    save_id: project.save_id || null,
    index
  }
}

// 从弹窗触发删除确认
const confirmDeleteFromModal = () => {
  if (selectedProject.value) {
    const p = selectedProject.value
    const record_type = p.record_type || 'simulation'
    const recordId = record_type === 'narrative'
      ? p.session_id
      : (p.simulation_id || p.session_id || p.project_id)
    const index = projects.value.findIndex(item => {
      const itemId = item.record_type === 'narrative'
        ? item.session_id
        : (item.simulation_id || item.session_id || item.project_id)
      return itemId === recordId && (item.save_id || null) === (p.save_id || null)
    })
    deleteTarget.value = {
      id: recordId,
      record_type,
      save_id: p.save_id || null,
      index
    }
  }
}

// 取消删除
const cancelDelete = () => {
  deleteTarget.value = null
}

// 执行删除
const executeDelete = async () => {
  if (!deleteTarget.value) return
  try {
    deleting.value = true
    const { id, record_type, save_id } = deleteTarget.value
    let res
    if (record_type === 'narrative' && save_id) {
      // 存档条目：只删除该存档快照
      res = await deleteNarrativeSave(id, save_id)
    } else if (record_type === 'narrative') {
      res = await deleteNarrativeSession(id)
    } else if (record_type === 'project_only') {
      res = await deleteProject(id)
    } else {
      res = await deleteSimulation(id)
    }
    if (res.success) {
      // 移除对应条目（叙事记录按 session_id 匹配，其他按 simulation_id/project_id）
      const before = projects.value.length
      projects.value = projects.value.filter(p => {
        const pId = p.record_type === 'narrative'
          ? p.session_id
          : (p.simulation_id || p.session_id || p.project_id)
        const sameId = pId === id
        if (!sameId) return true
        if (save_id) return (p.save_id || null) !== save_id
        return false
      })
      // 如果弹窗中的项目被删除，关闭弹窗
      const sel = selectedProject.value
      if (sel) {
        const selId = sel.record_type === 'narrative'
          ? sel.session_id
          : (sel.simulation_id || sel.session_id || sel.project_id)
        if (selId === id && (sel.save_id || null) === (save_id || null)) {
          selectedProject.value = null
        }
      }
    }
  } catch (error) {
    console.error('删除推演记录失败:', error)
  } finally {
    deleting.value = false
    deleteTarget.value = null
  }
}

// 加载历史项目（合并仿真 + 叙事 + 图谱仅记录）
const loadHistory = async () => {
  try {
    loading.value = true
    const [simRes, narRes, projRes] = await Promise.allSettled([
      getSimulationHistory(20),
      getNarrativeHistory(20),
      listProjects(30)
    ])

    let allRecords = []
    let simData = []
    let narData = []

    // 仿真记录
    if (simRes.status === 'fulfilled' && simRes.value.success) {
      simData = (simRes.value.data || []).map(s => ({
        ...s,
        record_type: s.record_type || 'simulation'
      }))
    }

    // 叙事记录
    if (narRes.status === 'fulfilled' && narRes.value.success) {
      narData = narRes.value.data || []
    }

    // 去重：有叙事会话（无论是否已启动）的项目只显示叙事记录，不显示仿真记录，避免重复。
    const narrativeProjectIds = new Set(
      narData.map(n => n.project_id).filter(Boolean)
    )
    // 仿真记录：跳过有叙事会话的项目（叙事记录已单独展示）
    const filteredSimData = simData.filter(s => !narrativeProjectIds.has(s.project_id))
    // 叙事记录：全部展示（包括 player_entity_uuid==='pending' 的未完成会话）
    allRecords.push(...filteredSimData)
    allRecords.push(...narData)

    // 图谱仅记录（没有对应仿真记录的项目）
    if (projRes.status === 'fulfilled' && projRes.value.success) {
      const simProjectIds = new Set(allRecords.map(r => r.project_id).filter(Boolean))
      const projectOnlyData = (projRes.value.data || [])
        .filter(p => !simProjectIds.has(p.project_id))
        .map(p => ({
          ...p,
          record_type: 'project_only',
          files: (p.files || []).map(f => ({
            filename: f.original_filename || f.filename || String(f)
          }))
        }))
      allRecords.push(...projectOnlyData)
    }

    // 按 created_at 降序
    allRecords.sort((a, b) => {
      const ta = a.created_at || ''
      const tb = b.created_at || ''
      return tb.localeCompare(ta)
    })

    projects.value = allRecords
  } catch (error) {
    console.error('加载历史项目失败:', error)
    projects.value = []
  } finally {
    loading.value = false
  }
}

// 根据标题栏位置决定展开/收起（带滞后区间防止抖动）
const checkExpand = () => {
  if (!sectionHeader.value) return
  const rect = sectionHeader.value.getBoundingClientRect()
  const vh = window.innerHeight

  if (!isExpanded.value && rect.top < vh * 0.48) {
    // 向下滚：标题过视口中点偏上 → 展开
    isExpanded.value = true
  } else if (isExpanded.value && rect.top > vh * 0.52) {
    // 向上滚：标题退回视口中点偏下 → 收起
    isExpanded.value = false
  }
  // 48%~52% 缓冲区维持当前状态，防止在中点边界抖动
}

// 初始化滚动监听
const initScrollListener = () => {
  if (scrollHandler) {
    window.removeEventListener('scroll', scrollHandler)
  }

  scrollHandler = () => {
    if (expandDebounceTimer) {
      clearTimeout(expandDebounceTimer)
    }
    expandDebounceTimer = setTimeout(() => {
      checkExpand()
      expandDebounceTimer = null
    }, 60)
  }

  window.addEventListener('scroll', scrollHandler, { passive: true })
}

// 编辑标题时自动聚焦输入框
watch(isEditingTitle, (val) => {
  if (val) {
    nextTick(() => {
      titleInputRef.value?.focus()
    })
  }
})

// 监听路由变化，当返回首页时重新加载数据
watch(() => route.path, (newPath) => {
  if (newPath === '/') {
    loadHistory()
  }
})

onMounted(async () => {
  // 确保 DOM 渲染完成后再加载数据
  await nextTick()
  await loadHistory()
  
  // 等待 DOM 渲染后初始化滚动监听，并立即检查一次当前位置
  setTimeout(() => {
    initScrollListener()
    checkExpand()
  }, 100)
})

// 如果使用 keep-alive，在组件激活时重新加载数据
onActivated(() => {
  loadHistory()
})

onUnmounted(() => {
  if (scrollHandler) {
    window.removeEventListener('scroll', scrollHandler)
    scrollHandler = null
  }
  if (expandDebounceTimer) {
    clearTimeout(expandDebounceTimer)
    expandDebounceTimer = null
  }
})
</script>

<style scoped>
/* 容器 */
.history-database {
  position: relative;
  width: 100%;
  min-height: 280px;
  margin-top: 40px;
  padding: 35px 0 40px;
  overflow: visible;
}

/* 无项目时简化显示 */
.history-database.no-projects {
  min-height: auto;
  padding: 40px 0 20px;
}

/* 技术网格背景 */
.tech-grid-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
}

/* 使用CSS背景图案创建固定间距的正方形网格 */
.grid-pattern {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    linear-gradient(to right, rgba(0, 0, 0, 0.05) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(0, 0, 0, 0.05) 1px, transparent 1px);
  background-size: 50px 50px;
  /* 从左上角开始定位，高度变化时只在底部扩展，不影响已有网格位置 */
  background-position: top left;
}

.gradient-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    linear-gradient(to right, rgba(255, 255, 255, 0.9) 0%, transparent 15%, transparent 85%, rgba(255, 255, 255, 0.9) 100%),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.8) 0%, transparent 20%, transparent 80%, rgba(255, 255, 255, 0.8) 100%);
  pointer-events: none;
}

/* 标题区域 */
.section-header {
  position: relative;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  margin-bottom: 24px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  padding: 0 40px;
}

.section-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #E5E7EB, transparent);
  max-width: 300px;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 500;
  color: #9CA3AF;
  letter-spacing: 3px;
  text-transform: uppercase;
}

.record-count {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 7px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0;
  color: #6B7280;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  vertical-align: middle;
  text-transform: none;
}

/* 卡片容器 */
.cards-container {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0 40px;
  transition: min-height 700ms cubic-bezier(0.23, 1, 0.32, 1);
  /* min-height 由 JS 动态计算，根据卡片数量自适应 */
}

/* 项目卡片 */
.project-card {
  position: absolute;
  width: 280px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 0;
  padding: 14px;
  cursor: pointer;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  transition: box-shadow 0.3s ease, border-color 0.3s ease, transform 700ms cubic-bezier(0.23, 1, 0.32, 1), opacity 700ms cubic-bezier(0.23, 1, 0.32, 1);
}

.project-card:hover {
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  border-color: rgba(0, 0, 0, 0.4);
  z-index: 1000 !important;
}

.project-card.hovering {
  z-index: 1000 !important;
}

/* 卡片头部 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F3F4F6;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.7rem;
}

.card-id {
  color: #6B7280;
  letter-spacing: 0.5px;
  font-weight: 500;
}

/* 功能状态图标组 */
.card-status-icons {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-icon {
  font-size: 0.75rem;
  transition: all 0.2s ease;
  cursor: default;
}

.status-icon.available {
  opacity: 1;
}

/* 不同功能的颜色 */
.status-icon:nth-child(1).available { color: #3B82F6; } /* 图谱构建 - 蓝色 */
.status-icon:nth-child(2).available { color: #F59E0B; } /* 环境搭建 - 橙色 */
.status-icon:nth-child(3).available { color: #10B981; } /* 分析报告 - 绿色 */

.status-icon.unavailable {
  color: #D1D5DB;
  opacity: 0.5;
}

/* 轮数进度显示 */
.card-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  letter-spacing: 0.5px;
  font-weight: 600;
  font-size: 0.65rem;
}

.status-dot {
  font-size: 0.5rem;
}

/* 进度状态颜色 */
.card-progress.completed { color: #10B981; }    /* 已完成 - 绿色 */
.card-progress.in-progress { color: #F59E0B; }  /* 进行中 - 橙色 */
.card-progress.not-started { color: #9CA3AF; }  /* 未开始 - 灰色 */
.card-status.pending { color: #9CA3AF; }

/* 文件列表区域 */
.card-files-wrapper {
  position: relative;
  width: 100%;
  min-height: 48px;
  max-height: 110px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: linear-gradient(135deg, #f8f9fa 0%, #f1f3f4 100%);
  border-radius: 4px;
  border: 1px solid #e8eaed;
  overflow: hidden;
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 更多文件提示 */
.files-more {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3px 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: #6B7280;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 3px;
  letter-spacing: 0.3px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 3px;
  transition: all 0.2s ease;
}

.file-item:hover {
  background: rgba(255, 255, 255, 1);
  transform: translateX(2px);
  border-color: #e5e7eb;
}

/* 简约文件标签样式 */
.file-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 16px;
  padding: 0 4px;
  border-radius: 2px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  font-weight: 600;
  line-height: 1;
  text-transform: uppercase;
  letter-spacing: 0.2px;
  flex-shrink: 0;
  min-width: 28px;
}

/* 低饱和度配色方案 - Morandi色系 */
.file-tag.pdf { background: #f2e6e6; color: #a65a5a; }
.file-tag.doc { background: #e6eff5; color: #5a7ea6; }
.file-tag.xls { background: #e6f2e8; color: #5aa668; }
.file-tag.ppt { background: #f5efe6; color: #a6815a; }
.file-tag.txt { background: #f0f0f0; color: #757575; }
.file-tag.code { background: #eae6f2; color: #815aa6; }
.file-tag.img { background: #e6f2f2; color: #5aa6a6; }
.file-tag.zip { background: #f2f0e6; color: #a69b5a; }
.file-tag.other { background: #f3f4f6; color: #6b7280; }

.file-name {
  font-family: 'Inter', sans-serif;
  font-size: 0.7rem;
  color: #4b5563;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.1px;
}

/* 无文件时的占位 */
.files-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 48px;
  color: #9CA3AF;
}

.empty-file-icon {
  font-size: 1rem;
  opacity: 0.5;
}

.empty-file-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.5px;
}

/* 悬停时文件区域效果 */
.project-card:hover .card-files-wrapper {
  border-color: #d1d5db;
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
}

/* 角落装饰 */
.corner-mark.top-left-only {
  position: absolute;
  top: 6px;
  left: 6px;
  width: 8px;
  height: 8px;
  border-top: 1.5px solid rgba(0, 0, 0, 0.4);
  border-left: 1.5px solid rgba(0, 0, 0, 0.4);
  pointer-events: none;
  z-index: 10;
}

/* 卡片标题 */
.card-title {
  font-family: 'Inter', -apple-system, sans-serif;
  font-size: 0.9rem;
  font-weight: 700;
  color: #111827;
  margin: 0 0 6px 0;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.3s ease;
}

.project-card:hover .card-title {
  color: #2563EB;
}

/* 卡片描述 */
.card-desc {
  font-family: 'Inter', sans-serif;
  font-size: 0.75rem;
  color: #6B7280;
  margin: 0 0 16px 0;
  line-height: 1.5;
  height: 34px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* 卡片底部 */
.card-footer {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #F3F4F6;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #9CA3AF;
  font-weight: 500;
}

/* 日期时间组合 */
.card-datetime {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 底部轮数进度显示 */
.card-footer .card-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  letter-spacing: 0.5px;
  font-weight: 600;
  font-size: 0.65rem;
}

.card-footer .status-dot {
  font-size: 0.5rem;
}

/* 进度状态颜色 - 底部 */
.card-footer .card-progress.completed { color: #10B981; }
.card-footer .card-progress.in-progress { color: #F59E0B; }
.card-footer .card-progress.not-started { color: #9CA3AF; }

/* 底部装饰线 */
.card-bottom-line {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  width: 0;
  background-color: #000;
  transition: width 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  z-index: 20;
}

.project-card:hover .card-bottom-line {
  width: 100%;
}

/* 空状态 */
.empty-state, .loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 48px;
  color: #9CA3AF;
}

.empty-icon {
  font-size: 2rem;
  opacity: 0.5;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #E5E7EB;
  border-top-color: #6B7280;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 响应式 */
@media (max-width: 1200px) {
  .project-card {
    width: 240px;
  }
}

@media (max-width: 768px) {
  .cards-container {
    padding: 0 20px;
  }
  .project-card {
    width: 200px;
  }
}

/* ===== 历史回放详情弹窗样式 ===== */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: #FFFFFF;
  width: 560px;
  max-width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

/* 动画过渡 */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-content {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .modal-content {
  transition: all 0.2s ease-in;
}

.modal-enter-from .modal-content {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

.modal-leave-to .modal-content {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

/* 弹窗头部 */
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  border-bottom: 1px solid #F3F4F6;
  background: #FFFFFF;
}

.modal-title-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.modal-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
  letter-spacing: 0.5px;
}

.modal-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  background: #F9FAFB;
}

.modal-progress.completed { color: #10B981; background: rgba(16, 185, 129, 0.1); }
.modal-progress.in-progress { color: #F59E0B; background: rgba(245, 158, 11, 0.1); }
.modal-progress.not-started { color: #9CA3AF; background: #F3F4F6; }

.modal-create-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  font-size: 1.5rem;
  color: #9CA3AF;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border-radius: 6px;
}

.modal-close:hover {
  background: #F3F4F6;
  color: #111827;
}

/* 标题编辑区域 */
.modal-title-edit-section {
  padding: 16px 32px 0;
}

.modal-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #F9FAFB;
  border: 1px solid #F3F4F6;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.modal-title-display:hover {
  border-color: #D1D5DB;
}

.modal-title-text {
  flex: 1;
  font-size: 1rem;
  font-weight: 500;
  color: #1F2937;
}

.modal-title-edit-icon {
  font-size: 0.85rem;
  color: #9CA3AF;
  opacity: 0;
  transition: opacity 0.2s;
}

.modal-title-display:hover .modal-title-edit-icon {
  opacity: 1;
}

.modal-title-edit-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.modal-title-input {
  width: 100%;
  padding: 10px 14px;
  font-size: 1rem;
  font-weight: 500;
  color: #1F2937;
  background: #FFFFFF;
  border: 1px solid #6B7280;
  border-radius: 8px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.modal-title-input:focus {
  border-color: #3B82F6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.modal-title-edit-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.title-btn {
  padding: 4px 14px;
  font-size: 0.8rem;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  transition: background 0.2s;
}

.title-btn.save {
  background: #1F2937;
  color: #FFFFFF;
}

.title-btn.save:hover:not(:disabled) {
  background: #374151;
}

.title-btn.save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.title-btn.cancel {
  background: #F3F4F6;
  color: #6B7280;
}

.title-btn.cancel:hover:not(:disabled) {
  background: #E5E7EB;
}

/* 弹窗内容 */
.modal-body {
  padding: 24px 32px;
}

.modal-section {
  margin-bottom: 24px;
}

.modal-section:last-child {
  margin-bottom: 0;
}

.modal-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  font-weight: 500;
}

.modal-requirement {
  font-size: 0.95rem;
  color: #374151;
  line-height: 1.6;
  padding: 16px;
  background: #F9FAFB;
  border: 1px solid #F3F4F6;
  border-radius: 8px;
}

.modal-files {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 200px;
  overflow-y: auto;
  padding-right: 4px;
}

/* 自定义滚动条样式 */
.modal-files::-webkit-scrollbar {
  width: 4px;
}

.modal-files::-webkit-scrollbar-track {
  background: #F3F4F6;
  border-radius: 2px;
}

.modal-files::-webkit-scrollbar-thumb {
  background: #D1D5DB;
  border-radius: 2px;
}

.modal-files::-webkit-scrollbar-thumb:hover {
  background: #9CA3AF;
}

.modal-file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.modal-file-item:hover {
  border-color: #D1D5DB;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
}

.modal-file-name {
  font-size: 0.85rem;
  color: #4B5563;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-empty {
  font-size: 0.85rem;
  color: #9CA3AF;
  padding: 16px;
  background: #F9FAFB;
  border: 1px dashed #E5E7EB;
  border-radius: 6px;
  text-align: center;
}

/* 推演回放分割线 */
.modal-divider {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 32px 0;
  background: #FFFFFF;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #E5E7EB, transparent);
}

.divider-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 2px;
  text-transform: uppercase;
  white-space: nowrap;
}

/* 导航按钮 */
.modal-actions {
  display: flex;
  gap: 16px;
  padding: 20px 32px;
  background: #FFFFFF;
}

.modal-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FFFFFF;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;
}

.modal-btn:hover:not(:disabled) {
  border-color: #000000;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #F9FAFB;
}

.btn-step {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 500;
  color: #9CA3AF;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.btn-icon {
  font-size: 1.4rem;
  line-height: 1;
  transition: color 0.2s ease;
}

.btn-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #4B5563;
}

.modal-btn.btn-project .btn-icon { color: #3B82F6; }
.modal-btn.btn-simulation .btn-icon { color: #F59E0B; }
.modal-btn.btn-report .btn-icon { color: #10B981; }

.modal-btn:hover:not(:disabled) .btn-text {
  color: #111827;
}

/* 不可回放提示 */
.modal-playback-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 32px 20px;
  background: #FFFFFF;
}

.hint-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
  text-align: center;
  line-height: 1.5;
}

/* 叙事模式标签 */
.card-mode-tag.narrative {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 600;
  color: #8B5CF6;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  background: rgba(139, 92, 246, 0.1);
  border-radius: 3px;
}

.modal-mode-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  padding: 4px 10px;
  background: rgba(100, 116, 139, 0.1);
  border-radius: 4px;
}

.modal-mode-tag.narrative {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: #8B5CF6;
  padding: 4px 10px;
  background: rgba(139, 92, 246, 0.1);
  border-radius: 4px;
}

/* 叙事模式 - 卡片头部状态标签 */
.card-narrative-status {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.3px;
  padding: 2px 8px;
  border-radius: 3px;
  background: rgba(139, 92, 246, 0.1);
  color: #8B5CF6;
}
.card-narrative-status.running,
.card-narrative-status.awaiting_player,
.card-narrative-status.processing_player { background: rgba(245, 158, 11, 0.1); color: #D97706; }
.card-narrative-status.completed { background: rgba(16, 185, 129, 0.1); color: #059669; }
.card-narrative-status.resumable { background: rgba(59, 130, 246, 0.1); color: #1D4ED8; }
.card-narrative-status.failed { background: rgba(239, 68, 68, 0.1); color: #DC2626; }

/* 叙事统计区域 */
.narrative-stats {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 6px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 3px;
}

.stat-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: #9CA3AF;
  letter-spacing: 0.3px;
}

.stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  color: #4B5563;
}

/* 卡片删除按钮 */
.card-delete-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: #D1D5DB;
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.2s ease;
  z-index: 10;
}

.project-card:hover .card-delete-btn {
  opacity: 1;
}

.card-delete-btn:hover {
  background: #FEE2E2;
  color: #EF4444;
}

/* 弹窗删除按钮 */
.modal-delete-section {
  display: flex;
  justify-content: center;
  padding: 0 32px 24px;
}

.modal-delete-btn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #9CA3AF;
  background: transparent;
  border: 1px solid #E5E7EB;
  padding: 8px 20px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.modal-delete-btn:hover {
  color: #EF4444;
  border-color: #EF4444;
  background: #FEF2F2;
}

/* 删除确认弹窗 */
.confirm-dialog {
  background: #FFFFFF;
  padding: 32px;
  border-radius: 12px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  max-width: 380px;
  width: 90vw;
}

.confirm-text {
  font-size: 0.95rem;
  color: #374151;
  text-align: center;
  margin: 0 0 24px;
  line-height: 1.5;
}

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.confirm-btn {
  padding: 8px 24px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid #E5E7EB;
}

.confirm-btn.cancel {
  background: #FFFFFF;
  color: #6B7280;
}

.confirm-btn.cancel:hover {
  background: #F3F4F6;
}

.confirm-btn.danger {
  background: #EF4444;
  color: #FFFFFF;
  border-color: #EF4444;
}

.confirm-btn.danger:hover {
  background: #DC2626;
}

.confirm-btn.danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
