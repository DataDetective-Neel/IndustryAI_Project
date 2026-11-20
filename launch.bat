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
