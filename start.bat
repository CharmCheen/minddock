@echo off
chcp 65001 >nul
echo ============================================
echo   MindDock Startup (Backend + Frontend)
echo ============================================
echo.

:: Check conda environment
echo [1/4] Checking conda environment...
conda env list | findstr /i "minddock" >nul
if %errorlevel% neq 0 (
    echo   [ERROR] minddock environment not found.
    echo   Run: conda env create -f environment.yml
    echo   Then: conda activate minddock
    pause
    exit /b 1
)
echo   [OK] minddock environment found

:: Activate conda environment
call conda activate minddock

:: Get current directory
set ROOT_DIR=%~dp0
set ROOT_DIR=%ROOT_DIR:~0,-1%

:: Start backend (background)
echo.
echo [2/4] Starting backend (http://localhost:8000)...
start "MindDock-Backend" cmd /k "cd /d "%ROOT_DIR%" && python -m app.demo serve"
timeout /t 3 /nobreak >nul

:: Start frontend
echo.
echo [3/4] Starting frontend (http://localhost:3000)...
start "MindDock-Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && pnpm dev"

echo.
echo [4/4] Done!
echo.
echo   Backend API: http://localhost:8000
echo   Frontend:    http://localhost:3000
echo   API Docs:    http://localhost:8000/docs
echo.
echo ============================================
echo   Press any key to open browser...
echo ============================================
pause >nul
start http://localhost:3000
