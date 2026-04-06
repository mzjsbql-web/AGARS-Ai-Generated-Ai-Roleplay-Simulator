<template>
  <div class="narrative-player">
    <!-- Status Bar -->
    <div class="status-bar">
      <div class="status-left">
        <span class="turn-indicator">Turn {{ currentTurn }}</span>
        <span class="status-badge" :class="statusClass">
          <span class="status-dot"></span>
          {{ statusLabel }}
        </span>
      </div>
      <div class="status-right">
        <button
          class="save-btn"
          :class="{ 'save-success': saveSuccess }"
          @click="handleSave"
          v-if="canSave"
          :disabled="saving"
        >
          {{ saveSuccess ? '已存档' : (saving ? '存档中...' : '存档') }}
        </button>
        <div class="load-save-wrapper">
          <button class="load-btn" @click="toggleSaveList">读档</button>
          <div class="save-list-panel" v-if="showSaveList">
            <div class="save-list-header">
              <span>存档列表</span>
              <button class="save-list-close" @click="showSaveList = false">×</button>
            </div>
            <div class="save-list-loading" v-if="savesLoading">加载中...</div>
            <div class="save-list-empty" v-else-if="saves.length === 0">暂无存档</div>
            <div
              v-else
              v-for="s in saves"
              :key="s.save_id"
              class="save-list-item"
            >
              <div class="save-item-info">
                <span class="save-item-desc">{{ s.description }}</span>
                <span class="save-item-time">{{ formatSaveTime(s.save_time) }}</span>
              </div>
              <div class="save-item-actions">
                <button class="save-item-load" @click="handleLoadSave(s.save_id)" :disabled="loadingSaveId === s.save_id">
                  {{ loadingSaveId === s.save_id ? '读取中...' : '读取' }}
                </button>
                <button class="save-item-del" @click="handleDeleteSave(s.save_id)">删</button>
              </div>
            </div>
          </div>
        </div>
        <button class="stop-btn" @click="handleStop" v-if="isRunning">
          停止
        </button>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="content-area">
      <!-- Left: Main Narrative -->
      <div class="narrative-panel">
        <div class="narrative-scroll" ref="narrativeScroll">
          <template v-for="(segment, idx) in narrativeSegments" :key="idx">
            <!-- Player Choice -->
            <div
              v-if="segment.type === 'player_choice'"
              class="player-choice-segment"
              :class="{ 'new-segment': idx >= previousSegmentCount }"
            >▷ {{ segment.text }}</div>

            <!-- Opening / Player Scene -->
            <div
              v-else-if="segment.type !== 'npc_events'"
              class="narrative-segment"
              :class="{ 'new-segment': idx >= previousSegmentCount }"
            >
              <!-- 时间地点标头（player_scene 有 world_time 时显示） -->
              <div v-if="segment.world_time" class="segment-time-header">
                {{ segment.world_time }}{{ segment.location ? ' · ' + segment.location : '' }}
              </div>
              <p
                v-for="(para, pIdx) in splitParagraphs(segment.text)"
                :key="pIdx"
              >{{ para.text }}</p>
            </div>

            <!-- NPC Events: collapsible block -->
            <div
              v-else
              class="npc-events-block"
              :class="{ 'new-segment': idx >= previousSegmentCount }"
            >
              <div class="npc-events-header" @click="toggleNpcBlock(idx)">
                <span class="npc-events-icon">{{ expandedNpcBlocks[idx] ? '▾' : '▸' }}</span>
                <span class="npc-events-title">背景动态 · {{ segment.world_time || ('回合 ' + segment.turn_number) }}</span>
                <span class="npc-events-count">{{ (segment.events || []).length }} 条</span>
              </div>
              <transition name="expand">
                <div class="npc-events-body" v-if="expandedNpcBlocks[idx]">
                  <div
                    v-for="(event, eIdx) in (segment.events || [])"
                    :key="eIdx"
                    class="npc-event-item"
                    :class="{ 'high-importance': event.importance >= 0.7 }"
                  >
                    <span class="npc-event-agent">{{ event.agent_name }}</span>
                    <span class="npc-event-desc">{{ event.action_description }}</span>
                  </div>
                </div>
              </transition>
            </div>
          </template>

          <!-- Typing indicator when NPCs are processing -->
          <div class="typing-indicator" v-if="status === 'running'">
            <span></span><span></span><span></span>
            NPC 正在行动...
          </div>
        </div>
      </div>

      <!-- Right: Side Panel -->
      <div class="side-panel">
        <!-- World Map -->
        <WorldMapPanel
          :worldMap="worldMap"
          :agentLocations="agentLocations"
          :profiles="characterProfiles"
          :playerEntityUuid="playerEntityUuid"
        />

        <!-- Collapsible Character Profiles -->
        <div class="side-section profiles-section" :class="{ collapsed: profilesPanelCollapsed }">
          <h3 @click="profilesPanelCollapsed = !profilesPanelCollapsed" class="collapsible-header">
            <span class="collapse-icon">{{ profilesPanelCollapsed ? '▸' : '▾' }}</span>
            角色列表 <span class="count-badge">{{ characterProfiles.length }}</span>
          </h3>
          <div v-if="!profilesPanelCollapsed" class="profiles-panel-body">
            <div class="profiles-panel-search">
              <input
                v-model="profilePanelSearch"
                type="text"
                placeholder="搜索角色名..."
                class="profiles-panel-search-input"
              />
            </div>
            <div class="profiles-panel-scroll">
              <div
                v-for="profile in filteredPanelProfiles"
                :key="profile.entity_uuid"
                class="profile-panel-item"
                :class="{
                  'is-player': profile.is_player,
                  expanded: expandedProfileUuid === profile.entity_uuid
                }"
              >
                <div class="profile-panel-row" @click="toggleProfileExpand(profile.entity_uuid)">
                  <span class="profile-panel-name">
                    {{ profile.name }}
                    <span v-if="profile.is_player" class="profile-panel-player-tag">玩家</span>
                  </span>
                  <span class="profile-panel-loc">{{ agentLocations[profile.entity_uuid] || profile.current_location || '' }}</span>
                </div>
                <div v-if="expandedProfileUuid === profile.entity_uuid" class="profile-panel-detail">
                  <div v-if="profile.profession" class="profile-detail-line"><span class="detail-label">职业</span>{{ profile.profession }}</div>
                  <div v-if="profile.personality" class="profile-detail-line"><span class="detail-label">性格</span>{{ profile.personality }}</div>
                  <div v-if="profile.temperament" class="profile-detail-line"><span class="detail-label">气质</span>{{ profile.temperament }}</div>
                  <div v-if="profile.goals && profile.goals.length" class="profile-detail-line"><span class="detail-label">目标</span>{{ profile.goals.join('、') }}</div>
                  <div v-if="profile.backstory" class="profile-detail-line"><span class="detail-label">背景</span>{{ profile.backstory.length > 100 ? profile.backstory.slice(0, 100) + '...' : profile.backstory }}</div>
                  <div v-if="profile.speech_style" class="profile-detail-line"><span class="detail-label">话风</span>{{ profile.speech_style }}</div>
                  <button class="profile-panel-edit-btn" @click.stop="openCharacterEditFromPanel(profile)">编辑</button>
                </div>
              </div>
              <div v-if="filteredPanelProfiles.length === 0" class="profiles-panel-empty">无匹配角色</div>
            </div>
          </div>
        </div>

        <!-- Background Events -->
        <div class="side-section events-section">
          <h3>背景事件 <span class="count-badge">{{ backgroundEvents.length }}</span></h3>
          <div class="events-scroll" ref="eventsScroll">
            <div
              v-for="(event, idx) in backgroundEvents"
              :key="idx"
              class="event-item"
              :class="{ 'high-importance': event.importance >= 0.7 }"
            >
              <div class="event-header">
                <span class="event-agent">{{ event.agent_name }}</span>
                <span class="event-turn">T{{ event.turn_number }}</span>
              </div>
              <div class="event-body">{{ event.action_description }}</div>
            </div>
            <div v-if="backgroundEvents.length === 0" class="empty-events">
              暂无事件
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Character Editor Modal (during awaiting_player) -->
    <transition name="fade">
      <div class="char-editor-overlay" v-if="showCharacterEditor" @click.self="showCharacterEditor = false">
        <div class="char-editor-panel">
          <div class="char-editor-header">
            <span class="char-editor-title">{{ editingCharacter ? '编辑角色' : '角色列表' }}</span>
            <button class="char-editor-close" @click="closeCharacterEditor">&times;</button>
          </div>

          <!-- Character list -->
          <div v-if="!editingCharacter" class="char-list">
            <div class="char-list-scroll">
              <div
                v-for="profile in characterProfiles"
                :key="profile.entity_uuid"
                class="char-item"
                :class="{ 'is-player': profile.is_player }"
              >
                <div class="char-item-info">
                  <span class="char-item-name">{{ profile.name }}</span>
                  <span class="char-item-type">{{ profile.entity_type || '角色' }}</span>
                  <span v-if="profile.is_player" class="char-item-player-badge">玩家</span>
                  <span v-if="profile.current_location && profile.current_location !== '未知'" class="char-item-location-badge">
                    {{ profile.current_location }}
                  </span>
                </div>
                <button class="char-item-edit-btn" @click="openCharacterEdit(profile)">编辑</button>
              </div>
            </div>
            <button class="char-add-btn" @click="openCharacterAdd">+ 添加新角色</button>
          </div>

          <!-- Character edit form -->
          <div v-else class="char-edit-form">
            <div class="char-form-scroll">
              <div class="form-group">
                <label>名称</label>
                <input v-model="charForm.name" placeholder="角色名称" />
              </div>
              <div class="form-row">
                <div class="form-group half">
                  <label>职业</label>
                  <input v-model="charForm.profession" placeholder="职业" />
                </div>
                <div class="form-group half">
                  <label>性别</label>
                  <select v-model="charForm.gender">
                    <option value="male">男</option>
                    <option value="female">女</option>
                    <option value="other">其他</option>
                  </select>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group half">
                  <label>年龄</label>
                  <input v-model.number="charForm.age" type="number" placeholder="年龄" />
                </div>
                <div class="form-group half">
                  <label>MBTI</label>
                  <input v-model="charForm.mbti" placeholder="如 INTJ" />
                </div>
              </div>
              <div class="form-group">
                <label>人设/性格</label>
                <textarea v-model="charForm.persona" rows="3" placeholder="角色性格描述"></textarea>
              </div>
              <div class="form-group">
                <label>背景/简介</label>
                <textarea v-model="charForm.bio" rows="3" placeholder="角色背景故事"></textarea>
              </div>
              <div class="form-group">
                <label>话题兴趣 (逗号分隔)</label>
                <input v-model="charForm.topicsStr" placeholder="话题1, 话题2, ..." />
              </div>
              <div class="form-group">
                <label>关系 <span style="color:#888;font-size:12px">（与其他角色的关系，对应图谱边）</span></label>
                <div v-for="(rel, rIdx) in charForm.relationships" :key="rIdx" class="char-rel-row">
                  <input v-model="rel.name" placeholder="角色名" class="char-rel-name" />
                  <input v-model="rel.relation" placeholder="关系描述" class="char-rel-desc" />
                  <button class="char-rel-remove" @click="charForm.relationships.splice(rIdx, 1)">&times;</button>
                  <span v-if="rel.source === 'graph'" class="char-rel-badge">图谱</span>
                  <span v-else-if="rel.source === 'llm'" class="char-rel-badge llm">推断</span>
                </div>
                <button class="char-rel-add" @click="charForm.relationships.push({ name: '', relation: '' })">+ 添加关系</button>
              </div>
            </div>
            <div class="char-form-actions">
              <button class="char-form-cancel" @click="editingCharacter = null">取消</button>
              <button class="char-form-save" @click="saveCharacterEdit" :disabled="charSaving">
                {{ charSaving ? '保存中...' : '保存' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Choice Panel (slides up when awaiting player) -->
    <transition name="slide-up">
      <div class="choice-panel" v-if="status === 'awaiting_player' && playerTurnData">
        <div class="choice-header">
          你的回合 - 请做出选择
          <button class="edit-characters-btn" @click="openCharacterList">编辑角色</button>
        </div>
        <div class="choice-grid">
          <button
            v-for="choice in playerTurnData.choices"
            :key="choice.id"
            class="choice-btn"
            :class="[`risk-${choice.risk_level}`, { selected: selectedChoiceId === choice.id }]"
            @click="selectChoice(choice.id)"
          >
            <span class="choice-label">{{ choice.label }}</span>
            <span class="choice-desc">{{ choice.description }}</span>
            <span class="choice-risk">{{ riskLabels[choice.risk_level] || choice.risk_level }}</span>
          </button>
        </div>
        <div class="free-text-area">
          <input
            type="text"
            v-model="freeText"
            placeholder="或者输入自定义行动..."
            class="free-text-input"
            @keydown.enter="submitInput"
          />
          <button class="submit-btn" @click="submitInput" :disabled="submitting">
            {{ submitting ? '提交中...' : '确认' }}
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import {
  getNarrativeStatus,
  getNarrativeText,
  getNarrativeEvents,
  getNarrativeSession,
  submitPlayerInput,
  stopNarrative,
  getNarrativeProfiles,
  updateNarrativeProfile,
  addNarrativeProfile,
  saveNarrative,
  listNarrativeSaves,
  loadNarrativeSave,
  deleteNarrativeSave
} from '../api/narrative'
import WorldMapPanel from './WorldMapPanel.vue'

const props = defineProps({
  sessionId: { type: String, required: true }
})

const emit = defineEmits(['add-log', 'update-status'])

// --- State ---
const status = ref('idle')
const currentTurn = ref(0)
const narrativeSegments = ref([])
const backgroundEvents = ref([])
const playerTurnData = ref(null)
const previousSegmentCount = ref(0)
const selectedChoiceId = ref(null)
const freeText = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const expandedNpcBlocks = ref({})  // idx → boolean

// World map
const worldMap = ref({})
const agentLocations = ref({})
const playerEntityUuid = ref('')

// Polling state
let statusTimer = null
let narrativeTimer = null
let eventsTimer = null
let lastSegmentIndex = 0
let lastEventTurn = 0

// Refs
const narrativeScroll = ref(null)
const eventsScroll = ref(null)

// Constants
const riskLabels = {
  safe: '安全',
  moderate: '稳健',
  exploratory: '探索',
  risky: '冒险'
}

// --- Helpers ---
const splitParagraphs = (text) => {
  if (!text) return []
  return text.split('\n').filter(p => p.trim()).map(p => ({ text: p.trim() }))
}

const toggleNpcBlock = (idx) => {
  expandedNpcBlocks.value[idx] = !expandedNpcBlocks.value[idx]
}

// Normalize segment: if it's a string (old format), wrap into dict
const normalizeSegment = (s) => {
  if (typeof s === 'string') {
    return { text: s, type: 'opening', turn_number: 0, timestamp: '' }
  }
  return s
}

// --- Computed ---
const isRunning = computed(() => ['running', 'awaiting_player', 'processing_player'].includes(status.value))

const statusClass = computed(() => status.value)

const statusLabel = computed(() => {
  const labels = {
    idle: '待机',
    running: 'NPC 行动中',
    awaiting_player: '你的回合',
    processing_player: '处理中...',
    completed: '已结束',
    failed: '发生错误'
  }
  return labels[status.value] || status.value
})

// --- Polling ---
const startPolling = () => {
  stopPolling()
  statusTimer = setInterval(fetchStatus, 2000)
  narrativeTimer = setInterval(fetchNarrative, 3000)
  eventsTimer = setInterval(fetchEvents, 3000)
  // Immediate fetch
  fetchStatus()
  fetchNarrative()
  fetchEvents()
}

const stopPolling = () => {
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null }
  if (narrativeTimer) { clearInterval(narrativeTimer); narrativeTimer = null }
  if (eventsTimer) { clearInterval(eventsTimer); eventsTimer = null }
}

const fetchStatus = async () => {
  try {
    const res = await getNarrativeStatus(props.sessionId)
    if (res.success && res.data) {
      const prev = status.value
      status.value = res.data.status
      currentTurn.value = res.data.current_turn || 0
      errorMessage.value = res.data.error_message || ''

      if (res.data.player_turn_data && res.data.status === 'awaiting_player') {
        playerTurnData.value = res.data.player_turn_data
      }

      // Update live spatial data
      if (res.data.agent_locations) {
        agentLocations.value = res.data.agent_locations
      }
      if (res.data.player_entity_uuid) {
        playerEntityUuid.value = res.data.player_entity_uuid
      }

      // Emit status updates
      if (prev !== status.value) {
        emit('update-status', status.value === 'failed' ? 'error' :
          (status.value === 'completed' ? 'completed' : 'processing'))
      }

      // Stop polling when completed/failed/awaiting_player
      if (['completed', 'failed', 'awaiting_player'].includes(status.value)) {
        stopPolling()
        // Final fetch
        fetchNarrative()
        fetchEvents()
      }
    }
  } catch (err) {
    console.error('Status poll error:', err)
  }
}

// Fetch world map and profiles once (they change rarely)
const fetchSessionMeta = async () => {
  try {
    const res = await getNarrativeSession(props.sessionId)
    if (res.success && res.data) {
      if (res.data.world_map && Object.keys(res.data.world_map).length > 0) {
        worldMap.value = res.data.world_map
      }
      if (res.data.player_entity_uuid) {
        playerEntityUuid.value = res.data.player_entity_uuid
      }
      if (res.data.agent_locations) {
        agentLocations.value = res.data.agent_locations
      }
    }
  } catch (err) {
    console.error('Session meta fetch error:', err)
  }
}

// Also load profiles for the map (reuse characterProfiles)
const fetchProfilesForMap = async () => {
  try {
    const res = await getNarrativeProfiles(props.sessionId)
    if (res.success && res.data?.profiles) {
      characterProfiles.value = res.data.profiles
    }
  } catch (err) {
    // non-fatal
  }
}

let _fetchingNarrative = false
const fetchNarrative = async () => {
  if (_fetchingNarrative) return
  _fetchingNarrative = true
  try {
    const res = await getNarrativeText(props.sessionId, lastSegmentIndex)
    if (res.success && res.data) {
      const newSegments = (res.data.segments || []).map(normalizeSegment)
      if (newSegments.length > 0) {
        // 去重：用 turn_number + type 过滤已存在的段落
        const existing = new Set(
          narrativeSegments.value.map(s => `${s.turn_number}-${s.type}`)
        )
        const deduped = newSegments.filter(s => {
          const key = `${s.turn_number}-${s.type}`
          if (existing.has(key)) return false
          existing.add(key)
          return true
        })
        if (deduped.length > 0) {
          previousSegmentCount.value = narrativeSegments.value.length
          narrativeSegments.value.push(...deduped)
          // Auto-scroll
          await nextTick()
          autoScrollNarrative()
        }
        lastSegmentIndex = res.data.total_segments || narrativeSegments.value.length
      }
    }
  } catch (err) {
    console.error('Narrative poll error:', err)
  } finally {
    _fetchingNarrative = false
  }
}

const fetchEvents = async () => {
  try {
    const res = await getNarrativeEvents(props.sessionId, lastEventTurn)
    if (res.success && res.data) {
      const newEvents = (res.data.events || []).filter(e => !e.is_player)
      if (newEvents.length > 0) {
        // Dedup by turn_number + agent_name
        const existing = new Set(
          backgroundEvents.value.map(e => `${e.turn_number}-${e.agent_name}-${e.action_type}`)
        )
        let hasNewLocation = false
        for (const e of newEvents) {
          const key = `${e.turn_number}-${e.agent_name}-${e.action_type}`
          if (!existing.has(key)) {
            backgroundEvents.value.push(e)
            existing.add(key)
            if (e.action_type === 'location_reveal') {
              hasNewLocation = true
            }
          }
        }
        // Update cursor
        const maxTurn = Math.max(...newEvents.map(e => e.turn_number || 0))
        if (maxTurn > lastEventTurn) {
          lastEventTurn = maxTurn
        }
        // Refresh world map if a new location was revealed
        if (hasNewLocation) {
          fetchSessionMeta()
        }
      }
    }
  } catch (err) {
    console.error('Events poll error:', err)
  }
}

// --- Scroll ---
const autoScrollNarrative = () => {
  if (narrativeScroll.value) {
    narrativeScroll.value.scrollTop = narrativeScroll.value.scrollHeight
  }
}

// --- Player Input ---
const selectChoice = (id) => {
  selectedChoiceId.value = id
  freeText.value = ''
}

const submitInput = async () => {
  if (submitting.value) return
  if (!selectedChoiceId.value && !freeText.value.trim()) return

  submitting.value = true
  try {
    const payload = { session_id: props.sessionId }
    if (freeText.value.trim()) {
      payload.free_text = freeText.value.trim()
    } else {
      payload.choice_id = selectedChoiceId.value
    }

    await submitPlayerInput(payload)

    // Reset
    selectedChoiceId.value = null
    freeText.value = ''
    playerTurnData.value = null
    emit('add-log', '玩家输入已提交')

    // Resume polling to track backend processing
    startPolling()
  } catch (err) {
    console.error('Submit error:', err)
    emit('add-log', `提交失败: ${err.message}`)
  } finally {
    submitting.value = false
  }
}

// --- Collapsible Profile Panel (side panel) ---
const profilesPanelCollapsed = ref(false)
const expandedProfileUuid = ref(null)
const profilePanelSearch = ref('')

const filteredPanelProfiles = computed(() => {
  const q = profilePanelSearch.value.trim().toLowerCase()
  if (!q) return characterProfiles.value
  return characterProfiles.value.filter(p =>
    (p.name || '').toLowerCase().includes(q)
  )
})

const toggleProfileExpand = (uuid) => {
  expandedProfileUuid.value = expandedProfileUuid.value === uuid ? null : uuid
}

const openCharacterEditFromPanel = (profile) => {
  showCharacterEditor.value = true
  openCharacterEdit(profile)
}

// --- Character Editor ---
const showCharacterEditor = ref(false)
const characterProfiles = ref([])
const editingCharacter = ref(null)  // null = list view, object = editing
const editingCharacterIsNew = ref(false)
const charSaving = ref(false)
const charForm = ref({
  name: '', profession: '', gender: 'male', age: null,
  mbti: '', persona: '', bio: '', topicsStr: '',
  relationships: []
})

const openCharacterList = async () => {
  showCharacterEditor.value = true
  editingCharacter.value = null
  try {
    const res = await getNarrativeProfiles(props.sessionId)
    if (res.success && res.data?.profiles) {
      characterProfiles.value = res.data.profiles
    }
  } catch (err) {
    console.error('Failed to load profiles:', err)
  }
}

const closeCharacterEditor = () => {
  showCharacterEditor.value = false
  editingCharacter.value = null
}

const openCharacterEdit = (profile) => {
  editingCharacter.value = profile
  editingCharacterIsNew.value = false
  charForm.value = {
    name: profile.name || '',
    profession: profile.profession || '',
    gender: profile.gender || 'male',
    age: profile.age || null,
    mbti: profile.mbti || '',
    persona: profile.persona || profile.personality || '',
    bio: profile.bio || profile.backstory || '',
    topicsStr: (profile.interested_topics || profile.goals || []).join(', '),
    relationships: (profile.relationships || []).map(r => ({ ...r }))
  }
}

const openCharacterAdd = () => {
  editingCharacter.value = { _isNew: true }
  editingCharacterIsNew.value = true
  charForm.value = {
    name: '', profession: '', gender: 'male', age: null,
    mbti: '', persona: '', bio: '', topicsStr: '',
    relationships: []
  }
}

const saveCharacterEdit = async () => {
  if (charSaving.value) return
  const form = charForm.value
  if (!form.name.trim()) return

  charSaving.value = true
  const topics = form.topicsStr.split(/[,，]/).map(t => t.trim()).filter(Boolean)
  const relationships = form.relationships.filter(r => r.name && r.relation)

  try {
    const profileData = {
      name: form.name,
      profession: form.profession,
      gender: form.gender,
      age: form.age,
      mbti: form.mbti,
      personality: form.persona,
      persona: form.persona,
      backstory: form.bio,
      bio: form.bio,
      goals: topics,
      interested_topics: topics,
      relationships: relationships
    }

    if (editingCharacterIsNew.value) {
      profileData.entity_type = '角色'
      const res = await addNarrativeProfile(props.sessionId, profileData)
      if (res.success && res.data) {
        characterProfiles.value.push(res.data)
        emit('add-log', `已添加角色: ${form.name}`)
      }
    } else {
      const uuid = editingCharacter.value.entity_uuid
      const res = await updateNarrativeProfile(props.sessionId, uuid, profileData)
      if (res.success && res.data) {
        // Update in local list
        const idx = characterProfiles.value.findIndex(p => p.entity_uuid === uuid)
        if (idx >= 0) {
          characterProfiles.value[idx] = res.data
        }
        emit('add-log', `已更新角色: ${form.name}`)
      }
    }
    editingCharacter.value = null
  } catch (err) {
    console.error('Save character failed:', err)
    emit('add-log', `保存角色失败: ${err.message}`)
  } finally {
    charSaving.value = false
  }
}

// --- Save ---
const saving = ref(false)
const saveSuccess = ref(false)
let saveSuccessTimer = null

const canSave = computed(() => ['awaiting_player', 'idle'].includes(status.value))

const handleSave = async () => {
  if (saving.value) return
  saving.value = true
  saveSuccess.value = false
  try {
    const res = await saveNarrative(props.sessionId)
    if (res.success) {
      saveSuccess.value = true
      emit('add-log', '存档成功')
      if (saveSuccessTimer) clearTimeout(saveSuccessTimer)
      saveSuccessTimer = setTimeout(() => { saveSuccess.value = false }, 2000)
      // 若存档列表已打开则刷新
      if (showSaveList.value) {
        const listRes = await listNarrativeSaves(props.sessionId)
        if (listRes.success) saves.value = listRes.data || []
      }
    } else {
      emit('add-log', `存档失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    console.error('Save error:', err)
    emit('add-log', `存档失败: ${err.message}`)
  } finally {
    saving.value = false
  }
}

// --- Save List ---
const showSaveList = ref(false)
const saves = ref([])
const savesLoading = ref(false)
const loadingSaveId = ref(null)

const formatSaveTime = (isoStr) => {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${mm}/${dd} ${hh}:${min}`
}

const toggleSaveList = async () => {
  showSaveList.value = !showSaveList.value
  if (showSaveList.value) {
    savesLoading.value = true
    try {
      const res = await listNarrativeSaves(props.sessionId)
      if (res.success) saves.value = res.data || []
    } catch (err) {
      console.error('List saves error:', err)
    } finally {
      savesLoading.value = false
    }
  }
}

const handleLoadSave = async (saveId) => {
  if (loadingSaveId.value) return
  loadingSaveId.value = saveId
  try {
    const res = await loadNarrativeSave(props.sessionId, saveId)
    if (res.success) {
      emit('add-log', `已读取存档（回合${res.data.current_turn}）`)
      showSaveList.value = false
    } else {
      emit('add-log', `读取失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    console.error('Load save error:', err)
    emit('add-log', `读取失败: ${err.message}`)
  } finally {
    loadingSaveId.value = null
  }
}

const handleDeleteSave = async (saveId) => {
  try {
    const res = await deleteNarrativeSave(props.sessionId, saveId)
    if (res.success) {
      saves.value = saves.value.filter(s => s.save_id !== saveId)
      emit('add-log', '存档已删除')
    }
  } catch (err) {
    console.error('Delete save error:', err)
  }
}

const handleStop = async () => {
  try {
    await stopNarrative({ session_id: props.sessionId })
    emit('add-log', '叙事引擎已停止')
  } catch (err) {
    console.error('Stop error:', err)
  }
}

// --- Lifecycle ---
onMounted(() => {
  startPolling()
  fetchSessionMeta()
  fetchProfilesForMap()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.narrative-player {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FAFAF9;
  font-family: 'Noto Serif SC', 'Source Han Serif SC', 'Georgia', serif;
  position: relative;
}

/* Status Bar */
.status-bar {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid #E8E5E0;
  background: #FFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.turn-indicator {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  color: #666;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
  background: #F0F0F0;
  color: #666;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #CCC;
}

.status-badge.running .status-dot { background: #FF5722; animation: pulse 1s infinite; }
.status-badge.awaiting_player { background: #E3F2FD; color: #1565C0; }
.status-badge.awaiting_player .status-dot { background: #1565C0; animation: pulse 1s infinite; }
.status-badge.processing_player .status-dot { background: #FF9800; animation: pulse 0.5s infinite; }
.status-badge.completed { background: #E8F5E9; color: #2E7D32; }
.status-badge.completed .status-dot { background: #4CAF50; }
.status-badge.failed { background: #FFEBEE; color: #C62828; }
.status-badge.failed .status-dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.4; } }

.status-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.save-btn {
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 4px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #1565C0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.save-btn:hover:not(:disabled) { background: #E3F2FD; border-color: #1565C0; }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.save-btn.save-success { background: #E8F5E9; color: #2E7D32; border-color: #4CAF50; }

.stop-btn {
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 4px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #F44336;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.stop-btn:hover { background: #FFF5F5; border-color: #F44336; }

.load-save-wrapper {
  position: relative;
}
.load-btn {
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 4px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #5C6BC0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.load-btn:hover { background: #EDE7F6; border-color: #5C6BC0; }
.save-list-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 280px;
  background: #FFF;
  border: 1px solid #E0E0E0;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  z-index: 200;
  max-height: 320px;
  overflow-y: auto;
}
.save-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #424242;
  border-bottom: 1px solid #F0F0F0;
}
.save-list-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  color: #9E9E9E;
  line-height: 1;
  padding: 0 2px;
}
.save-list-close:hover { color: #424242; }
.save-list-loading, .save-list-empty {
  padding: 16px 12px;
  font-size: 12px;
  color: #9E9E9E;
  text-align: center;
}
.save-list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #F5F5F5;
  gap: 8px;
}
.save-list-item:last-child { border-bottom: none; }
.save-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.save-item-desc {
  font-size: 12px;
  color: #212121;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.save-item-time {
  font-size: 11px;
  color: #9E9E9E;
}
.save-item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.save-item-load {
  border: 1px solid #1565C0;
  background: #E3F2FD;
  color: #1565C0;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 3px;
  cursor: pointer;
}
.save-item-load:hover:not(:disabled) { background: #BBDEFB; }
.save-item-load:disabled { opacity: 0.5; cursor: not-allowed; }
.save-item-del {
  border: 1px solid #E0E0E0;
  background: #FFF;
  color: #9E9E9E;
  padding: 2px 6px;
  font-size: 11px;
  border-radius: 3px;
  cursor: pointer;
}
.save-item-del:hover { background: #FFF5F5; color: #F44336; border-color: #F44336; }

/* Content Area */
.content-area {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* Narrative Panel */
.narrative-panel {
  flex: 6;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #E8E5E0;
}

.narrative-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
}

.narrative-segment {
  margin-bottom: 24px;
  animation: fadeIn 0.6s ease;
}

.segment-time-header {
  font-family: 'JetBrains Mono', 'Space Grotesk', monospace;
  font-size: 11px;
  font-weight: 600;
  color: #AAA;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #F0EFED;
}

.narrative-segment p {
  font-size: 16px;
  line-height: 1.9;
  color: #2C2C2C;
  margin: 0 0 12px;
  text-indent: 2em;
}


.player-choice-segment {
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: #1565C0;
  margin: 4px 0 20px;
  padding: 6px 14px;
  border-left: 3px solid #1565C0;
  background: #EFF6FF;
  border-radius: 0 4px 4px 0;
  animation: fadeIn 0.4s ease;
}

.narrative-segment.new-segment {
  animation: fadeInUp 0.8s ease;
}


/* NPC Events Block */
.npc-events-block {
  margin-bottom: 24px;
  border: 1px solid #E8E5E0;
  border-radius: 6px;
  background: #FAFAF9;
  overflow: hidden;
  animation: fadeIn 0.6s ease;
}

.npc-events-block.new-segment {
  animation: fadeInUp 0.8s ease;
}

.npc-events-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  user-select: none;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 13px;
  color: #888;
  transition: background 0.15s;
}

.npc-events-header:hover {
  background: #F0EFED;
}

.npc-events-icon {
  font-size: 11px;
  color: #AAA;
  width: 12px;
}

.npc-events-title {
  font-weight: 600;
  color: #777;
}

.npc-events-count {
  margin-left: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #AAA;
}

.npc-events-body {
  padding: 0 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.npc-event-item {
  display: flex;
  gap: 8px;
  padding: 6px 10px;
  background: #FFF;
  border-radius: 4px;
  border-left: 2px solid #E0E0E0;
  font-size: 13px;
  line-height: 1.5;
}

.npc-event-item.high-importance {
  border-left-color: #FF5722;
  background: #FFF8F5;
}

.npc-event-agent {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  color: #555;
  white-space: nowrap;
  flex-shrink: 0;
}

.npc-event-desc {
  color: #666;
}

/* Expand transition */
.expand-enter-active { transition: all 0.3s ease; overflow: hidden; }
.expand-leave-active { transition: all 0.2s ease; overflow: hidden; }
.expand-enter-from { opacity: 0; max-height: 0; }
.expand-enter-to { opacity: 1; max-height: 500px; }
.expand-leave-from { opacity: 1; max-height: 500px; }
.expand-leave-to { opacity: 0; max-height: 0; }

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Collapsible Profile Panel */
.profiles-section {
  max-height: 45%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.profiles-section.collapsed {
  max-height: none;
  flex: none;
}
.collapsible-header {
  cursor: pointer;
  user-select: none;
}
.collapsible-header:hover {
  color: #666;
}
.collapse-icon {
  font-size: 11px;
  margin-right: 2px;
}
.profiles-panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.profiles-panel-search {
  padding: 0 0 8px;
}
.profiles-panel-search-input {
  width: 100%;
  height: 28px;
  padding: 0 8px;
  border: 1px solid #E0E0E0;
  border-radius: 4px;
  font-size: 12px;
  outline: none;
  background: #FAFAFA;
  box-sizing: border-box;
}
.profiles-panel-search-input:focus {
  border-color: #999;
  background: #FFF;
}
.profiles-panel-scroll {
  flex: 1;
  overflow-y: auto;
}
.profile-panel-item {
  border-bottom: 1px solid #F0F0F0;
}
.profile-panel-item.is-player {
  background: #FAFBFF;
}
.profile-panel-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  cursor: pointer;
  font-size: 13px;
}
.profile-panel-row:hover {
  background: #F8F8F8;
}
.profile-panel-name {
  font-weight: 600;
  color: #333;
  display: flex;
  align-items: center;
  gap: 6px;
}
.profile-panel-player-tag {
  font-size: 10px;
  font-weight: 500;
  color: #7C3AED;
  background: #F3EEFF;
  padding: 1px 5px;
  border-radius: 3px;
}
.profile-panel-loc {
  font-size: 11px;
  color: #999;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-panel-detail {
  padding: 4px 0 10px 12px;
  font-size: 12px;
  color: #555;
}
.profile-detail-line {
  margin-bottom: 4px;
  line-height: 1.5;
}
.detail-label {
  display: inline-block;
  width: 36px;
  color: #999;
  font-size: 11px;
  flex-shrink: 0;
}
.profile-panel-edit-btn {
  margin-top: 6px;
  padding: 3px 12px;
  font-size: 11px;
  border: 1px solid #DDD;
  border-radius: 3px;
  background: #FFF;
  color: #666;
  cursor: pointer;
}
.profile-panel-edit-btn:hover {
  border-color: #999;
  color: #333;
}
.profiles-panel-empty {
  padding: 16px 0;
  text-align: center;
  color: #CCC;
  font-size: 12px;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Typing Indicator */
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  font-size: 13px;
  color: #999;
  font-family: 'Space Grotesk', sans-serif;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #CCC;
  animation: typingBounce 1.2s infinite;
}
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

/* Side Panel */
.side-panel {
  flex: 4;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #FFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.side-section {
  padding: 16px;
  border-bottom: 1px solid #E8E5E0;
}

.side-section h3 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #999;
  margin: 0 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  background: #F0F0F0;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 11px;
  color: #666;
}

/* Events */
.events-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.events-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 16px;
}

.event-item {
  padding: 8px 10px;
  margin-bottom: 6px;
  background: #F9F9F9;
  border-radius: 6px;
  border-left: 3px solid #E0E0E0;
  transition: all 0.2s;
}

.event-item.high-importance {
  border-left-color: #FF5722;
  background: #FFF8F5;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.event-agent {
  font-size: 12px;
  font-weight: 700;
  color: #333;
}

.event-turn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
}

.event-body {
  font-size: 12px;
  line-height: 1.5;
  color: #666;
}

.empty-events {
  text-align: center;
  padding: 24px;
  font-size: 13px;
  color: #CCC;
}

/* Choice Panel */
.choice-panel {
  border-top: 2px solid #1565C0;
  background: #FFF;
  padding: 20px 24px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.choice-header {
  font-size: 14px;
  font-weight: 700;
  color: #1565C0;
  margin-bottom: 14px;
}

.choice-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.choice-btn {
  border: 2px solid #E0E0E0;
  background: #FFF;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.choice-btn:hover { border-color: #999; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.choice-btn.selected { border-color: #1565C0; background: #E3F2FD; }

.choice-btn.risk-safe { border-left: 4px solid #4CAF50; }
.choice-btn.risk-moderate { border-left: 4px solid #2196F3; }
.choice-btn.risk-exploratory { border-left: 4px solid #FF9800; }
.choice-btn.risk-risky { border-left: 4px solid #F44336; }

.choice-label {
  font-size: 14px;
  font-weight: 700;
  color: #333;
}

.choice-desc {
  font-size: 12px;
  line-height: 1.4;
  color: #666;
}

.choice-risk {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #999;
}

/* Free Text */
.free-text-area {
  display: flex;
  gap: 10px;
}

.free-text-input {
  flex: 1;
  border: 2px solid #E0E0E0;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.2s;
}
.free-text-input:focus { border-color: #1565C0; }

.submit-btn {
  border: none;
  background: #1565C0;
  color: #FFF;
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}
.submit-btn:hover:not(:disabled) { background: #0D47A1; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Slide Transition */
.slide-up-enter-active { transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1); }
.slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from { transform: translateY(100%); opacity: 0; }
.slide-up-leave-to { transform: translateY(100%); opacity: 0; }

/* Fade Transition */
.fade-enter-active { transition: opacity 0.2s ease; }
.fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* Edit Characters Button */
.edit-characters-btn {
  margin-left: auto;
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.edit-characters-btn:hover { background: #F5F5F5; color: #333; border-color: #CCC; }

/* Choice Header - make flex */
.choice-header {
  display: flex;
  align-items: center;
}

/* Character Editor Overlay */
.char-editor-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
}

.char-editor-panel {
  width: 480px;
  max-height: 80vh;
  background: #FFF;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

.char-editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #EAEAEA;
  flex-shrink: 0;
}

.char-editor-title {
  font-size: 15px;
  font-weight: 700;
  color: #333;
}

.char-editor-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: #999;
  padding: 0;
  line-height: 1;
}
.char-editor-close:hover { color: #333; }

/* Character List */
.char-list {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.char-list-scroll {
  overflow-y: auto;
  max-height: 50vh;
  padding: 8px 0;
}

.char-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid #F5F5F5;
  transition: background 0.1s;
}
.char-item:hover { background: #FAFAFA; }
.char-item.is-player { background: #F0F7FF; }

.char-item-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.char-item-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.char-item-type {
  font-size: 11px;
  color: #FFF;
  background: #7B2D8E;
  padding: 1px 6px;
  border-radius: 6px;
}

.char-item-player-badge {
  font-size: 10px;
  font-weight: 700;
  color: #1565C0;
  background: #E3F2FD;
  padding: 1px 6px;
  border-radius: 6px;
}

.char-item-location-badge {
  font-size: 10px;
  font-weight: 600;
  color: #2E7D32;
  background: #E8F5E9;
  padding: 1px 6px;
  border-radius: 6px;
}

.char-item-edit-btn {
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.char-item-edit-btn:hover { background: #F0F0F0; color: #333; }

.char-add-btn {
  margin: 12px 20px;
  border: 2px dashed #E0E0E0;
  background: none;
  padding: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #999;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.char-add-btn:hover { border-color: #BBB; color: #666; background: #FAFAFA; }

/* Character Edit Form */
.char-edit-form {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.char-form-scroll {
  overflow-y: auto;
  max-height: 55vh;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.form-group input,
.form-group select,
.form-group textarea {
  border: 1px solid #E0E0E0;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
  background: #FFF;
}
.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus { border-color: #1565C0; }

.form-group textarea { resize: vertical; min-height: 60px; }

.form-row {
  display: flex;
  gap: 12px;
}

.form-group.half { flex: 1; }

.char-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid #EAEAEA;
  flex-shrink: 0;
}

.char-form-cancel {
  border: 1px solid #E0E0E0;
  background: #FFF;
  padding: 8px 20px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  border-radius: 6px;
  cursor: pointer;
}
.char-form-cancel:hover { background: #F5F5F5; }

.char-form-save {
  border: none;
  background: #1565C0;
  color: #FFF;
  padding: 8px 24px;
  font-size: 13px;
  font-weight: 700;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.char-form-save:hover:not(:disabled) { background: #0D47A1; }
.char-form-save:disabled { opacity: 0.5; cursor: not-allowed; }

/* Relationship editor */
.char-rel-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.char-rel-name {
  width: 100px;
  padding: 4px 8px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 4px;
  color: #E0E0E0;
  font-size: 13px;
}
.char-rel-desc {
  flex: 1;
  padding: 4px 8px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 4px;
  color: #E0E0E0;
  font-size: 13px;
}
.char-rel-remove {
  background: none;
  border: none;
  color: #F44336;
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.char-rel-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  background: #1B5E20;
  color: #A5D6A7;
  white-space: nowrap;
}
.char-rel-badge.llm {
  background: #4A148C;
  color: #CE93D8;
}
.char-rel-add {
  background: none;
  border: 1px dashed rgba(255,255,255,0.2);
  border-radius: 4px;
  color: #90CAF9;
  font-size: 12px;
  padding: 4px 10px;
  cursor: pointer;
  margin-top: 4px;
}
.char-rel-add:hover { border-color: #90CAF9; }
</style>
