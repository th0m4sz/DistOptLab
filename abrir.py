"""Abre el servidor existente o inicia la aplicación, evitando ejecuciones dobles."""
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8778'


def main():
    """Reutiliza nuestra aplicación si ya escucha en el puerto predeterminado."""
    # El tráfico hacia esta laptop no necesita los proxies de una red externa.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(URL + '/health', timeout=2) as response:
            info = json.load(response)
        # No confundir otro servidor HTTP con esta copia de la plataforma.
        if info.get('service') == 'distoptlab' and Path(info['data']).resolve() == (ROOT / 'datos').resolve():
            webbrowser.open(URL)
            return 0
    except (OSError, ValueError, KeyError):
        pass
    return subprocess.call([sys.executable, str(ROOT / 'app.py')], cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
