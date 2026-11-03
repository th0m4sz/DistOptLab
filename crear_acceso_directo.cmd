@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m herramientas.acceso_directo
) else (
  py -3.11 -m herramientas.acceso_directo
)
if errorlevel 1 pause
