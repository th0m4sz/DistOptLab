@echo off
setlocal
cd /d "%~dp0"
rem Preferir la version comprobada, sin modificar otros entornos instalados.
py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
  py -3.11 instalar.py
  goto resultado
)
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
  py -3 instalar.py
  goto resultado
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
  python instalar.py
  goto resultado
)
echo No se encontro Python 3.11 o posterior. Instala Python de 64 bits desde python.org.
echo Consulta la seccion Instalacion del README.
pause
exit /b 1
:resultado
set "install_result=%errorlevel%"
if not "%install_result%"=="0" echo La instalacion no termino. Revisa el error anterior y el README.
if not "%install_result%"=="0" goto fin
choice /C SN /N /M "Crear acceso directo en el escritorio? [S/N]: "
if errorlevel 2 goto fin
call crear_acceso_directo.cmd
:fin
pause
exit /b %install_result%
