# Función de este módulo: Gestiona ejemplos guardados por algoritmo y la retirada recuperable del catálogo.
"""Ejemplos por algoritmo y retirada recuperable del catálogo local."""
import copy
import re
from pathlib import Path
import uuid

from . import plugins
from .algorithms import build
from .storage import read_json, write_json
from .faults import upgrade_scenario_config

PUBLIC_DEFAULTS = Path(__file__).resolve().parents[1] / 'ejemplos' / 'predeterminados'


def default_path(root, algorithm_id):
    if not isinstance(algorithm_id, str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,63}', algorithm_id):
        raise ValueError('Identificador de algoritmo inválido')
    return Path(root) / 'ejemplos_predeterminados' / f'{algorithm_id}.json'


def save_default(root, config):
    if config.get('agent_view'):
        raise ValueError('Guarda la configuración completa del experimento')
    rt = build(upgrade_scenario_config(config))
    value = copy.deepcopy(rt.config)
    for key in ('clock_origin', 'coordinator', 'code_sha256', 'algorithm_name', 'timing_protocol'):
        value.pop(key, None)
    value['execution_mode'] = rt.mode
    value['plugin_sha256'] = rt.descriptor.sha256
    for node in value['nodes']:
        node.update(host='127.0.0.1', port=15000 + node['id'])
    value['source'] = 'Ejemplo predeterminado guardado por el usuario para este algoritmo.'
    write_json(default_path(root, rt.id), value)
    return value


def load_default(root, spec):
    value = read_json(default_path(root, spec.id))
    if value is None:
        value = read_json(PUBLIC_DEFAULTS / f'{spec.id}.json')
        if value is not None:
            value = copy.deepcopy(value)
            value['source'] = 'Ejemplo público incluido con la plataforma.'
    if value is None:
        return None
    if value.get('algorithm') != spec.id or value.get('plugin_sha256') != spec.sha256:
        raise ValueError('El ejemplo predeterminado pertenece a otra versión del algoritmo')
    value = upgrade_scenario_config(value)
    build(value)
    return value


def remove_algorithm(root, spec):
    source = spec.path.resolve()
    if source.parent != plugins.DIRECTORY.resolve() or not source.is_file():
        raise ValueError('Solo se pueden retirar algoritmos instalados en este catálogo')
    folder = Path(root) / 'algoritmos_eliminados' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    write_json(folder / 'retirada.json', {'filename': source.name, 'algorithm': spec.id})
    source.rename(folder / source.name)
    preset = default_path(root, spec.id)
    try:
        if preset.is_file():
            preset.rename(folder / 'ejemplo.json')
    except OSError:
        (folder / source.name).rename(source)
        raise
    return folder


def restore_algorithm(root, folder):
    folder = Path(folder).resolve()
    if folder.parent != (Path(root) / 'algoritmos_eliminados').resolve():
        raise ValueError('La retirada no pertenece a esta biblioteca')
    record = read_json(folder / 'retirada.json')
    filename = record['filename']
    if Path(filename).name != filename or not filename.endswith('.py'):
        raise ValueError('Archivo de algoritmo inválido')
    source = folder / filename
    spec = plugins.PluginSpec(source)
    found, _ = plugins.discover()
    target = plugins.DIRECTORY / filename
    preset = default_path(root, spec.id)
    if spec.id in found or target.exists() or ((folder / 'ejemplo.json').exists() and preset.exists()):
        raise ValueError('Ya existe un algoritmo o ejemplo con esa identidad; no se sobrescribió')
    source.rename(target)
    try:
        if (folder / 'ejemplo.json').is_file():
            preset.parent.mkdir(parents=True, exist_ok=True)
            (folder / 'ejemplo.json').rename(preset)
    except OSError:
        target.rename(source)
        raise
    return spec.id
