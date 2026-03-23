<template>
  <router-view />
  <MonitorPanel />
  <button
    class="monitor-fab"
    :class="{ active: monitorState.isOpen }"
    @click="toggleMonitor"
    title="AI Monitor (Ctrl+Shift+M)"
  >AI</button>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import MonitorPanel from './components/MonitorPanel.vue'
import { state as monitorState, toggleMonitor } from './store/monitorStore'

function onKeydown(e) {
  if (e.ctrlKey && e.shiftKey && e.key === 'M') {
    e.preventDefault()
    toggleMonitor()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style>
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #000000;
  background-color: #ffffff;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: #000000;
}

::-webkit-scrollbar-thumb:hover {
  background: #333333;
}

/* 全局按钮样式 */
button {
  font-family: inherit;
}

/* Monitor floating action button */
.monitor-fab {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #111;
  color: #ccc;
  border: 2px solid #333;
  font-size: 11px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  cursor: pointer;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s, color 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
.monitor-fab:hover {
  border-color: #666;
  color: #fff;
}
.monitor-fab.active {
  border-color: #ff6b00;
  color: #ff6b00;
}
</style>
