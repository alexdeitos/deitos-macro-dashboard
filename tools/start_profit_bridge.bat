@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0venv" (
  py -3 -m venv "%~dp0venv"
  call "%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip
  call "%~dp0venv\Scripts\python.exe" -m pip install -r "%~dp0requirements-windows.txt"
)
call "%~dp0venv\Scripts\python.exe" "%~dp0profit_excel_bridge.py"
endlocal
