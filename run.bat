@echo off
REM Starts PackCheck without auto-reload (avoids the reload loop caused by the .venv folder).
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo Open http://localhost:8000  (press Ctrl+C to stop)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
