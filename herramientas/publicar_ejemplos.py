"""Prepara archivos locales para versionar; no conecta con GitHub ni publica nada."""
import argparse
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

from lab.algorithms import build, refresh_registry, REGISTRY
from lab.storage import read_json, write_json


def public_config(config, spec):
    """Lista explícita: conserva matemáticas, excluye inventario y metadatos privados."""
    build(config)
    keys = ('schema_version', 'algorithm', 'plugin_sha256', 'name', 'steps', 'period_s',
            'parameters', 'edges', 'topology', 'require_connected', 'execution_mode',
            'coordinator_exchange', 'faults', 'demand_schedule')
    result = {k:copy.deepcopy(config[k]) for k in keys if k in config}
    result['plugin_sha256'] = spec.sha256
    result['execution_target'] = 'local'
    result['source'] = 'Ejemplo público incluido con la plataforma.'
    if 'faults' in result:
        original = result['faults']
        result['faults'] = {k:original[k] for k in ('version','state_policy') if k in original}
        result['faults']['events'] = [{k:v for k,v in event.items() if k in ('id','target','nodes','start','end')}
                                     for event in original.get('events', [])]
    if 'demand_schedule' in result:
        original = result['demand_schedule']
        result['demand_schedule'] = {k:original[k] for k in ('version','parameter')}
        result['demand_schedule']['events'] = [{k:event[k] for k in ('at','value')} for event in original['events']]
    result['nodes'] = []
    for node in config['nodes']:
        entry = {k:copy.deepcopy(node[k]) for k in ('id','params','function_profile') if k in node}
        timing = node.get('timing', {})
        if timing:
            entry['timing'] = {k:copy.deepcopy(timing[k]) for k in ('period_factor','send_delay_ms') if k in timing}
        entry.update(host='127.0.0.1', port=15000 + node['id'])
        result['nodes'].append(entry)
    for field in (*spec.parameters, *spec.fields):
        if any(word in field.key.casefold() for word in ('password','secret','token','credential','contrasena')):
            raise ValueError(f'Revisa el campo {field.key!r} antes de preparar un ejemplo público')
    build(result)
    return result


def prepare_examples(destination=None):
    refresh_registry()
    destination = Path(destination) if destination else ROOT / 'ejemplos' / 'predeterminados'
    tutorials = {'tutorial_gradiente':'gradiente', 'tutorial_perfiles':'perfiles'}
    prepared = {}
    for key, spec in REGISTRY.items():
        config = read_json(ROOT / 'datos' / 'ejemplos_predeterminados' / f'{key}.json')
        if config is None and key in tutorials:
            config = read_json(ROOT / 'ejemplos' / tutorials[key] / 'configuracion.json')
        if config is None:
            config = spec.make_example(4, 'anillo')
        prepared[key] = public_config(config, spec)
    for key, config in prepared.items():
        write_json(destination / f'{key}.json', config)
    return prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, help='Por defecto ejemplos/predeterminados')
    args = parser.parse_args()
    prepared = prepare_examples(args.destino)
    print(f'{len(prepared)} ejemplos públicos preparados. Tus configuraciones privadas permanecen intactas.')
    print('No se ha subido ni enviado ningún archivo.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
