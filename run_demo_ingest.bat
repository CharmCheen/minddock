@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "ASR_HOST=127.0.0.1"
set "ASR_PORT=9001"
set "LOG_DIR=%ROOT_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\demo_ingest.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul
(
  echo ============================================
  echo MindDock demo ingest log
  echo Time: %DATE% %TIME%
  echo Root: %ROOT_DIR%
  echo ============================================
) > "%LOG_FILE%"

echo ============================================
echo   MindDock Demo Ingest
echo   Requires Local ASR Ready
echo ============================================
echo.
echo Log:
echo   %LOG_FILE%
echo.

echo [1/4] Checking backend /health...
curl.exe -fsS --max-time 2 "http://%BACKEND_HOST%:%BACKEND_PORT%/health" >nul 2>> "%LOG_FILE%"
if errorlevel 1 goto FAIL_BACKEND
echo   [OK] Backend is running

echo.
echo [2/4] Checking Local ASR /health...
curl.exe -fsS --max-time 2 "http://%ASR_HOST%:%ASR_PORT%/health" >nul 2>> "%LOG_FILE%"
if errorlevel 1 goto FAIL_ASR
echo   [OK] Local ASR is running

echo.
echo [3/4] Checking backend model status...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Uri 'http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/model/status'; $r | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $env:TEMP\minddock_ingest_model_status.json -Encoding UTF8; $r.status } catch { 'error' }" > "%TEMP%\minddock_ingest_model_status.txt" 2>> "%LOG_FILE%"
set /p MODEL_STATUS=<"%TEMP%\minddock_ingest_model_status.txt"
type "%TEMP%\minddock_ingest_model_status.json" >> "%LOG_FILE%" 2>&1
echo   Model status: %MODEL_STATUS%
if /i not "%MODEL_STATUS%"=="ready" goto FAIL_MODEL
echo   [OK] Model is Ready

echo.
echo [4/4] Confirm real ingest input.
echo.
echo Before continuing, make sure:
echo   1. knowledge_base contains a valid wav/mp3/mp4 file.
echo   2. The file has no same-name sidecar:
echo      .transcript.md / .transcript.txt / .txt / .srt / .vtt
echo   3. For the first smoke test, prefer wav/mp3; use mp4 after audio passes.
echo.
choice /C YN /M "Run real MindDock ingest now"
if errorlevel 2 (
  echo Ingest cancelled.
  exit /b 0
)

echo.
echo Running ingest...
cd /d "%ROOT_DIR%"
call conda activate minddock >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_CONDA

python -m app.demo ingest
if errorlevel 1 goto FAIL_INGEST

echo.
echo ============================================
echo   Ingest complete
echo ============================================
echo.
echo Check the frontend:
echo   Source Drawer
echo   Transcript: local
echo   Summary / Outline
echo   search
echo   chat
echo   citation derived badge
echo.
pause
exit /b 0

:FAIL_BACKEND
echo.
echo [ERROR] MindDock backend is not running at http://%BACKEND_HOST%:%BACKEND_PORT%.
echo Run start.bat first and wait for Model Ready.
goto FAIL_COMMON

:FAIL_ASR
echo.
echo [ERROR] Local ASR server is not running at http://%ASR_HOST%:%ASR_PORT%.
echo Run start.bat first and wait for Model Ready.
goto FAIL_COMMON

:FAIL_MODEL
echo.
echo [ERROR] Local ASR model is not Ready.
echo Run start.bat first and wait for Model Ready.
goto FAIL_COMMON

:FAIL_CONDA
echo.
echo [ERROR] Failed to activate minddock environment.
goto FAIL_COMMON

:FAIL_INGEST
echo.
echo [ERROR] Ingest failed. Check the output above and log file.
goto FAIL_COMMON

:FAIL_COMMON
echo.
echo See log:
echo   %LOG_FILE%
echo.
pause
exit /b 1
