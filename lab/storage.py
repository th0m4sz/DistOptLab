# Función de este módulo: Lee y escribe archivos JSON y administra carpetas de experimentos, con escritura atómica.
"""Archivos JSON legibles; cada ejecución ocupa una carpeta independiente."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid


def now():
    """Fecha en UTC para comparar registros sin depender del huso horario local."""
    return datetime.now(timezone.utc).isoformat()


class InstanceLock:
    """Impide abrir dos gestores sobre la misma carpeta y detener ensayos ajenos."""
    def __init__(self, path):
        self.stream = Path(path).open('a+b')
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        # El bloqueo lo mantiene el sistema operativo, no la existencia del archivo.
        # Si el proceso termina, el bloqueo se libera aunque gestor.lock permanezca.
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise ValueError('Ya hay una aplicación abierta usando esta carpeta de datos. Abre su pestaña del navegador.') from exc

    def close(self):
        if self.stream.closed:
            return
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream, fcntl.LOCK_UN)
        self.stream.close()


def read_json(path, default=None):
    """Devuelve default si aún no existe el archivo; un JSON corrupto sí es un error."""
    for attempt in range(12):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8'))
        except FileNotFoundError:
            return default
        except PermissionError:
            # El reemplazo atómico, OneDrive o el antivirus pueden retener un
            # handle brevemente en Windows. Una contención no es un fallo matemático.
            if attempt==11:
                raise
            time.sleep(.02)


def write_json(path, value):
    """Escribe un archivo completo antes de reemplazar el anterior.

    Así un lector ve el JSON anterior o el nuevo, sin observar una escritura a medias.
    El temporal se crea en la misma carpeta para permitir el reemplazo atómico.
    """
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    write_bytes_atomic(path, data)


def write_bytes_atomic(path, data):
    """Publica un archivo completo, con margen para lectores y OneDrive en Windows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Un lector o el antivirus puede mantener abierto el destino en Windows.
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(min(.1, .01 * 2**attempt))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except PermissionError:
            # Un escáner puede retener también el temporal. No ocultar el error
            # del destino ni interrumpir una publicación ya completada.
            pass


class Store:
    """Organiza inventario y ensayos en archivos, sin necesitar una base de datos."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.runs = self.root / 'experimentos'
        self.runs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def folder(self, run_id):
        """Resuelve un ID simple; rechaza rutas que puedan salir de experimentos/."""
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', run_id):
            raise ValueError('Identificador de experimento inválido')
        return self.runs / run_id

    def create_run(self, config, code_hash):
        """Crea una carpeta nueva aunque se repitan el nombre y los parámetros."""
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
        folder = self.folder(run_id)
        folder.mkdir(exist_ok=False)
        write_json(folder / 'config.json', config)
        write_json(folder / 'ejecucion.json', {
            'id': run_id, 'name': config['name'], 'algorithm': config['algorithm'],
            'created_at': now(), 'status': 'starting', 'mode': 'local_tcp',
            'code_sha256': code_hash, 'nodes': len(config['nodes']),
            'steps': config['steps'], 'error': None,
        })
        return run_id

    def update_run(self, run_id, **changes):
        """Modifica el resumen bajo bloqueo para coordinar interfaz y supervisor."""
        with self.lock:
            path = self.folder(run_id) / 'ejecucion.json'
            current = read_json(path)
            if current is None:
                raise ValueError('El experimento no existe')
            current.update(changes)
            write_json(path, current)

    def list_runs(self):
        """Lista ensayos del más reciente al más antiguo usando sus resúmenes."""
        records = []
        for path in self.runs.glob('*/ejecucion.json'):
            try:
                records.append(read_json(path))
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda r: r['created_at'], reverse=True)

    def delete_run(self, run_id):
        """Elimina un ensayo terminado; nunca borra una ejecución activa."""
        with self.lock:
            folder = self.folder(run_id)
            record = read_json(folder / 'ejecucion.json')
            if record is None:
                raise ValueError('El experimento no existe')
            if record.get('status') in ('starting', 'running', 'stopping'):
                raise ValueError('Detén el experimento y espera a que termine antes de eliminarlo')
            # folder() solo acepta un ID simple y siempre lo sitúa bajo experimentos/.
            shutil.rmtree(folder)

    def devices(self):
        """Devuelve el inventario guardado; no implica que las placas estén conectadas."""
        return read_json(self.root / 'dispositivos.json', [])

    def save_device(self, device):
        """Valida y crea o actualiza un dispositivo; no almacena credenciales."""
        from .devices import validate_device
        device = validate_device(device)
        with self.lock:
            devices = self.devices()
            if any(d['host'] == device['host'] and d['port'] == device['port']
                   and d['id'] != device['id'] for d in devices):
                raise ValueError('Ya existe un dispositivo con ese host y puerto')
            devices = [d for d in devices if d['id'] != device['id']] + [device]
            write_json(self.root / 'dispositivos.json', devices)
        return device

    def delete_device(self, device_id):
        """Quita la entrada del inventario local; no ejecuta nada en la placa."""
        with self.lock:
            write_json(self.root / 'dispositivos.json',
                       [d for d in self.devices() if d['id'] != device_id])
