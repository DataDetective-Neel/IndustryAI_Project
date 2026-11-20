@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "STEP=Check Python 3.10"
py -3.10 -c "import sys; assert sys.version_info[:2] == (3,10) and sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 (
  echo Install 64-bit Python 3.10 with the Windows py launcher, then rerun setup.bat.
  goto fail
)
set "STEP=Check Node.js and npm"
node -e "let [a,b]=process.versions.node.split('.').map(Number);process.exit(a>=24?0:1)" >nul 2>&1
if errorlevel 1 (
  echo Install Node.js 24 or newer with npm on PATH, then reopen this terminal.
  goto fail
)
call npm --version >nul 2>&1
if errorlevel 1 (
  echo npm is missing. Reinstall Node.js with npm and reopen this terminal.
  goto fail
)
for /f "tokens=1 delims=." %%N in ('call npm --version') do if %%N LSS 10 (
  echo Install npm 10 or newer, then rerun setup.bat.
  goto fail
)
echo Initial dependency setup needs internet unless packages are cached locally.
set "STEP=Create local Python environment"
if not exist ".venv\Scripts\python.exe" py -3.10 -m venv .venv
if errorlevel 1 goto fail
set "STEP=Validate local Python environment"
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3,10) and sys.maxsize > 2**32"
if errorlevel 1 goto fail
set "STEP=Install Python dependencies"
".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
if errorlevel 1 goto fail
set "STEP=Open frontend directory"
pushd frontend || goto fail
set "STEP=Install frontend lockfile dependencies"
call npm ci
if errorlevel 1 goto frontend_fail
set "STEP=Build production frontend"
call npm run build
if errorlevel 1 goto frontend_fail
popd
echo Setup complete. Run launch.bat to inspect locally.
popd
exit /b 0
:frontend_fail
popd
:fail
echo ERROR: %STEP% failed. Fix the error above and rerun setup.bat.
popd
exit /b 1
