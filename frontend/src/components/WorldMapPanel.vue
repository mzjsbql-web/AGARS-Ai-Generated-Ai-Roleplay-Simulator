<template>
  <div class="wm-panel">
    <div class="wm-header">
      <span class="wm-title">世界地图</span>
      <div class="wm-controls" v-if="displayNodes.length > 0">
        <button class="wm-ctrl-btn" @click="zoomIn" title="放大">+</button>
        <button class="wm-ctrl-btn" @click="resetView" title="重置视图">⊙</button>
        <button class="wm-ctrl-btn" @click="zoomOut" title="缩小">−</button>
      </div>
    </div>

    <div v-if="displayNodes.length === 0" class="wm-empty">
      <div class="wm-empty-icon">◈</div>
      <div class="wm-empty-text">地图准备中...</div>
    </div>

    <template v-else>
      <div class="wm-svg-wrap" ref="wrapEl">
        <svg
          ref="svgEl"
          :viewBox="`0 0 ${VW} ${VH}`"
          class="wm-svg"
          :class="{ dragging: isDragging }"
          preserveAspectRatio="xMidYMid meet"
          @wheel.prevent="onWheel"
          @mousedown="onMouseDown"
          @dblclick="resetView"
          @contextmenu.prevent
        >
          <g :transform="viewTransform">
            <!-- Edges: dashed by default, highlighted on hover -->
            <line
              v-for="e in displayEdges"
              :key="e.id"
              :x1="e.x1" :y1="e.y1"
              :x2="e.x2" :y2="e.y2"
              :class="[
                'wm-edge',
                {
                  'wm-edge--active': hoveredEdgeSet.has(e.id),
                  'wm-edge--faded': hovered && !hoveredEdgeSet.has(e.id)
                }
              ]"
            />

            <!-- Nodes -->
            <g
              v-for="n in displayNodes"
              :key="n.id"
              class="wm-node-g"
              @mouseenter.stop="hovered = n"
              @mouseleave.stop="hovered = null"
            >
              <!-- Drop shadow -->
              <rect
                :x="n.x - n.nw/2 + 1" :y="n.y - NH/2 + 2"
                :width="n.nw" :height="NH" rx="7"
                fill="rgba(0,0,0,0.06)"
              />
              <!-- Room body -->
              <rect
                :x="n.x - n.nw/2" :y="n.y - NH/2"
                :width="n.nw" :height="NH" rx="7"
                :class="['wm-room', {
                  'wm-room--player': n.isPlayerLoc,
                  'wm-room--occupied': n.chars.length > 0 && !n.isPlayerLoc,
                  'wm-room--hover': hovered && hovered.id === n.id
                }]"
              />
              <!-- Animated ring for player location -->
              <rect
                v-if="n.isPlayerLoc"
                :x="n.x - n.nw/2 - 4" :y="n.y - NH/2 - 4"
                :width="n.nw + 8" :height="NH + 8" rx="10"
                fill="none" stroke="#1565C0" stroke-width="1.5"
                stroke-dasharray="5 4" opacity="0.4"
                class="wm-player-ring"
              />
              <!-- Location name -->
              <text
                :x="n.x" :y="n.y + 5"
                text-anchor="middle"
                :class="['wm-room-label', { 'wm-room-label--player': n.isPlayerLoc }]"
              >{{ n.id }}</text>

              <!-- Character dots below the room -->
              <g v-if="n.chars.length > 0">
                <template v-for="(c, ci) in n.chars.slice(0, 4)" :key="c.uuid">
                  <circle
                    :cx="charDotX(n, ci)" :cy="n.y + NH/2 + 11"
                    r="7"
                    :class="['wm-char-dot', { 'wm-char-dot--player': c.isPlayer }]"
                  />
                  <text
                    :x="charDotX(n, ci)" :y="n.y + NH/2 + 15"
                    text-anchor="middle"
                    class="wm-char-initial"
                  >{{ c.initial }}</text>
                </template>
                <text
                  v-if="n.chars.length > 4"
                  :x="charDotX(n, 4)" :y="n.y + NH/2 + 15"
                  text-anchor="middle"
                  class="wm-char-overflow"
                >+{{ n.chars.length - 4 }}</text>
              </g>
            </g>
          </g>
        </svg>
      </div>

      <!-- Info strip -->
      <div class="wm-info">
        <template v-if="hovered">
          <span class="wm-info-name">{{ hovered.id }}</span>
          <span v-if="hovered.description" class="wm-info-desc"> — {{ hovered.description }}</span>
          <div v-if="hovered.chars.length > 0" class="wm-info-row">
            <span class="wm-info-tag">在此</span>
            {{ hovered.chars.map(c => c.name).join('、') }}
          </div>
          <div v-if="hovered.adjacent && hovered.adjacent.length > 0" class="wm-info-row">
            <span class="wm-info-tag">可前往</span>
            {{ hovered.adjacent.join('、') }}
          </div>
        </template>
        <template v-else-if="playerNode">
          <span class="wm-info-name">{{ playerNode.id }}</span>
          <span class="wm-info-current"> — 当前位置</span>
          <div v-if="playerNode.adjacent && playerNode.adjacent.length > 0" class="wm-info-row">
            <span class="wm-info-tag">可前往</span>
            {{ playerNode.adjacent.join('、') }}
          </div>
        </template>
        <template v-else>
          <span class="wm-info-hint">悬停查看详情 · 滚轮缩放 · 拖拽平移</span>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  worldMap:        { type: Object, default: () => ({}) },
  agentLocations:  { type: Object, default: () => ({}) },
  profiles:        { type: Array,  default: () => [] },
  playerEntityUuid:{ type: String, default: '' }
})

