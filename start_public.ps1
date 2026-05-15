# 公网部署一键启动：Flask（隐藏窗口，PID 可控）+ cpolar 隧道 + 公网 URL 提取。
#
# 用法：
#   .\start_public.ps1
#
# 前置：
#   1. 已 `cd frontend; npm run build`（dist 存在）
#   2. 已 `Copy-Item .env.example .env` 并填入真实 token（含 KB_TRUST_PROXY=1）
#   3. 已 `pip install -r requirements.txt`
#   4. 已注册 cpolar 账号并跑过 `cpolar authtoken <你的token>`
#
# Ctrl+C 或任一子进程退出时自动收尾 Flask 与 cpolar。

$ErrorActionPreference = 'Stop'

# PowerShell 5.1 在 Ctrl+C 时直接终止脚本，不执行 try/finally → 子进程残留。
# PS7+ 才能可靠运行清理逻辑。检测 + 拒绝跑在 5.x。
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Error "需要 PowerShell 7+（当前 $($PSVersionTable.PSVersion)）；PS5.1 下 Ctrl+C 不触发 finally，子进程会残留。安装：winget install Microsoft.PowerShell，然后用 pwsh 启动本脚本。"
    exit 1
}

# ---------- 0. 路径与外部依赖检查 ----------

. (Join-Path $PSScriptRoot 'scripts\Load-DotEnv.ps1')

$cpolarExe = 'C:\Program Files\cpolar\cpolar.exe'
if (-not (Test-Path $cpolarExe)) {
    Write-Error "cpolar 未安装：$cpolarExe 不存在。注册并下载：https://www.cpolar.com/"
    exit 1
}

$envPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path $envPath)) {
    Write-Error ".env 不存在。请先 Copy-Item .env.example .env 并填入真实 token。"
    exit 1
}

$py = '<home>\anaconda3\envs\kb\python.exe'
if (-not (Test-Path $py)) {
    Write-Error "未找到 kb 环境 Python：$py"
    exit 1
}

$serve = Join-Path $PSScriptRoot 'scripts\serve.py'
if (-not (Test-Path $serve)) {
    Write-Error "找不到 scripts\serve.py"
    exit 1
}

$dist = Join-Path $PSScriptRoot 'frontend\dist\index.html'
if (-not (Test-Path $dist)) {
    Write-Error "frontend/dist 不存在，请先 cd frontend && npm run build"
    exit 1
}

# ---------- 1. 加载 .env ----------

Import-DotEnv -Path $envPath
Assert-EnvRequired -Keys @('KB_API_TOKEN', 'KB_SECRET_KEY', 'KB_TRUST_PROXY') `
    -Placeholders @('REPLACE_ME_USER_TOKEN', 'REPLACE_ME_SECRET_KEY') `
    -SecretKeys @('KB_API_TOKEN', 'KB_SECRET_KEY')

# ---------- 2. 全局变量与清理函数（必须在启动子进程之前定义，保证 try/finally 覆盖）----------

$script:flaskProc = $null
$script:cpolarProc = $null

function Stop-ChildIfAlive($p) {
    if ($p -and -not $p.HasExited) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { }
        # 简单等待，确认确实退出（避免后续脚本残留进程）
        for ($i = 0; $i -lt 10; $i++) {
            if ($p.HasExited) { break }
            Start-Sleep -Milliseconds 200
        }
    }
}

$flaskLog = Join-Path $PSScriptRoot 'flask_public.log'
$cpolarLog = Join-Path $PSScriptRoot 'cpolar.log'

