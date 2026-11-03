# Función de este módulo: Alinea registros en segundos y reconstruye métricas globales con el último estado conocido.
"""Observación posterior al cálculo: nunca modifica ni realimenta los algoritmos."""
import bisect
import csv
import math
from functools import lru_cache
from pathlib import Path

from .storage import read_json


def time_basis(folder):
    folder = Path(folder)
    timing = read_json(folder/'tiempos.json', {})
    if timing.get('origin_monotonic_s') is not None:
        return dict(kind='measured', label='Tiempo de ejecución (s)', timing=timing,
                    margin_s=max((n.get('alignment_margin_s', 0) for n in timing['nodes'].values()), default=0))
    config = read_json(folder/'config.json')
    if config.get('clock_scope') == 'shared_laptop' and config.get('clock_origin') is not None:
        return dict(kind='legacy_local', label='Tiempo desde lanzamiento local (s)', margin_s=None)
    return None


def sample_time(row, node, basis):
    if basis is None:
        return None
    if basis['kind'] == 'legacy_local':
        return row.get('wall_s')
    timing = basis['timing']
    entry = timing['nodes'].get(str(node))
    stamp = row.get('monotonic_s')
    if entry is None or stamp is None:
        return None
    value = stamp+entry['offset_s']-timing['origin_monotonic_s']
    # El estado inicial ya existía al liberar el inicio y no se actualiza antes.
    # También una estimación remota ligeramente negativa se limita al inicio:
    # ningún cálculo se libera antes de t=0. La marca cruda y el margen se conservan.
    return max(0.0, value)


def timing_text(folder):
    pending = read_json(Path(folder)/'tiempos.json', {})
    if pending.get('status') == 'preparing':
        return 'Preparando agentes y alineando relojes antes de iniciar el cronómetro.'
    basis = time_basis(folder)
    if not basis:
        return 'Este ensayo no tiene referencia temporal común. Los tiempos locales de las placas no permiten recuperar una duración global exacta; ejecuta un nuevo ensayo.'
    if basis['kind'] == 'legacy_local':
        return 'Ensayo local anterior: segundos compartidos desde el lanzamiento, incluyendo preparación. No tiene la nueva medición desde todos preparados.'
    value = basis['timing']
    if value.get('status') != 'completed':
        return 'Medición temporal en curso.' if value.get('status') == 'running' else 'Medición temporal incompleta: no se certifica una duración de ejecución terminada.'
    text = f"Hasta la última muestra: {value['duration_s']:.3f} s · Confirmación del gestor: {value['observed_duration_s']:.3f} s."
    if value['remote']:
        text += f" Alineación estimada: ±{basis['margin_s']:.4f} s; dispersión de arranques estimada: {value['start_spread_s']:.4f} s."
        if any('calibration_end_error' in n for n in value['nodes'].values()):
            text += ' No se pudo contrastar todos los relojes al finalizar.'
    text += ' Excluye envío previo de archivos y evaluación final; incluye comunicación, registro y esperas durante la ejecución.'
    return text


def temporal_rows(folder, interval=.1):
    """Últimos estados en una cuadrícula, o en cada registro si interval es None."""
    folder = Path(folder)
    if interval is not None and (not math.isfinite(interval) or interval < .001):
        raise ValueError('El intervalo de representación debe ser al menos 0.001 s')
    config = read_json(folder/'config.json')
    paths = [folder/'config.json', folder/'algoritmo.py'] + [folder/f'nodo_{n["id"]}.jsonl' for n in config['nodes']]
    if not time_basis(folder) or any(not p.exists() for p in paths):
        return []
    paths += [p for p in [folder/'tiempos.json']+[folder/f'nodo_{n["id"]}.json' for n in config['nodes']] if p.exists()]
    signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
    return _temporal_rows(str(folder.resolve()), float(interval) if interval is not None else None, signature)


