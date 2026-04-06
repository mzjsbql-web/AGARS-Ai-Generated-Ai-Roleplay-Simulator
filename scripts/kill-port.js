/**
 * 清理占用指定端口的残留进程（Windows）
 * 用法: node scripts/kill-port.js 5001
 */
const { execSync } = require('child_process')

const port = process.argv[2] || '5001'

try {
  const output = execSync(`netstat -ano | findstr :${port} | findstr LISTENING`, {
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe'],
  })

  const pids = new Set()
  for (const line of output.trim().split('\n')) {
    const pid = line.trim().split(/\s+/).pop()
    if (pid && pid !== '0') pids.add(pid)
  }

  for (const pid of pids) {
    try {
      execSync(`taskkill /F /PID ${pid}`, { stdio: 'ignore' })
      console.log(`Killed stale process on port ${port} (PID ${pid})`)
    } catch {}
  }
} catch {
  // findstr 没有匹配 = 端口空闲，正常
}
