<#
.SYNOPSIS
  简历优化助手 · 一键部署 & 启动脚本
.DESCRIPTION
  1. 检测 Python 环境
  2. 安装 / 更新项目依赖
  3. 检查 .env 配置文件
  4. 设置 HuggingFace 国内镜像（可选）
  5. 创建必要目录
  6. 启动 Streamlit 应用
.NOTES
  首次运行会自动引导配置 API Key。
  国内用户建议设置 HF_ENDPOINT 镜像加速 BGE 模型下载。
#>

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
Set-Location $projectRoot

# ══════════════════════════════════════════════════════════════
# 1. 横幅
# ══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    📄 简历优化助手 · 一键部署           ║" -ForegroundColor Cyan
Write-Host "║    Resume Optimizer v3.0                ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ══════════════════════════════════════════════════════════════
# 2. 检测 Python
# ══════════════════════════════════════════════════════════════
Write-Host "[1/5] 检测 Python 环境..." -ForegroundColor Yellow

$pythonCmd = $null
# 优先查找 python3，其次 python
foreach ($cmd in @("python3", "python")) {
    try {
        $v = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = $cmd
            Write-Host "  ✓ $v" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "  ✗ 未找到 Python，请先安装 Python 3.10+ " -ForegroundColor Red
    Write-Host "    下载地址: https://www.python.org/downloads/" -ForegroundColor Gray
    exit 1
}

# ══════════════════════════════════════════════════════════════
# 3. 安装 / 更新依赖
# ══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[2/5] 安装项目依赖..." -ForegroundColor Yellow

$reqFile = Join-Path $projectRoot "requirements_resume.txt"
if (-not (Test-Path $reqFile)) {
    Write-Host "  ✗ 未找到 requirements_resume.txt" -ForegroundColor Red
    exit 1
}

# 检测是否使用国内镜像
$useMirror = $false
try {
    $mirrorTest = & $pythonCmd -m pip config get global.index-url 2>$null
    if ($mirrorTest -match "tuna|aliyun|tencent|ustc|huaweicloud") {
        $useMirror = $true
        Write-Host "  ℹ 检测到国内 PyPI 镜像，将使用镜像加速" -ForegroundColor Gray
    }
} catch {}

& $pythonCmd -m pip install -r $reqFile --quiet --disable-pip-version-check

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ 依赖安装失败，尝试手动安装：" -ForegroundColor Red
    Write-Host "    pip install -r requirements_resume.txt" -ForegroundColor White
    exit 1
}
Write-Host "  ✓ 依赖安装完成" -ForegroundColor Green

# ══════════════════════════════════════════════════════════════
# 4. 检查 .env 配置
# ══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[3/5] 检查配置文件..." -ForegroundColor Yellow

$envFile = Join-Path $projectRoot ".env"

if (-not (Test-Path $envFile)) {
    Write-Host "  ⚠ 未找到 .env 文件，正在从模板创建..." -ForegroundColor DarkYellow

    $envContent = @'
# 简历优化助手 · 环境变量配置
# 请将下面 sk-xxx 替换为你的真实 API Key

DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
HF_ENDPOINT=https://hf-mirror.com
LLM_PROVIDER=deepseek
'@
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Write-Host "  ✓ 已创建 .env 模板文件" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor DarkYellow
    Write-Host "  ║  ⚠ 请先编辑 .env 文件，填入你的 DeepSeek API Key ║" -ForegroundColor DarkYellow
    Write-Host "  ║    文件位置: $envFile" -ForegroundColor DarkYellow
    Write-Host "  ║    获取 Key: https://platform.deepseek.com          ║" -ForegroundColor DarkYellow
    Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor DarkYellow
    Write-Host ""
    $answer = Read-Host "  是否已配置好 API Key？(y/n)"
    if ($answer -ne "y") {
        Write-Host "  请配置好后再运行本脚本。" -ForegroundColor Gray
        exit 0
    }
}

# 读取并验证
try {
    $envContent = Get-Content $envFile -Encoding UTF8 -Raw
    if ($envContent -match "sk-your-deepseek-api-key-here") {
        Write-Host "  ⚠ 检测到 .env 中仍为示例 Key，请修改为真实 API Key" -ForegroundColor DarkYellow
        Write-Host "    文件: $envFile" -ForegroundColor Gray
    } else {
        Write-Host "  ✓ .env 配置文件已就绪" -ForegroundColor Green
    }
} catch {
    Write-Host "  ⚠ 无法读取 .env 文件，将使用系统环境变量" -ForegroundColor DarkYellow
}

# ══════════════════════════════════════════════════════════════
# 5. 设置 HF 镜像 + 创建目录
# ══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[4/5] 初始化运行环境..." -ForegroundColor Yellow

# 设置 HuggingFace 镜像（国内加速下载 BGE 模型）
$env:HF_ENDPOINT = "https://hf-mirror.com"
Write-Host "  ✓ HF_ENDPOINT 已设置为 hf-mirror.com（国内镜像）" -ForegroundColor Green

# 确保必要目录存在
$dirsToCreate = @(
    (Join-Path $projectRoot "data"),
    (Join-Path $projectRoot "data\logs"),
    (Join-Path $projectRoot "chroma_db")
)
foreach ($dir in $dirsToCreate) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
}
Write-Host "  ✓ 工作目录已就绪" -ForegroundColor Green

# ══════════════════════════════════════════════════════════════
# 6. 启动 Streamlit
# ══════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[5/5] 启动 Streamlit 应用..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  🌐 应用将在浏览器中自动打开" -ForegroundColor Cyan
Write-Host "  📍 本地地址: http://localhost:8501" -ForegroundColor Cyan
Write-Host "  🛑 按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""

# 构建启动命令
$appFile = Join-Path $projectRoot "resume_optimizer.py"

if (-not (Test-Path $appFile)) {
    Write-Host "  ✗ 未找到 resume_optimizer.py" -ForegroundColor Red
    exit 1
}

# 启动（不自动打开浏览器）
& $pythonCmd -m streamlit run $appFile --server.headless true

Write-Host ""
Write-Host "  应用已停止。" -ForegroundColor Gray
Write-Host ""
