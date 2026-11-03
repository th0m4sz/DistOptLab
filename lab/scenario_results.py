# Función de este módulo: Valida registros con participantes variables y separa el resultado del ensayo de la convergencia.
import csv
import json
import math
from pathlib import Path

from .algorithms import build_saved
from .faults import set_context
from .storage import read_json, write_json


def evaluate_scenario(folder):
    from .parameter_schedule import reference_values
    from .results import read_records
    from .plugins import json_value
    from .equations import Interpreter
    folder = Path(folder)
    rt = build_saved(read_json(folder/'config.json'), folder)
    plan = rt.fault_plan
    records, events = {}, []
    interrupted = False
    for i in rt.ids:
        meta = read_json(folder/f'nodo_{i}.json')
        if not meta or meta['status'] not in ('completed', 'fault_interrupted'):
            raise ValueError(f'Agente {i}: no terminó el escenario correctamente')
        if meta['run_id'] != read_json(folder/'ejecucion.json')['id'] or meta['config_sha256'] != rt.fingerprint:
            raise ValueError('Registros de otro ensayo')
        interrupted |= meta['status'] == 'fault_interrupted'
        rows = read_records(folder, i, strict=True)
        if [r['round'] for r in rows] != list(range(meta['round']+1)):
            raise ValueError(f'Agente {i}: faltan índices lógicos')
        previous = -1
        for row in rows:
            json_value(row)
            k = row['round']
            if row['node'] != i or row['wall_s'] < previous or row['active'] != (not plan.offline(i,k)) or row['phase'] != plan.phase(k):
                raise ValueError('Identidad, tiempo, disponibilidad o etapa incorrectos')
            set_context(rt, k)
            if row['active']:
                rt.check_state(i, row['state'])
            else:
                rt.check_received_state(i, row['state'])
            if not row['active'] and row['values']:
                raise ValueError('Una muestra inactiva no debe dibujarse como producción vigente')
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in row['values'].values()):
                raise ValueError('Observaciones no finitas')
            previous = row['wall_s']
        if not rows or rows[-1]['state'] != meta['state']:
            raise ValueError('El resumen final no coincide con los registros')
        records[i] = rows
        with (folder/f'eventos_{i}.jsonl').open(encoding='utf-8') as stream:
            node_events = [json.loads(line) for line in stream]
        expected = [k for k in plan.boundaries if k <= meta['round']]
        if [e['k'] for e in node_events] != expected:
            raise ValueError('Faltan eventos de una etapa')
        events.extend(node_events)
    for i in rt.ids:
        with (folder/f'entradas_{i}.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                k = row['k']
                expected = set(rt.neighbors[i]) & set(plan.participants(k)) if rt.mode != 'coordinator' else set()
                if set(row['neighbor_ids']) != expected or plan.offline(i,k):
                    raise ValueError('Vecinos o entrada de un agente inactivo incorrectos')
                for j, sample in row['peers'].items():
                    version = sample['version']
                    if type(version) is not int or not 0 <= version < len(records[int(j)]) or sample['state'] != records[int(j)][version]['state']:
                        raise ValueError('La muestra usada no existe en el registro del vecino')
                    if rt.mode == 'sync' and version != k:
                        raise ValueError('Se mezclaron rondas síncronas')
                    if rt.mode == 'async' and plan.phase(version) != plan.phase(k):
                        raise ValueError('Se mezclaron etapas asíncronas')
    if rt.mode == 'coordinator' and rt.coordinator_exchange == 'async':
        from .results import validate_coordinator_trace
        validate_coordinator_trace(rt, folder, records)
    report = dict(records_valid=True, complete=not interrupted, convergence_evaluated=False,
                  equations_verified=False, scenario_outcome='interrupted' if interrupted else 'continued',
                  algorithm=rt.id, planned_events=plan.events, state_policy=plan.state_policy,
                  conclusion=('Escenario registrado. El algoritmo se interrumpió ante la falla programada.' if interrupted else
                              'Escenario terminado. Continuar calculando no demuestra convergencia ni recuperación del balance.'))
    model = getattr(rt.module, 'ASISTENTE', None)
    series = []
    errors = []
    if model and model.get('global_metrics'):
        end = min(len(v) for v in records.values())-1
        rounds = [end] if rt.asynchronous else range(end+1)
        for k in rounds:
            # Solo cuentan agentes disponibles; una potencia congelada no es producción activa.
            active = plan.active(k)
            row = {'round': k, **reference_values(rt, k)}
            if not active:
                row.update({m['name']: None for m in model['global_metrics']})
            else:
                set_context(rt,k)
                ctx = Interpreter(model,rt,k=k,all_states={i:records[i][k]['state'] for i in active})
                for metric in model['global_metrics']:
                    try:
                        value = ctx.evaluate(metric['expression'])
                        if type(value) not in (int,float,bool) or not math.isfinite(value):
                            raise ValueError('La métrica no es un escalar finito')
                        row[metric['name']] = value
                        ctx.env[metric['name']] = value
                    except Exception as exc:
                        row[metric['name']] = None
                        errors.append(f"Índice {k}, {metric['name']}: {exc}")
            series.append(row)
        if rt.asynchronous:
            report['conclusion'] += ' El agregado asíncrono es terminal; no representa un instante común.'
        if series:
            with (folder/'serie_global.csv').open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(series[0]))
                writer.writeheader()
                writer.writerows(series)
    if errors:
        report['metric_errors'] = errors[:100]
        report['conclusion'] += f' No se pudieron calcular {len(errors)} métricas; consulta metric_errors.'
    if hasattr(rt.module,'evaluar_escenario'):
        try:
            summary=json_value(rt.module.evaluar_escenario(rt,records,events))
            if not isinstance(summary,dict) or ('converged' in summary and type(summary['converged']) is not bool):
                raise ValueError('evaluar_escenario debe devolver un dict y converged booleano si lo incluye')
            report['algorithm_report']=summary
            if isinstance(summary.get('conclusion'),str):
                report['conclusion']=summary['conclusion']
            if 'converged' in summary:
                report.update(converged=summary['converged'],convergence_evaluated=True)
        except Exception as exc:
            report['evaluation_error']=str(exc)
    write_json(folder/'eventos.json',dict(planned=plan.events,observed=events))
    write_json(folder/'evaluacion.json',report)
    return report
