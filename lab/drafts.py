# Función de este módulo: Gestiona la recuperación y retirada recuperable de borradores del asistente.
"""Retirada recuperable de diseños; nunca elimina algoritmos ni ensayos."""
from pathlib import Path
import uuid

from .storage import read_json, write_json


def latest_recovery(root):
    """Conserva incluso expresiones y valores JSON aún incompletos del formulario."""
    root = Path(root).resolve()
    files = sorted((root / 'recuperacion').glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for path in files:
        try:
            entry = read_json(path)
            source = entry.get('draft')
            if source and (Path(source).resolve().parent != root or not Path(source).is_file()):
                continue
            if isinstance(entry.get('model'), dict):
                return entry['model'], source
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return None, None


def save_recovery(path, model, draft=None):
    write_json(path, {'model': model, 'draft': str(draft) if draft else None})


def remove_draft(root, selected):
    root = Path(root).resolve()
    source = Path(selected).resolve()
    if source.parent != root or source.suffix != '.json' or not source.is_file():
        raise ValueError('Selecciona un borrador existente de esta carpeta')
    folder = root / 'eliminados' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    archived = folder / source.name
    source.rename(archived)
    return archived


def restore_draft(root, archived):
    root = Path(root).resolve()
    archived = Path(archived).resolve()
    if archived.parent.parent != root / 'eliminados' or archived.suffix != '.json' or not archived.is_file():
        raise ValueError('No se encontró el borrador eliminado')
    destination = root / archived.name
    if destination.exists():
        raise ValueError('Ya existe un borrador con ese archivo; no se sobrescribió')
    archived.rename(destination)
    archived.parent.rmdir()
    return destination
