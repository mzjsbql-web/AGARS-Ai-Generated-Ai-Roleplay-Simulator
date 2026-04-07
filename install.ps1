#Requires -Version 5.1
<#
.SYNOPSIS
    AGARS 一键安装脚本 (Windows)
.DESCRIPTION
    自动检测并安装所有依赖：Node.js、Python、uv、Docker Desktop、FalkorDB
    然后安装项目依赖并启动数据库容器。
.NOTES
    以普通用户权限运行即可，部分安装步骤可能弹出 UAC 提示。
    用法：右键本文件 → "使用 PowerShell 运行"
    或在终端中执行：powershell -ExecutionPolicy Bypass -File install.ps1
#>

$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = 'AGARS Installer'

# ============================================================
# 工具函数
# ============================================================

function Write-Step($step, $msg) {
    Write-Host "`n[$step] " -ForegroundColor Cyan -NoNewline
    Write-Host $msg -ForegroundColor White
}

function Write-OK($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-Skip($msg) {
    Write-Host "  [SKIP] $msg" -ForegroundColor DarkGray
}

function Write-Warn($msg) {
    Write-Host "  [WARN] $msg" -ForegroundColor Yellow
}

function Write-Fail($msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
}

function Test-Command($name) {
    try {
        $null = & $name --version 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

# 脚本级变量：保存 winget.exe 的完整路径，绕开 Windows Server 上 AppExecution Alias 的 Access Denied 问题
$script:WingetExe = $null

function Resolve-Winget {
    # 找到可用的 winget.exe 并缓存到 $script:WingetExe
    # 优先测试已缓存的路径
    if ($script:WingetExe) {
        if ($script:WingetExe -eq 'winget' -or (Test-Path $script:WingetExe)) {
            return $true
        }
        # 缓存的路径已失效，清除
        $script:WingetExe = $null
    }

    # 方式1：直接调用 winget（桌面版 Windows 通常可用）
    try {
        $null = winget --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            $script:WingetExe = 'winget'
            return $true
        }
    } catch { }

    # 方式2：通过完整路径绕开 AppExecution Alias（Windows Server 关键路径）
    $realPath = Find-Winget
    if ($realPath) {
        try {
            $null = & $realPath --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                $script:WingetExe = $realPath
                Write-Host "  [INFO] Using winget via full path: $realPath" -ForegroundColor DarkGray
                return $true
            }
        } catch { }
    }

    return $false
}

function Test-Winget {
    return (Resolve-Winget)
}

function Invoke-WingetInstall($packageId) {
    # 尝试用 winget 安装，返回是否成功
    if (-not (Resolve-Winget)) { return $false }
    try {
        & $script:WingetExe install $packageId --source winget --accept-source-agreements --accept-package-agreements
        return ($LASTEXITCODE -eq 0)
    } catch {
        Write-Warn "winget install failed: $_"
        return $false
    }
}

function Install-NodeDirect {
    # 直接下载 Node.js LTS MSI 安装（winget 不可用时的备选方案）
    Write-Host "  Downloading Node.js LTS installer directly..." -ForegroundColor Yellow
    try {
        $tmpDir = Join-Path $env:TEMP 'node-install'
        New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
        $msiPath = Join-Path $tmpDir 'node-lts.msi'

        # 获取最新 LTS 版本号
        $indexUrl = 'https://nodejs.org/dist/index.json'
        $versions = Invoke-RestMethod -Uri $indexUrl -UseBasicParsing
        $ltsVer = ($versions | Where-Object { $_.lts -ne $false } | Select-Object -First 1).version
        $msiUrl = "https://nodejs.org/dist/$ltsVer/node-$ltsVer-x64.msi"

        Write-Host "  Downloading Node.js $ltsVer ..." -ForegroundColor Gray
        Invoke-WebRequest -Uri $msiUrl -OutFile $msiPath -UseBasicParsing

        Write-Host "  Running installer (may prompt UAC)..." -ForegroundColor Gray
        Start-Process msiexec.exe -ArgumentList "/i `"$msiPath`" /qn /norestart" -Wait -Verb RunAs
        return $true
    } catch {
        Write-Fail "Direct Node.js install failed: $_"
        return $false
    }
}

function Install-PythonDirect {
    # 直接下载 Python 安装（winget 不可用时的备选方案）
    Write-Host "  Downloading Python installer directly..." -ForegroundColor Yellow
    try {
        $tmpDir = Join-Path $env:TEMP 'python-install'
        New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
        $exePath = Join-Path $tmpDir 'python-installer.exe'

        $pyUrl = 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe'

        Write-Host "  Downloading Python 3.12.8 ..." -ForegroundColor Gray
        Invoke-WebRequest -Uri $pyUrl -OutFile $exePath -UseBasicParsing

        Write-Host "  Running installer (may prompt UAC)..." -ForegroundColor Gray
        Start-Process $exePath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -Verb RunAs
        return $true
    } catch {
        Write-Fail "Direct Python install failed: $_"
        return $false
    }
}

function Find-Winget {
    # winget 可能在多个位置，逐个查找
    $candidates = @(
        (Get-Command winget -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe",
        "$env:ProgramFiles\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe",
        "C:\Program Files\WindowsApps\Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe\winget.exe"
    )
    foreach ($pattern in $candidates) {
        if (-not $pattern) { continue }
        $resolved = Resolve-Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($resolved -and (Test-Path $resolved)) {
            return $resolved.Path
        }
    }
    return $null
}

function Install-Winget {
    # Windows Server / LTSC 没有预装 winget，需要手动安装
    Write-Host "  winget not found, installing..." -ForegroundColor Yellow
    try {
        # 下载最新 winget release
        $apiUrl = 'https://api.github.com/repos/microsoft/winget-cli/releases/latest'
        $release = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
        $msixUrl = ($release.assets | Where-Object { $_.name -match '\.msixbundle$' } | Select-Object -First 1).browser_download_url
        $licUrl  = ($release.assets | Where-Object { $_.name -match 'License.*\.xml$' } | Select-Object -First 1).browser_download_url

        $tmpDir = Join-Path $env:TEMP 'winget-install'
        New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
        $msixPath = Join-Path $tmpDir 'winget.msixbundle'
        $licPath  = Join-Path $tmpDir 'license.xml'

        Invoke-WebRequest -Uri $msixUrl -OutFile $msixPath -UseBasicParsing
        Invoke-WebRequest -Uri $licUrl -OutFile $licPath -UseBasicParsing

        # 尝试系统级安装（需要管理员）
        try {
            Add-AppxProvisionedPackage -Online -PackagePath $msixPath -LicensePath $licPath -ErrorAction Stop | Out-Null
        } catch {
            # 备选：用户级安装
            Add-AppxPackage -Path $msixPath -ErrorAction Stop
        }

        Refresh-Path

        # Appx 安装后 winget 可能不在 PATH 中，手动查找并加入
        $wingetPath = Find-Winget
        if ($wingetPath) {
            $wingetDir = Split-Path $wingetPath
            if ($env:Path -notlike "*$wingetDir*") {
                $env:Path = "$wingetDir;$env:Path"
            }
            # 缓存完整路径，后续调用直接用，绕开 Alias
            $script:WingetExe = $wingetPath
            Write-OK "winget installed ($wingetPath)"
            return $true
        } else {
            Write-Warn "winget installed but could not locate executable. Please restart terminal and re-run."
            return $false
        }
    } catch {
        Write-Warn "Could not install winget automatically: $_"
        Write-Host "  Manual install: https://github.com/microsoft/winget-cli/releases" -ForegroundColor Yellow
        return $false
    }
}

function Refresh-Path {
    # 重新加载 PATH，让刚安装的程序立即可用
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
}

# ============================================================
# 主流程
# ============================================================

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $projectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   AGARS - One-Click Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project: $projectRoot"
Write-Host ""

$needsRestart = $false

# --------------------------------------------------
# Step 1: PowerShell 执行策略
# --------------------------------------------------
Write-Step "1/7" "Checking PowerShell execution policy..."

$policy = Get-ExecutionPolicy
if ($policy -eq 'Restricted') {
    try {
        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force -ErrorAction Stop
        Write-OK "Execution policy set to RemoteSigned"
    } catch {
        Write-Warn "Could not change execution policy (current: $policy). If the script is running, this is fine."
    }
} else {
    Write-Skip "Already set to $policy"
}

# --------------------------------------------------
# Step 1.5: Ensure winget is available
# --------------------------------------------------
if (-not (Test-Winget)) {
    Install-Winget
}

# --------------------------------------------------
# Step 2: Node.js
# --------------------------------------------------
Write-Step "2/7" "Checking Node.js..."

if (Test-Command 'node') {
    $nodeVer = (node --version 2>$null)
    Write-Skip "Node.js $nodeVer already installed"
} else {
    Write-Host "  Installing Node.js LTS..." -ForegroundColor Yellow
    $installed = Invoke-WingetInstall 'OpenJS.NodeJS.LTS'
    if (-not $installed) {
        # winget 失败（常见于 Windows Server），尝试直接下载 MSI
        $installed = Install-NodeDirect
    }
    if (-not $installed) {
        Write-Fail "Auto-install failed. Please install Node.js manually: https://nodejs.org/"
        Write-Host "  Press Enter to continue after manual install, or Ctrl+C to exit."
        Read-Host
    }
    Refresh-Path
    if (Test-Command 'node') {
        Write-OK "Node.js $(node --version) installed"
    } else {
        $needsRestart = $true
        Write-Warn "Node.js installed but not in PATH yet (will be available after terminal restart)"
    }
}

# --------------------------------------------------
# Step 3: Python
# --------------------------------------------------
Write-Step "3/7" "Checking Python..."

if (Test-Command 'python') {
    $pyVer = (python --version 2>$null)
    Write-Skip "$pyVer already installed"
} else {
    Write-Host "  Installing Python 3.12..." -ForegroundColor Yellow
    $installed = Invoke-WingetInstall 'Python.Python.3.12'
    if (-not $installed) {
        # winget 失败（常见于 Windows Server），尝试直接下载安装
        $installed = Install-PythonDirect
    }
    if (-not $installed) {
        Write-Fail "Auto-install failed. Please install Python manually: https://www.python.org/"
        Write-Host "  Press Enter to continue after manual install, or Ctrl+C to exit."
        Read-Host
    }
    Refresh-Path
    if (Test-Command 'python') {
        Write-OK "$(python --version) installed"
    } else {
        $needsRestart = $true
        Write-Warn "Python installed but not in PATH yet (will be available after terminal restart)"
    }
}

# --------------------------------------------------
# Step 4: uv (Python package manager)
# --------------------------------------------------
Write-Step "4/7" "Checking uv..."

if (Test-Command 'uv') {
    $uvVer = (uv --version 2>$null)
    Write-Skip "uv $uvVer already installed"
} else {
    Write-Host "  Installing uv..." -ForegroundColor Yellow
    try {
        irm https://astral.sh/uv/install.ps1 | iex
        Refresh-Path
        if (Test-Command 'uv') {
            Write-OK "uv $(uv --version) installed"
        } else {
            $needsRestart = $true
            Write-Warn "uv installed but not in PATH yet"
        }
    } catch {
        Write-Fail "Failed to install uv: $_"
        Write-Host "  Manual install: https://docs.astral.sh/uv/getting-started/installation/"
    }
}

# --------------------------------------------------
# Step 5: Docker Desktop
# --------------------------------------------------
Write-Step "5/7" "Checking Docker..."

if (Test-Command 'docker') {
    $dockerVer = (docker --version 2>$null)
    Write-Skip "$dockerVer already installed"
} else {
    Write-Host "  Installing Docker Desktop (may require admin privileges)..." -ForegroundColor Yellow
    $installed = Invoke-WingetInstall 'Docker.DockerDesktop'
    if ($installed) {
        $needsRestart = $true
        Write-OK "Docker Desktop installed. Please restart your computer and launch Docker Desktop."
    } else {
        Write-Fail "Auto-install failed. Please install Docker Desktop manually: https://www.docker.com/products/docker-desktop/"
        Write-Host "  Common causes:" -ForegroundColor Yellow
        Write-Host "    - Installation was cancelled or requires admin privileges"
        Write-Host "    - WSL2 or Hyper-V not enabled"
        Write-Host "  Press Enter to continue after manual install, or Ctrl+C to exit."
        Read-Host
    }
    Refresh-Path
}

# --------------------------------------------------
# 如果需要重启终端，提前提示
# --------------------------------------------------
if ($needsRestart) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Yellow
    Write-Host "  Some tools were just installed and may"     -ForegroundColor Yellow
    Write-Host "  not be in PATH yet. If the next steps"      -ForegroundColor Yellow
    Write-Host "  fail, please CLOSE this terminal, open"     -ForegroundColor Yellow
    Write-Host "  a new one, and re-run this script."         -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press Enter to continue, or Ctrl+C to exit and restart terminal first."
    Read-Host
    Refresh-Path
}

# --------------------------------------------------
# Step 6: Install project dependencies
# --------------------------------------------------
Write-Step "6/7" "Installing project dependencies (npm + uv)..."

try {
    # Root + frontend npm install
    Write-Host "  Running npm install..." -ForegroundColor Gray
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed in root" }

    Set-Location "$projectRoot\frontend"
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed in frontend" }
    Set-Location $projectRoot

    # Backend Python dependencies
    Write-Host "  Running uv sync (backend)..." -ForegroundColor Gray
    Set-Location "$projectRoot\backend"
    uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    Set-Location $projectRoot

    Write-OK "All dependencies installed"
} catch {
    Set-Location $projectRoot
    Write-Fail "Dependency install failed: $_"
    Write-Host "  You can retry manually: npm run setup:all" -ForegroundColor Yellow
}

# --------------------------------------------------
# Step 7: FalkorDB container
# --------------------------------------------------
Write-Step "7/7" "Setting up FalkorDB database..."

if (Test-Command 'docker') {
    try {
        $container = docker ps -a --filter "name=falkordb" --format "{{.Names}}" 2>$null
        if ($container -eq 'falkordb') {
            docker start falkordb 2>$null | Out-Null
            Write-Skip "FalkorDB container already exists, started"
        } else {
            Write-Host "  Pulling and starting FalkorDB..." -ForegroundColor Gray
            docker run -d --name falkordb -p 6379:6379 falkordb/falkordb
            if ($LASTEXITCODE -eq 0) {
                Write-OK "FalkorDB container created and running"
            } else {
                throw "docker run failed"
            }
        }
    } catch {
        Write-Fail "Failed to start FalkorDB: $_"
        Write-Host "  Make sure Docker Desktop is running, then run:" -ForegroundColor Yellow
        Write-Host "  docker run -d --name falkordb -p 6379:6379 falkordb/falkordb" -ForegroundColor Yellow
    }
} else {
    Write-Warn "Docker not available. After installing Docker Desktop and restarting, run:"
    Write-Host "  docker run -d --name falkordb -p 6379:6379 falkordb/falkordb" -ForegroundColor Yellow
}

# ============================================================
# Done
# ============================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Make sure Docker Desktop is running"
Write-Host "  2. Run the project:  " -NoNewline
Write-Host "npm run dev" -ForegroundColor Yellow
Write-Host "  3. Open browser:     " -NoNewline
Write-Host "http://localhost:5173" -ForegroundColor Yellow
Write-Host "  4. Go to Settings (top-right) to configure your API keys"
Write-Host ""
Write-Host "If you encounter issues, see README.md for details."
Write-Host ""

# 保持窗口打开（双击运行时）
if ($Host.Name -eq 'ConsoleHost') {
    Write-Host "Press any key to exit..." -ForegroundColor DarkGray
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
}
