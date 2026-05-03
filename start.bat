@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "LOG_DIR=%ROOT_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\startup.log"

set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "FRONTEND_HOST=127.0.0.1"
set "FRONTEND_PORT=3000"

set "MINDDOCK_ENV=minddock"
set "ASR_ENV=local-asr"
set "ASR_HOST=127.0.0.1"
set "ASR_PORT=9001"
set "ASR_MODEL=base"
set "ASR_DEVICE=auto"
set "ASR_COMPUTE=int8"
set "ASR_TIMEOUT=120"
set "ASR_DIR=%ROOT_DIR%\tools\local_asr_server"
set "LOCAL_ASR_MODEL_BASE_PATH=%ROOT_DIR%\models\faster-whisper-base"
set "BUILD_FRONTEND=0"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul
(
  echo ============================================
  echo MindDock startup log
  echo Time: %DATE% %TIME%
  echo Root: %ROOT_DIR%
  echo ============================================
) > "%LOG_FILE%"

echo ============================================
echo   MindDock One-click Startup
echo   Local ASR + Backend + Frontend + Preload
echo ============================================
echo.
echo Project root:
echo   %ROOT_DIR%
echo Log:
echo   %LOG_FILE%
echo.

echo [1/9] Checking conda environments...
call conda env list >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_CONDA_LIST

call conda env list | findstr /i "%MINDDOCK_ENV%" >nul
if errorlevel 1 goto FAIL_MINDDOCK_ENV
echo   [OK] minddock environment found

call conda env list | findstr /i "%ASR_ENV%" >nul
if errorlevel 1 goto FAIL_ASR_ENV
echo   [OK] local-asr environment found

echo.
echo [2/9] Checking Local ASR server, faster-whisper import, and model files...
if not exist "%ASR_DIR%\server.py" goto FAIL_ASR_SERVER

echo   Checking faster-whisper import in %ASR_ENV%...
call conda run -n %ASR_ENV% python -c "import sys; print(sys.executable); import faster_whisper; print('faster-whisper ok')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_FASTER_WHISPER
echo   [OK] faster-whisper import ok

if not exist "%LOCAL_ASR_MODEL_BASE_PATH%\model.bin" goto FAIL_MODEL_FILES
if not exist "%LOCAL_ASR_MODEL_BASE_PATH%\config.json" goto FAIL_MODEL_FILES
if not exist "%LOCAL_ASR_MODEL_BASE_PATH%\tokenizer.json" goto FAIL_MODEL_FILES
if not exist "%LOCAL_ASR_MODEL_BASE_PATH%\vocabulary.txt" goto FAIL_MODEL_FILES
echo   [OK] local model files found

echo.
echo [3/9] Starting Local ASR server...
call :CHECK_URL "http://%ASR_HOST%:%ASR_PORT%/health" 2
if errorlevel 1 (
  echo   Starting Local ASR at http://%ASR_HOST%:%ASR_PORT% ...
  echo Starting Local ASR window... >> "%LOG_FILE%" 2>&1
  start "MindDock-Local-ASR" cmd /k "chcp 65001 >nul && set ""LOCAL_ASR_MODEL_BASE_PATH=%LOCAL_ASR_MODEL_BASE_PATH%"" && cd /d ""%ASR_DIR%"" && call conda activate %ASR_ENV% && uvicorn server:app --host %ASR_HOST% --port %ASR_PORT%"
  call :WAIT_URL "http://%ASR_HOST%:%ASR_PORT%/health" 60 "Local ASR /health"
  if errorlevel 1 goto FAIL_ASR_HEALTH
) else (
  echo   [OK] Local ASR already running at http://%ASR_HOST%:%ASR_PORT%
)
echo   [OK] Local ASR /health ready

echo.
echo [4/9] Starting MindDock backend...
call :CHECK_URL "http://%BACKEND_HOST%:%BACKEND_PORT%/health" 2
if errorlevel 1 (
  echo   Starting backend at http://%BACKEND_HOST%:%BACKEND_PORT% ...
  echo Starting backend window... >> "%LOG_FILE%" 2>&1
  start "MindDock-Backend" cmd /k "chcp 65001 >nul && cd /d ""%ROOT_DIR%"" && call conda activate %MINDDOCK_ENV% && python -m app.demo serve --port %BACKEND_PORT%"
  call :WAIT_URL "http://%BACKEND_HOST%:%BACKEND_PORT%/health" 60 "Backend /health"
  if errorlevel 1 goto FAIL_BACKEND_HEALTH
) else (
  echo   [OK] Backend already running at http://%BACKEND_HOST%:%BACKEND_PORT%
)
echo   [OK] Backend /health ready