// ── Canvas constants ──────────────────────────────────────────
const VW = 580
const VH = 360
const NH = 38
const NW_MIN = 68
const NW_MAX = 230
const NODE_GAP = 22   // min gap between node edges (AABB)

// ── DOM refs ─────────────────────────────────────────────────
const svgEl = ref(null)

// ── Zoom / Pan ────────────────────────────────────────────────
const zoom   = ref(1)
const panX   = ref(0)
const panY   = ref(0)
const isDragging = ref(false)

const viewTransform = computed(() =>
  `translate(${panX.value},${panY.value}) scale(${zoom.value})`
)

// Convert screen coords → SVG viewBox coords
const toSVG = (clientX, clientY) => {
  if (!svgEl.value) return { x: 0, y: 0 }
  const pt = svgEl.value.createSVGPoint()
  pt.x = clientX; pt.y = clientY
  return pt.matrixTransform(svgEl.value.getScreenCTM().inverse())
}

let _dragStart = null  // { svgX, svgY, panX, panY }

const onMouseDown = (e) => {
  if (e.button !== 0) return
  isDragging.value = true
  const p = toSVG(e.clientX, e.clientY)
  _dragStart = { sx: p.x, sy: p.y, px: panX.value, py: panY.value }
}

const onMouseMove = (e) => {
  if (!isDragging.value || !_dragStart) return
  const p = toSVG(e.clientX, e.clientY)
  panX.value = _dragStart.px + (p.x - _dragStart.sx)
  panY.value = _dragStart.py + (p.y - _dragStart.sy)
}

const onMouseUp = () => { isDragging.value = false; _dragStart = null }

const onWheel = (e) => {
  const p = toSVG(e.clientX, e.clientY)
  const factor = e.deltaY < 0 ? 1.15 : 0.87
  const newZoom = Math.max(0.25, Math.min(5, zoom.value * factor))
  const ratio = newZoom / zoom.value
  panX.value = p.x - (p.x - panX.value) * ratio
  panY.value = p.y - (p.y - panY.value) * ratio
  zoom.value = newZoom
}

const resetView = () => { zoom.value = 1; panX.value = 0; panY.value = 0 }
const zoomIn    = () => { zoom.value = Math.min(5, zoom.value * 1.2) }
const zoomOut   = () => { zoom.value = Math.max(0.25, zoom.value / 1.2) }

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup',   onMouseUp)
})
onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup',   onMouseUp)
})

// ── Node sizing ───────────────────────────────────────────────
function nodeWidth(name) {
  // 14px per CJK char at 12.5px bold; 24px horizontal inner padding
  return Math.max(NW_MIN, Math.min(NW_MAX, Math.ceil(name.length * 14) + 24))
}