@lru_cache(maxsize=8)
def _temporal_rows(folder, interval, signature):
    from .parameter_schedule import reference_values
    from .algorithms import build_saved
    from .equations import Interpreter, model_from_source
    from .faults import upgrade_scenario_config
    from .results import read_records
    folder = Path(folder)
    basis = time_basis(folder)
    try:
        model = model_from_source((folder/'algoritmo.py').read_text(encoding='utf-8-sig'))
    except (ValueError, SyntaxError):
        return []
    if not model or not model.get('global_metrics'):
        return []
    rt = build_saved(upgrade_scenario_config(read_json(folder/'config.json')), folder)
    records = {i: read_records(folder, i) for i in rt.ids}
    if not records or not all(records.values()):
        return []
    clocks = {i: [sample_time(r, i, basis) for r in rows] for i, rows in records.items()}
    if any(any(t is None for t in times) for times in clocks.values()):
        return []
    if any(any(b < a for a, b in zip(times, times[1:])) for times in clocks.values()):
        raise ValueError('Marcas temporales desordenadas: no se reconstruye la curva')
    # Un agente terminado conserva su estado. A uno todavía en marcha no se le
    # inventan muestras posteriores a la última descarga disponible.
    unfinished = [i for i in rt.ids if read_json(folder/f'nodo_{i}.json', {}).get('status') != 'completed']
    end = min(clocks[i][-1] for i in unfinished) if unfinished else max(t[-1] for t in clocks.values())
    begin = max(t[0] for t in clocks.values())
    if end < begin:
        return []
    if interval is None:
        # Evolución del evaluador: cada cambio registrado, sin inventar puntos
        # intermedios ni equiparar los índices locales de distintos agentes.
        samples = {t for times in clocks.values() for t in times if begin <= t <= end}
    else:
        count = math.floor((end-begin)/interval)
        if count > 20000:
            raise ValueError('Más de 20000 muestras temporales: aumenta el intervalo de representación')
        samples = {begin+j*interval for j in range(count+1)} | {end}
    for i, rows in records.items():
        for j in range(1, len(rows)):
            reference_changed = (reference_values(rt, rows[j]['round']) != reference_values(rt, rows[j-1]['round']))
            if rows[j].get('active', True) != rows[j-1].get('active', True) or reference_changed:
                if begin <= clocks[i][j] <= end:
                    samples.add(clocks[i][j])
    series = []
    for t in sorted(samples):
        selected = {i: records[i][bisect.bisect_right(clocks[i], t)-1] for i in rt.ids}
        active = [i for i, row in selected.items() if row.get('active', True)]
        rt.active_ids = rt.available_ids = active
        rt.active_neighbors = {i: {j:w for j,w in ns.items() if j in active} for i,ns in rt.neighbors.items()}
        rounds = {i:r['round'] for i,r in selected.items()}
        # No existe un k global asíncrono. Dentro de sum_all/mean_all/... cada
        # estado conserva su propio k; una expresión global que exige k queda vacía.
        common_k = next(iter(rounds.values())) if len(set(rounds.values())) == 1 else None
        ctx = Interpreter(model, rt, k=common_k, all_rounds=rounds,
                          all_states={i:selected[i]['state'] for i in active})
        row = {'time/experiment_s':t, 'source/index_min':min(rounds.values()), 'source/index_max':max(rounds.values()),
               'source/active_agents':len(active), 'source/sample_age_max_s':max(t-sample_time(r,i,basis) for i,r in selected.items())}
        row.update(reference_values(rt, indices=[rounds[i] for i in active]))
        for metric in model['global_metrics']:
            value = None
            if active:
                try:
                    value = ctx.evaluate(metric['expression'])
                    if type(value) not in (int,float,bool) or not math.isfinite(value):
                        value = None
                except Exception:
                    value = None
            row[metric['name']] = value
            if value is not None:
                ctx.env[metric['name']] = value
        series.append(row)
    return series


def export_timing(folder):
    folder = Path(folder)
    timing = read_json(folder/'tiempos.json', {})
    if timing.get('status') != 'completed':
        return
    columns = ['node', 'start_s', 'last_sample_s', 'alignment_margin_s', 'offset_change_s']
    with (folder/'tiempos_agentes.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for node, entry in timing['nodes'].items():
            writer.writerow(dict(node=node, **{k:entry.get(k) for k in columns[1:]}))