echo.
echo [5/9] Saving Local ASR provider config...
set "CONFIG_JSON=%TEMP%\minddock_local_asr_config.json"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$cfg=[ordered]@{provider='local';enabled=$true;base_url='';api_key='';model='whisper-1';timeout_seconds=%ASR_TIMEOUT%;local_asr_server_path=$env:ASR_DIR;local_asr_host='%ASR_HOST%';local_asr_port=%ASR_PORT%;local_asr_model='%ASR_MODEL%';local_asr_device='%ASR_DEVICE%';local_asr_compute_type='%ASR_COMPUTE%';local_asr_auto_start=$true;local_asr_timeout_seconds=%ASR_TIMEOUT%}; $cfg | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $env:CONFIG_JSON -Encoding UTF8" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_CONFIG_JSON

curl.exe -fsS -X PUT "http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config" -H "Content-Type: application/json" --data-binary "@%CONFIG_JSON%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_CONFIG_SAVE
del "%CONFIG_JSON%" >nul 2>nul
echo   [OK] Local ASR config saved

echo.
echo [6/9] Preloading Local ASR model and waiting for Ready...
set "PRELOAD_JSON=%TEMP%\minddock_local_asr_preload.json"
set "PRELOAD_STATUS=%TEMP%\minddock_local_asr_preload_status.txt"
set "MODEL_STATUS_FILE=%TEMP%\minddock_local_asr_model_status.txt"
>"%PRELOAD_JSON%" echo {"model":"%ASR_MODEL%","device":"%ASR_DEVICE%","compute_type":"%ASR_COMPUTE%"}

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Method Post -Uri 'http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/model/preload' -ContentType 'application/json' -InFile $env:PRELOAD_JSON; $r | ConvertTo-Json -Depth 6 | Tee-Object -FilePath $env:PRELOAD_STATUS } catch { $_ | Out-String | Tee-Object -FilePath $env:PRELOAD_STATUS; exit 1 }" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_PRELOAD
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r=Get-Content -Raw -LiteralPath $env:PRELOAD_STATUS | ConvertFrom-Json; if ($r.status -eq 'failed') { exit 2 }" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto FAIL_PRELOAD_FAILED
del "%PRELOAD_JSON%" >nul 2>nul

call :WAIT_MODEL_READY
if errorlevel 1 goto FAIL_MODEL_READY
echo   [OK] Model Ready: %ASR_MODEL% / %ASR_DEVICE% / %ASR_COMPUTE%

echo.
echo [7/9] Frontend build setting...
if "%BUILD_FRONTEND%"=="1" (
  echo   BUILD_FRONTEND=1, running pnpm build...
  pushd "%ROOT_DIR%\frontend"
  call pnpm build >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    popd
    goto FAIL_FRONTEND_BUILD
  )
  popd
  echo   [OK] Frontend build completed
) else (
  echo   [SKIP] Frontend build skipped by default
)

echo.
echo [8/9] Starting frontend dev server...
call :CHECK_URL "http://%FRONTEND_HOST%:%FRONTEND_PORT%" 2
if errorlevel 1 (
  echo   Starting frontend at http://%FRONTEND_HOST%:%FRONTEND_PORT% ...
  start "MindDock-Frontend" cmd /k "chcp 65001 >nul && cd /d ""%ROOT_DIR%\frontend"" && pnpm dev --host %FRONTEND_HOST% --port %FRONTEND_PORT%"
  call :WAIT_URL "http://%FRONTEND_HOST%:%FRONTEND_PORT%" 60 "Frontend"
  if errorlevel 1 goto FAIL_FRONTEND_HEALTH
) else (
  echo   [OK] Frontend already running at http://%FRONTEND_HOST%:%FRONTEND_PORT%
)
echo   [OK] Frontend ready

echo.
echo [9/9] Opening browser...
start "" "http://localhost:%FRONTEND_PORT%"

echo.
echo ============================================
echo   System started to usable state
echo ============================================
echo   Local ASR: Ready
echo   Backend:   Ready
echo   Frontend:  Ready
echo   Model:     %ASR_MODEL% / %ASR_DEVICE% / %ASR_COMPUTE% Ready
echo.
echo Next step for real validation:
echo   Put a valid wav/mp3/mp4 without sidecar into knowledge_base
echo   Then run:
echo   run_demo_ingest.bat
echo.
echo start.bat does not run ingest and does not call /v1/audio/transcriptions.
echo.
pause
exit /b 0

:CHECK_URL
curl.exe -fsS --max-time %~2 "%~1" >nul 2>> "%LOG_FILE%"
exit /b %ERRORLEVEL%

