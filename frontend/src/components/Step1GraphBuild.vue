<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <!-- Step 01: Ontology -->
      <div class="step-card" :class="{ 'active': currentPhase === 0, 'completed': currentPhase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">本体生成</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 0" class="badge success">已完成</span>
            <span v-else-if="currentPhase === 0" class="badge processing">生成中</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/graph/ontology/generate</p>
          <p class="description">
            LLM分析文档内容与模拟需求，提取出现实种子，自动生成合适的本体结构
          </p>

          <!-- Loading / Progress -->
          <div v-if="currentPhase === 0 && ontologyProgress" class="progress-section">
            <div class="spinner-sm"></div>
            <span>{{ ontologyProgress.message || '正在分析文档...' }}</span>
          </div>

          <!-- Detail Overlay -->
          <div v-if="selectedOntologyItem" class="ontology-detail-overlay">
            <div class="detail-header">
               <div class="detail-title-group">
                  <span class="detail-type-badge">{{ selectedOntologyItem.itemType === 'entity' ? 'ENTITY' : 'RELATION' }}</span>
                  <span class="detail-name">{{ selectedOntologyItem.name }}</span>
               </div>
               <button class="close-btn" @click="selectedOntologyItem = null">×</button>
            </div>
            <div class="detail-body">
               <div class="detail-desc">{{ selectedOntologyItem.description }}</div>
               
               <!-- Attributes -->
               <div class="detail-section" v-if="selectedOntologyItem.attributes?.length">
                  <span class="section-label">ATTRIBUTES</span>
                  <div class="attr-list">
                     <div v-for="attr in selectedOntologyItem.attributes" :key="attr.name" class="attr-item">
                        <span class="attr-name">{{ attr.name }}</span>
                        <span class="attr-type">({{ attr.type }})</span>
                        <span class="attr-desc">{{ attr.description }}</span>
                     </div>
                  </div>
               </div>

               <!-- Examples (Entity) -->
               <div class="detail-section" v-if="selectedOntologyItem.examples?.length">
                  <span class="section-label">EXAMPLES</span>
                  <div class="example-list">
                     <span v-for="ex in selectedOntologyItem.examples" :key="ex" class="example-tag">{{ ex }}</span>
                  </div>
               </div>

               <!-- Source/Target (Relation) -->
               <div class="detail-section" v-if="selectedOntologyItem.source_targets?.length">
                  <span class="section-label">CONNECTIONS</span>
                  <div class="conn-list">
                     <div v-for="(conn, idx) in selectedOntologyItem.source_targets" :key="idx" class="conn-item">
                        <span class="conn-node">{{ conn.source }}</span>
                        <span class="conn-arrow">→</span>
                        <span class="conn-node">{{ conn.target }}</span>
                     </div>
                  </div>
               </div>
            </div>
          </div>

          <!-- Generated Entity Tags -->
          <div v-if="projectData?.ontology?.entity_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED ENTITY TYPES</span>
            <div class="tags-list">
              <span
                v-for="entity in projectData.ontology.entity_types"
                :key="entity.name"
                class="entity-tag clickable"
                :class="entity.is_agent === false ? 'entity-tag--static' : 'entity-tag--agent'"
                :title="entity.is_agent === false ? '静态实体（不参与叙事行动）' : '行动实体（可作为叙事 Agent）'"
                @click="selectOntologyItem(entity, 'entity')"
              >
                {{ entity.name }}<span v-if="entity.is_agent === false" class="tag-badge tag-badge--static">静态</span><span v-else class="tag-badge tag-badge--agent">Agent</span>
              </span>
            </div>
          </div>

          <!-- Generated Relation Tags -->
          <div v-if="projectData?.ontology?.edge_types" class="tags-container" :class="{ 'dimmed': selectedOntologyItem }">
            <span class="tag-label">GENERATED RELATION TYPES</span>
            <div class="tags-list">
              <span 
                v-for="rel in projectData.ontology.edge_types" 
                :key="rel.name" 
                class="entity-tag clickable"
                @click="selectOntologyItem(rel, 'relation')"
              >
                {{ rel.name }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Graph Build -->
      <div class="step-card" :class="{ 'active': currentPhase === 1 || (currentPhase === 0 && projectData?.ontology), 'completed': currentPhase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">GraphRAG构建</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 1" class="badge success">已完成</span>
            <span v-else-if="currentPhase === 1" class="badge processing">{{ buildProgress?.progress || 0 }}%</span>
            <span v-else-if="currentPhase === 0 && projectData?.ontology" class="badge accent">待构建</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/graph/build</p>
          <p class="description">
            基于生成的本体，将文档自动分块后调用 Graphiti 构建知识图谱，提取实体和关系
          </p>

          <!-- 构建参数设置 -->
          <div v-if="projectData?.ontology" class="build-settings">
            <span class="tag-label">BUILD PARAMETERS</span>
            <div class="settings-grid">
              <div class="setting-item">
                <label class="setting-label">chunk_size</label>
                <input
                  type="number"
                  :value="localSettings.chunk_size"
                  @input="updateSetting('chunk_size', $event)"
                  :disabled="currentPhase >= 1"
                  min="100" max="5000" step="100"
                  class="setting-input"
                />
                <span class="setting-hint">推荐 1000-2000</span>
              </div>
              <div class="setting-item">
                <label class="setting-label">batch_size</label>
                <input
                  type="number"
                  :value="localSettings.batch_size"
                  @input="updateSetting('batch_size', $event)"
                  :disabled="currentPhase >= 1"
                  min="1" max="50" step="1"
                  class="setting-input"
                />
                <span class="setting-hint">推荐 5-15</span>
              </div>
              <div class="setting-item">
                <label class="setting-label">chunk_overlap</label>
                <input
                  type="number"
                  :value="localSettings.chunk_overlap"
                  @input="updateSetting('chunk_overlap', $event)"
                  :disabled="currentPhase >= 1"
                  min="0" max="500" step="10"
                  class="setting-input"
                />
                <span class="setting-hint">推荐 0-100</span>
              </div>
            </div>
            <p class="settings-note">使用 embedding 语义切分，chunk_size 为目标大小；chunk_overlap 仅在降级时生效</p>

            <!-- 开始构建按钮 -->
            <button
              v-if="currentPhase === 0 && projectData?.ontology && !buildProgress"
              class="action-btn build-btn"
              @click="emit('start-build')"
            >
              开始构建图谱 →
            </button>
          </div>

          <!-- Stats Cards -->
          <div class="stats-grid" v-if="graphStats.nodes > 0 || currentPhase >= 1">
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.nodes }}</span>
              <span class="stat-label">实体节点</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.edges }}</span>
              <span class="stat-label">关系边</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.types }}</span>
              <span class="stat-label">SCHEMA类型</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 手动合并节点 -->
      <div class="step-card" v-if="graphStats.nodes > 0">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num" style="color:#000">⇄</span>
            <span class="step-title">手动合并节点</span>
          </div>
          <button class="toggle-merge-btn" @click="showMergePanel = !showMergePanel">
            {{ showMergePanel ? '收起' : '展开' }}
          </button>
        </div>

        <div v-if="showMergePanel" class="card-content">
          <p class="description">选择 2 个或更多节点后点击合并。边数最多的节点将作为主节点保留，其余节点的关系边会转移过来后被删除。</p>

          <!-- 已选节点 -->
          <div v-if="selectedForMerge.size > 0" class="selected-nodes">
            <span class="tag-label">已选 {{ selectedForMerge.size }} 个节点</span>
            <div class="selected-tags">
              <span
                v-for="uuid in selectedForMerge"
                :key="uuid"
                class="selected-tag"
                @click="selectedForMerge.delete(uuid)"
                :title="nodeMap[uuid]?.summary"
              >
                {{ nodeMap[uuid]?.name || uuid.slice(0, 8) }} ×
              </span>
            </div>
            <button
              class="action-btn merge-btn"
              :disabled="selectedForMerge.size < 2 || merging"
              @click="handleMerge"
            >
              <span v-if="merging" class="spinner-sm"></span>
              {{ merging ? '合并中...' : `合并所选 ${selectedForMerge.size} 个节点` }}
            </button>
            <div v-if="mergeResult" class="merge-result" :class="mergeResult.ok ? 'ok' : 'err'">
              {{ mergeResult.msg }}
            </div>
          </div>

          <!-- 节点列表 -->
          <div class="merge-search">
            <input
              v-model="mergeSearch"
              placeholder="搜索节点名称..."
              class="setting-input"
              style="width:100%"
            />
          </div>
          <div class="node-list">
            <div
              v-for="node in filteredNodes"
              :key="node.uuid"
              class="node-row"
              :class="{ selected: selectedForMerge.has(node.uuid) }"
              @click="toggleSelect(node.uuid)"
            >
              <span class="node-check">{{ selectedForMerge.has(node.uuid) ? '☑' : '☐' }}</span>
              <div class="node-info">
                <span class="node-name">{{ node.name }}</span>
                <span class="node-summary">{{ node.summary?.slice(0, 80) || '—' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: Complete -->
      <div class="step-card" :class="{ 'active': currentPhase === 2, 'completed': currentPhase >= 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">构建完成</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase >= 2" class="badge accent">进行中</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">图谱构建已完成，请选择模拟模式</p>
          <div class="mode-buttons">
            <button
              class="action-btn mode-btn oasis-btn"
              :disabled="currentPhase < 2 || creatingSimulation"
              @click="handleEnterEnvSetup"
            >
              <span v-if="creatingSimulation === 'oasis'" class="spinner-sm"></span>
              {{ creatingSimulation === 'oasis' ? '创建中...' : 'OASIS 双平台模拟 →' }}
            </button>
            <button
              class="action-btn mode-btn narrative-btn"
              :disabled="currentPhase < 2 || creatingSimulation"
              @click="handleEnterNarrative"
            >
              <span v-if="creatingSimulation === 'narrative'" class="spinner-sm"></span>
              {{ creatingSimulation === 'narrative' ? '创建中...' : 'RP 叙事模式 →' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ projectData?.project_id || 'NO_PROJECT' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, reactive, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { createSimulation } from '../api/simulation'
import { mergeEntities } from '../api/graph'

const router = useRouter()

const props = defineProps({
  currentPhase: { type: Number, default: 0 },
  projectData: Object,
  ontologyProgress: Object,
  buildProgress: Object,
  graphData: Object,
  systemLogs: { type: Array, default: () => [] },
  buildSettings: { type: Object, default: () => ({ chunk_size: 1500, batch_size: 10, chunk_overlap: 50 }) }
})

const emit = defineEmits(['next-step', 'start-build', 'update-settings', 'refresh-graph'])

// 本地设置副本，用于输入框绑定
const localSettings = reactive({ ...props.buildSettings })

// 同步父组件传入的 buildSettings
watch(() => props.buildSettings, (val) => {
  Object.assign(localSettings, val)
}, { deep: true })

const updateSetting = (key, event) => {
  const val = Number(event.target.value)
  if (!isNaN(val) && val > 0) {
    localSettings[key] = val
    emit('update-settings', { ...localSettings })
  }
}

const selectedOntologyItem = ref(null)
const logContent = ref(null)
const creatingSimulation = ref(false) // false | 'oasis' | 'narrative'

// 手动合并
const showMergePanel = ref(false)
const mergeSearch = ref('')
const selectedForMerge = reactive(new Set())
const merging = ref(false)
const mergeResult = ref(null)

const nodeMap = computed(() => {
  const map = {}
  for (const n of (props.graphData?.nodes || [])) {
    map[n.uuid] = n
  }
  return map
})

const filteredNodes = computed(() => {
  const nodes = props.graphData?.nodes || []
  const q = mergeSearch.value.trim().toLowerCase()
  return q ? nodes.filter(n => n.name?.toLowerCase().includes(q)) : nodes
})

const toggleSelect = (uuid) => {
  if (selectedForMerge.has(uuid)) selectedForMerge.delete(uuid)
  else selectedForMerge.add(uuid)
}

const handleMerge = async () => {
  if (selectedForMerge.size < 2 || merging.value) return
  const graphId = props.projectData?.graph_id
  if (!graphId) { mergeResult.value = { ok: false, msg: '缺少 graph_id' }; return }

  merging.value = true
  mergeResult.value = null
  try {
    const res = await mergeEntities(graphId, [...selectedForMerge])
    if (res.success) {
      mergeResult.value = { ok: true, msg: `合并成功，保留节点: ${res.data?.canonical_uuid?.slice(0, 8)}...` }
      selectedForMerge.clear()
      emit('refresh-graph')
    } else {
      mergeResult.value = { ok: false, msg: res.error || '合并失败' }
    }
  } catch (e) {
    mergeResult.value = { ok: false, msg: e.message }
  } finally {
    merging.value = false
  }
}

// 进入环境搭建 - 创建 simulation 并跳转（OASIS 模式）
const handleEnterEnvSetup = async () => {
  if (!props.projectData?.project_id || !props.projectData?.graph_id) {
    console.error('缺少项目或图谱信息')
    return
  }

  creatingSimulation.value = 'oasis'

  try {
    const res = await createSimulation({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      enable_twitter: true,
      enable_reddit: true,
      mode: 'oasis'
    })

    if (res.success && res.data?.simulation_id) {
      router.push({
        name: 'Simulation',
        params: { simulationId: res.data.simulation_id }
      })
    } else {
      console.error('创建模拟失败:', res.error)
      alert('创建模拟失败: ' + (res.error || '未知错误'))
    }
  } catch (err) {
    console.error('创建模拟异常:', err)
    alert('创建模拟异常: ' + err.message)
  } finally {
    creatingSimulation.value = false
  }
}

// 进入叙事模式 - 创建 simulation 并跳转（narrative 模式）
const handleEnterNarrative = async () => {
  if (!props.projectData?.project_id || !props.projectData?.graph_id) {
    console.error('缺少项目或图谱信息')
    return
  }

  creatingSimulation.value = 'narrative'

  try {
    const res = await createSimulation({
      project_id: props.projectData.project_id,
      graph_id: props.projectData.graph_id,
      enable_twitter: false,
      enable_reddit: true,  // 需要启用至少一个平台，否则 profiles 不会保存到磁盘
      mode: 'narrative'
    })

    if (res.success && res.data?.simulation_id) {
      router.push({
        name: 'Simulation',
        params: { simulationId: res.data.simulation_id },
        query: { mode: 'narrative' }
      })
    } else {
      console.error('创建模拟失败:', res.error)
      alert('创建模拟失败: ' + (res.error || '未知错误'))
    }
  } catch (err) {
    console.error('创建模拟异常:', err)
    alert('创建模拟异常: ' + err.message)
  } finally {
    creatingSimulation.value = false
  }
}

const selectOntologyItem = (item, type) => {
  selectedOntologyItem.value = { ...item, itemType: type }
}

const graphStats = computed(() => {
  const nodes = props.graphData?.node_count || props.graphData?.nodes?.length || 0
  const edges = props.graphData?.edge_count || props.graphData?.edges?.length || 0
  const types = props.projectData?.ontology?.entity_types?.length || 0
  return { nodes, edges, types }
})

const formatDate = (dateStr) => {
  if (!dateStr) return '--:--:--'
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour12: false }) + '.' + d.getMilliseconds()
}

// Auto-scroll logs
watch(() => props.systemLogs.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})
</script>

<style scoped>
.workbench-panel {
  height: 100%;
  background-color: #FAFAFA;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.3s ease;
  position: relative; /* For absolute overlay */
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.accent { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

/* Step 01 Tags */
.tags-container {
  margin-top: 12px;
  transition: opacity 0.3s;
}

.tags-container.dimmed {
    opacity: 0.3;
    pointer-events: none;
}

.tag-label {
  display: block;
  font-size: 10px;
  color: #AAA;
  margin-bottom: 8px;
  font-weight: 600;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  background: #F5F5F5;
  border: 1px solid #EEE;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.2s;
}

.entity-tag.clickable {
    cursor: pointer;
}

.entity-tag.clickable:hover {
    background: #E0E0E0;
    border-color: #CCC;
}

.entity-tag--agent {
  border-color: #B8D4F0;
  background: #EEF5FD;
}

.entity-tag--static {
  border-color: #DDD;
  background: #F5F5F5;
  opacity: 0.75;
}

.tag-badge {
  display: inline-block;
  margin-left: 5px;
  padding: 0 4px;
  border-radius: 3px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  vertical-align: middle;
  line-height: 1.6;
}

.tag-badge--agent {
  background: #C8E0F8;
  color: #2A6BA8;
}

.tag-badge--static {
  background: #E8E8E8;
  color: #888;
}

/* Ontology Detail Overlay */
.ontology-detail-overlay {
    position: absolute;
    top: 60px; /* Below header roughly */
    left: 20px;
    right: 20px;
    bottom: 20px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(4px);
    z-index: 10;
    border: 1px solid #EAEAEA;
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

.detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #EAEAEA;
    background: #FAFAFA;
}

.detail-title-group {
    display: flex;
    align-items: center;
    gap: 8px;
}

.detail-type-badge {
    font-size: 9px;
    font-weight: 700;
    color: #FFF;
    background: #000;
    padding: 2px 6px;
    border-radius: 2px;
    text-transform: uppercase;
}

.detail-name {
    font-size: 14px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

.close-btn {
    background: none;
    border: none;
    font-size: 18px;
    color: #999;
    cursor: pointer;
    line-height: 1;
}

.close-btn:hover {
    color: #333;
}

.detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}

.detail-desc {
    font-size: 12px;
    color: #444;
    line-height: 1.5;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px dashed #EAEAEA;
}

.detail-section {
    margin-bottom: 16px;
}

.section-label {
    display: block;
    font-size: 10px;
    font-weight: 600;
    color: #AAA;
    margin-bottom: 8px;
}

.attr-list, .conn-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.attr-item {
    font-size: 11px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: baseline;
    padding: 4px;
    background: #F9F9F9;
    border-radius: 4px;
}

.attr-name {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #000;
}

.attr-type {
    color: #999;
    font-size: 10px;
}

.attr-desc {
    color: #555;
    flex: 1;
    min-width: 150px;
}

.example-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}

.example-tag {
    font-size: 11px;
    background: #FFF;
    border: 1px solid #E0E0E0;
    padding: 3px 8px;
    border-radius: 12px;
    color: #555;
}

.conn-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    padding: 6px;
    background: #F5F5F5;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}

.conn-node {
    font-weight: 600;
    color: #333;
}

.conn-arrow {
    color: #BBB;
}

/* Build Settings */
.build-settings {
  margin-bottom: 16px;
}

.build-settings .settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin-top: 8px;
}

.build-settings .setting-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.build-settings .setting-label {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  color: #666;
  font-weight: 600;
}

.build-settings .setting-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #E0E0E0;
  background: #F9F9F9;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
  border-radius: 4px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.build-settings .setting-input:focus {
  border-color: #FF5722;
}

.build-settings .setting-input:disabled {
  background: #F0F0F0;
  color: #999;
  cursor: not-allowed;
}

.build-settings .setting-hint {
  font-size: 10px;
  color: #AAA;
}

.build-settings .settings-note {
  margin-top: 8px;
  font-size: 10px;
  color: #AAA;
}

.build-btn {
  width: 100%;
  margin-top: 12px;
  background: #FF5722 !important;
}

.build-btn:hover:not(:disabled) {
  background: #E64A19 !important;
  opacity: 1 !important;
}

/* Step 02 Stats */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Step 03 Buttons */
.mode-buttons {
  display: flex;
  gap: 12px;
}

.action-btn {
  flex: 1;
  background: #000;
  color: #FFF;
  border: none;
  padding: 14px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.85;
  transform: translateY(-1px);
}

.action-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
  transform: none;
}