// AABB full overlap resolution — fully separates the pair each call
// Returns true if there was an overlap to fix
function aabbSeparate(a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const minX = (a.nw + b.nw) / 2 + NODE_GAP
  const minY = NH + NODE_GAP
  const ox = minX - Math.abs(dx)
  const oy = minY - Math.abs(dy)
  if (ox <= 0 || oy <= 0) return false
  // Push along the axis with LESS overlap (minimal displacement)
  if (ox < oy) {
    const half = ox / 2 + 0.5          // +0.5 ensures no re-touch after rounding
    const sign = (dx === 0 ? 1 : Math.sign(dx))
    a.x -= half * sign; b.x += half * sign
  } else {
    const half = oy / 2 + 0.5
    const sign = (dy === 0 ? 1 : Math.sign(dy))
    a.y -= half * sign; b.y += half * sign
  }
  return true
}

// Clip edge line to the node rectangle border
function clipToBorder(cx, cy, tx, ty, nw) {
  const dx = tx - cx, dy = ty - cy
  if (dx === 0 && dy === 0) return { x: cx, y: cy }
  const w2 = nw / 2, h2 = NH / 2
  const t = Math.min(w2 / Math.abs(dx || 1e-9), h2 / Math.abs(dy || 1e-9))
  return { x: cx + dx * t, y: cy + dy * t }
}

// ── Layout state ──────────────────────────────────────────────
const rawNodes = ref([])
const rawEdges = ref([])

function buildLayout() {
  const locNames = Object.keys(props.worldMap)
  if (!locNames.length) { rawNodes.value = []; rawEdges.value = []; return }

  // Deduplicated edges
  const edgeSet = new Set()
  const edgeKeys = []
  for (const [name, data] of Object.entries(props.worldMap)) {
    for (const adj of (data.adjacent || [])) {
      const key = [name, adj].sort().join('¦')
      if (!edgeSet.has(key)) { edgeSet.add(key); edgeKeys.push(key) }
    }
  }

  // Initial positions: circular, scaled by node count for breathing room
  const R = Math.max(100, locNames.length * 18)
  const nodes = locNames.map((name, i) => {
    const angle = (2 * Math.PI * i) / locNames.length - Math.PI / 2
    return {
      id:          name,
      description: props.worldMap[name]?.description || '',
      adjacent:    props.worldMap[name]?.adjacent    || [],
      nw: nodeWidth(name),
      x: VW / 2 + Math.cos(angle) * R,
      y: VH / 2 + Math.sin(angle) * R,
      vx: 0, vy: 0
    }
  })

  const edges = edgeKeys.map(key => {
    const [aId, bId] = key.split('¦')
    return { id: key, s: nodes.find(n => n.id === aId), t: nodes.find(n => n.id === bId) }
  }).filter(e => e.s && e.t)

  // ── Force simulation ─────────────────────────────────────────
  // Short REST_LEN so connected rooms feel spatially adjacent;
  // strong repulsion pushes unconnected rooms apart — this creates
  // a map-like layout where topology is directly visible.
  const ITERS    = 400
  const REPULSE  = 14000
  const SPRING_K = 0.09
  const REST_LEN = 115   // short: adjacent rooms appear close
  const CTR_K    = 0.012
  const DAMP     = 0.72

  for (let iter = 0; iter < ITERS; iter++) {
    const alpha = Math.pow(1 - iter / ITERS, 1.2)

    // Repulsion between every pair
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x - nodes[i].x || 0.01
        const dy = nodes[j].y - nodes[i].y || 0.01
        const d2 = dx * dx + dy * dy
        const d  = Math.sqrt(d2)
        const f  = (REPULSE / d2) * alpha
        nodes[i].vx -= (dx / d) * f;  nodes[i].vy -= (dy / d) * f
        nodes[j].vx += (dx / d) * f;  nodes[j].vy += (dy / d) * f
      }
    }

    // Spring attraction along edges
    for (const e of edges) {
      const dx = e.t.x - e.s.x
      const dy = e.t.y - e.s.y
      const d  = Math.sqrt(dx * dx + dy * dy) + 0.01
      const f  = (d - REST_LEN) * SPRING_K * alpha
      const nx = dx / d, ny = dy / d
      e.s.vx += nx * f;  e.s.vy += ny * f
      e.t.vx -= nx * f;  e.t.vy -= ny * f
    }

    // Integrate + center gravity (no boundary clamp during sim — let nodes spread)
    for (const n of nodes) {
      n.vx += (VW / 2 - n.x) * CTR_K
      n.vy += (VH / 2 - n.y) * CTR_K
      n.vx *= DAMP;  n.vy *= DAMP
      n.x  += n.vx;  n.y  += n.vy
    }
  }

  // ── Hard overlap removal ──────────────────────────────────────
  // Each call to aabbSeparate fully resolves one pair; run until
  // no overlaps remain (converges quickly, typically < 60 passes).
  for (let pass = 0; pass < 300; pass++) {
    let anyOverlap = false
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++)
        if (aabbSeparate(nodes[i], nodes[j])) anyOverlap = true
    if (!anyOverlap) break
  }

  // ── Auto-fit: scale + center all nodes to fill the viewBox ───
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const n of nodes) {
    minX = Math.min(minX, n.x - n.nw / 2)
    maxX = Math.max(maxX, n.x + n.nw / 2)
    minY = Math.min(minY, n.y - NH / 2)
    maxY = Math.max(maxY, n.y + NH / 2)
  }
  const PAD = 48
  const scaleX = (VW - PAD * 2) / (maxX - minX || 1)
  const scaleY = (VH - PAD * 2) / (maxY - minY || 1)
  const scale  = Math.min(scaleX, scaleY, 1.4)  // never enlarge past 1.4×
  const cx     = (minX + maxX) / 2
  const cy     = (minY + maxY) / 2
  for (const n of nodes) {
    n.x = VW / 2 + (n.x - cx) * scale
    n.y = VH / 2 + (n.y - cy) * scale
  }

  // One final overlap pass after scaling (scale can bring nodes closer)
  for (let pass = 0; pass < 200; pass++) {
    let anyOverlap = false
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++)
        if (aabbSeparate(nodes[i], nodes[j])) anyOverlap = true
    if (!anyOverlap) break
  }

  rawNodes.value = nodes
  rawEdges.value = edges
  resetView()
}

