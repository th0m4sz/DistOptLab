# Función de este módulo: Ejecuta un agente con fallas lógicas programadas y deja trazas de cada etapa.
"""La Pi sigue encendida; el proceso suspende el cálculo y la publicación según el escenario."""
import copy
import json
import os
from pathlib import Path
import signal
import threading
import time

from .algorithms import build_saved
from .faults import set_context, ScenarioInterrupted, SCENARIO_WAIT_S
from .network import RoundExchange, SnapshotStore, ProtocolError, serve
from .storage import now, read_json, write_json
from .transport import Latest, Inbox, CoordinatorClient, serve as serve_latest
from .timing import WorkerTiming, LoopMetrics


ExpectedInterruption = ScenarioInterrupted


def execute(config_path, node_id, run_id, folder):
    folder = Path(folder)
    config = read_json(config_path)
    if config.get('agent_view', {}).get('node_id') != node_id:
        raise ValueError('El worker necesita la configuración local de su propio agente')
    rt = build_saved(config, folder)
    plan = rt.fault_plan
    stopped = threading.Event()
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stopped.set())
    start = config.get('clock_origin', time.monotonic())
    k, computed, phase = 0, 0, -1
    state = rt.initial_state(node_id)
    store = Latest(rt,node_id,run_id) if rt.mode=='async' else RoundExchange(rt,node_id,run_id) if rt.mode=='sync' else SnapshotStore(rt,node_id,run_id)
    bind = rt.nodes[node_id]['host'] if config.get('execution_target') == 'remote' else '127.0.0.1'
    server = None
    inbox = coordinator = None
    status = 'starting'
    error = None
    last_row = None
    last_status = 0
    timing = WorkerTiming(config, folder, node_id, run_id)
    performance=LoopMetrics()
    meta = dict(node=node_id, pid=os.getpid(), run_id=run_id, config_sha256=rt.fingerprint,
                config_scope='local', config_file=Path(config_path).name, role='agente', steps=rt.steps,
                connection=f'servidor TCP {bind}:{rt.nodes[node_id]["port"]}', phase_ready=-1)

    def save(value, force=True):
        nonlocal last_status
        current = time.monotonic()
        if not force and value == meta.get('status') and current-last_status < .3:
            return
        meta.update(status=value, round=k, computed_steps=computed, state=state, error=error,
                    active=not plan.offline(node_id, k), wall_s=time.monotonic()-start,
                    phase=plan.phase(k), updated_at=now(),performance=performance.summary(computed))
        write_json(folder / f'nodo_{node_id}.json', meta)
        last_status = time.monotonic()

    def check_stop():
        if stopped.is_set() or (folder/'DETENER').exists():
            raise InterruptedError('Detenido por el usuario')
        if any((folder/name).exists() for name in ('INTERRUPCION', 'FINALIZAR')):
            raise ExpectedInterruption('Otro agente interrumpió el algoritmo ante la falla programada')
        if config.get('execution_target') == 'remote':
            try:
                if time.time()-(folder/'GESTOR_ACTIVO').stat().st_mtime > 30:
                    raise InterruptedError('Se perdió la señal de actividad del gestor')
            except FileNotFoundError:
                raise InterruptedError('Se perdió la señal de actividad del gestor')

    try:
        save('starting')
        if rt.mode == 'async':
            server = serve_latest((bind, rt.nodes[node_id]['port']), store.respond)
            inbox = Inbox(rt, node_id, run_id)
        elif rt.mode == 'sync':
            server = serve(store, bind)
        else:
            endpoint = config['coordinator']
            meta['connection'] = f'cliente TCP → {endpoint["host"]}:{endpoint["port"]}'
            coordinator = CoordinatorClient((endpoint['host'], endpoint['port']), rt, run_id, node_id)
        timing.wait_start(check_stop)
        performance.begin()
        with (folder/f'nodo_{node_id}.jsonl').open('x', encoding='utf-8') as logs, \
             (folder/f'entradas_{node_id}.jsonl').open('x', encoding='utf-8') as trace, \
             (folder/f'eventos_{node_id}.jsonl').open('x', encoding='utf-8') as events:
            while k <= rt.steps:
                check_stop()
                tick = time.monotonic()
                if k in plan.boundaries:
                    control_start=time.perf_counter()
                    meta['phase_ready'] = k
                    save('waiting_phase')
                    deadline = time.monotonic()+SCENARIO_WAIT_S
                    while not (folder/f'FASE_{k}.LISTA').exists():
                        check_stop()
                        if time.monotonic() > deadline:
                            raise TimeoutError('No se pudo acordar el inicio de la etapa con todos los agentes')
                        stopped.wait(.01)
                    before = rt.active_ids[:]
                    set_context(rt, k)
                    if inbox:
                        with inbox.lock:
                            inbox.phase = k
                    change = dict(kind='cambio_de_etapa', phase=k, k=k, node=node_id,
                                  active_ids=rt.active_ids, available_ids=rt.available_ids,
                                  removed=sorted(set(before)-set(rt.active_ids)),
                                  joined=sorted(set(rt.active_ids)-set(before)),
                                  wall_s=time.monotonic()-start, state_policy=plan.state_policy,
                                  reinitialized=False)
                    if k and node_id in rt.available_ids:
                        if plan.state_policy == 'reset_returning' and node_id in change['joined']:
                            state = rt.initial_state(node_id)
                            change['reinitialized'] = True
                        if hasattr(rt.module, 'al_cambiar_red'):
                            state = rt.check_state(node_id, rt.module.al_cambiar_red(rt, node_id, copy.deepcopy(state), copy.deepcopy(change)))
                    events.write(json.dumps(change, allow_nan=False)+'\n')
                    events.flush()
                    phase = k
                    performance.add('control_wait_s',control_start)
                set_context(rt, k)
                active = node_id in rt.available_ids
                record_start=time.perf_counter()
                store.publish(k, state)
                stamp = time.monotonic()
                row = dict(round=k, wall_s=stamp-start, monotonic_s=stamp, node=node_id, state=state,
                           values=rt.observe(node_id, state, k) if active else {}, active=active, phase=phase)
                last_row = copy.deepcopy(row)
                logs.write(json.dumps(row, allow_nan=False)+'\n')
                logs.flush()
                # El registro JSONL conserva cada índice. El resumen visual no
                # necesita fsync y reemplazo atómico en cada actualización.
                save('running' if active else 'faulted', force=False)
                performance.add('record_s',record_start)
                if k == rt.steps:
                    if coordinator and rt.coordinator_exchange == 'async' and active:
                        coordinator.publish_final(k,state,SCENARIO_WAIT_S,check_stop=check_stop)
                    break
                if active:
                    exchange_start=time.perf_counter()
                    aggregate, peers, inputs = None, {}, {}
                    if rt.mode == 'sync':
                        neighbors = rt.active_neighbors[node_id]
                        peers = store.fetch(k,SCENARIO_WAIT_S,check_stop=check_stop,neighbors=neighbors)
                        inputs = {j:dict(state=s,version=k,age_s=None) for j,s in peers.items()}
                    elif rt.mode == 'async':
                        neighbors = rt.active_neighbors[node_id]
                        deadline = time.monotonic()+SCENARIO_WAIT_S
                        while True:
                            inputs = inbox.scenario_snapshot(phase, neighbors)
                            if inputs is not None:
                                break
                            check_stop()
                            if time.monotonic() > deadline:
                                raise TimeoutError('No llegó la primera muestra de los vecinos de esta etapa')
                            stopped.wait(.001)
                        peers = {j: value['state'] for j, value in inputs.items()}
                    else:
                        try:
                            aggregate = coordinator.fetch(k, state, SCENARIO_WAIT_S, check_stop=check_stop)
                        except TimeoutError as exc:
                            if plan.offline('coordinator',k):
                                raise ExpectedInterruption('El coordinador no pudo completar la ronda por la falla programada') from exc
                            raise
                    trace.write(json.dumps(dict(k=k, phase=phase, peers=inputs,
                                    neighbor_ids=sorted(peers), global_data=aggregate,
                                    coordinator=getattr(coordinator,'last_trace',None)), allow_nan=False)+'\n')
                    trace.flush()
                    performance.add('exchange_s',exchange_start)
                    check_stop()
                    update_start=time.perf_counter()
                    state = rt.update(node_id, state, peers, k, aggregate)
                    performance.add('update_s',update_start)
                    computed += 1
                    factor = rt.nodes[node_id].get('timing', {}).get('period_factor', 1) if rt.asynchronous else 1
                    pacing_start=time.perf_counter()
                    stopped.wait(max(0, rt.period*factor-(time.monotonic()-tick)))
                    performance.add('pacing_s',pacing_start)
                k += 1
        performance.end()
        status = 'completed'
    except ExpectedInterruption as exc:
        status, error = 'fault_interrupted', str(exc)
        # Cierre cooperativo inmediato: las esperas de otros agentes también
        # deben poder cancelarse. En placas el aviso se propaga por TCP y SFTP.
        (folder/'INTERRUPCION').touch()
        if isinstance(store, SnapshotStore):
            store.interrupt(str(exc))
    except (TimeoutError, ProtocolError) as exc:
        status, error = 'failed', str(exc)
    except InterruptedError as exc:
        status, error = 'stopped', str(exc)
    except Exception as exc:
        status, error = 'failed', str(exc)
    finally:
        if last_row is not None:
            k, state = last_row['round'], last_row['state']
        timing.finish(last_row.get('monotonic_s') if last_row else None, status)
        save(status)
        if status in ('completed', 'fault_interrupted') and (server or timing.enabled):
            deadline = time.monotonic()+max(120, rt.steps*(rt.period+0.1)+30)
            while not stopped.is_set() and not any((folder/n).exists() for n in ('DETENER', 'FINALIZAR')) and time.monotonic() < deadline:
                timing.service()
                stopped.wait(.005 if timing.enabled else .05)
        if inbox:
            inbox.close()
        if isinstance(store,RoundExchange):store.close()
        if coordinator:
            coordinator.close()
        if server:
            server.shutdown()
            server.server_close()
    return 0 if status in ('completed', 'fault_interrupted') else 1
