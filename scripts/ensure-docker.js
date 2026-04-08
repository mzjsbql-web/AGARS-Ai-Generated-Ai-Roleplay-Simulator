/**
 * 确保 Docker Desktop 正在运行（Windows）
 * 如果 Docker 已安装但未启动，自动拉起 Docker Desktop 并等待就绪。
 * 用法: node scripts/ensure-docker.js
 */
const { execSync, spawn } = require('child_process')

function isDockerRunning() {
  try {
    execSync('docker info', { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function main() {
  // 检查 docker 命令是否存在
  try {
    execSync('docker --version', { stdio: 'ignore' })
  } catch {
    console.log('[ensure-docker] Docker not installed, skipping')
    return
  }

  if (isDockerRunning()) {
    return
  }

  console.log('[ensure-docker] Docker is not running, starting Docker Desktop...')

  // 尝试启动 Docker Desktop
  const dockerPath = `${process.env.ProgramFiles}\\Docker\\Docker\\Docker Desktop.exe`
  try {
    spawn(dockerPath, [], { detached: true, stdio: 'ignore' }).unref()
  } catch {
    console.log('[ensure-docker] Could not start Docker Desktop, please start it manually')
    return
  }

  // 等待 Docker 就绪（最多 60 秒）
  const maxWait = 60
  let waited = 0
  while (waited < maxWait) {
    await sleep(3000)
    waited += 3
    if (isDockerRunning()) {
      console.log(`[ensure-docker] Docker Desktop is ready (${waited}s)`)
      return
    }
    if (waited % 9 === 0) {
      console.log(`[ensure-docker] Waiting for Docker... (${waited}s)`)
    }
  }

  console.log('[ensure-docker] Docker Desktop is still starting, continuing anyway...')
}

main()
