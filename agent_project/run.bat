@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 🧹 清理 Python 缓存…
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

set PYTHONDONTWRITEBYTECODE=1

echo 🚀 启动简历优化 Agent…
echo    浏览器访问：http://localhost:8502
echo    停止：Ctrl+C 然后关窗口
echo.

python -m streamlit run app.py --server.port 8502
pause
