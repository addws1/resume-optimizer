# 简历优化 Agent v2.0 · PowerShell 启动脚本
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "🧹 清理 Python 缓存…"
Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

$env:PYTHONDONTWRITEBYTECODE = "1"

Write-Host "🚀 启动简历优化 Agent…"
Write-Host "   浏览器访问：http://localhost:8502"
Write-Host "   停止：Ctrl+C"
Write-Host ""

python -m streamlit run app.py --server.port 8502