.narrative-btn {
  background: #FF5722;
}

.narrative-btn:hover:not(:disabled) {
  background: #E64A19;
  opacity: 1;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #FF5722;
  margin-bottom: 12px;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid #FFCCBC;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}

/* 手动合并 */
.toggle-merge-btn {
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid #E0E0E0;
  background: #F5F5F5;
  border-radius: 4px;
  cursor: pointer;
  color: #555;
}
.toggle-merge-btn:hover { background: #E0E0E0; }

.selected-nodes {
  margin-bottom: 12px;
}
.selected-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 10px;
}
.selected-tag {
  background: #FF5722;
  color: #FFF;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 12px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
}
.selected-tag:hover { background: #E64A19; }

.merge-btn {
  width: 100%;
  margin-top: 4px;
  background: #000;
}
.merge-result {
  margin-top: 8px;
  font-size: 11px;
  padding: 6px 10px;
  border-radius: 4px;
}
.merge-result.ok { background: #E8F5E9; color: #2E7D32; }
.merge-result.err { background: #FFEBEE; color: #C62828; }

.merge-search { margin: 10px 0 8px; }

.node-list {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid #EAEAEA;
  border-radius: 4px;
}
.node-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  cursor: pointer;
  border-bottom: 1px solid #F5F5F5;
  transition: background 0.15s;
}
.node-row:last-child { border-bottom: none; }
.node-row:hover { background: #F9F9F9; }
.node-row.selected { background: #FFF3E0; }

.node-check {
  font-size: 14px;
  color: #FF5722;
  flex-shrink: 0;
  margin-top: 1px;
}
.node-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.node-name {
  font-size: 12px;
  font-weight: 600;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}
.node-summary {
  font-size: 11px;
  color: #888;
  line-height: 1.4;
  word-break: break-all;
}
</style>
