@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   MindDock Demo Ingest
echo   Requires Local ASR Ready
echo ============================================
echo.

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "ASR_HOST=127.0.0.1"
set "ASR_PORT=9001"

echo [1/4] Checking backend...
curl.exe -s http://%BACKEND_HOST%:%BACKEND_PORT%/health >nul 2>nul
if !errorlevel! neq 0 (
    echo   [ERROR] MindDock backend is not running at http://%BACKEND_HOST%:%BACKEND_PORT%.
    echo   Run start.bat first and wait for Model Ready.
    pause
    exit /b 1
)
echo   [OK] Backend is running

echo.
echo [2/4] Checking Local ASR server...
curl.exe -s http://%ASR_HOST%:%ASR_PORT%/health >nul 2>nul
if !errorlevel! neq 0 (
    echo   [ERROR] Local ASR server is not running at http://%ASR_HOST%:%ASR_PORT%.
    echo   Run start.bat first and wait for Model Ready.
    pause
    exit /b 1
)
echo   [OK] Local ASR is running

echo.
echo [3/4] Checking Local ASR model status through backend...
set "MODEL_STATUS="
for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "try { (Invoke-RestMethod -Uri 'http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/model/status').status } catch { 'error' }"`) do set "MODEL_STATUS=%%S"
echo   Model status: !MODEL_STATUS!
if /i not "!MODEL_STATUS!"=="ready" (
    echo   [ERROR] Local ASR model is not Ready.
    echo   Run start.bat or use Settings to preload the model first.
    pause
    exit /b 1
)
echo   [OK] Model is Ready

echo.
echo [4/4] Ready to ingest.
echo.
echo Before continuing, make sure knowledge_base contains a valid wav/mp3/mp4 file
echo without a matching sidecar transcript. For the first smoke test, prefer wav/mp3.
echo This script does not create demo files and does not run video frame understanding.
echo.
choice /C YN /M "Run MindDock ingest now"
if errorlevel 2 (
    echo Ingest cancelled.
    exit /b 0
)

echo.
echo Running ingest...
cd /d "%ROOT_DIR%"
call conda activate minddock
if !errorlevel! neq 0 (
    echo   [ERROR] Failed to activate minddock environment.
    pause
    exit /b 1
)

python -m app.demo ingest
if !errorlevel! neq 0 (
    echo   [ERROR] Ingest failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Ingest complete
echo ============================================
echo.
echo Next checks:
echo   1. Open Source Drawer and confirm Transcript: local.
echo   2. Search for a phrase from the audio transcript.
echo   3. Ask a chat question about the ingested media.
echo   4. Confirm citations and derived transcript badges when derived chunks are enabled.
echo.
pause
endlocal