// ── Computed display data ─────────────────────────────────────
const hovered = ref(null)

const displayNodes = computed(() => {
  if (!rawNodes.value.length) return []

  const locChars = {}
  for (const [uuid, loc] of Object.entries(props.agentLocations)) {
    const p = props.profiles.find(p => p.entity_uuid === uuid)
    if (!p) continue
    if (!locChars[loc]) locChars[loc] = []
    locChars[loc].push({
      uuid,
      name:     p.name || '?',
      isPlayer: !!(p.is_player || uuid === props.playerEntityUuid),
      initial:  (p.name || '?')[0].toUpperCase()
    })
  }

  return rawNodes.value.map(n => ({
    ...n,
    chars:       locChars[n.id] || [],
    isPlayerLoc: (locChars[n.id] || []).some(c => c.isPlayer)
  }))
})

const displayEdges = computed(() =>
  rawEdges.value.map(e => {
    const s = displayNodes.value.find(n => n.id === e.s.id)
    const t = displayNodes.value.find(n => n.id === e.t.id)
    if (!s || !t) return null
    const p1 = clipToBorder(s.x, s.y, t.x, t.y, s.nw)
    const p2 = clipToBorder(t.x, t.y, s.x, s.y, t.nw)
    return { id: e.id, sId: e.s.id, tId: e.t.id, x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y }
  }).filter(Boolean)
)

// Which edge IDs are connected to the hovered node
const hoveredEdgeSet = computed(() => {
  if (!hovered.value) return new Set()
  return new Set(
    displayEdges.value
      .filter(e => e.sId === hovered.value.id || e.tId === hovered.value.id)
      .map(e => e.id)
  )
})

const playerNode = computed(() =>
  displayNodes.value.find(n => n.isPlayerLoc) || null
)

// Character dot x-position (centered under node)
function charDotX(node, idx) {
  const count = Math.min(node.chars.length, 5)
  const total = (count - 1) * 16
  return node.x - total / 2 + idx * 16
}

