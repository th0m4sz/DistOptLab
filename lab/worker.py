# Función de este módulo: Ejecuta un agente: inicializa su estado, recibe vecinos, calcula actualizaciones y registra resultados.
"""Un proceso independiente por agente. No importa la interfaz ni el evaluador."""
import argparse
import csv
import json
import os
from pathlib import Path
import signal
import threading
import time

from .algorithms import build_saved
from .network import RoundExchange, SnapshotStore, serve
from .storage import now, read_json, write_json
from .transport import Latest, Inbox, CoordinatorClient, serve as serve_latest
from .timing import WorkerTiming, LoopMetrics


def execute(config_path, node_id, run_id, folder):
    """Ejecuta un único agente y conserva su trayectoria completa.

    config_path contiene parámetros y vecinos; folder pertenece a esta ejecución.
    Devuelve 0 solo si termina todas las rondas. El gestor usa ese código para
    distinguir un final correcto de una parada o un fallo.
    """
    folder = Path(folder)
    config = read_json(config_path)
    if config.get('faults', {}).get('events'):
        from .scenario_worker import execute as execute_scenario
        return execute_scenario(config_path, node_id, run_id, folder)
    if config.get('agent_view', {}).get('node_id') != node_id:
        raise ValueError('El worker necesita la configuración local de su propio agente')
    runtime = build_saved(config, folder)
    stopped = threading.Event()
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stopped.set())
    # Una pérdida prolongada del gestor detiene únicamente el ensayo remoto.
    lease_thread = None
    lease_done = threading.Event()
    if config.get('execution_target') == 'remote':
        def watch_lease():
            while not lease_done.wait(1):
                try:
                    if time.time() - (folder / 'GESTOR_ACTIVO').stat().st_mtime > 30:
                        stopped.set()
                        return
                except FileNotFoundError:
                    stopped.set()
                    return
        lease_thread = threading.Thread(target=watch_lease, daemon=True)
        lease_thread.start()
    # Solo este proceso modifica su estado. SnapshotStore expone copias por
    # ronda a los vecinos; el gestor no le envía soluciones calculadas.
    state = runtime.initial_state(node_id)
    store = Latest(runtime,node_id,run_id) if runtime.mode == 'async' else RoundExchange(runtime,node_id,run_id) if runtime.mode=='sync' else SnapshotStore(runtime,node_id,run_id)
    store.publish(0, state)
    inbox = coordinator = trace = None
    if runtime.mode == 'coordinator':
        endpoint = runtime.config['coordinator']
        connection = f'cliente TCP → {endpoint["host"]}:{endpoint["port"]}'
    else:
        node_endpoint = runtime.nodes[node_id]
        connection = f'servidor TCP {node_endpoint["host"]}:{node_endpoint["port"]}'
    meta = dict(node=node_id, pid=os.getpid(), connection=connection,
                role='agente', run_id=run_id, config_sha256=runtime.fingerprint,
                config_scope='local', config_file=Path(config_path).name,
                status='starting', round=0, steps=runtime.steps, state=state, error=None)
    started = runtime.config.get('clock_origin',time.monotonic())
    bind_host = runtime.nodes[node_id]['host'] if runtime.config.get('execution_target') == 'remote' else '127.0.0.1'
    local_period = runtime.period * (runtime.nodes[node_id].get('timing', {}).get('period_factor',1) if runtime.asynchronous else 1)
    last_status = 0
    server = None
    complete = 0
    timing = WorkerTiming(config, folder, node_id, run_id)
    last_sample = None
    performance=LoopMetrics()

    def check_stop():
        if stopped.is_set() or (folder / 'DETENER').exists():
            raise InterruptedError('Detenido durante el arranque')

    def save_status(status, error=None):
        """Publica un resumen pequeño para la interfaz, separado del CSV completo."""
        meta.update(status=status, error=error, round=complete, state=state,
                    wall_s=time.monotonic() - started, updated_at=now(),performance=performance.summary(complete))
        write_json(folder / f'nodo_{node_id}.json', meta)

    try:
        with (folder / f'nodo_{node_id}.jsonl').open('x', encoding='utf-8') as stream:
            def record():
                nonlocal last_sample
                last_sample = time.monotonic()
                row = dict(round=complete, wall_s=last_sample - started, monotonic_s=last_sample, node=node_id,
                           state=state, values=runtime.observe(node_id, state, complete))
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                stream.flush()

            record()
            # En placas se escucha en la IP asignada; localmente solo en loopback.
            if runtime.mode == 'coordinator':
                endpoint=runtime.config['coordinator']
                coordinator=CoordinatorClient((endpoint['host'],endpoint['port']),runtime,run_id,node_id)
                if runtime.coordinator_exchange == 'async':
                    trace=(folder/f'entradas_{node_id}.jsonl').open('x',encoding='utf-8')
            elif runtime.mode == 'async':
                server=serve_latest((bind_host,runtime.nodes[node_id]['port']),store.respond)
                inbox=Inbox(runtime,node_id,run_id)
                trace=(folder/f'entradas_{node_id}.jsonl').open('x',encoding='utf-8')
                deadline=time.monotonic()+20
                while inbox.snapshot() is None:
                    if stopped.is_set() or (folder/'DETENER').exists():
                        raise InterruptedError('Detenido durante el arranque')
                    if time.monotonic()>deadline:
                        raise TimeoutError('No llegó la primera muestra de todos los vecinos')
                    stopped.wait(.005)
            else:
                server = serve(store, bind_host)
            save_status('starting')
            timing.wait_start(check_stop)
            performance.begin()
            save_status('running')
            for k in range(runtime.steps):
                if stopped.is_set() or (folder / 'DETENER').exists():
                    raise InterruptedError('Detenido por el usuario')
                tick = time.monotonic()
                # Todos los mensajes deben pertenecer a k: no mezclar rondas.
                # La primera espera es mayor porque los procesos arrancan por separado.
                aggregate=None
                exchange_start=time.perf_counter()
                if runtime.mode == 'coordinator':
                    peers={}
                    aggregate=coordinator.fetch(k,state,20 if k==0 else 5,check_stop=check_stop)
                    if runtime.coordinator_exchange == 'async':
                        trace.write(json.dumps(dict(k=k,coordinator=coordinator.last_trace,global_data=aggregate),allow_nan=False)+'\n')
                        trace.flush()
                elif runtime.mode == 'async':
                    inputs=inbox.snapshot()
                    peers={j:value['state'] for j,value in inputs.items()}
                    # Este registro permite reproducir el orden REAL, aunque k
                    # y las versiones vecinas sean distintos en cada ejecución.
                    trace.write(json.dumps(dict(k=k,peers=inputs),allow_nan=False)+'\n')
                else:
                    peers = store.fetch(k,20 if k==0 else 3,check_stop=check_stop)
                performance.add('exchange_s',exchange_start)
                if stopped.is_set() or (folder / 'DETENER').exists():
                    raise InterruptedError('Detenido por el usuario')
                # Único punto del bucle que aplica la ecuación del algoritmo.
                update_start=time.perf_counter()
                state = runtime.update(node_id, state, peers, k, aggregate)
                performance.add('update_s',update_start)
                complete = k + 1
                record_start=time.perf_counter()
                record()
                store.publish(complete, state)
                # El CSV guarda cada ronda; el resumen visual se actualiza menos
                # veces para no gastar tiempo de ejecución escribiendo JSON.
                if time.monotonic() - last_status >= .3:
                    save_status('running')
                    last_status = time.monotonic()
                performance.add('record_s',record_start)
                # El periodo es un mínimo, no una garantía de tiempo real.
                pacing_start=time.perf_counter()
                stopped.wait(max(0, local_period - (time.monotonic() - tick)))
                performance.add('pacing_s',pacing_start)
            if coordinator and runtime.coordinator_exchange == 'async':
                coordinator.publish_final(runtime.steps,state,5,check_stop=check_stop)
            performance.end()
            timing.finish(last_sample, 'completed')
            save_status('completed')
    except (InterruptedError, KeyboardInterrupt) as exc:
        store.fail('Experimento detenido')
        save_status('stopped', str(exc))
    except Exception as exc:
        store.fail(str(exc))
        save_status('stopped' if (folder / 'DETENER').exists() else 'failed', str(exc))
        print(f'Agente {node_id}: {exc}', flush=True)
    finally:
        # También en modo coordinado el proceso queda disponible para la
        # comprobación final del reloj; esa espera no cuenta como cálculo.
        if timing.enabled and meta['status'] == 'completed':
            deadline = time.monotonic()+max(120, runtime.steps*(runtime.period*10+.1)+30)
            while not stopped.is_set() and not any((folder/name).exists() for name in ('FINALIZAR','DETENER')) and time.monotonic()<deadline:
                timing.service()
                stopped.wait(.005)
        if trace:
            trace.close()
        if inbox:
            inbox.close()
        if coordinator:
            coordinator.close()
        if isinstance(store,RoundExchange):store.close()
        if server:
            # Mantener el último estado disponible para que los vecinos terminen.
            if meta['status'] == 'completed':
                # Un nodo rápido conserva su último estado mientras los demás
                # terminan. No imponer aquí el antiguo margen fijo de 3.2 s.
                deadline=time.monotonic()+max(120,runtime.steps*(runtime.period*10+.1)+30)
                while not stopped.is_set() and not any((folder/name).exists() for name in ('FINALIZAR','DETENER')) and time.monotonic()<deadline:
                    stopped.wait(.05)
            server.shutdown()
            server.server_close()
    lease_done.set()
    if lease_thread:
        lease_thread.join(timeout=2)
    return 0 if meta['status'] == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--id', type=int, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.config, args.id, args.run_id, args.folder))
