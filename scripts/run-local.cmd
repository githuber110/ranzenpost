@echo off
setlocal
set ROOT=%~dp0..
set ISERV_DATA_DIR=%ROOT%\data
set ISERV_FRONTEND_DIR=%ROOT%\frontend
set HOST=127.0.0.1
if /I "%~1"=="lan" set HOST=0.0.0.0
if not exist "%ISERV_DATA_DIR%" mkdir "%ISERV_DATA_DIR%"
cd /d "%ROOT%\backend"
echo.
echo   IServ Connector
echo   http://127.0.0.1:8100
if /I "%~1"=="lan" (
  echo   LAN mode: reachable from your phone on this network
  for /f "tokens=14" %%i in ('ipconfig ^| findstr /c:"IPv4"') do echo   http://%%i:8100
)
echo.
"%ROOT%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host %HOST% --port 8100
endlocal
