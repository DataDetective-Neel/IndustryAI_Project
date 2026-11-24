@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" goto missing
if not exist "frontend\dist\index.html" goto missing
if not exist "frontend\dist\assets" goto missing
if not exist "frontend\dist\assets\*.js" goto missing
if not exist "frontend\dist\assets\*.css" goto missing
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, multipart, cv2, numpy, PIL, yaml, torch; from pcb_landmarks.compare import load_config; load_config('configs/comparison.json')"
if errorlevel 1 goto missing
".venv\Scripts\python.exe" -c "import hashlib,json,os; from pathlib import Path; configs=[('configs/landmarks.json','PCB_CHECKPOINT'),('configs/component_model.json','PCB_COMPONENT_CHECKPOINT')]; [p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==c['checkpoint_sha256'] or (_ for _ in ()).throw(ValueError('Missing or invalid model: '+str(p))) for f,e in configs for c in [json.loads(Path(f).read_text())] for p in [Path(os.environ.get(e,c['checkpoint_path']))]]"
if errorlevel 1 goto missing
".venv\Scripts\python.exe" -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',8000)); s.close()" >nul 2>&1
if errorlevel 1 (
  echo Port 8000 is occupied. Close the existing server before retrying. No process was stopped.
  popd
  exit /b 1
)
echo Open http://127.0.0.1:8000/ in your browser.
echo Press Ctrl+C to stop the server. No installation or build runs at launch.
".venv\Scripts\python.exe" -m uvicorn pcb_landmarks.web:app --host 127.0.0.1 --port 8000
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
:missing
echo Setup outputs are missing or incomplete. Run setup.bat while online, then retry.
popd
exit /b 1