try {
    # ---------- 3. 启动 Flask 并用 /health 探测就绪（不仅看端口）----------

    Write-Host '[1/3] 启动 Flask...' -ForegroundColor Cyan
    $script:flaskProc = Start-Process $py `
        -ArgumentList $serve `
        -WorkingDirectory $PSScriptRoot `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $flaskLog `
        -RedirectStandardError "$flaskLog.err"

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if ($script:flaskProc.HasExited) {
            throw "Flask 启动失败。日志：$flaskLog / $flaskLog.err"
        }
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/health' -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($r.StatusCode -eq 200 -and $r.Content -match '"ok"\s*:\s*true') {
                $ready = $true; break
            }
        } catch { }
    }
    if (-not $ready) {
        throw "Flask 在 30 秒内 /health 未返回 200，查看 $flaskLog"
    }
    Write-Host "      Flask 就绪（PID=$($script:flaskProc.Id), 日志=$flaskLog）" -ForegroundColor Green

    # ---------- 4. 启动 cpolar ----------

    Write-Host '[2/3] 启动 cpolar 隧道...' -ForegroundColor Cyan
    $script:cpolarProc = Start-Process $cpolarExe `
        -ArgumentList 'http', '5000' `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $cpolarLog `
        -RedirectStandardError "$cpolarLog.err"

    # 先用 Get-NetTCPConnection 筛出 cpolar 实际在监听的端口，再去抓 URL；
    # 比对 4040..4045 全量重试 HTTP 高效得多
    $dashboardPort = $null
    $publicUrl = $null
    # cpolar 公网域名会随服务端调度变化（.cpolar.cn / .cpolar.top / .cpolar.io 等），
    # 用宽松正则匹配多种顶级域，避免脚本因后缀变更误报失败
    $urlRegex = 'https://[a-zA-Z0-9.-]+\.cpolar\.[a-z]+'
    # 总超时用 stopwatch 控制，避免 fallback 端口（4040..4045）每轮全扫导致
    # 最坏 90 × 6 × 1s 累加（实测可达 540s）远超用户感知的 90s
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $maxSeconds = 90
    while ($sw.Elapsed.TotalSeconds -lt $maxSeconds) {
        Start-Sleep -Seconds 1
        if ($script:cpolarProc.HasExited) {
            throw "cpolar 进程已退出。日志：$cpolarLog / $cpolarLog.err"
        }
        # 优先使用 Get-NetTCPConnection 拿真实监听端口（精确、O(1) 候选）
        $candidates = @()
        try {
            $candidates = Get-NetTCPConnection -State Listen -OwningProcess $script:cpolarProc.Id -ErrorAction Stop |
                Where-Object { $_.LocalPort -ge 4040 -and $_.LocalPort -lt 4060 } |
                Select-Object -ExpandProperty LocalPort -Unique
        } catch {
            # 权限不足等场景才走 fallback；这里只试 4040 一个最常用端口，
            # 不要把 4040..4045 全 6 个端口都试（防累加超时）
            $candidates = @(4040)
        }
        foreach ($p in $candidates) {
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$p/http/in" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
                $m = [regex]::Match($resp.Content, $urlRegex)
                if ($m.Success) {
                    $dashboardPort = $p
                    $publicUrl = $m.Value
                    break
                }
            } catch { }
        }
        if ($publicUrl) { break }
    }
    $sw.Stop()

    if (-not $publicUrl) {
        throw '无法从 cpolar dashboard 抓取公网 URL；可能 authtoken 未配置或网络异常。'
    }

    # ---------- 5. 完成 ----------

    Write-Host ''
    Write-Host '[3/3] 部署完成' -ForegroundColor Green
    Write-Host ('=' * 60) -ForegroundColor DarkGray
    Write-Host "  公网入口: $publicUrl" -ForegroundColor Yellow
    Write-Host "  本地入口: http://127.0.0.1:5000" -ForegroundColor DarkGray
    Write-Host "  cpolar 控制台: http://127.0.0.1:$dashboardPort" -ForegroundColor DarkGray
    Write-Host "  Flask 日志: $flaskLog" -ForegroundColor DarkGray
    Write-Host "  cpolar 日志: $cpolarLog" -ForegroundColor DarkGray
    Write-Host ('=' * 60) -ForegroundColor DarkGray
    Write-Host ''
    Write-Host '本窗口保持开启以维持隧道。Ctrl+C 或任一子进程退出会自动清理。' -ForegroundColor Cyan

    # ---------- 6. 主循环 ----------

    while ($true) {
        Start-Sleep -Seconds 2
        if ($script:cpolarProc.HasExited) {
            Write-Host ''; Write-Host 'cpolar 已退出，关闭 Flask...' -ForegroundColor Yellow
            break
        }
        if ($script:flaskProc.HasExited) {
            Write-Host ''; Write-Host 'Flask 已退出，关闭 cpolar...' -ForegroundColor Yellow
            break
        }
    }
}
finally {
    # 即使 Flask/cpolar 启动到主循环之间按 Ctrl+C 或抛异常，也会执行清理
    Stop-ChildIfAlive $script:cpolarProc
    Stop-ChildIfAlive $script:flaskProc
    Write-Host '已退出。' -ForegroundColor Green
}
