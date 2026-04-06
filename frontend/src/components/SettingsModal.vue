<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="settings-overlay" @click.self="$emit('close')">
        <div class="settings-modal">
          <!-- Header -->
          <div class="settings-header">
            <h2>设置</h2>
            <div class="preset-bar">
              <select class="preset-select" v-model="selectedPresetId" @change="onPresetSelect">
                <option value="">-- 选择 Preset --</option>
                <option v-for="p in presets" :key="p.id" :value="p.id">
                  {{ p.name }}{{ p.is_default ? ' (默认)' : '' }}
                </option>
              </select>
              <button class="preset-btn preset-btn--apply" @click="doApplyPreset" :disabled="!selectedPresetId || presetBusy" title="应用选中的 Preset">应用</button>
              <button class="preset-btn preset-btn--save" @click="doSavePreset" :disabled="presetBusy" title="将当前设置保存为新 Preset">保存为...</button>
              <button class="preset-btn preset-btn--overwrite" @click="doOverwritePreset" :disabled="!selectedPresetId || isDefaultPreset || presetBusy" title="用当前设置覆盖选中的 Preset">覆盖</button>
              <button class="preset-btn preset-btn--delete" @click="doDeletePreset" :disabled="!selectedPresetId || isDefaultPreset || presetBusy" title="删除选中的 Preset">删除</button>
              <span class="preset-divider">|</span>
              <button class="preset-btn preset-btn--export" @click="doExportPreset" :disabled="!selectedPresetId || presetBusy" title="导出 Preset 为 JSON 文件">导出</button>
              <label class="preset-btn preset-btn--import" :class="{ disabled: presetBusy }" title="从 JSON 文件导入 Preset">
                导入
                <input type="file" accept=".json" style="display:none" @change="doImportPreset" :disabled="presetBusy" />
              </label>
            </div>
            <button class="close-btn" @click="$emit('close')">×</button>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="settings-loading">加载中...</div>

          <!-- Content -->
          <div v-else class="settings-body">
            <!-- Tab bar -->
            <div class="tab-bar">
              <button
                :class="['tab-btn', { active: activeTab === 'creative' }]"
                @click="activeTab = 'creative'"
              >
                创意控制 ({{ creativePrompts.length }})
              </button>
              <button
                :class="['tab-btn', { active: activeTab === 'advanced' }]"
                @click="activeTab = 'advanced'"
              >
                高级设置 ({{ advancedPrompts.length }})
              </button>
              <button
                :class="['tab-btn', { active: activeTab === 'narrative-engine' }]"
                @click="activeTab = 'narrative-engine'"
              >
                叙事引擎 ({{ neSettings.length }})
              </button>
              <button
                :class="['tab-btn', { active: activeTab === 'variables' }]"
                @click="activeTab = 'variables'"
              >
                变量参考
              </button>
              <button
                :class="['tab-btn', { active: activeTab === 'env-config' }]"
                @click="activeTab = 'env-config'"
              >
                全局配置
              </button>
            </div>

            <!-- Advanced warning -->
            <div v-if="activeTab === 'advanced'" class="advanced-warning">
              ⚠ 高级设置中的 Prompt 涉及数据解析、工具调用等复杂逻辑，修改可能导致功能异常。请谨慎操作。
            </div>

            <!-- Prompt list (creative / advanced tabs) -->
            <div v-if="activeTab !== 'narrative-engine' && activeTab !== 'env-config' && activeTab !== 'variables'" class="prompt-list">
              <div
                v-for="prompt in currentPrompts"
                :key="prompt.key"
                class="prompt-card"
              >
                <div class="prompt-header" @click="toggleExpand(prompt.key)">
                  <div class="prompt-info">
                    <span class="prompt-label">{{ prompt.label }}</span>
                    <span v-if="prompt.is_modified" class="modified-badge">已修改</span>
                  </div>
                  <span class="expand-icon">{{ expandedKeys.has(prompt.key) ? '▾' : '▸' }}</span>
                </div>

                <p class="prompt-desc">{{ prompt.description }}</p>

                <div v-if="expandedKeys.has(prompt.key)" class="prompt-editor">
                  <div class="editor-field">
                    <label>System Message</label>
                    <textarea
                      v-model="editBuffer[prompt.key].system"
                      rows="4"
                      spellcheck="false"
                    ></textarea>
                  </div>
                  <div class="editor-field">
                    <label>User Template</label>
                    <textarea
                      v-model="editBuffer[prompt.key].template"
                      rows="8"
                      spellcheck="false"
                    ></textarea>
                  </div>
                  <div class="llm-params-row">
                    <div class="llm-param-field">
                      <label>Temperature</label>
                      <input
                        type="number"
                        class="llm-param-input"
                        v-model.number="editBuffer[prompt.key].temperature"
                        min="0" max="2" step="0.1"
                      />
                    </div>
                    <div class="llm-param-field">
                      <label>Max Tokens</label>
                      <input
                        type="number"
                        class="llm-param-input llm-param-input--wide"
                        v-model.number="editBuffer[prompt.key].max_tokens"
                        min="64" max="65536" step="256"
                      />
                    </div>
                  </div>
                  <div class="api-config-row">
                    <div class="api-config-field api-config-model">
                      <label>模型</label>
                      <div class="api-model-wrap">
                        <input type="text" class="api-config-input"
                          v-model="editBuffer[prompt.key].model"
                          placeholder="留空则用全局默认"
                          spellcheck="false" />
                        <button class="btn-fetch-models btn-fetch-models--sm"
                          @click="doFetchModels(prompt.key, editBuffer[prompt.key].base_url || envBuffer.LLM_BASE_URL, editBuffer[prompt.key].api_key || envBuffer.LLM_API_KEY)"
                          :disabled="picker?.key === prompt.key && picker?.loading"
                          title="拉取可用模型">
                          {{ picker?.key === prompt.key && picker?.loading ? '…' : '↓' }}
                        </button>
                      </div>
                      <template v-if="picker?.key === prompt.key">
                        <div v-if="picker.error" class="model-fetch-error">{{ picker.error }}</div>
                        <div v-else-if="picker.models.length" class="model-fetch-dropdown">
                          <select @change="pickPromptModel(prompt.key, $event.target.value)">
                            <option value="">— 选择模型 —</option>
                            <option v-for="m in picker.models" :key="m" :value="m">{{ m }}</option>
                          </select>
                          <button class="btn-model-close" @click="closePicker">×</button>
                        </div>
                      </template>
                    </div>
                    <div class="api-config-field api-config-url">
                      <label>Base URL</label>
                      <input type="text" class="api-config-input"
                        v-model="editBuffer[prompt.key].base_url"
                        placeholder="留空则用全局默认"
                        spellcheck="false" />
                    </div>
                    <div class="api-config-field api-config-key">
                      <label>API Key</label>
                      <input type="password" class="api-config-input"
                        v-model="editBuffer[prompt.key].api_key"
                        placeholder="留空则用全局默认"
                        spellcheck="false" />
                    </div>
                  </div>
                  <!-- 多轮对话编辑器（content_wrapper 等带 messages 字段的 prompt） -->
                  <div v-if="editBuffer[prompt.key].messages !== undefined" class="editor-field">
                    <label>发送内容包装 <span style="font-weight:normal;color:#888">（{user_content} 替换为实际文本。清空则不包装。角色选项根据当前 API 自动切换。）</span></label>
                    <div v-for="(msg, idx) in editBuffer[prompt.key].messages" :key="idx" class="msg-row" style="display:flex;gap:6px;margin-bottom:6px;align-items:start">
                      <select v-model="msg.role" style="width:130px;padding:4px;border:1px solid #555;border-radius:4px;background:#1e1e1e;color:#ddd;font-size:12px">
                        <template v-if="isGoogleApi">
                          <option value="user">user</option>
                          <option value="model">model</option>
                          <option value="system_instruction">system_instruction</option>
                        </template>
                        <template v-else>
                          <option value="user">user</option>
                          <option value="assistant">assistant</option>
                          <option value="system">system</option>
                          <option value="developer">developer</option>
                        </template>
                      </select>
                      <textarea v-model="msg.content" rows="2" spellcheck="false" style="flex:1;padding:6px;border:1px solid #555;border-radius:4px;background:#1e1e1e;color:#ddd;font-family:monospace;font-size:12px;resize:vertical"></textarea>
                      <button @click="editBuffer[prompt.key].messages.splice(idx, 1)" style="padding:4px 8px;background:#c0392b;color:#fff;border:none;border-radius:4px;cursor:pointer" title="删除">✕</button>
                    </div>
                    <div style="display:flex;gap:8px;align-items:center">
                      <button @click="editBuffer[prompt.key].messages.push({role: isGoogleApi ? 'user' : 'user', content:''})" style="padding:4px 12px;background:#2d6a4f;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">+ 添加一轮</button>
                      <span style="color:#666;font-size:11px">当前 SDK: {{ isGoogleApi ? 'Google 原生' : 'OpenAI 兼容' }}</span>
                    </div>
                  </div>

                  <div class="editor-actions">
                    <button class="btn-save" @click="savePrompt(prompt.key)" :disabled="saving">
                      {{ saving ? '保存中...' : '保存' }}
                    </button>
                    <button class="btn-reset" @click="resetSingle(prompt.key)" :disabled="saving">
                      恢复默认
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Variables reference tab -->
            <div v-if="activeTab === 'variables'" class="var-ref">
              <div class="var-ref-info">
                以下是 Prompt 模板中可用的 <code>{变量名}</code> 占位符。编辑 Prompt 时可以引用这些变量，系统会在运行时自动替换为实际值。
              </div>
              <div v-for="group in varGroups" :key="group.key" class="var-group">
                <div class="var-group-title">{{ group.label }}</div>
                <table class="var-table">
                  <thead>
                    <tr>
                      <th class="var-th-name">变量名</th>
                      <th class="var-th-desc">说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="v in group.items" :key="v.name">
                      <td class="var-td-name"><code>{<span>{{ v.name }}</span>}</code></td>
                      <td class="var-td-desc">{{ v.description }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Narrative Engine settings tab -->
            <div v-if="activeTab === 'narrative-engine'" class="ne-settings">
              <div class="ne-info">
                调整叙事引擎的上下文窗口大小。修改后下一回合立即生效。
              </div>
              <div
                v-for="s in neSettings"
                :key="s.key"
                class="ne-card"
              >
                <div class="ne-card-header">
                  <div>
                    <span class="ne-label">{{ s.label }}</span>
                    <span v-if="s.is_modified" class="modified-badge">已修改</span>
                  </div>
                </div>
                <p class="ne-desc">{{ s.description }}（范围: {{ s.min }} - {{ s.max }}，默认: {{ s.default }}）</p>
                <div class="ne-controls">
                  <input
                    type="number"
                    class="ne-input"
                    v-model.number="neEditBuffer[s.key]"
                    :min="s.min"
                    :max="s.max"
                  />
                  <button class="btn-save" @click="saveNeSetting(s.key)" :disabled="saving">
                    {{ saving ? '保存中...' : '保存' }}
                  </button>
                  <button class="btn-reset" @click="resetNeSingle(s.key)" :disabled="saving">
                    恢复默认
                  </button>
                </div>
              </div>
            </div>

            <!-- Global env config tab -->
            <div v-if="activeTab === 'env-config'" class="env-config">
            <div class="env-section">
              <div class="env-section-title">LLM 基础配置</div>
              <div class="env-field">
                <label>LLM_API_KEY</label>
                <input type="password" class="env-input" v-model="envBuffer.LLM_API_KEY" spellcheck="false" autocomplete="off" />
              </div>
              <div class="env-field">
                <label>LLM_BASE_URL</label>
                <input type="text" class="env-input" v-model="envBuffer.LLM_BASE_URL" spellcheck="false" />
              </div>
              <div class="env-field">
                <label>LLM_MODEL_NAME</label>
                <input type="text" class="env-input" v-model="envBuffer.LLM_MODEL_NAME" spellcheck="false" />
                <button class="btn-fetch-models"
                  @click="doFetchModels('llm', envBuffer.LLM_BASE_URL, envBuffer.LLM_API_KEY)"
                  :disabled="picker?.key === 'llm' && picker?.loading">
                  {{ picker?.key === 'llm' && picker?.loading ? '…' : '拉取' }}
                </button>
              </div>
              <template v-if="picker?.key === 'llm'">
                <div v-if="picker.error" class="model-fetch-error">{{ picker.error }}</div>
                <div v-else-if="picker.models.length" class="model-fetch-dropdown">
                  <select @change="pickEnvModel('LLM_MODEL_NAME', $event.target.value)">
                    <option value="">— 选择模型 —</option>
                    <option v-for="m in picker.models" :key="m" :value="m">{{ m }}</option>
                  </select>
                  <button class="btn-model-close" @click="closePicker">×</button>
                </div>
              </template>
              <div class="env-field">
                <label>SDK 模式</label>
                <select class="env-input" v-model="envBuffer.LLM_USE_GOOGLE_SDK">
                  <option value="auto">自动检测（根据 URL 判断）</option>
                  <option value="true">强制使用 Google 原生 SDK</option>
                  <option value="false">强制使用 OpenAI 兼容模式</option>
                </select>
                <span class="env-field-hint">当前判定: {{ isGoogleApi ? 'Google 原生 SDK' : 'OpenAI 兼容' }}</span>
              </div>
              <div class="env-field env-field--checkbox">
                <label>
                  <input
                    type="checkbox"
                    :checked="envBuffer.LLM_GEMINI_SAFETY_BLOCK_NONE === 'true'"
                    @change="envBuffer.LLM_GEMINI_SAFETY_BLOCK_NONE = $event.target.checked ? 'true' : 'false'"
                  />
                  禁用 Gemini Safety Filter（BLOCK_NONE）
                </label>
                <span class="env-field-hint">仅对 Gemini API 有效，可避免请求被安全过滤器截断</span>
              </div>
            </div>
            <div class="env-section">
              <div class="env-section-title">Embedding 配置</div>
              <div class="env-field">
                <label>EMBEDDING_API_KEY</label>
                <input type="password" class="env-input" v-model="envBuffer.EMBEDDING_API_KEY" spellcheck="false" autocomplete="off" />
              </div>
              <div class="env-field">
                <label>EMBEDDING_BASE_URL</label>
                <input type="text" class="env-input" v-model="envBuffer.EMBEDDING_BASE_URL" spellcheck="false" />
              </div>
              <div class="env-field">
                <label>EMBEDDING_MODEL_NAME</label>
                <input type="text" class="env-input" v-model="envBuffer.EMBEDDING_MODEL_NAME" spellcheck="false" />
                <button class="btn-fetch-models"
                  @click="doFetchModels('emb', envBuffer.EMBEDDING_BASE_URL, envBuffer.EMBEDDING_API_KEY)"
                  :disabled="picker?.key === 'emb' && picker?.loading">
                  {{ picker?.key === 'emb' && picker?.loading ? '…' : '拉取' }}
                </button>
              </div>
              <template v-if="picker?.key === 'emb'">
                <div v-if="picker.error" class="model-fetch-error">{{ picker.error }}</div>
                <div v-else-if="picker.models.length" class="model-fetch-dropdown">
                  <select @change="pickEnvModel('EMBEDDING_MODEL_NAME', $event.target.value)">
                    <option value="">— 选择模型 —</option>
                    <option v-for="m in picker.models" :key="m" :value="m">{{ m }}</option>
                  </select>
                  <button class="btn-model-close" @click="closePicker">×</button>
                </div>
              </template>
            </div>
            <div class="env-section">
              <div class="env-section-title">其他服务</div>
              <div class="env-field">
                <label>ZEP_API_KEY</label>
                <input type="password" class="env-input" v-model="envBuffer.ZEP_API_KEY" spellcheck="false" autocomplete="off" />
              </div>
              <div class="env-field">
                <label>FALKORDB_HOST</label>
                <input type="text" class="env-input" v-model="envBuffer.FALKORDB_HOST" spellcheck="false" />
              </div>
              <div class="env-field">
                <label>FALKORDB_PORT</label>
                <input type="text" class="env-input env-input--short" v-model="envBuffer.FALKORDB_PORT" spellcheck="false" />
              </div>
              <div class="env-field">
                <label>FALKORDB_PASSWORD</label>
                <input type="password" class="env-input" v-model="envBuffer.FALKORDB_PASSWORD" spellcheck="false" autocomplete="off" />
              </div>
            </div>
            <div class="env-actions">
              <button class="btn-save" @click="saveEnvConfig" :disabled="saving">
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="settings-footer">
            <button
              v-if="activeTab === 'narrative-engine'"
              class="btn-reset-all"
              @click="resetNeAll"
              :disabled="saving"
            >
              全部恢复默认
            </button>
            <button
              v-else-if="activeTab !== 'env-config' && activeTab !== 'variables'"
              class="btn-reset-all"
              @click="resetAll"
              :disabled="saving"
            >
              全部恢复默认
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { getPrompts, updatePrompt, resetPrompt, getLlmProfiles, getEnvConfig, updateEnvConfig, fetchModels, getPromptVariables } from '../api/settings'
import { getNarrativeEngineSettings, updateNarrativeEngineSetting, resetNarrativeEngineSetting } from '../api/settings'
import { getPresets, createPreset, updatePreset, deletePreset, applyPreset, exportPreset, importPreset } from '../api/settings'

const props = defineProps({ visible: Boolean })
const emit = defineEmits(['close'])

const loading = ref(false)
const saving = ref(false)
const prompts = ref([])
const activeTab = ref('creative')
const expandedKeys = ref(new Set())
const editBuffer = ref({})
const llmProfiles = ref([])

// Narrative engine settings
const neSettings = ref([])
const neEditBuffer = ref({})

// Prompt variables reference
const promptVariables = ref({})
const varGroups = computed(() => {
  const labels = { narrative: '叙事模式（Narrative）', oasis: '社交模拟（OASIS）', common: '通用（Common）' }
  const order = ['narrative', 'oasis', 'common']
  return order
    .filter(k => promptVariables.value[k]?.length)
    .map(k => ({ key: k, label: labels[k], items: promptVariables.value[k] }))
})

// 模型拉取：同一时间只有一个 picker 打开
const picker = ref(null) // { key, loading, models, error } | null

async function doFetchModels(key, baseUrl, apiKey) {
  picker.value = { key, loading: true, models: [], error: '' }
  try {
    const res = await fetchModels({ base_url: baseUrl, api_key: apiKey })
    picker.value = { key, loading: false, models: res.data || [], error: '' }
  } catch (e) {
    picker.value = { key, loading: false, models: [], error: e.response?.data?.error || e.message }
  }
}

function pickEnvModel(field, modelId) {
  if (modelId) envBuffer.value[field] = modelId
  picker.value = null
}

function pickPromptModel(promptKey, modelId) {
  if (modelId && editBuffer.value[promptKey]) editBuffer.value[promptKey].model = modelId
  picker.value = null
}

function closePicker() {
  picker.value = null
}

// Global env config
const envBuffer = ref({
  LLM_API_KEY: '', LLM_BASE_URL: '', LLM_MODEL_NAME: '',
  LLM_GEMINI_SAFETY_BLOCK_NONE: 'false',
  LLM_USE_GOOGLE_SDK: 'auto',
  EMBEDDING_API_KEY: '', EMBEDDING_BASE_URL: '', EMBEDDING_MODEL_NAME: '',
  ZEP_API_KEY: '',
  FALKORDB_HOST: '', FALKORDB_PORT: '', FALKORDB_PASSWORD: '',
})

// Preset 管理
const presets = ref([])
const selectedPresetId = ref('')
const presetBusy = ref(false)
const isDefaultPreset = computed(() => {
  const p = presets.value.find(x => x.id === selectedPresetId.value)
  return p?.is_default === true
})

async function fetchPresets() {
  try {
    const res = await getPresets()
    presets.value = res.data || []
  } catch (e) {
    console.error('Failed to load presets', e)
  }
}

function onPresetSelect() {
  // 仅选择，不自动应用
}

async function doApplyPreset() {
  if (!selectedPresetId.value) return
  const p = presets.value.find(x => x.id === selectedPresetId.value)
  if (!confirm(`确定应用 Preset「${p?.name || selectedPresetId.value}」？当前未保存的设置修改将被覆盖。`)) return
  presetBusy.value = true
  try {
    await applyPreset(selectedPresetId.value)
    await fetchAll()
  } catch (e) {
    alert('应用失败: ' + (e.response?.data?.error || e.message))
  } finally {
    presetBusy.value = false
  }
}

async function doSavePreset() {
  const name = prompt('请输入 Preset 名称:')
  if (!name?.trim()) return
  presetBusy.value = true
  try {
    const res = await createPreset({ name: name.trim() })
    await fetchPresets()
    if (res.data?.id) selectedPresetId.value = res.data.id
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.error || e.message))
  } finally {
    presetBusy.value = false
  }
}

