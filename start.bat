@echo off
chcp 65001 >nul
echo ============================================
echo   MindDock Startup (Backend + Frontend)
echo ============================================
echo.

:: Check conda environment
echo [1/5] Checking conda environment...
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
set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

:: Start backend
echo.
echo [2/5] Starting backend (http://localhost:8000)...
start "MindDock-Backend" cmd /k "cd /d "%ROOT_DIR%" && python -m app.demo serve"
timeout /t 3 /nobreak >nul

:: Build frontend
echo.
echo [3/5] Building frontend...
cd /d "%ROOT_DIR%\frontend"

call pnpm build
if %errorlevel% neq 0 (
    echo.
    echo   [ERROR] Frontend build failed.
    echo   Please check the error messages above.
    pause
    exit /b 1
)
echo   [OK] Frontend build completed

:: Start frontend dev server
echo.
echo [4/5] Starting frontend dev server (http://localhost:3000)...
start "MindDock-Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && pnpm dev"

echo.
echo [5/5] Done!
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