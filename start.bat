@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   MindDock One-click Startup
echo   Local ASR + Backend + Frontend + Preload
echo ============================================
echo.

:: =========================
:: Config
:: =========================
set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "FRONTEND_HOST=127.0.0.1"
set "FRONTEND_PORT=3000"

set "ENABLE_LOCAL_ASR=1"
set "ASR_ENV=local-asr"
set "ASR_HOST=127.0.0.1"
set "ASR_PORT=9001"
set "ASR_MODEL=base"
set "ASR_DEVICE=auto"
set "ASR_COMPUTE=int8"
set "ASR_TIMEOUT=120"
set "ASR_DIR=%ROOT_DIR%\tools\local_asr_server"

:: Local faster-whisper model path override
set "LOCAL_ASR_MODEL_BASE_PATH=D:\models\faster-whisper-base"

:: Whether to build frontend before dev server: 1=yes, 0=no
set "BUILD_FRONTEND=0"

echo Project root:
echo   %ROOT_DIR%
echo.

:: =========================
:: Check conda envs
:: =========================
echo [1/9] Checking conda environments...

conda env list | findstr /i "minddock" >nul
if %errorlevel% neq 0 (
    echo   [ERROR] minddock environment not found.
    echo   Run: conda env create -f environment.yml
    pause
    exit /b 1
)
echo   [OK] minddock environment found

if "%ENABLE_LOCAL_ASR%"=="1" (
    conda env list | findstr /i "%ASR_ENV%" >nul
    if !errorlevel! neq 0 (
        echo   [ERROR] %ASR_ENV% environment not found.
        echo   Please create it first:
        echo   conda create -n local-asr python=3.10 -y
        echo   conda activate local-asr
        echo   pip install -r "%ASR_DIR%\requirements.txt"
        pause
        exit /b 1
    )
    echo   [OK] %ASR_ENV% environment found
)

:: =========================
:: Check local ASR files and deps
:: =========================
echo.
echo [2/9] Checking Local ASR files and model...

if "%ENABLE_LOCAL_ASR%"=="1" (
    if not exist "%ASR_DIR%\server.py" (
        echo   [ERROR] Local ASR server.py not found:
        echo   %ASR_DIR%\server.py
        pause
        exit /b 1
    )
    echo   [OK] Local ASR server found

    conda run -n %ASR_ENV% python -c "import faster_whisper; print('faster-whisper ok')" >nul 2>nul
    if !errorlevel! neq 0 (
        echo   [ERROR] faster-whisper is not installed in %ASR_ENV%.
        echo   Run:
        echo   conda activate %ASR_ENV%
        echo   pip install -r "%ASR_DIR%\requirements.txt"
        pause
        exit /b 1
    )
    echo   [OK] faster-whisper import ok

    if not exist "%LOCAL_ASR_MODEL_BASE_PATH%\model.bin" (
        echo   [WARN] Local base model not found or incomplete:
        echo   %LOCAL_ASR_MODEL_BASE_PATH%
        echo.
        echo   Expected at least:
        echo   - config.json
        echo   - model.bin
        echo   - tokenizer.json
        echo   - vocabulary.txt
        echo.
        echo   Preload may try to download the model if no valid local path is found.
        echo.
    ) else (
        echo   [OK] Local faster-whisper base model found
    )
)

:: =========================
:: Start Local ASR server
:: =========================
echo.
echo [3/9] Starting Local ASR server...

if "%ENABLE_LOCAL_ASR%"=="1" (
    curl.exe -s http://%ASR_HOST%:%ASR_PORT%/health >nul 2>nul
    if !errorlevel! equ 0 (
        echo   [OK] Local ASR already running at http://%ASR_HOST%:%ASR_PORT%
    ) else (
        echo   Starting Local ASR at http://%ASR_HOST%:%ASR_PORT% ...
        start "MindDock-Local-ASR" cmd /k "chcp 65001 >nul && set ""LOCAL_ASR_MODEL_BASE_PATH=%LOCAL_ASR_MODEL_BASE_PATH%"" && cd /d ""%ASR_DIR%"" && call conda activate %ASR_ENV% && uvicorn server:app --host %ASR_HOST% --port %ASR_PORT%"
        timeout /t 5 /nobreak >nul

        curl.exe -s http://%ASR_HOST%:%ASR_PORT%/health >nul 2>nul
        if !errorlevel! equ 0 (
            echo   [OK] Local ASR started
        ) else (
            echo   [WARN] Local ASR may still be starting.
            echo   Waiting a bit more...
            timeout /t 5 /nobreak >nul
            curl.exe -s http://%ASR_HOST%:%ASR_PORT%/health >nul 2>nul
            if !errorlevel! neq 0 (
                echo   [ERROR] Local ASR did not become ready at http://%ASR_HOST%:%ASR_PORT%/health.
                echo   Check the MindDock-Local-ASR window and fix it before continuing.
                pause
                exit /b 1
            )
            echo   [OK] Local ASR started
        )
    )
) else (
    echo   [SKIP] Local ASR disabled
)

:: =========================
:: Start backend
:: =========================
echo.
echo [4/9] Starting MindDock backend...

curl.exe -s http://%BACKEND_HOST%:%BACKEND_PORT%/health >nul 2>nul
if !errorlevel! equ 0 (
    echo   [OK] Backend already running at http://%BACKEND_HOST%:%BACKEND_PORT%
) else (
    start "MindDock-Backend" cmd /k "chcp 65001 >nul && cd /d ""%ROOT_DIR%"" && call conda activate minddock && python -m app.demo serve --port %BACKEND_PORT%"
)

