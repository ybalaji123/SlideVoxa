@echo off
REM SlideVoxa — Start the development server
echo Starting SlideVoxa backend...
cd /d "%~dp0"
..\venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
