<template>
  <div class="home-container">

    <!-- ═══ NAVBAR ═══ -->
    <nav class="navbar">
      <div class="nav-brand"><span class="brand-accent">A</span>GARS</div>
      <div class="nav-links">
        <button class="settings-btn" @click="showSettings = true" title="设置">
          <svg class="gear-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/>
          </svg>
        </button>
      </div>
    </nav>

    <!-- ═══ HERO ═══ -->
    <section class="hero">

      <!-- Left: text -->
      <div class="hero-left">
        <div class="hero-meta-row">
          <span class="meta-tag">AI-GENERATED AI ROLEPLAY SIMULATOR</span>
          <span class="meta-version">/ v0.2-preview</span>
        </div>

        <h1 class="hero-title">
          输入任意文本<br>
          <span class="hero-title-accent">即刻召唤平行世界</span>
        </h1>

        <!-- Stats row — replaces prose paragraph -->
        <div class="hero-stats">
          <div class="hero-stat">
            <div class="stat-value">知识图谱</div>
            <div class="stat-label">自动构建世界观</div>
          </div>
          <div class="stat-divider"></div>
          <div class="hero-stat">
            <div class="stat-value">2 种</div>
            <div class="stat-label">推演模式</div>
          </div>
          <div class="stat-divider"></div>
          <div class="hero-stat">
            <div class="stat-value">API 直调</div>
            <div class="stat-label">成本接近 SillyTavern</div>
          </div>
        </div>

        <p class="hero-sub">
          上传任意文档，AGARS 自动提取现实种子、构建知识图谱，并生成完整的 AI 模拟世界。
          支持<strong>群体动力学仿真</strong>与<strong>互动叙事</strong>两种推演路径。
        </p>

        <div class="hero-actions">
          <button class="btn-primary" @click="scrollToConsole">开始模拟 <span>→</span></button>
          <button class="btn-ghost" @click="scrollToFeatures">了解功能 <span>↓</span></button>
        </div>

        <!-- Mode strip -->
        <div class="mode-strip">
          <div class="mode-item">
            <span class="mode-dot mode-dot--oasis"></span>
            <div>
              <div class="mode-name">OASIS 模式</div>
              <div class="mode-desc">群体动力学 · 涌现行为 · 舆情预测</div>
            </div>
          </div>
          <div class="mode-divider"></div>
          <div class="mode-item mode-item--accent">
            <span class="mode-dot mode-dot--narrative"></span>
            <div>
              <div class="mode-name">Narrative 模式 <span class="original-badge">AGARS 原创</span></div>
              <div class="mode-desc">互动叙事 · AI NPC · 玩家驱动剧情</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: image — pure white zone -->
      <div class="hero-right">
        <img :src="homepageImg" alt="AGARS Simulated Worlds" class="petri-img" />
        <div class="petri-caption">
          <span class="petri-caption-dot">◎</span>
          任意文本均可生成独立的平行世界实例
        </div>
      </div>

    </section>

    <!-- ═══ FEATURE CARDS ═══ -->
    <section class="features" id="features">
      <div class="features-header">
        <span class="section-eyebrow">CORE CAPABILITIES</span>
        <h2 class="features-title">功能概览</h2>
      </div>

      <div class="features-grid">

        <!-- Card 01: OASIS -->
        <div class="feature-card">
          <div class="feature-card-inner">
            <div class="feature-num">01</div>
            <div class="feature-icon-wrap">
              <svg viewBox="0 0 40 40" width="36" height="36" fill="none">
                <circle cx="10" cy="20" r="4" stroke="currentColor" stroke-width="1.5"/>
                <circle cx="30" cy="10" r="4" stroke="currentColor" stroke-width="1.5"/>
                <circle cx="30" cy="30" r="4" stroke="currentColor" stroke-width="1.5"/>
                <line x1="14" y1="18" x2="26" y2="12" stroke="currentColor" stroke-width="1.2"/>
                <line x1="14" y1="22" x2="26" y2="28" stroke="currentColor" stroke-width="1.2"/>
                <line x1="30" y1="14" x2="30" y2="26" stroke="currentColor" stroke-width="1.2"/>
              </svg>
            </div>
            <div class="feature-tag-line">GROUP DYNAMICS · FROM MIROFISH</div>
            <h3 class="feature-name">OASIS 群体模拟</h3>
            <p class="feature-desc">
              继承自 MiroFish，基于开源 OASIS 框架，模拟真实社会中信息传播、舆情涌现与群体行为。支持双平台并行推演与动态变量注入，适合预测复杂社会系统的演化轨迹。
            </p>
          </div>
        </div>

        <!-- Card 02: Narrative — accent (orange) -->
        <div class="feature-card feature-card--accent">
          <div class="feature-card-inner">
            <div class="feature-num">02</div>
            <div class="feature-icon-wrap">
              <svg viewBox="0 0 40 40" width="36" height="36" fill="none">
                <rect x="6" y="6" width="28" height="22" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
                <line x1="6" y1="13" x2="34" y2="13" stroke="currentColor" stroke-width="1"/>
                <circle cx="10" cy="9.5" r="1.2" fill="currentColor" opacity="0.6"/>
                <circle cx="13.5" cy="9.5" r="1.2" fill="currentColor" opacity="0.6"/>
                <line x1="11" y1="19" x2="29" y2="19" stroke="currentColor" stroke-width="1.3"/>
                <line x1="11" y1="23" x2="24" y2="23" stroke="currentColor" stroke-width="1.3"/>
                <path d="M11 32 L15 29 L19 32 L23 28 L27 32" stroke="currentColor" stroke-width="1.3" fill="none"/>
              </svg>
            </div>
            <div class="feature-tag-line">AGARS ORIGINAL · INTERACTIVE NARRATIVE</div>
            <h3 class="feature-name">Narrative 互动叙事</h3>
            <p class="feature-desc">
              AGARS 核心原创能力。以玩家身份进入 AI 自动构建的叙事宇宙，与 NPC 实时对话、做出选择、推动剧情。支持存档、读档与多分支探索，世界一致性由知识图谱保证。
            </p>
          </div>
        </div>

        <!-- Card 03: Deep Analysis -->
        <div class="feature-card">
          <div class="feature-card-inner">
            <div class="feature-num">03</div>
            <div class="feature-icon-wrap">
              <svg viewBox="0 0 40 40" width="36" height="36" fill="none">
                <circle cx="17" cy="17" r="9" stroke="currentColor" stroke-width="1.5"/>
                <line x1="23.5" y1="23.5" x2="33" y2="33" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                <line x1="12" y1="17" x2="22" y2="17" stroke="currentColor" stroke-width="1.2"/>
                <line x1="17" y1="12" x2="17" y2="22" stroke="currentColor" stroke-width="1.2"/>
              </svg>
            </div>
            <div class="feature-tag-line">DEEP ANALYSIS · FROM MIROFISH</div>
            <h3 class="feature-name">深度分析工具集</h3>
            <p class="feature-desc">
              继承自 MiroFish 的 ReportAgent，配备 4 种专业工具：InsightForge 因果溯源、PanoramaSearch 全景事件重建、QuickSearch 图谱语义查询，以及并行 Agent 访谈系统，从模拟结果中提取深度洞见。
            </p>
          </div>
        </div>

      </div>
    </section>

    <!-- ═══ NARRATIVE SPOTLIGHT ═══ -->
    <section class="narrative-spotlight">
      <div class="narrative-inner">

        <div class="narrative-left">
          <div class="narrative-eyebrow">AGARS ORIGINAL FEATURE</div>
          <h2 class="narrative-title">Narrative 模式</h2>
          <p class="narrative-sub">进入 AI 构建的叙事宇宙，成为故事的一部分</p>

          <ul class="narrative-features">
            <li>
              <span class="nf-icon">→</span>
              <span><strong>实时 NPC 对话</strong> — 每个角色拥有独立记忆、人格与目标，对话逻辑始终自洽</span>
            </li>
            <li>
              <span class="nf-icon">→</span>
              <span><strong>玩家驱动剧情</strong> — 你的每一个选择都会改变 AI 世界的走向与 NPC 的后续行为</span>
            </li>
            <li>
              <span class="nf-icon">→</span>
              <span><strong>存档 / 读档 / 多周目</strong> — 自由回溯时间线，探索不同选择的平行分支</span>
            </li>
            <li>
              <span class="nf-icon">→</span>
              <span><strong>知识图谱世界观</strong> — 从真实文档自动构建，世界的逻辑一致性由 GraphRAG 保证</span>
            </li>
          </ul>

          <div class="narrative-vs">
            <div class="vs-col">
              <div class="vs-label">OASIS 模式</div>
              <div class="vs-desc">基于开源项目改造<br>群体仿真 · 观察者视角</div>
            </div>
            <div class="vs-sep">VS</div>
            <div class="vs-col vs-col--accent">
              <div class="vs-label">Narrative 模式</div>
              <div class="vs-desc">AGARS 核心原创<br>互动叙事 · 玩家视角</div>
            </div>
          </div>
        </div>

        <!-- Chat mockup -->
        <div class="narrative-right">
          <div class="chat-mockup">
            <div class="chat-mockup-header">
              <span class="chat-dot"></span>
              <span class="chat-dot"></span>
              <span class="chat-dot chat-dot--active"></span>
              <span class="chat-scene">场景 · 第三章 古城废墟</span>
            </div>
            <div class="chat-messages">
              <div class="chat-msg chat-msg--narrative">
                <div class="chat-role">叙事</div>
                <div class="chat-bubble">暮色渐浓，古城废墟中残垣断壁投下长长的阴影。你站在坍塌的城门前，风中隐约传来金属碰撞的回声。向导林苍在你身侧停下脚步，而远处的暗哨中，守卫赵铁似乎已经注意到了你们。</div>
              </div>
              <div class="chat-msg chat-msg--player">
                <div class="chat-role">你的行动</div>
                <div class="chat-bubble">压低身形，示意林苍安静，沿着废墙向侧门迂回。</div>
              </div>
              <div class="chat-msg chat-msg--npc">
                <div class="chat-role">NPC · 向导 林苍</div>
                <div class="chat-bubble">林苍犹豫片刻，紧跟上来，低声道："侧门那边有陷阱，我上次来的时候差点中招。"</div>
              </div>
              <div class="chat-msg chat-msg--npc">
                <div class="chat-role">NPC · 守卫 赵铁</div>
                <div class="chat-bubble">赵铁从暗哨起身，手按刀柄，朝城门方向走了几步，警觉地扫视四周。 <span style="opacity:0.5">[移动到: 城门废墟]</span></div>
              </div>
            </div>
            <div class="chat-choices">
              <div class="choice-label">下一步行动</div>
              <div class="choice-btn choice-btn--active">继续迂回，让林苍带路避开陷阱</div>
              <div class="choice-btn">停下来，等赵铁走远再行动</div>
            </div>
          </div>
        </div>

      </div>
    </section>

    <!-- ═══ SIMULATION PIPELINE (branching) ═══ -->
    <section class="workflow-section">
      <div class="workflow-inner">
        <div class="workflow-eyebrow">SIMULATION PIPELINE</div>

        <div class="pipeline">

          <!-- Left: shared steps -->
          <div class="pl-shared">
            <div class="pl-step">
              <div class="pipe-num">01</div>
              <div class="pipe-name">图谱构建</div>
              <div class="pipe-desc">文档解析 · 实体抽取 · GraphRAG</div>
            </div>
            <div class="pl-vert-line"></div>
            <div class="pl-step">
              <div class="pipe-num">02</div>
              <div class="pipe-name">环境搭建</div>
              <div class="pipe-desc">人设生成 · 关系网络 · 参数注入</div>
            </div>
            <div class="pl-fork-hint">选择模式 →</div>
          </div>

          <!-- Right: two branch rows -->
          <div class="pl-branches">

            <div class="pl-branch pl-branch--oasis">
              <div class="branch-tag">
                <span class="branch-dot branch-dot--oasis"></span>OASIS 路径
              </div>
              <div class="branch-flow">
                <div class="pl-step pl-step--flow">
                  <div class="pipe-num">03</div>
                  <div class="pipe-name">模拟运行</div>
                  <div class="pipe-desc">双平台并行 · 多轮推演</div>
                </div>
                <span class="flow-arr">→</span>
                <div class="pl-step pl-step--flow">
                  <div class="pipe-num">04</div>
                  <div class="pipe-name">报告生成</div>
                  <div class="pipe-desc">ReportAgent · 4 种分析工具</div>
                </div>
                <span class="flow-arr">→</span>
                <div class="pl-step pl-step--flow">
                  <div class="pipe-num">05</div>
                  <div class="pipe-name">深度互动</div>
                  <div class="pipe-desc">Agent 对话 · 问卷调查</div>
                </div>
              </div>
            </div>

            <div class="pl-branch pl-branch--narrative">
              <div class="branch-tag branch-tag--narrative">
                <span class="branch-dot branch-dot--narrative"></span>Narrative 路径
                <span class="branch-original">AGARS 原创</span>
              </div>
              <div class="branch-flow">
                <div class="pl-step pl-step--flow pl-step--narr">
                  <div class="pipe-num">03</div>
                  <div class="pipe-name">选择角色</div>
                  <div class="pipe-desc">编辑人设 · 确认入场身份</div>
                </div>
                <span class="flow-arr flow-arr--narr">→</span>
                <div class="pl-step pl-step--flow pl-step--narr">
                  <div class="pipe-num">04</div>
                  <div class="pipe-name">叙事推演</div>
                  <div class="pipe-desc">实时 NPC · 玩家选择驱动</div>
                </div>
                <span class="flow-arr flow-arr--narr">→</span>
                <div class="pl-step pl-step--flow pl-step--narr">
                  <div class="pipe-num">05</div>
                  <div class="pipe-name">存档 / 读档</div>
                  <div class="pipe-desc">多分支探索 · 时间线回溯</div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </section>

    <!-- ═══ CONSOLE ═══ -->
    <section class="launch-section" id="console">
      <div class="launch-layout">

        <div class="launch-info">
          <div class="launch-status">
            <span class="status-dot">■</span> 系统就绪
          </div>
          <h2 class="launch-title">构建你的<br>平行世界</h2>
          <p class="launch-desc">
            上传任意非结构化文档（报告、小说、新闻、历史资料），用自然语言描述推演需求，引擎将自动完成其余所有工作。
          </p>
          <div class="launch-meta-cards">
            <div class="lm-card">
              <div class="lm-value">百万级</div>
              <div class="lm-label">Agent 规模上限</div>
            </div>
            <div class="lm-card">
              <div class="lm-value">2 种</div>
              <div class="lm-label">推演模式</div>
            </div>
            <div class="lm-card lm-card--full">
              <div class="lm-value lm-value--sm">API 直调</div>
              <div class="lm-label">运行成本接近 SillyTavern</div>
            </div>
          </div>
          <div class="launch-hints">
            <div class="hint-item"><span class="hint-icon">◇</span><span>支持 PDF、MD、TXT 格式</span></div>
            <div class="hint-item"><span class="hint-icon">◇</span><span>系统自动选择最优推演模式</span></div>
          </div>
        </div>

        <div class="launch-console">
          <div class="console-block">
            <div class="console-header">
              <span class="console-label">01 / 现实种子</span>
              <span class="console-meta">支持格式: PDF · MD · TXT</span>
            </div>
            <div
              class="upload-zone"
              :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
              @dragover.prevent="handleDragOver"
              @dragleave.prevent="handleDragLeave"
              @drop.prevent="handleDrop"
              @click="triggerFileInput"
            >
              <input
                ref="fileInput"
                type="file"
                multiple
                accept=".pdf,.md,.txt"
                @change="handleFileSelect"
                style="display: none"
                :disabled="loading"
              />
              <div v-if="files.length === 0" class="upload-placeholder">
                <div class="upload-arrow">↑</div>
                <div class="upload-title">拖拽文件上传</div>
                <div class="upload-hint">或点击浏览文件系统</div>
              </div>
              <div v-else class="file-list">
                <div v-for="(file, index) in files" :key="index" class="file-item">
                  <span class="file-icon">📄</span>
                  <span class="file-name">{{ file.name }}</span>
                  <button @click.stop="removeFile(index)" class="remove-btn">×</button>
                </div>
              </div>
            </div>
          </div>

          <div class="console-divider"><span>输入参数</span></div>

          <div class="console-block">
            <div class="console-header">
              <span class="console-label">>_ 02 / 模拟提示词</span>
            </div>
            <div class="input-wrapper">
              <textarea
                v-model="formData.simulationRequirement"
                class="code-input"
                placeholder="// 用自然语言输入模拟或预测需求（例：若发布撤销处分公告，会引发什么舆情走向）"
                rows="5"
                :disabled="loading"
              ></textarea>
              <div class="model-badge">引擎: AGARS-V1.0</div>
            </div>
          </div>

          <div class="console-block btn-block">
            <button class="start-btn" @click="startSimulation" :disabled="!canSubmit || loading">
              <span v-if="!loading">启动引擎</span>
              <span v-else>初始化中...</span>
              <span class="btn-arrow">→</span>
            </button>
          </div>
        </div>

      </div>
    </section>

    <!-- ═══ HISTORY ═══ -->
    <HistoryDatabase />

    <SettingsModal :visible="showSettings" @close="showSettings = false" />

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import SettingsModal from '../components/SettingsModal.vue'
import homepageImg from '../assets/homepage.png'

