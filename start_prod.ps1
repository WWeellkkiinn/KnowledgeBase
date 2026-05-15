# 公网部署启动脚本：加载 .env → 启动 Flask（同源托管前端 dist + API + Socket.IO）。
#
# 用法（PowerShell）：
#   .\start_prod.ps1
#
# 前置：
#   1. 已运行 `npm run build`（frontend/dist 必须存在）
#   2. 已从 .env.example 复制出 .env 并填入真实 token
#   3. 已 pip install -r requirements.txt（含 flask-limiter）

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'scripts\Load-DotEnv.ps1')

$envPath = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path $envPath)) {
    Write-Error ".env 不存在。请先 Copy-Item .env.example .env 并填入真实 token。"
    exit 1
}

Import-DotEnv -Path $envPath
Assert-EnvRequired -Keys @('KB_API_TOKEN', 'KB_SECRET_KEY', 'KB_TRUST_PROXY') `
    -Placeholders @('REPLACE_ME_USER_TOKEN', 'REPLACE_ME_SECRET_KEY') `
    -SecretKeys @('KB_API_TOKEN', 'KB_SECRET_KEY')

# 前端产物检查
$dist = Join-Path $PSScriptRoot 'frontend\dist\index.html'
if (-not (Test-Path $dist)) {
    Write-Error "frontend/dist 不存在，请先 cd frontend && npm run build"
    exit 1
}

# 启动 Flask（用 kb 环境的完整 Python 路径，避免依赖 conda activate）
$py = '<home>\anaconda3\envs\kb\python.exe'
if (-not (Test-Path $py)) {
    Write-Error "未找到 kb 环境 Python：$py"
    exit 1
}

Write-Host '启动 KnowledgeBase（公网部署模式）...' -ForegroundColor Cyan
Write-Host "  KB_TRUST_PROXY=$env:KB_TRUST_PROXY"
Write-Host '  监听 127.0.0.1:5000；公网入口由 .\start_public.ps1 提供（cpolar 隧道）'
Write-Host ''

& $py (Join-Path $PSScriptRoot 'scripts\serve.py')