async function doOverwritePreset() {
  if (!selectedPresetId.value || isDefaultPreset.value) return
  const p = presets.value.find(x => x.id === selectedPresetId.value)
  if (!confirm(`确定用当前设置覆盖 Preset「${p?.name}」？`)) return
  presetBusy.value = true
  try {
    await updatePreset(selectedPresetId.value, {})
    await fetchPresets()
  } catch (e) {
    alert('覆盖失败: ' + (e.response?.data?.error || e.message))
  } finally {
    presetBusy.value = false
  }
}

async function doDeletePreset() {
  if (!selectedPresetId.value || isDefaultPreset.value) return
  const p = presets.value.find(x => x.id === selectedPresetId.value)
  if (!confirm(`确定删除 Preset「${p?.name}」？此操作不可撤销。`)) return
  presetBusy.value = true
  try {
    await deletePreset(selectedPresetId.value)
    selectedPresetId.value = ''
    await fetchPresets()
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.error || e.message))
  } finally {
    presetBusy.value = false
  }
}

async function doExportPreset() {
  if (!selectedPresetId.value) return
  presetBusy.value = true
  try {
    const res = await exportPreset(selectedPresetId.value)
    const json = JSON.stringify(res.data, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `preset-${res.data?.name || selectedPresetId.value}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('导出失败: ' + (e.response?.data?.error || e.message))
  } finally {
    presetBusy.value = false
  }
}

async function doImportPreset(event) {
  const file = event.target.files?.[0]
  if (!file) return
  presetBusy.value = true
  try {
    const text = await file.text()
    const data = JSON.parse(text)
    const res = await importPreset(data)
    await fetchPresets()
    if (res.data?.id) selectedPresetId.value = res.data.id
  } catch (e) {
    alert('导入失败: ' + (e.response?.data?.error || e.message))
  } finally {
    presetBusy.value = false
    // 重置 file input，允许再次选择同一文件
    event.target.value = ''
  }
}

const isGoogleApi = computed(() => {
  const mode = (envBuffer.value.LLM_USE_GOOGLE_SDK || 'auto').toLowerCase()
  if (mode === 'true') return true
  if (mode === 'false') return false
  return (envBuffer.value.LLM_BASE_URL || '').includes('generativelanguage.googleapis.com')
})
const creativePrompts = computed(() => prompts.value.filter(p => p.category === 'creative'))
const advancedPrompts = computed(() => prompts.value.filter(p => p.category === 'advanced'))
const currentPrompts = computed(() =>
  activeTab.value === 'creative' ? creativePrompts.value : advancedPrompts.value
)

watch(() => props.visible, async (val) => {
  if (val) await fetchAll()
})

async function fetchAll() {
  loading.value = true
  try {
    await Promise.all([fetchPrompts(), fetchNeSettings(), fetchLlmProfiles(), fetchEnvConfig(), fetchVarRef(), fetchPresets()])
  } finally {
    loading.value = false
  }
}

async function fetchPrompts() {
  try {
    const res = await getPrompts()
    prompts.value = res.data || []
    const buf = {}
    for (const p of prompts.value) {
      const entry = { system: p.system, template: p.template, temperature: p.temperature, max_tokens: p.max_tokens, api_key: p.api_key || '', base_url: p.base_url || '', model: p.model || '' }
      if (p.messages !== undefined) entry.messages = JSON.parse(JSON.stringify(p.messages))
      buf[p.key] = entry
    }
    editBuffer.value = buf
  } catch (e) {
    console.error('Failed to load prompts', e)
  }
}

async function fetchLlmProfiles() {
  try {
    const res = await getLlmProfiles()
    llmProfiles.value = res.data || []
  } catch (e) {
    console.error('Failed to load LLM profiles', e)
  }
}

async function fetchEnvConfig() {
  try {
    const res = await getEnvConfig()
    if (res.data) Object.assign(envBuffer.value, res.data)
  } catch (e) {
    console.error('Failed to load env config', e)
  }
}

async function fetchVarRef() {
  try {
    const res = await getPromptVariables()
    promptVariables.value = res.data || {}
  } catch (e) {
    console.error('Failed to load prompt variables', e)
  }
}

async function saveEnvConfig() {
  saving.value = true
  try {
    await updateEnvConfig({ ...envBuffer.value })
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

async function fetchNeSettings() {
  try {
    const res = await getNarrativeEngineSettings()
    neSettings.value = res.data || []
    const buf = {}
    for (const s of neSettings.value) {
      buf[s.key] = s.value
    }
    neEditBuffer.value = buf
  } catch (e) {
    console.error('Failed to load narrative engine settings', e)
  }
}

function toggleExpand(key) {
  const s = new Set(expandedKeys.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedKeys.value = s
}

async function savePrompt(key) {
  saving.value = true
  try {
    const buf = editBuffer.value[key]
    const payload = { system: buf.system, template: buf.template, temperature: buf.temperature, max_tokens: buf.max_tokens, api_key: buf.api_key, base_url: buf.base_url, model: buf.model }
    if (buf.messages !== undefined) payload.messages = buf.messages
    await updatePrompt(key, payload)
    const p = prompts.value.find(x => x.key === key)
    if (p) p.is_modified = true
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

async function resetSingle(key) {
  if (!confirm(`确定恢复「${prompts.value.find(p => p.key === key)?.label}」为默认值？`)) return
  saving.value = true
  try {
    await resetPrompt(key)
    await fetchPrompts()
  } catch (e) {
    alert('重置失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  if (!confirm('确定将所有 Prompt 恢复为默认值？此操作不可撤销。')) return
  saving.value = true
  try {
    await resetPrompt(null)
    await fetchPrompts()
  } catch (e) {
    alert('重置失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

// Narrative engine setting actions
async function saveNeSetting(key) {
  saving.value = true
  try {
    await updateNarrativeEngineSetting(key, neEditBuffer.value[key])
    const s = neSettings.value.find(x => x.key === key)
    if (s) {
      s.value = neEditBuffer.value[key]
      s.is_modified = true
    }
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

async function resetNeSingle(key) {
  if (!confirm(`确定恢复「${neSettings.value.find(s => s.key === key)?.label}」为默认值？`)) return
  saving.value = true
  try {
    await resetNarrativeEngineSetting(key)
    await fetchNeSettings()
  } catch (e) {
    alert('重置失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

async function resetNeAll() {
  if (!confirm('确定将所有叙事引擎配置恢复为默认值？')) return
  saving.value = true
  try {
    await resetNarrativeEngineSetting(null)
    await fetchNeSettings()
  } catch (e) {
    alert('重置失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
/* Overlay */
.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

/* Modal */
.settings-modal {
  background: #fff;
  width: 780px;
  max-width: 94vw;
  max-height: 85vh;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

/* Header */
.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid #e5e5e5;
  flex-wrap: wrap;
  gap: 8px;
}
.settings-header h2 {
  margin: 0;
  font-size: 18px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-weight: 600;
  flex-shrink: 0;
}
.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
  line-height: 1;
  padding: 0 4px;
}
.close-btn:hover {
  color: #000;
}

/* Preset bar */
.preset-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  margin: 0 16px;
  flex-wrap: wrap;
}
.preset-select {
  padding: 4px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  background: #fff;
  min-width: 140px;
  max-width: 200px;
}
.preset-select:focus {
  outline: none;
  border-color: #FF4500;
}
.preset-btn {
  padding: 3px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  cursor: pointer;
  background: #fff;
  color: #555;
  white-space: nowrap;
  transition: all 0.15s;
}
.preset-btn:hover:not(:disabled):not(.disabled) {
  border-color: #999;
  color: #333;
}
.preset-btn:disabled, .preset-btn.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.preset-btn--apply {
  background: #FF4500;
  color: #fff;
  border-color: #FF4500;
}
.preset-btn--apply:hover:not(:disabled) {
  background: #e03e00;
  border-color: #e03e00;
}
.preset-btn--save {
  background: #2d6a4f;
  color: #fff;
  border-color: #2d6a4f;
}
.preset-btn--save:hover:not(:disabled) {
  background: #245a42;
  border-color: #245a42;
}
.preset-btn--delete {
  color: #c0392b;
  border-color: #e0b0a8;
}
.preset-btn--delete:hover:not(:disabled) {
  border-color: #c0392b;
  background: #fdf0ee;
}
.preset-btn--import {
  display: inline-flex;
  align-items: center;
}
.preset-divider {
  color: #ddd;
  font-size: 14px;
  margin: 0 2px;
  user-select: none;
}

/* Loading */
.settings-loading {
  padding: 48px;
  text-align: center;
  color: #999;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}

/* Body */
.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 16px;
}

/* Tabs */
.tab-bar {
  display: flex;
  gap: 0;
  margin: 16px 0 12px;
  border-bottom: 1px solid #e5e5e5;
}
.tab-btn {
  padding: 8px 16px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  color: #666;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.tab-btn:hover {
  color: #333;
}
.tab-btn.active {
  color: #FF4500;
  border-bottom-color: #FF4500;
  font-weight: 500;
}

/* Advanced warning */
.advanced-warning {
  background: #fff8f0;
  border: 1px solid #ffe0c0;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: #b35c00;
  margin-bottom: 12px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  line-height: 1.5;
}

/* Prompt card */
.prompt-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prompt-card {
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 12px 16px;
  transition: border-color 0.2s;
}
.prompt-card:hover {
  border-color: #ccc;
}

.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}
.prompt-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.prompt-label {
  font-weight: 500;
  font-size: 14px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}
.modified-badge {
  font-size: 11px;
  background: #FF4500;
  color: #fff;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}
.expand-icon {
  color: #999;
  font-size: 14px;
}
.prompt-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: #999;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}

/* Editor */
.prompt-editor {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.editor-field label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: #666;
  margin-bottom: 4px;
  font-family: 'JetBrains Mono', monospace;
}
.editor-field textarea {
  width: 100%;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
  line-height: 1.5;
  resize: vertical;
  background: #fafafa;
  box-sizing: border-box;
}
.editor-field textarea:focus {
  outline: none;
  border-color: #FF4500;
  background: #fff;
}

.llm-params-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 8px 10px;
  background: #f5f5f5;
  border-radius: 4px;
  border: 1px solid #e5e5e5;
}
.llm-param-field {
  display: flex;
  align-items: center;
  gap: 6px;
}
.llm-param-field label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.llm-param-input {
  width: 72px;
  padding: 4px 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
  text-align: center;
  background: #fff;
}
.llm-param-input--wide {
  width: 88px;
}
.llm-param-input:focus {
  outline: none;
  border-color: #FF4500;
}
.api-config-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  background: #f0f4ff;
  border-radius: 4px;
  border: 1px solid #d0d8f0;
}
.api-config-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.api-config-field label {
  font-size: 11px;
  font-weight: 500;
  color: #666;
  font-family: 'JetBrains Mono', monospace;
}
.api-config-model { flex: 1; min-width: 140px; }
.api-config-url   { flex: 2; min-width: 200px; }
.api-config-key   { flex: 2; min-width: 200px; }
.api-config-input {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #c8d0e8;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  background: #fff;
  box-sizing: border-box;
}
.api-config-input:focus {
  outline: none;
  border-color: #FF4500;
}
.llm-param-select {
  padding: 4px 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  background: #fff;
  max-width: 160px;
}
.llm-param-select:focus {
  outline: none;
  border-color: #FF4500;
}
.llm-param-hint {
  font-size: 11px;
  color: #aaa;
  font-family: 'JetBrains Mono', monospace;
  margin-left: auto;
}

.editor-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.btn-save,
.btn-reset,
.btn-reset-all {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  transition: all 0.2s;
}
.btn-save {
  background: #FF4500;
  color: #fff;
  border: none;
}
.btn-save:hover:not(:disabled) {
  background: #e03e00;
}
.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-reset {
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
}
.btn-reset:hover:not(:disabled) {
  border-color: #999;
  color: #333;
}

/* Footer */
.settings-footer {
  padding: 12px 24px;
  border-top: 1px solid #e5e5e5;
  display: flex;
  justify-content: flex-end;
}
.btn-reset-all {
  background: #fff;
  color: #999;
  border: 1px solid #ddd;
}
.btn-reset-all:hover:not(:disabled) {
  border-color: #FF4500;
  color: #FF4500;
}

/* Narrative engine settings */
.ne-info {
  background: #f0f7ff;
  border: 1px solid #c0d8f0;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: #1a5276;
  margin-bottom: 12px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  line-height: 1.5;
}
.ne-settings {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ne-card {
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 12px 16px;
  transition: border-color 0.2s;
}
.ne-card:hover {
  border-color: #ccc;
}
.ne-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ne-label {
  font-weight: 500;
  font-size: 14px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}
.ne-desc {
  margin: 4px 0 8px;
  font-size: 12px;
  color: #999;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}
.ne-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ne-input {
  width: 100px;
  padding: 5px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  font-family: 'JetBrains Mono', monospace;
  text-align: center;
  background: #fafafa;
}
.ne-input:focus {
  outline: none;
  border-color: #FF4500;
  background: #fff;
}

/* Global env config */
.env-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 4px;
}
.env-section {
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.env-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #444;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  margin-bottom: 2px;
}
.env-field {
  display: flex;
  align-items: center;
  gap: 10px;
}
.env-field--checkbox {
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.env-field--checkbox label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #333;
  font-weight: 500;
}
.env-field-hint {
  font-size: 12px;
  color: #888;
  margin-left: 22px;
  width: 100%;
}
.env-field label {
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: #666;
  width: 200px;
  flex-shrink: 0;
}
.env-input {
  flex: 1;
  padding: 5px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
  background: #fafafa;
  box-sizing: border-box;
}
.env-input--short {
  flex: 0 0 100px;
}
.env-input:focus {
  outline: none;
  border-color: #FF4500;
  background: #fff;
}
.env-actions {
  display: flex;
  justify-content: flex-end;
  padding-bottom: 4px;
}

/* Model fetch */
.btn-fetch-models {
  flex-shrink: 0;
  padding: 5px 10px;
  border: 1px solid #c8d0e8;
  border-radius: 4px;
  background: #f0f4ff;
  color: #446;
  font-size: 12px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.btn-fetch-models:hover:not(:disabled) {
  background: #e0e8ff;
}
.btn-fetch-models:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-fetch-models--sm {
  padding: 3px 7px;
  font-size: 13px;
}
.api-model-wrap {
  display: flex;
  gap: 4px;
  align-items: center;
}
.api-model-wrap .api-config-input {
  flex: 1;
  min-width: 0;
}
.model-fetch-dropdown {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}
.model-fetch-dropdown select {
  flex: 1;
  padding: 4px 6px;
  border: 1px solid #c8d0e8;
  border-radius: 4px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  background: #fff;
  max-width: 100%;
}
.model-fetch-dropdown select:focus {
  outline: none;
  border-color: #FF4500;
}
.btn-model-close {
  padding: 2px 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
  color: #999;
  font-size: 14px;
  cursor: pointer;
  line-height: 1;
}
.btn-model-close:hover {
  color: #333;
  border-color: #999;
}
.model-fetch-error {
  margin-top: 4px;
  font-size: 11px;
  color: #c00;
  font-family: 'JetBrains Mono', monospace;
}

/* Variables reference tab */
.var-ref-info {
  background: #f0f7ff;
  border: 1px solid #c8d8f0;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: #335;
  margin-bottom: 16px;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  line-height: 1.6;
}
.var-ref-info code {
  background: #e8eef8;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12px;
  color: #c7254e;
}
.var-group {
  margin-bottom: 20px;
}
.var-group-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 2px solid #FF4500;
  display: inline-block;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}
.var-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.var-table thead {
  background: #f8f9fa;
}
.var-th-name,
.var-th-desc {
  text-align: left;
  padding: 6px 10px;
  font-weight: 500;
  color: #666;
  border-bottom: 1px solid #e5e5e5;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
}
.var-th-name {
  width: 220px;
}
.var-td-name {
  padding: 5px 10px;
  border-bottom: 1px solid #f0f0f0;
  vertical-align: top;
}
.var-td-name code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12px;
  color: #c7254e;
  white-space: nowrap;
}
.var-td-desc {
  padding: 5px 10px;
  border-bottom: 1px solid #f0f0f0;
  color: #444;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  line-height: 1.5;
}
.var-table tbody tr:hover {
  background: #fafbfc;
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