const router = useRouter()

const showSettings = ref(false)
const formData = ref({ simulationRequirement: '' })
const files = ref([])
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)
const fileInput = ref(null)


const canSubmit = computed(() =>
  formData.value.simulationRequirement.trim() !== '' && files.value.length > 0
)

const triggerFileInput = () => {
  if (!loading.value) fileInput.value?.click()
}

const handleFileSelect = (event) => {
  addFiles(Array.from(event.target.files))
}

const handleDragOver = () => {
  if (!loading.value) isDragOver.value = true
}

const handleDragLeave = () => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  addFiles(Array.from(e.dataTransfer.files))
}

const addFiles = (newFiles) => {
  const valid = newFiles.filter(f => ['pdf', 'md', 'txt'].includes(f.name.split('.').pop().toLowerCase()))
  files.value.push(...valid)
}

const removeFile = (index) => {
  files.value.splice(index, 1)
}

const scrollToConsole = () => {
  document.getElementById('console')?.scrollIntoView({ behavior: 'smooth' })
}

const scrollToFeatures = () => {
  document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
}

const startSimulation = () => {
  if (!canSubmit.value || loading.value) return
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(files.value, formData.value.simulationRequirement)
    router.push({ name: 'Process', params: { projectId: 'new' } })
  })
}
</script>