:WAIT_URL
set "WAIT_URL_TARGET=%~1"
set "WAIT_URL_SECONDS=%~2"
set "WAIT_URL_NAME=%~3"
set /a WAIT_URL_COUNT=0
:WAIT_URL_LOOP
call :CHECK_URL "%WAIT_URL_TARGET%" 2
if not errorlevel 1 exit /b 0
set /a WAIT_URL_COUNT+=1
if %WAIT_URL_COUNT% GEQ %WAIT_URL_SECONDS% exit /b 1
if %WAIT_URL_COUNT%==1 echo   Waiting for %WAIT_URL_NAME% ...
powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>nul
goto WAIT_URL_LOOP

:WAIT_MODEL_READY
set /a MODEL_WAIT_COUNT=0
:WAIT_MODEL_LOOP
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Uri 'http://%BACKEND_HOST%:%BACKEND_PORT%/frontend/media-transcript-config/local/model/status'; $r | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $env:MODEL_STATUS_FILE -Encoding UTF8; $r.status } catch { 'error' }" > "%TEMP%\minddock_model_status_value.txt" 2>> "%LOG_FILE%"
set /p MODEL_STATUS=<"%TEMP%\minddock_model_status_value.txt"
echo   Model status: %MODEL_STATUS%
type "%MODEL_STATUS_FILE%" >> "%LOG_FILE%" 2>&1
if /i "%MODEL_STATUS%"=="ready" exit /b 0
if /i "%MODEL_STATUS%"=="failed" exit /b 2
if /i "%MODEL_STATUS%"=="error" exit /b 3
set /a MODEL_WAIT_COUNT+=5
if %MODEL_WAIT_COUNT% GEQ 300 exit /b 1
powershell -NoProfile -Command "Start-Sleep -Seconds 5" >nul 2>nul
goto WAIT_MODEL_LOOP

:FAIL_CONDA_LIST
echo.
echo [ERROR] Failed to run "conda env list".
goto FAIL_COMMON

:FAIL_MINDDOCK_ENV
echo.
echo [ERROR] minddock environment not found.
echo Run: conda env create -f environment.yml
goto FAIL_COMMON

:FAIL_ASR_ENV
echo.
echo [ERROR] local-asr environment not found.
echo Run:
echo   conda create -n local-asr python=3.10 -y
echo   conda activate local-asr
echo   pip install -r "%ASR_DIR%\requirements.txt"
goto FAIL_COMMON

:FAIL_ASR_SERVER
echo.
echo [ERROR] Local ASR server.py not found:
echo   %ASR_DIR%\server.py
goto FAIL_COMMON

:FAIL_FASTER_WHISPER
echo.
echo [ERROR] faster-whisper import failed in local-asr.
echo Full error was written to:
echo   %LOG_FILE%
echo.
echo To install dependencies, run:
echo   conda run -n local-asr python -m pip install -r "%ASR_DIR%\requirements.txt"
goto FAIL_COMMON

:FAIL_MODEL_FILES
echo.
echo [ERROR] Local faster-whisper base model directory is missing required files.
echo Required:
echo   model.bin
echo   config.json
echo   tokenizer.json
echo   vocabulary.txt
echo.
echo Please place faster-whisper-base model files under:
echo   %LOCAL_ASR_MODEL_BASE_PATH%
goto FAIL_COMMON

:FAIL_ASR_HEALTH
echo.
echo [ERROR] Local ASR did not become ready at http://%ASR_HOST%:%ASR_PORT%/health within 60 seconds.
goto FAIL_COMMON

:FAIL_BACKEND_HEALTH
echo.
echo [ERROR] Backend did not become ready at http://%BACKEND_HOST%:%BACKEND_PORT%/health within 60 seconds.
goto FAIL_COMMON

:FAIL_CONFIG_JSON
echo.
echo [ERROR] Failed to write Local ASR config JSON.
goto FAIL_COMMON

:FAIL_CONFIG_SAVE
echo.
echo [ERROR] Failed to save Local ASR provider config through backend API.
del "%CONFIG_JSON%" >nul 2>nul
goto FAIL_COMMON

:FAIL_PRELOAD
echo.
echo [ERROR] Failed to trigger Local ASR model preload.
goto FAIL_COMMON

:FAIL_PRELOAD_FAILED
echo.
echo [ERROR] Local ASR model preload returned failed.
goto FAIL_COMMON

:FAIL_MODEL_READY
echo.
echo [ERROR] Local ASR model did not reach Ready within 5 minutes, or status failed.
goto FAIL_COMMON

:FAIL_FRONTEND_BUILD
echo.
echo [ERROR] Frontend build failed.
goto FAIL_COMMON

:FAIL_FRONTEND_HEALTH
echo.
echo [ERROR] Frontend did not become ready at http://%FRONTEND_HOST%:%FRONTEND_PORT% within 60 seconds.
goto FAIL_COMMON

:FAIL_COMMON
echo.
echo See log:
echo   %LOG_FILE%
echo.
pause
exit /b 1
