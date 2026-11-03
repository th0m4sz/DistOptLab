# Función de este módulo: Detecta cambios en los registros para evitar refrescos de interfaz redundantes.
"""Solo observación de archivos: no participa en la comunicación del algoritmo."""
from pathlib import Path


def folder_revision(folder):
    """Firma ligera: no abre ni interpreta registros que no han cambiado.

    Detecta también archivos nuevos, eliminados y reemplazados atómicamente.
    Debe consultarse fuera del bucle de eventos de la interfaz.
    """
    entries = []
    for path in Path(folder).iterdir():
        if path.suffix not in ('.json', '.jsonl', '.csv', '.py'):
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue  # Un escritor pudo reemplazar/eliminar un temporal.
        entries.append((path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(entries))


class RefreshGate:
    """Recuerda únicamente una vista completada; un fallo permite reintentar."""
    def __init__(self):
        self.completed = None

    def needed(self, run_id, revision, views):
        return self.completed != (run_id, revision, views)

    def commit(self, run_id, revision, views):
        self.completed = (run_id, revision, views)