<style scoped>
/* ─── Variables ─── */
:root {
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  --font-cn:   'Noto Sans SC', system-ui, sans-serif;
}

.home-container {
  min-height: 100vh;
  background: #fff;
  font-family: var(--font-sans);
  color: #000;
}

/* ─── NAVBAR ─── */
.navbar {
  height: 60px;
  background: #000;
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 48px;
  position: sticky;
  top: 0;
  z-index: 1100; /* above HistoryDatabase card hover z-index:1000 */
}

.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 2px;
  font-size: 1.15rem;
}
.brand-accent { color: #FF4500; }

.nav-links { display: flex; align-items: center; gap: 16px; }

.settings-btn {
  background: none;
  border: 1px solid rgba(255,255,255,0.25);
  color: #fff;
  width: 32px; height: 32px;
  padding: 0;
  border-radius: 4px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: border-color 0.2s, color 0.2s;
}
.settings-btn:hover { border-color: #FF4500; color: #FF4500; }
.gear-icon { width: 16px; height: 16px; }


/* ─── HERO ─── */
.hero {
  display: flex;
  align-items: center;
  min-height: calc(100vh - 60px);
  max-width: 1400px;
  margin: 0 auto;
  padding: 72px 48px;
  gap: 64px;
}

/* Left */
.hero-left { flex: 1; min-width: 0; }

.hero-meta-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 28px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
}
.meta-tag {
  background: #000;
  color: #fff;
  padding: 5px 12px;
  font-weight: 700;
  letter-spacing: 1.5px;
}
.meta-version { color: #999; letter-spacing: 0.5px; }

.hero-title {
  font-size: clamp(2.8rem, 4.5vw, 4.6rem);
  font-weight: 500;
  line-height: 1.15;
  letter-spacing: -2px;
  margin: 0 0 36px 0;
}
.hero-title-accent {
  background: linear-gradient(90deg, #FF4500 0%, #111 60%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
}

/* Stats row */
.hero-stats {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 28px;
  border: 1px solid #e8e8e8;
}
.hero-stat {
  flex: 1;
  padding: 18px 24px;
  text-align: center;
}
.stat-value {
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 1.5rem;
  color: #000;
  margin-bottom: 4px;
}
.stat-divider {
  width: 1px;
  height: 56px;
  background: #e8e8e8;
  flex-shrink: 0;
}
.stat-label {
  font-size: 0.75rem;
  color: #999;
  font-family: var(--font-mono);
  letter-spacing: 0.3px;
}

/* Short sub-paragraph */
.hero-sub {
  font-size: 0.95rem;
  line-height: 1.8;
  color: #555;
  max-width: 540px;
  margin-bottom: 36px;
  font-family: var(--font-cn);
}
.hero-sub strong { color: #000; font-weight: 600; }

.hero-actions { display: flex; gap: 16px; margin-bottom: 36px; }

.btn-primary {
  background: #000;
  color: #fff;
  border: none;
  padding: 14px 32px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.9rem;
  letter-spacing: 1px;
  cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  transition: background 0.2s, transform 0.15s;
}
.btn-primary:hover { background: #FF4500; transform: translateY(-1px); }

.btn-ghost {
  background: transparent;
  color: #000;
  border: 1px solid #ccc;
  padding: 14px 28px;
  font-family: var(--font-mono);
  font-weight: 500;
  font-size: 0.88rem;
  cursor: pointer;
  display: flex; align-items: center; gap: 8px;
  transition: border-color 0.2s;
}
.btn-ghost:hover { border-color: #000; }

/* Mode strip */
.mode-strip {
  display: flex;
  align-items: stretch;
  max-width: 500px;
  border: 1px solid #e8e8e8;
}
.mode-item {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 20px;
}
.mode-item--accent { background: #fdf2ef; }
.mode-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}
.mode-dot--oasis    { background: #999; }
.mode-dot--narrative { background: #FF4500; }
.mode-name {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.78rem;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.original-badge {
  font-size: 0.6rem;
  background: #FF4500;
  color: #fff;
  padding: 1px 6px;
  letter-spacing: 0.5px;
  font-weight: 700;
}
.mode-desc {
  font-size: 0.72rem;
  color: #888;
  font-family: var(--font-mono);
  line-height: 1.5;
}
.mode-divider { width: 1px; background: #e8e8e8; flex-shrink: 0; }

/* Right — pure white, no border, no background noise */
.hero-right {
  flex: 0 0 auto;
  width: 460px;
  background: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}
.petri-img {
  width: 100%;
  max-width: 460px;
  display: block;
}
.petri-caption {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #bbb;
  display: flex;
  align-items: center;
  gap: 8px;
  letter-spacing: 0.5px;
}
.petri-caption-dot { color: #FF4500; }

/* ─── FEATURES ─── */
.features {
  background: #000;
  padding: 72px 48px;
}
.features-header {
  max-width: 1400px;
  margin: 0 auto 40px;
}
.section-eyebrow {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 2.5px;
  color: #FF4500;
  margin-bottom: 10px;
}
.features-title {
  font-size: 2rem;
  font-weight: 500;
  color: #fff;
  margin: 0;
}

.features-grid {
  max-width: 1400px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2px;
  background: #222;
}
.feature-card { background: #111; transition: background 0.2s; }
.feature-card:hover { background: #161616; }
.feature-card--accent { background: #FF4500; }
.feature-card--accent:hover { background: #e03d00; }

.feature-card-inner {
  padding: 40px 34px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  box-sizing: border-box;
}
.feature-num {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 700;
  color: rgba(255,255,255,0.2);
  letter-spacing: 1px;
}
.feature-card--accent .feature-num { color: rgba(255,255,255,0.5); }
.feature-icon-wrap { color: rgba(255,255,255,0.65); margin-bottom: 2px; }
.feature-card--accent .feature-icon-wrap { color: rgba(255,255,255,0.9); }
.feature-tag-line {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 1.8px;
  color: rgba(255,255,255,0.35);
}
.feature-card--accent .feature-tag-line { color: rgba(255,255,255,0.7); }
.feature-name {
  font-size: 1.2rem;
  font-weight: 600;
  color: #fff;
  margin: 0;
  line-height: 1.3;
}
.feature-desc {
  font-size: 0.87rem;
  line-height: 1.75;
  color: rgba(255,255,255,0.5);
  font-family: var(--font-cn);
  margin: 0;
  flex: 1;
}
.feature-card--accent .feature-desc { color: rgba(255,255,255,0.88); }

/* ─── NARRATIVE SPOTLIGHT ─── */
.narrative-spotlight {
  background: #0a0a0a;
  padding: 88px 48px;
  border-top: 1px solid #1a1a1a;
}
.narrative-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  gap: 80px;
  align-items: center;
}

/* Left text */
.narrative-left { flex: 1; }

.narrative-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 2.5px;
  color: #FF4500;
  margin-bottom: 16px;
}
.narrative-title {
  font-size: 2.8rem;
  font-weight: 500;
  color: #fff;
  margin: 0 0 12px;
  letter-spacing: -1px;
}
.narrative-sub {
  font-size: 1rem;
  color: #777;
  font-family: var(--font-cn);
  margin: 0 0 36px;
  line-height: 1.7;
}

.narrative-features {
  list-style: none;
  padding: 0;
  margin: 0 0 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.narrative-features li {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  font-family: var(--font-cn);
  font-size: 0.9rem;
  color: rgba(255,255,255,0.65);
  line-height: 1.65;
}
.nf-icon {
  color: #FF4500;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  margin-top: 1px;
  flex-shrink: 0;
}
.narrative-features strong { color: #fff; font-weight: 600; }

/* VS comparison */
.narrative-vs {
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid #2a2a2a;
  max-width: 480px;
}
.vs-col {
  flex: 1;
  padding: 18px 22px;
}
.vs-col--accent { background: rgba(255,69,0,0.1); border-left: 2px solid #FF4500; }
.vs-label {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  font-weight: 700;
  color: #fff;
  margin-bottom: 6px;
}
.vs-desc {
  font-size: 0.75rem;
  color: #666;
  font-family: var(--font-mono);
  line-height: 1.6;
}
.vs-col--accent .vs-label { color: #FF4500; }
.vs-col--accent .vs-desc  { color: #aaa; }
.vs-sep {
  padding: 0 16px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: #444;
}

/* Right: Chat mockup */
.narrative-right { flex: 0 0 400px; }

.chat-mockup {
  background: #111;
  border: 1px solid #2a2a2a;
  font-family: var(--font-cn);
  overflow: hidden;
}
.chat-mockup-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  background: #0d0d0d;
  border-bottom: 1px solid #2a2a2a;
}
.chat-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #333;
}
.chat-dot--active { background: #FF4500; }
.chat-scene {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #555;
  margin-left: 8px;
  letter-spacing: 0.5px;
}

.chat-messages {
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.chat-msg { display: flex; flex-direction: column; gap: 5px; }
.chat-role {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: #555;
  letter-spacing: 0.5px;
}
.chat-msg--narrative .chat-role { color: #888; font-style: italic; }
.chat-msg--narrative .chat-bubble {
  background: transparent;
  border-color: #222;
  color: rgba(255,255,255,0.6);
  font-style: italic;
  max-width: 100%;
}
.chat-msg--player { align-items: flex-end; }
.chat-msg--player .chat-role { color: #FF4500; }

.chat-bubble {
  display: inline-block;
  font-size: 0.85rem;
  line-height: 1.6;
  color: rgba(255,255,255,0.8);
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  padding: 10px 14px;
  max-width: 90%;
}
.chat-msg--player .chat-bubble {
  background: #1a0800;
  border-color: #3d1100;
}

/* Typing animation */
.chat-bubble--typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 14px;
}
.typing-dot {
  width: 5px; height: 5px;
  background: #555;
  border-radius: 50%;
  animation: typingBounce 1.2s ease-in-out infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-5px); opacity: 1; }
}

.chat-choices {
  padding: 12px 16px 16px;
  border-top: 1px solid #1f1f1f;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.choice-label {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: #444;
  letter-spacing: 1px;
  margin-bottom: 2px;
}
.choice-btn {
  font-size: 0.82rem;
  color: rgba(255,255,255,0.45);
  background: #151515;
  border: 1px solid #222;
  padding: 9px 12px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s;
}
.choice-btn--active {
  background: #FF4500;
  color: #fff;
  border-color: #FF4500;
}
.choice-btn:not(.choice-btn--active):hover {
  border-color: #444;
  color: rgba(255,255,255,0.7);
}

/* ─── WORKFLOW / PIPELINE ─── */
.workflow-section {
  padding: 64px 48px;
  background: #fafafa;
  border-top: 1px solid #eee;
  border-bottom: 1px solid #eee;
}
.workflow-inner { max-width: 1400px; margin: 0 auto; }
.workflow-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 2.5px;
  color: #bbb;
  margin-bottom: 28px;
}

/* Main pipeline container — full width */
.pipeline {
  display: flex;
  border: 1px solid #e0e0e0;
  background: #fff;
}

/* Left column: shared steps */
.pl-shared {
  flex: 0 0 200px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 28px 24px;
  border-right: 1px solid #e0e0e0;
  gap: 0;
}
.pl-step {
  padding: 10px 0;
}
.pl-vert-line {
  width: 1px;
  height: 20px;
  background: #e0e0e0;
  margin: 2px 0 2px 6px;
}
.pl-fork-hint {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: #bbb;
  margin-top: 10px;
  letter-spacing: 0.5px;
}

/* Right column: two branch rows */
.pl-branches {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.pl-branch {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 20px 28px;
  gap: 0;
}
.pl-branch--oasis { border-bottom: 1px solid #ececec; }
.pl-branch--narrative { background: #fdf2ef; }

.branch-tag {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  font-weight: 700;
  color: #aaa;
  letter-spacing: 1px;
  min-width: 100px;
  flex-shrink: 0;
  margin-right: 20px;
  display: flex;
  align-items: center;
  gap: 7px;
}
.branch-tag--narrative { color: #FF4500; }

.branch-flow {
  flex: 1;
  display: flex;
  align-items: stretch;
  gap: 0;
}

/* Step cards inside branch rows */
.pl-step--flow {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #e8e8e8;
  background: #fff;
}
.pl-step--narr {
  background: rgba(255, 69, 0, 0.03);
  border-color: rgba(255, 69, 0, 0.15);
}

.flow-arr {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: #ccc;
  padding: 0 10px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.flow-arr--narr { color: rgba(255, 69, 0, 0.3); }

.pipe-num {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  font-weight: 700;
  color: #FF4500;
  margin-bottom: 5px;
}
.pipe-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #000;
  margin-bottom: 3px;
}
.pipe-desc {
  font-family: var(--font-mono);
  font-size: 0.64rem;
  color: #aaa;
  line-height: 1.5;
}

.branch-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.branch-dot--oasis     { background: #bbb; }
.branch-dot--narrative { background: #FF4500; }

.branch-original {
  font-size: 0.55rem;
  background: #FF4500;
  color: #fff;
  padding: 1px 5px;
  letter-spacing: 0.5px;
  font-weight: 700;
}

/* ─── CONSOLE ─── */
.launch-section {
  padding: 80px 48px;
  max-width: 1400px;
  margin: 0 auto;
}
.launch-layout {
  display: flex;
  border: 1px solid #ccc;
  align-items: stretch;
}

/* Left info panel */
.launch-info {
  flex: 0 0 320px;
  background: #f8f8f8;
  border-right: 1px solid #e0e0e0;
  padding: 36px 32px;
  display: flex;
  flex-direction: column;
}

.launch-status {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #aaa;
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 16px;
}
.status-dot { color: #FF4500; font-size: 0.55rem; }

.launch-title {
  font-size: 2.1rem;
  font-weight: 500;
  letter-spacing: -1px;
  line-height: 1.2;
  margin: 0 0 14px;
}
.launch-desc {
  font-size: 0.85rem;
  line-height: 1.8;
  color: #777;
  font-family: var(--font-cn);
  margin-bottom: 24px;
}

/* Mini metric cards inside launch-info */
.launch-meta-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
}
.lm-card {
  flex: 1;
  min-width: 80px;
  background: #fff;
  border: 1px solid #e8e8e8;
  padding: 12px 14px;
}
.lm-card--full { flex: 0 0 100%; }
.lm-value {
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 1.2rem;
  color: #000;
  margin-bottom: 3px;
}
.lm-value--sm { font-size: 0.95rem; }
.lm-label {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #aaa;
}

.launch-hints {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: auto; /* push to bottom */
}
.hint-item {
  display: flex; align-items: flex-start; gap: 10px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #999;
  line-height: 1.5;
}
.hint-icon { color: #FF4500; font-size: 0.6rem; margin-top: 2px; flex-shrink: 0; }

/* Right: console box */
.launch-console { flex: 1; padding: 8px; }

.console-block { padding: 20px; }
.console-block.btn-block { padding-top: 0; }
.console-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 13px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #888;
}
.console-label { color: #333; font-weight: 600; }
.console-meta { color: #bbb; }

.upload-zone {
  border: 1px dashed #ccc;
  height: 175px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  background: #fafafa;
  transition: background 0.2s, border-color 0.2s;
}
.upload-zone:hover { background: #f0f0f0; border-color: #999; }
.upload-zone.drag-over { background: #fff8f6; border-color: #FF4500; }

.upload-placeholder { text-align: center; }
.upload-arrow {
  width: 36px; height: 36px;
  border: 1px solid #ddd;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 12px;
  color: #bbb;
}
.upload-title { font-size: 0.88rem; font-weight: 500; margin-bottom: 4px; }
.upload-hint { font-family: var(--font-mono); font-size: 0.7rem; color: #bbb; }

.file-list {
  width: 100%; padding: 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.file-item {
  display: flex; align-items: center; gap: 8px;
  background: #fff;
  padding: 7px 10px;
  border: 1px solid #eee;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}
.file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remove-btn {
  background: none; border: none; cursor: pointer;
  font-size: 1.1rem; color: #ccc; padding: 0; line-height: 1;
}
.remove-btn:hover { color: #FF4500; }

.console-divider {
  display: flex; align-items: center; margin: 2px 0;
}
.console-divider::before, .console-divider::after {
  content: ''; flex: 1; height: 1px; background: #eee;
}
.console-divider span {
  padding: 0 14px;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #ccc;
  letter-spacing: 1px;
}

.input-wrapper {
  position: relative;
  border: 1px solid #ddd;
  background: #fafafa;
}
.code-input {
  width: 100%; border: none; background: transparent;
  padding: 15px 16px;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  line-height: 1.65;
  resize: vertical; outline: none;
  min-height: 115px;
  box-sizing: border-box;
}
.model-badge {
  position: absolute; bottom: 9px; right: 13px;
  font-family: var(--font-mono);
  font-size: 0.62rem; color: #ccc;
}

.start-btn {
  width: 100%;
  background: #000; color: #fff;
  border: none;
  padding: 18px 24px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.95rem;
  display: flex; justify-content: space-between; align-items: center;
  cursor: pointer;
  letter-spacing: 1px;
  transition: background 0.2s, transform 0.15s;
  animation: pulseShadow 2.5s infinite;
}
.start-btn:not(:disabled):hover { background: #FF4500; transform: translateY(-1px); }
.start-btn:disabled {
  background: #e5e5e5; color: #aaa;
  cursor: not-allowed; animation: none; transform: none;
}
.btn-arrow { font-size: 1.1rem; }

@keyframes pulseShadow {
  0%   { box-shadow: 0 0 0 0 rgba(0,0,0,0.2); }
  70%  { box-shadow: 0 0 0 6px rgba(0,0,0,0); }
  100% { box-shadow: 0 0 0 0 rgba(0,0,0,0); }
}

/* ─── Responsive ─── */
@media (max-width: 1100px) {
  .hero { flex-direction: column; padding: 60px 32px; min-height: auto; }
  .hero-right { width: 100%; }
  .petri-img { max-width: 340px; margin: 0 auto; }
  .features-grid { grid-template-columns: 1fr; }
  .feature-card--accent { order: -1; }
  .narrative-inner { flex-direction: column; gap: 48px; }
  .narrative-right { flex: auto; width: 100%; }
  .pipeline { flex-direction: column; }
  .pl-shared { flex: none; flex-direction: row; flex-wrap: wrap; gap: 12px; align-items: center; border-right: none; border-bottom: 1px solid #e0e0e0; }
  .pl-vert-line { display: none; }
  .pl-fork-hint { display: none; }
  .pl-branch { flex-wrap: wrap; gap: 8px; }
  .branch-flow { flex-wrap: wrap; }
  .pl-step--flow { min-width: 110px; }
  .launch-layout { flex-direction: column; }
  .launch-info { flex: none; border-right: none; border-bottom: 1px solid #e0e0e0; }
  .launch-section { padding: 60px 32px; }
}
@media (max-width: 640px) {
  .navbar { padding: 0 24px; }
  .hero { padding: 48px 24px; }
  .features { padding: 60px 24px; }
  .narrative-spotlight { padding: 60px 24px; }
  .workflow-section { padding: 48px 24px; }
  .mode-strip { flex-direction: column; }
  .mode-divider { width: 100%; height: 1px; }
  .hero-stats { flex-direction: column; }
  .stat-divider { width: 100%; height: 1px; }
}
</style>
