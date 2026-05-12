@echo off
chcp 65001 >nul
title = 喵酱 Live2D Desktop Pet
cd /d "%~dp0"

echo.
echo ============================================
echo   喵酱 Live2D Desktop Pet
echo ============================================
echo.
echo   Available commands:
echo     start.bat                Start backend + pet
echo     start.bat pet            Start just pet (PySide6)
echo     start.bat electron       Start just pet (Electron)
echo     start.bat backend        Start just backend
echo     start.bat test           Run full test suite
echo     start.bat test fast      Run unit tests only
echo     start.bat status         Check services
echo     start.bat install        Install dependencies
echo.

python launcher.py %*
if %errorlevel% neq 0 (
    echo.
    pause
)
