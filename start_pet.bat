@echo off
chcp 65001 >nul
title = 喵酱 Live2D Desktop Pet =
cd /d "%~dp0"

echo.
echo ============================================
echo   喵酱 Live2D Desktop Pet
echo ============================================
echo.

:: Check node_modules
if not exist "node_modules\" (
    echo [*] Installing Electron...
    call npm install
)

:: Check backend
echo [*] Checking backend...
curl -s -o nul http://localhost:12393 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Backend not running, starting...
    cd /d "%~dp0..\Open-LLM-VTuber"
    start "喵酱 Backend" /min cmd /c "set NO_PROXY=localhost,127.0.0.1,::1,.local && set no_proxy=localhost,127.0.0.1,::1,.local && uv run run_server.py"
    cd /d "%~dp0"
    timeout /t 8 /nobreak >nul
) else (
    echo [OK] Backend running on http://localhost:12393
)

echo [*] Launching Live2D Pet...
echo.
echo   ╔══════════════════════════════════╗
echo   ║  Ctrl+Shift+Space  快捷聊天     ║
echo   ║  Ctrl+Shift+H      显示/隐藏    ║
echo   ║  Ctrl+Shift+T      穿透开关    ║
echo   ║  右键托盘          完整菜单     ║
echo   ╚══════════════════════════════════╝
echo.

npx electron .

