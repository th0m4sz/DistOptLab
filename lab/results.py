# Función de este módulo: Lee registros, prepara series y CSV, y evalúa los criterios declarados por el algoritmo.
"""Registros completos JSONL, CSV tabulares y gráficas independientes del dominio."""
import csv
import json
import math
from functools import lru_cache
from pathlib import Path

from .algorithms import build_saved
from .plugins import PluginSpec, json_value
from .storage import read_json, write_json
from .temporal_results import time_basis, sample_time, temporal_rows, export_timing


def read_records(folder, node_id, strict=False):
    path = Path(folder) / f'nodo_{node_id}.jsonl'
    if not path.exists():
        if strict:
            raise ValueError(f'Falta el registro del agente {node_id}')
        return []
    result = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if not line.endswith('\n') and not strict:
                break  # Un escritor puede estar publicando la última fila.
            result.append(json.loads(line))
    return result


def read_series(folder, node_id):
    return [dict(round=r['round'], wall_s=r['wall_s'], node=r['node'], **r['values'])
            for r in read_records(folder, node_id)]


def export_csv(folder):
    folder = Path(folder)
    config = read_json(folder / 'config.json')
    basis = time_basis(folder)
    for node in config['nodes']:
        rows = read_records(folder, node['id'])
        if not rows:
            continue
        keys = sorted({key for row in rows for key in row['values']})
        # Prefijo evita colisiones con nombres internos (round, node, wall_s).
        with (folder / f'nodo_{node["id"]}.csv').open('w', encoding='utf-8', newline='') as stream:
            time_columns = ['monotonic_s', 'experiment_s'] if basis else []
            writer = csv.DictWriter(stream, fieldnames=['round', 'wall_s', 'node'] + time_columns + ['value/' + k for k in keys])
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(round=row['round'], wall_s=row['wall_s'], node=row['node'],
                                     **(dict(monotonic_s=row.get('monotonic_s'), experiment_s=sample_time(row, node['id'], basis)) if basis else {}),
                                     **{'value/' + k: v for k, v in row['values'].items()}))


    reconstructed = reconstructed_rows(folder)
    if reconstructed:
        with (folder/'serie_global_por_indice.csv').open('w',encoding='utf-8',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(reconstructed[0]))
            writer.writeheader()
            writer.writerows(reconstructed)
    try:
        timed = temporal_rows(folder)
    except ValueError as exc:
        # Un límite de representación no invalida registros matemáticos completos.
        timed = []
        write_json(folder/'exportacion_temporal.json', dict(interval_s=.1, error=str(exc)))
    if timed:
        with (folder/'serie_global_por_tiempo.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(timed[0]))
            writer.writeheader()
            writer.writerows(timed)
    evolution = evaluator_rows(folder)
    if evolution and 'time/experiment_s' in evolution[0]:
        with (folder/'serie_global_evolucion.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(evolution[0]))
            writer.writeheader()
            writer.writerows(evolution)
    export_timing(folder)


def validate_coordinator_trace(runtime, folder, records):
    """Comprueba versiones de origen contra los registros, sin reejecutar el método."""
    for i in runtime.ids:
        with (Path(folder)/f'entradas_{i}.jsonl').open(encoding='utf-8') as stream:
            entries = [json.loads(line) for line in stream]
        expected = [r['round'] for r in records[i][:-1] if r.get('active',True)]
        actual = [e['k'] for e in entries]
        if actual != expected:
            # Una interrupción cooperativa puede ocurrir después del cálculo y
            # antes de registrar su salida. La entrada última sigue siendo auditable.
            meta = read_json(Path(folder)/f'nodo_{i}.json')
            trailing = records[i][-1]
            if (meta.get('status') != 'fault_interrupted' or not trailing.get('active',True)
                    or actual != expected+[trailing['round']]):
                raise ValueError('Traza de coordinador asíncrono incompleta')
        previous = 0
        for entry in entries:
            k, trace = entry['k'], entry['coordinator']
            phase = runtime.fault_plan.phase(k)
            ids = runtime.fault_plan.participants(k)
            if trace['sequence'] <= previous or trace['phase'] != phase or set(trace['sources']) != {str(j) for j in ids}:
                raise ValueError('Secuencia, etapa o participantes incorrectos en el coordinador')
            previous = trace['sequence']
            for j, sample in trace['sources'].items():
                version = sample['version']
                rows = records[int(j)]
                if (type(version) is not int or not 0<=version<len(rows) or not rows[version].get('active',True)
                        or runtime.fault_plan.phase(version)!=phase or not math.isfinite(sample['age_s']) or sample['age_s']<0):
                    raise ValueError('El agregado usa una muestra no registrada, inactiva o de otra etapa')
            if trace['sources'][str(i)]['version'] != k:
                raise ValueError('El agregado no incluye la entrada propia de este paso')


def evaluate(folder):
    folder = Path(folder)
    config = read_json(folder / 'config.json')
    if config.get('faults', {}).get('events'):
        from .scenario_results import evaluate_scenario
        return evaluate_scenario(folder)
    runtime = build_saved(config, folder)
    execution = read_json(folder / 'ejecucion.json')
    logs = {}
    for i in runtime.ids:
        meta = read_json(folder / f'nodo_{i}.json')
        if not meta or meta['status'] != 'completed' or meta['round'] != runtime.steps:
            raise ValueError('Registros incompletos')
        if meta['run_id'] != execution['id'] or meta['config_sha256'] != runtime.fingerprint or meta['node'] != i:
            raise ValueError('Registros de otra ejecución')
        rows = read_records(folder, i, strict=True)
        if [r['round'] for r in rows] != list(range(runtime.steps + 1)):
            raise ValueError(f'Agente {i}: faltan rondas o están desordenadas')
        previous = -1
        for row in rows:
            json_value(row)
            if row['node'] != i or row['wall_s'] < previous:
                raise ValueError('Identificador o tiempo de registro inválido')
            previous = row['wall_s']
            runtime.check_state(i, row['state'])
            if not isinstance(row['values'], dict) or any(type(v) not in (float, int) or not math.isfinite(v) for v in row['values'].values()):
                raise ValueError('Mediciones inválidas')
        if rows[-1]['state'] != meta['state']:
            raise ValueError('El estado final y el resumen no coinciden')
        logs[i] = [r['state'] for r in rows]
    inputs = {}
    if runtime.mode == 'coordinator' and runtime.coordinator_exchange == 'async':
        validate_coordinator_trace(runtime, folder, {i:read_records(folder,i,strict=True) for i in runtime.ids})
    if runtime.mode == 'async':
        for i in runtime.ids:
            with (folder / f'entradas_{i}.jsonl').open(encoding='utf-8') as stream:
                inputs[i] = [json.loads(line) for line in stream]
            if [row['k'] for row in inputs[i]] != list(range(runtime.steps)):
                raise ValueError('Traza asíncrona incompleta')
            for row in inputs[i]:
                if set(row['peers']) != {str(j) for j in runtime.neighbors[i]}:
                    raise ValueError('Vecinos incorrectos en la traza')
                for key, item in row['peers'].items():
                    version = item['version']
                    if type(version) is not int or not 0 <= version <= runtime.steps or item['state'] != logs[int(key)][version]:
                        raise ValueError('La muestra usada no existe en el registro vecino')
    report = dict(records_valid=True, complete=True, algorithm=runtime.id,
                  convergence_evaluated=False, equations_verified=False,
                  conclusion='Registros completos. El algoritmo no ha definido un criterio de convergencia.')
    # Un método estocástico o con memoria no puede reproducirse suponiendo estado escalar puro.
    # El autor puede aportar explícitamente su verificación, recibiendo las entradas reales.
    if hasattr(runtime.module, 'verificar'):
        report['verification'] = json_value(runtime.module.verificar(runtime, logs, inputs))
    if hasattr(runtime.module, 'evaluar'):
        summary, global_series = runtime.module.evaluar(runtime, logs)
        json_value(summary)
        if not isinstance(summary, dict):
            raise ValueError('evaluar() debe devolver (resumen dict, serie global list)')
        if 'converged' in summary and type(summary['converged']) is not bool:
            raise ValueError('converged debe ser un booleano')
        report['convergence_evaluated'] = 'converged' in summary
        report['algorithm_report'] = summary
        for key in ('converged', 'conclusion'):
            if key in summary:
                report[key] = summary[key]
        if global_series:
            json_value(global_series)
            if not isinstance(global_series, list) or any(not isinstance(row, dict) or any(isinstance(v, (dict, list)) for v in row.values()) for row in global_series):
                raise ValueError('La serie global debe ser una lista de filas con valores escalares')
            keys = list(dict.fromkeys(k for row in global_series for k in row))
            with (folder / 'serie_global.csv').open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=keys)
                writer.writeheader()
                writer.writerows(global_series)
    export_csv(folder)
    write_json(folder / 'evaluacion.json', report)
    return report


def catalog(folder):
    folder = Path(folder)
    config = read_json(folder / 'config.json')
    labels = dict(PluginSpec(folder / 'algoritmo.py').metrics)
    if config.get('demand_schedule'):
        labels['reference/'+config['demand_schedule']['parameter']] = 'Demanda de referencia'
    keys = {key for n in config['nodes'] for r in read_records(folder, n['id']) for key in r['values']}
    return {key: labels.get(key, key) for key in sorted(keys)}


def global_rows(folder):
    path = Path(folder) / 'serie_global.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    # El evaluador asíncrono del asistente publica un único agregado terminal.
    # Su tiempo es el último registro terminal, no una ronda simultánea.
    config = read_json(Path(folder) / 'config.json')
    if len(rows) == 1 and (config.get('execution_mode') == 'async' or config.get('coordinator_exchange') == 'async') and config.get('clock_scope') != 'per_agent' and not rows[0].get('wall_s'):
        records = [read_records(folder, node['id']) for node in config['nodes']]
        if records and all(records):
            rows[0]['wall_s'] = max(group[-1]['wall_s'] for group in records)
    return rows


def evaluator_rows(folder):
    """Conserva el evaluador manual; amplía el terminal del asistente por tiempo.

    Los CSV originales y la conclusión final permanecen intactos. Si el asistente
    solo publicó un agregado asíncrono terminal, sus métricas se observan también
    en cada instante registrado, con el último estado disponible de cada agente.
    Sin reloj común o sin modelo declarativo se conserva la salida original.
    """
    rows = global_rows(folder)
    config = read_json(Path(folder)/'config.json')
    if (len(rows) != 1 or not (config.get('execution_mode') == 'async'
                               or config.get('coordinator_exchange') == 'async')):
        return rows
    evolution = temporal_rows(folder, interval=None)
    if not evolution:
        return rows
    # Las columnas y métricas siguen siendo las del evaluador archivado.
    metrics = set(rows[0]) - {'round', 'wall_s'}
    if not metrics or not metrics.issubset(evolution[0]):
        return rows  # Un evaluador manual puede añadir métricas no declaradas.
    return [{k:v for k,v in row.items() if k in metrics or k.startswith(('time/', 'source/'))}
            for row in evolution]


def reconstructed_rows(folder):
    """Observación por índice local, nunca una instantánea física asíncrona.

    Solo métricas declaradas por el asistente; no vuelve a ejecutar paso ni evaluar.
    El caché se invalida al cambiar registros, configuración o algoritmo archivado.
    """
    folder = Path(folder)
    config = read_json(folder/'config.json')
    paths = [folder/'config.json', folder/'algoritmo.py'] + [folder/f'nodo_{n["id"]}.jsonl' for n in config['nodes']]
    if any(not p.exists() for p in paths):
        return []
    signature = tuple((p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
    return _reconstructed_rows(str(folder.resolve()), signature)


@lru_cache(maxsize=16)
def _reconstructed_rows(folder, signature):
    from .parameter_schedule import reference_values
    from .equations import Interpreter, model_from_source
    from .faults import upgrade_scenario_config
    folder = Path(folder)
    try:
        model = model_from_source((folder/'algoritmo.py').read_text(encoding='utf-8-sig'))
    except (ValueError, SyntaxError):
        return []
    if not model or not model.get('global_metrics'):
        return []
    config = upgrade_scenario_config(read_json(folder/'config.json'))
    rt = build_saved(config, folder)
    records = {i:{r['round']:r for r in read_records(folder,i)} for i in rt.ids}
    common = sorted(set.intersection(*(set(rows) for rows in records.values()))) if records else []
    # Resolución de informe acotada; mantener ambos lados de cada cambio de disponibilidad.
    stride = max(1, math.ceil(len(common)/800))
    chosen = set(common[::stride]) | set(common[-1:])
    for at, _ in rt.parameter_schedule.events:
        chosen.update((at-1, at))
    for rows in records.values():
        previous = None
        for k, row in rows.items():
            if previous is not None and row.get('active',True)!=rows[previous].get('active',True):
                chosen.update((previous,k))
            previous = k
    series = []
    for k in common:
        if k not in chosen:
            continue
        active = [i for i in rt.ids if records[i][k].get('active',True)]
        rt.active_ids = rt.available_ids = active
        rt.active_neighbors = {i:{j:w for j,w in ns.items() if j in active} for i,ns in rt.neighbors.items()}
        rt.scenario_round = k
        ctx = Interpreter(model,rt,k=k,all_states={i:records[i][k]['state'] for i in active})
        row = {'round':k, **reference_values(rt, k)}
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


def global_catalog(folder, reconstructed=False, temporal=False, interval=.1):
    rows = temporal_rows(folder, interval) if temporal else reconstructed_rows(folder) if reconstructed else evaluator_rows(folder)
    labels = {}
    try:
        from .equations import model_from_source
        model = model_from_source((Path(folder) / 'algoritmo.py').read_text(encoding='utf-8-sig'))
        labels = {r['name']: r.get('label') or r['name'] for r in model['global_metrics']}
    except (OSError, ValueError, SyntaxError):
        pass  # Los algoritmos Python manuales pueden no tener modelo del asistente.
    config = read_json(Path(folder)/'config.json')
    schedule = config.get('demand_schedule')
    if schedule:
        labels['reference/'+schedule['parameter']] = 'Demanda de referencia'
    return {key: labels.get(key, key) for key in (rows[0] if rows else [])
            if key not in ('round', 'wall_s') and not key.startswith(('time/', 'source/'))
            if any(as_number(row.get(key)) is not None for row in rows)}


def as_number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def chart_series(folder, metric, max_points=800, x_axis='@round', agents=None, kind='lines', scope='agents', interval=.1):
    folder = Path(folder)
    config = read_json(folder / 'config.json')
    basis = time_basis(folder) if x_axis == '@experiment_s' or scope == 'global_time' else None
    groups = [('Global por tiempo (último estado)', temporal_rows(folder, interval))] if scope == 'global_time' else [('Global por índice (reconstruido)', reconstructed_rows(folder))] if scope == 'global_index' else [('Global', evaluator_rows(folder))] if scope != 'agents' else [
        (f'Agente {n["id"]}', read_records(folder, n['id'])) for n in config['nodes']
        if agents is None or n['id'] in agents]
    traces = []
    for name, rows in groups:
        points = []
        for index, row in enumerate(rows):
            values = row if scope != 'agents' else row['values']
            x = (row.get('round', index) if scope != 'agents' else row['round']) if x_axis == '@round' else (
                row.get('wall_s') if x_axis == '@wall_s' else values.get(x_axis))
            if scope == 'global_time':
                x = row.get('time/experiment_s')
            elif scope == 'global' and x_axis == '@experiment_s':
                x = row.get('time/experiment_s')
            elif x_axis == '@experiment_s' and scope == 'agents':
                x = sample_time(row, row['node'], basis)
            points.append((as_number(x), as_number(values.get(metric))))
        if not points:
            continue
        # Conservar extremos y huecos, además de una muestra uniforme.
        stride = 1 if scope == 'global_time' else max(1, math.ceil(len(points) / max_points))
        indices = set(range(0, len(points), stride)) | {len(points)-1}
        for k in range(1, len(points)):
            if (points[k][1] is None) != (points[k-1][1] is None):
                indices.update((k-1, k))
            if metric.startswith('reference/') and points[k][1] != points[k-1][1]:
                indices.update((k-1, k))
        chosen = [points[k] for k in sorted(indices)]
        single = len(chosen) == 1 and chosen[0][0] is not None and chosen[0][1] is not None
        trace = dict(name=name, x=[p[0] for p in chosen], y=[p[1] for p in chosen],
                     mode='markers+text' if single else kind, type='scatter', connectgaps=False)
        if single:
            trace.update(text=[format(chosen[0][1], '.8g')], textposition='top center')
        if scope == 'global_time' or x_axis == '@experiment_s' or metric.startswith('reference/'):
            trace['line'] = dict(shape='hv')
        traces.append(trace)
    return traces
