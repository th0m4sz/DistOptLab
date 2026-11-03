"""Crea un ZIP público con los mismos ejemplos preparados para GitHub."""
import argparse
from datetime import datetime
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def create_archive(destination=None, root=ROOT):
    root = Path(root).resolve()
    destination = Path(destination) if destination else root.parent / 'entregas'
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ('distoptlab_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.zip')
    files = ['app.py', 'abrir.py', 'instalar.py', 'instalar.cmd', 'iniciar.cmd',
             'crear_acceso_directo.cmd', 'README.md', 'README.es.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'requirements.txt',
             'requirements-lock.txt', '.gitignore', '.gitattributes']
    for directory in ('lab', 'herramientas', 'algoritmos', 'docs', 'ejemplos', 'plantillas', 'tests'):
        files.extend(str(p.relative_to(root)) for p in (root / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts
                     and p.suffix not in ('.pyc', '.tmp', '.log', '.zip', '.lnk'))
    missing = [name for name in files if not (root / name).is_file()]
    if missing:
        raise ValueError('Faltan archivos de distribución: ' + ', '.join(missing))
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(set(files)):
            path = root / name
            bundle.write(path, root.name + '/' + path.relative_to(root).as_posix())
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, help='Carpeta del ZIP; por defecto ../entregas')
    args = parser.parse_args()
    print(f'ZIP listo: {create_archive(args.destino)}')
    print('Incluye ejemplos públicos. Excluye datos/, tmp/, entornos y accesos directos personales.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
