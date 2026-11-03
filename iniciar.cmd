@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta instalar.cmd primero.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" abrir.py
if errorlevel 1 pause
