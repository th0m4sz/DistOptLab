"""Comprueba el entorno y los archivos necesarios sin iniciar ensayos ni tocar datos."""
import importlib
from importlib import metadata
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))


def main():
    errors = []
    print(f'Python {platform.python_version()} · {platform.system()} · {platform.machine()}')
    print(f'Intérprete: {sys.executable}')
    if sys.version_info < (3, 11):
        errors.append('Se necesita Python 3.11 o posterior.')
    required = ('app.py', 'abrir.py', 'requirements-lock.txt', 'lab/worker.py',
                'herramientas/__init__.py', 'herramientas/compartir.py',
                'herramientas/acceso_directo.py', 'herramientas/publicar_ejemplos.py',
                'crear_acceso_directo.cmd',
                'plantillas/algoritmo_vacio.py', 'docs/PRIMER_ALGORITMO.md',
                'ejemplos/gradiente/modelo.json', 'lab/faults.py', 'lab/scenario_worker.py',
                'docs/FALLAS.md', 'ejemplos/fallas/consenso_con_fallas.json')
    for name in required:
        if not (ROOT / name).is_file():
            errors.append('Falta el archivo ' + name + '; extrae el ZIP completo.')
    try:
        pins = dict(line.split('==', 1) for line in
                    (ROOT / 'requirements-lock.txt').read_text(encoding='utf-8').splitlines()
                    if line and not line.startswith('#'))
        for name, expected in pins.items():
            try:
                actual = metadata.version(name)
                if actual != expected:
                    errors.append(f'{name}: instalado {actual}, esperado {expected}. Ejecuta instalar.cmd.')
            except metadata.PackageNotFoundError:
                errors.append(f'Falta la dependencia {name}. Ejecuta el instalador.')
        for name in ('nicegui', 'paramiko', 'plotly', 'matplotlib', 'lab.figure_export_ui', 'lab.learning_ui', 'lab.designer_ui', 'lab.scenario_ui'):
            importlib.import_module(name)
        from lab.algorithms import LOAD_ERRORS, REGISTRY, refresh_registry
        refresh_registry()
        errors.extend(f'Algoritmo no válido: {name}: {error}' for name, error in LOAD_ERRORS.items())
        if not REGISTRY:
            errors.append('No se encontró ningún algoritmo en algoritmos/.')
        from lab.algorithm_library import load_default
        for spec in REGISTRY.values():
            load_default(ROOT / 'datos', spec)
    except Exception as exc:
        errors.append(f'No se pudieron cargar los módulos: {exc}')
    if errors:
        print('\n'.join('- ' + error for error in errors))
        return 1
    print('Instalación verificada: dependencias, módulos, tutorial y catálogo disponibles.')
    print('Esta comprobación no garantiza conexión a placas ni convergencia de un algoritmo.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
