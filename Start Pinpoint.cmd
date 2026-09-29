@echo off
rem Builds the frontend, starts Pinpoint on http://127.0.0.1:8000 and opens it.
cd /d "%~dp0"
echo Building the Pinpoint frontend...
call npm --prefix frontend run build --silent || (echo Frontend build failed. & pause & exit /b 1)
echo Starting Pinpoint at http://127.0.0.1:8000  (close this window to stop it)
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process http://127.0.0.1:8000"
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