// ── Rebuild on world map change ───────────────────────────────
watch(() => props.worldMap, map => {
  if (Object.keys(map).length > 0) buildLayout()
}, { immediate: true })
</script>

<style scoped>
.wm-panel {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid #E8E5E0;
  background: #FAFAFA;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.wm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 6px;
}
.wm-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: #999;
}
.wm-controls {
  display: flex;
  gap: 2px;
}
.wm-ctrl-btn {
  width: 22px;
  height: 22px;
  border: 1px solid #E0E0E0;
  background: #FFF;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.1s;
  padding: 0;
}
.wm-ctrl-btn:hover { background: #F0F0F0; color: #333; }

/* Empty */
.wm-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  gap: 6px;
}
.wm-empty-icon { font-size: 20px; color: #DDD; }
.wm-empty-text { font-size: 12px; color: #CCC; }

/* SVG container */
.wm-svg-wrap {
  padding: 0 6px;
  /* Fixed height so zoom/pan doesn't change panel size */
  height: 300px;
  overflow: hidden;
}
.wm-svg {
  width: 100%;
  height: 100%;
  cursor: grab;
  display: block;
  user-select: none;
}
.wm-svg.dragging { cursor: grabbing; }

/* Edges */
.wm-edge {
  stroke: #D0D0D0;
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
  opacity: 0.45;
  transition: opacity 0.15s, stroke 0.15s, stroke-width 0.15s;
}
.wm-edge--active {
  stroke: #888;
  stroke-width: 2;
  stroke-dasharray: none;
  opacity: 1;
}
.wm-edge--faded {
  opacity: 0.08;
}

/* Room node */
.wm-node-g { cursor: pointer; }

.wm-room {
  fill: #FFFFFF;
  stroke: #DEDEDE;
  stroke-width: 1.5;
  transition: fill 0.15s, stroke 0.15s, filter 0.15s;
}
.wm-room--player {
  fill: #EBF3FF;
  stroke: #1565C0;
  stroke-width: 2;
}
.wm-room--occupied {
  fill: #FFFBF5;
  stroke: #D4A574;
}
.wm-room--hover {
  stroke: #777;
  stroke-width: 2;
  filter: drop-shadow(0 2px 5px rgba(0,0,0,0.13));
}

/* Animated player ring */
.wm-player-ring {
  animation: wm-dash 2.5s linear infinite;
}
@keyframes wm-dash {
  to { stroke-dashoffset: -18; }
}

/* Room label */
.wm-room-label {
  fill: #555;
  font-size: 12.5px;
  font-weight: 600;
  font-family: 'Noto Sans SC', 'PingFang SC', system-ui, sans-serif;
  pointer-events: none;
  dominant-baseline: middle;
}
.wm-room-label--player {
  fill: #1565C0;
  font-weight: 700;
}

/* Character dots */
.wm-char-dot {
  fill: #BDBDBD;
  stroke: #FAFAFA;
  stroke-width: 1.5;
}
.wm-char-dot--player { fill: #1565C0; }

.wm-char-initial {
  fill: #FFF;
  font-size: 7px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  dominant-baseline: middle;
  text-anchor: middle;
  pointer-events: none;
}
.wm-char-overflow {
  fill: #AAA;
  font-size: 8px;
  font-family: 'JetBrains Mono', monospace;
  dominant-baseline: middle;
  text-anchor: middle;
  pointer-events: none;
}

/* Info strip */
.wm-info {
  margin: 4px 10px 10px;
  padding: 7px 10px;
  background: #F2F2F1;
  border-radius: 6px;
  font-size: 11.5px;
  line-height: 1.6;
  min-height: 26px;
  color: #555;
}
.wm-info-name { font-weight: 700; color: #222; }
.wm-info-desc { color: #888; }
.wm-info-current { color: #1565C0; font-weight: 500; }
.wm-info-row {
  display: flex;
  align-items: baseline;
  gap: 5px;
  flex-wrap: wrap;
}
.wm-info-tag {
  font-size: 9.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #B0B0B0;
  white-space: nowrap;
}
.wm-info-hint { color: #CCC; font-style: italic; font-size: 11px; }
</style>
