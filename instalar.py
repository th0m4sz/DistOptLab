"""Prepara un entorno propio; no utiliza paquetes de la plataforma original."""
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 11):
        print('Se necesita Python 3.11 o posterior. La versión comprobada es Python 3.11 de 64 bits.')
        return 1
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    try:
        if not python.exists():
            print('Creando el entorno independiente .venv...', flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(python), '-c',
                        'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'], check=True)
        print('Instalando las versiones fijadas en requirements-lock.txt...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r',
                        str(ROOT / 'requirements-lock.txt')], check=True, cwd=ROOT)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True, cwd=ROOT)
        subprocess.run([str(python), '-m', 'herramientas.verificar_instalacion'], check=True, cwd=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'Instalación incompleta: {exc}')
        print('Consulta el error anterior y la sección Solución de problemas del README.')
        return 1
    print('Instalación terminada. En Windows abre iniciar.cmd; en Linux/macOS usa .venv/bin/python abrir.py.')
    print('En Windows puedes crear un acceso en el escritorio con crear_acceso_directo.cmd.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