:: Wait for backend health
echo   Waiting for backend /health...
set /a BACKEND_WAIT=0
:WAIT_BACKEND
curl.exe -s http://%BACKEND_HOST%:%BACKEND_PORT%/health >nul 2>nul
if !errorlevel! equ 0 (
    echo   [OK] Backend is ready
    goto BACKEND_READY
)
set /a BACKEND_WAIT+=1
if !BACKEND_WAIT! geq 30 (
    echo   [ERROR] Backend did not become ready within timeout.
    echo   Stop here to avoid a false-success demo startup.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto WAIT_BACKEND

:BACKEND_READY

:: =========================
:: Auto-save Local ASR config
:: =========================
echo.
echo [5/9] Saving Local ASR provider config to backend...

set "CONFIG_JSON=%TEMP%\minddock_local_asr_config.json"

(
echo {
echo   "provider": "local",
echo   "enabled": true,
echo   "base_url": "",
echo   "api_key": "",
echo   "model": "whisper-1",
echo   "timeout_seconds": %ASR_TIMEOUT%,
echo   "local_asr_server_path": "%ASR_DIR:\=\\%",
echo   "local_asr_host": "%ASR_HOST%",
echo   "local_asr_port": %ASR_PORT%,
echo   "local_asr_model": "%ASR_MODEL%",
echo   "local_asr_device": "%ASR_DEVICE%",
echo   "local_asr_compute_type": "%ASR_COMPUTE%",
echo   "local_asr_auto_start": true,
echo   "local_asr_timeout_seconds": %ASR_TIMEOUT%
echo }
) > "%CONFIG_JSON%"

curl.exe -fsS -X PUT "http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config" ^
  -H "Content-Type: application/json" ^
  --data-binary "@%CONFIG_JSON%" >nul

if !errorlevel! equ 0 (
    echo   [OK] Local ASR config saved
) else (
    echo   [ERROR] Failed to save Local ASR config.
    del "%CONFIG_JSON%" >nul 2>nul
    pause
    exit /b 1
)

del "%CONFIG_JSON%" >nul 2>nul

:: =========================
:: Start/check ASR via backend + preload model
:: =========================
echo.
echo [6/9] Starting/checking Local ASR through backend...

curl.exe -fsS -X POST "http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/start" >nul 2>nul
if !errorlevel! neq 0 (
    echo   [ERROR] Backend failed to start/check Local ASR.
    pause
    exit /b 1
)

echo   Checking Local ASR status...
curl.exe -s "http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/status"
echo.

echo.
echo   Triggering model preload: %ASR_MODEL% / %ASR_DEVICE% / %ASR_COMPUTE% ...
curl.exe -s -X POST "http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/model/preload" ^
  -H "Content-Type: application/json" ^
  -d "{}"
echo.

echo.
echo   Waiting for model Ready status...
set /a MODEL_WAIT=0
set "MODEL_STATUS="

:WAIT_MODEL
for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "try { (Invoke-RestMethod -Uri 'http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/model/status').status } catch { 'error' }"`) do set "MODEL_STATUS=%%S"

echo   Model status: !MODEL_STATUS!

if /i "!MODEL_STATUS!"=="ready" (
    echo   [OK] Local ASR model is Ready
    goto MODEL_READY
)

if /i "!MODEL_STATUS!"=="failed" (
    echo   [ERROR] Model preload failed. Check MindDock-Local-ASR window.
    pause
    exit /b 1
)

set /a MODEL_WAIT+=1
if !MODEL_WAIT! geq 60 (
    echo   [ERROR] Model did not become Ready within timeout.
    echo   Stop here to avoid a false-success demo startup.
    pause
    exit /b 1
)

timeout /t 5 /nobreak >nul
goto WAIT_MODEL

:MODEL_READY

:: =========================
:: Build frontend
:: =========================
echo.
echo [7/9] Building frontend...

cd /d "%ROOT_DIR%\frontend"

if "%BUILD_FRONTEND%"=="1" (
    call pnpm build
    if !errorlevel! neq 0 (
        echo.
        echo   [ERROR] Frontend build failed.
        echo   Please check the error messages above.
        pause
        exit /b 1
    )
    echo   [OK] Frontend build completed
) else (
    echo   [SKIP] Frontend build skipped
)

:: =========================
:: Start frontend
:: =========================
echo.
echo [8/9] Starting frontend dev server...

curl.exe -s http://%FRONTEND_HOST%:%FRONTEND_PORT% >nul 2>nul
if !errorlevel! equ 0 (
    echo   [OK] Frontend already running at http://%FRONTEND_HOST%:%FRONTEND_PORT%
) else (
    start "MindDock-Frontend" cmd /k "chcp 65001 >nul && cd /d ""%ROOT_DIR%\frontend"" && pnpm dev --host %FRONTEND_HOST% --port %FRONTEND_PORT%"
)

timeout /t 3 /nobreak >nul

:: =========================
:: Done
:: =========================
echo.
echo [9/9] Done!
echo.
echo   Local ASR:   http://%ASR_HOST%:%ASR_PORT%
echo   Backend API: http://localhost:%BACKEND_PORT%
echo   Frontend:    http://localhost:%FRONTEND_PORT%
echo   API Docs:    http://localhost:%BACKEND_PORT%/docs
echo.
echo Frontend should now be directly usable:
echo   Provider: Local ASR
echo   Model: %ASR_MODEL%
echo   Device: %ASR_DEVICE%
echo   Compute Type: %ASR_COMPUTE%
echo   Model Status should be Ready if preload succeeded.
echo.
echo Next manual step for real validation:
echo   Put a valid wav/mp3/mp4 without sidecar into knowledge_base
echo   Then run:
echo   conda activate minddock
echo   python -m app.demo ingest
echo.
echo ============================================
echo   Press any key to open browser...
echo ============================================

pause >nul
start http://localhost:%FRONTEND_PORT%

endlocal
