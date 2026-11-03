# Función de este módulo: Desde la laptop, envía archivos por SFTP, inicia procesos por SSH y recoge los registros de las Pi.
"""Despliegue SSH/SFTP; los estados del algoritmo viajan directamente entre Pi."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import threading
import time

from .algorithms import agent_config, build, build_saved
from .runner import ROOT, code_manifest
from .results import evaluate
from .storage import now, read_json, write_json, write_bytes_atomic
from .timing import TimingSession

ENGINE = ('__init__', 'algorithms', 'plugins', 'profiles', 'equations',
          'network', 'storage', 'transport', 'worker', 'coordinator', 'faults', 'scenario_worker', 'timing', 'parameter_schedule')


def remote_command(client, code):
    """Un script Python constante; argumentos y rutas usan quoting de POSIX."""
    _, out, err = client.exec_command('python3 -c ' + shlex.quote(code), timeout=10)
    value = out.read(65536).decode('utf-8', errors='replace')
    error = err.read(4096).decode('utf-8', errors='replace')
    if out.channel.recv_exit_status() != 0:
        raise ValueError(error or 'No se pudo ejecutar Python 3 en la placa')
    return json.loads(value)


def preflight(client, count=1):
    return remote_command(client, '''import json,sys,socket,platform,pathlib
if sys.version_info < (3,10): raise RuntimeError('Se necesita Python 3.10 o posterior')
holders=[]
for _ in range(''' + str(int(count)) + '''):
 s=socket.socket(); s.bind(('0.0.0.0',0)); holders.append(s)
print(json.dumps(dict(home=str(pathlib.Path.home()),hostname=socket.gethostname(),
 python=platform.python_version(),machine=platform.machine(),ports=[s.getsockname()[1] for s in holders])))
for s in holders: s.close()
''')


def mkdirs(sftp, path):
    current = PurePosixPath('/')
    for part in PurePosixPath(path).parts[1:]:
        current /= part
        try:
            sftp.stat(str(current))
        except FileNotFoundError:
            sftp.mkdir(str(current))


def put(sftp, path, content):
    with sftp.open(str(path), 'wb') as stream:
        stream.write(content)


def touch(sftp, path):
    put(sftp, path, b'')


def deployment_files(folder, node_id=None):
    """Lista cerrada: un worker nunca recibe config.json ni parámetros ajenos."""
    files = {'lab/' + name + '.py': (ROOT / 'lab' / (name + '.py')).read_bytes()
             for name in ENGINE}
    files['algoritmo.py'] = (folder / 'algoritmo.py').read_bytes()
    name = 'config.json' if node_id is None else f'config_agente_{node_id}.json'
    files[name] = (folder / name).read_bytes()
    return files


def start_remote(manager, config, devices, sessions):
    """Valida una placa por agente y toma propiedad de sesiones solo al arrancar."""
    with manager.lock:
        if manager.active:
            raise ValueError('Ya hay un experimento activo')
        from .faults import upgrade_scenario_config
        config = upgrade_scenario_config(config)
        ids = {n['id'] for n in config['nodes']}
        if set(devices) != ids or set(sessions) != ids:
            raise ValueError('Asigna y conecta una placa para cada agente')
        endpoints = [(d['host'], d['port']) for d in devices.values()]
        if len(set(endpoints)) != len(ids):
            raise ValueError('Usa una placa diferente para cada agente')
        # Preflight no escribe ni instala nada. Se hace antes de crear el ensayo.
        mode = build(config).mode
        infos = {i: preflight(sessions[i], 2 if mode == 'coordinator' and i == min(ids) else 1)
                 for i in sorted(ids)}
        if len({v['hostname'] for v in infos.values()}) != len(ids):
            raise ValueError('Dos direcciones apuntan a equipos con el mismo hostname; revisa la asignación')
        from .devices import resolve_host
        for node in config['nodes']:
            i = node['id']
            node.update(host=resolve_host(devices[i]['host']), port=infos[i]['ports'][0])
        config.pop('clock_origin', None)
        config.update(execution_target='remote', clock_scope='per_agent', execution_mode=mode, timing_protocol=1)
        if mode == 'coordinator':
            first = min(ids)
            config['coordinator'] = dict(host=next(n['host'] for n in config['nodes'] if n['id'] == first),
                                         port=infos[first]['ports'][1])
        runtime = build(config)
        source = runtime.descriptor.path.read_bytes()
        config['plugin_sha256'] = hashlib.sha256(source).hexdigest()
        config['algorithm_name'] = runtime.name
        runtime = build(config)
        digest, manifest = code_manifest()
        run_id = manager.store.create_run(config, digest)
        folder = manager.store.folder(run_id)
        (folder / 'algoritmo.py').write_bytes(source)
        runtime = build_saved(config, folder)
        for i in runtime.ids:
            write_json(folder / f'config_agente_{i}.json', agent_config(runtime, i))
        write_json(folder / 'software.json', dict(code_sha256=digest, files=manifest, devices=infos))
        write_json(folder / 'despliegue.json', dict(devices=devices, clock_scope='per_agent',
                   coordinator_node=min(ids) if mode == 'coordinator' else None))
        manager.store.update_run(run_id, mode='remote_tcp')
        manager.active = run_id
        manager.thread = threading.Thread(target=execute_remote,
            args=(manager, run_id, runtime, sessions, infos), daemon=True)
        manager.thread.start()
        return run_id


def collect(sftp, remote, folder, names, defer_locked=False, service=None, incremental=False, stats=None):
    """Un bloqueo local temporal no detiene la ejecución en las placas.

    En seguimiento se conserva la versión previa y se reintenta en la próxima
    consulta. Al recoger el resultado final se exige una copia completa.
    Entre bloques se atiende el control del ensayo: una descarga grande no
    debe agotar las esperas de etapa ni la señal de actividad de las placas.
    """
    published = True
    for name in names:
        try:
            path=folder/name
            append=incremental and name.endswith('.jsonl')
            previous=path.read_bytes() if append and path.exists() else b''
            size=sftp.stat(str(remote/name)).st_size if name.endswith('.jsonl') else None
            if append and size<len(previous):
                raise ValueError('El registro remoto se truncó durante el ensayo: '+name)
            if append and size==len(previous):continue
            with sftp.open(str(remote / name), 'rb') as stream:
                if append:stream.seek(len(previous))
                if size is not None and hasattr(stream,'prefetch'):
                    stream.prefetch(file_size=size,max_concurrent_requests=8)
                chunks = []
                remaining=None if size is None else size-len(previous)
                while True:
                    if service:
                        service()
                    if remaining==0:break
                    block = stream.read(65536 if remaining is None else min(65536,remaining))
                    if not block:
                        break
                    chunks.append(block)
                    if remaining is not None:remaining-=len(block)
                    if stats is not None:stats['received_bytes']=stats.get('received_bytes',0)+len(block)
                data = b''.join(chunks)
                if stats is not None:stats['file_reads']=stats.get('file_reads',0)+1
        except FileNotFoundError:
            continue
        except PermissionError:
            # También el origen puede estar retenido durante su reemplazo.
            # En seguimiento se reintenta en la siguiente consulta; al cerrar,
            # una lectura denegada sigue siendo un error que debe informarse.
            if not defer_locked:
                raise
            published = False
            continue
        try:
            if name.endswith('.json'):
                # Los resúmenes remotos también se reemplazan de forma atómica.
                write_json(folder / name, json.loads(data))
            else:
                if name.endswith('.jsonl') and not data.endswith(b'\n'):
                    data = data[:data.rfind(b'\n')+1]
                write_bytes_atomic(folder / name, previous+data if append else data)
        except PermissionError:
            if not defer_locked:
                raise
            published = False
    return published


def execute_remote(manager, run_id, runtime, sessions, infos):
    folder = manager.store.folder(run_id)
    jobs, sftps = [], {}
    status, error = 'failed', None
    timing = None
    heartbeat_stop=threading.Event()
    heartbeat_channels={}
    heartbeat_threads=[]
    heartbeat_errors={}
    transfers={}
    final_collected=set()
    started = time.monotonic()
    factor = max(n.get('timing', {}).get('period_factor', 1) for n in runtime.nodes.values())
    deadline = started + max(120, runtime.steps * (runtime.period * factor + .25) + 60)
    try:
        for i in runtime.ids:
            sftps[i] = sessions[i].open_sftp()
            sftps[i].get_channel().settimeout(8)
            remote = PurePosixPath(infos[i]['home']) / 'laboratorio_flexible' / 'experimentos' / run_id / f'agente_{i}'
            jobs.append(dict(i=i, remote=remote, module='worker', channel=None))
        if runtime.mode == 'coordinator':
            i = runtime.ids[0]
            remote = PurePosixPath(infos[i]['home']) / 'laboratorio_flexible' / 'experimentos' / run_id / 'coordinador'
            jobs.insert(0, dict(i=i, remote=remote, module='coordinator', channel=None))
        # Preparar todas las carpetas antes de que un agente pida la primera ronda.
        for job in jobs:
            sftp, remote = sftps[job['i']], job['remote']
            mkdirs(sftp, remote / 'lab')
            for name, content in deployment_files(folder, job['i'] if job['module'] == 'worker' else None).items():
                put(sftp, remote / name, content)
            touch(sftp, remote / 'GESTOR_ACTIVO')
        # Un canal por placa mantiene la actividad aunque la descarga de datos
        # o una conexión distinta sea lenta. No comparte el SFTP entre hilos.
        for i in runtime.ids:
            lease=sessions[i].open_sftp();lease.get_channel().settimeout(4)
            heartbeat_channels[i]=lease
            def keep_alive(i=i,lease=lease):
                while not heartbeat_stop.is_set():
                    try:
                        for job in jobs:
                            if job['i']==i:touch(lease,job['remote']/'GESTOR_ACTIVO')
                        heartbeat_errors.pop(i,None)
                    except Exception as exc:heartbeat_errors[i]=str(exc) or type(exc).__name__
                    heartbeat_stop.wait(2)
            thread=threading.Thread(target=keep_alive,daemon=True)
            heartbeat_threads.append(thread);thread.start()
        for job in jobs:
            if (folder / 'DETENER').exists():
                raise InterruptedError('Detenido antes de iniciar las placas')
            touch(sftps[job['i']], job['remote'] / 'GESTOR_ACTIVO')
            remote = str(job['remote'])
            args = ['python3', '-u', '-m', 'lab.' + job['module'], '--folder', remote, '--run-id', run_id]
            if job['module'] == 'worker':
                args += ['--id', str(job['i']), '--config', str(job['remote'] / f'config_agente_{job["i"]}.json')]
            command = 'cd ' + shlex.quote(remote) + ' && exec ' + shlex.join(args)
            channel = sessions[job['i']].get_transport().open_session(timeout=8)
            channel.set_combine_stderr(True)
            channel.exec_command(command)
            job['channel'] = channel
        workers = {j['i']: j for j in jobs if j['module']=='worker'}
        def timing_read(i, name):
            try:
                with sftps[i].open(str(workers[i]['remote']/name), 'rb') as stream:
                    return json.loads(stream.read())
            except (FileNotFoundError, PermissionError, json.JSONDecodeError):
                return None
        def timing_write(i, name, value):
            for attempt in range(12):
                try:
                    put(sftps[i], workers[i]['remote']/name, json.dumps(value).encode())
                    return
                except PermissionError:
                    if attempt == 11:
                        raise
                    time.sleep(.02)
        def timing_lease():
            if (folder/'DETENER').exists():raise InterruptedError('Detenido durante el seguimiento remoto')
        timing = TimingSession(folder, runtime.ids, run_id, remote=True,
                               read=timing_read, write=timing_write, heartbeat=timing_lease)
        timing.begin()
        from .faults import release_phase, finished
        def send_phase(value):
            for job in jobs:
                touch(sftps[job['i']], job['remote'] / f'FASE_{value["released"]}.LISTA')
        last_control = [0.0]
        def service_control():
            timing_lease()
            if not runtime.fault_plan.enabled or time.monotonic()-last_control[0] < 1:
                return
            # Consultas pequeñas y actuales, independientes del último JSONL
            # descargado. Solo liberan fronteras ya alcanzadas por todos.
            states = [timing_read(i, f'nodo_{i}.json') for i in runtime.ids]
            if all(states):
                release_phase(folder, runtime, states, send_phase)
            last_control[0] = time.monotonic()
        # El límite operativo de cálculo comienza después de preparar los equipos.
        deadline = time.monotonic()+max(120, runtime.steps*(runtime.period*factor+.25)+60)
        manager.store.update_run(run_id, status='running')
        stopped_at = None
        while True:
            for job in jobs:
                sftp, remote, channel = sftps[job['i']], job['remote'], job['channel']
                touch(sftp, remote / 'GESTOR_ACTIVO')
                if channel.recv_ready():
                    name = 'consola_coordinador.txt' if job['module'] == 'coordinator' else f'consola_{job["i"]}.txt'
                    with (folder / name).open('ab') as stream:
                        while channel.recv_ready():
                            stream.write(channel.recv(65536))
                names = ['coordinador.json'] if job['module'] == 'coordinator' else [f'nodo_{job["i"]}.json']
                collect(sftp, remote, folder, names, defer_locked=True, service=service_control,stats=transfers)
            states = manager.states(run_id)
            release_phase(folder, runtime, states, send_phase)
            expected_interrupt = runtime.fault_plan.enabled and any(s['status']=='fault_interrupted' for s in states)
            complete = finished(states) if runtime.fault_plan.enabled else all(s['status'] == 'completed' for s in states)
            if all(s['status'] == 'completed' for s in states):
                timing.complete()
            if expected_interrupt:
                for job in jobs:
                    touch(sftps[job['i']], job['remote'] / 'FINALIZAR')
            if any(s['status'] == 'failed' for s in states):
                error = 'Falló un agente remoto. Revisa su estado y consola.'
            if not (folder / 'DETENER').exists() and any(j['channel'].exit_status_ready() and j['channel'].recv_exit_status() != 0 for j in jobs):
                error = 'Falló un proceso remoto. Revisa su consola.'
            if time.monotonic() > deadline:
                error = 'Se agotó el tiempo máximo del ensayo en placas'
            if error:
                (folder / 'DETENER').touch()
            stop = (folder / 'DETENER').exists()
            if complete or stop:
                for job in jobs:
                    touch(sftps[job['i']], job['remote'] / ('DETENER' if stop else 'FINALIZAR'))
            else:
                # La vista en vivo recibe solo bytes nuevos de cada JSONL;
                # los resúmenes y las etapas tienen prioridad sobre las curvas.
                for job in jobs:
                    if job['module']=='worker':
                        i=job['i']
                        collect(sftps[i],job['remote'],folder,
                            [f'nodo_{i}.jsonl',f'entradas_{i}.jsonl',f'eventos_{i}.jsonl'],
                            defer_locked=True,service=service_control,incremental=True,stats=transfers)
            if stop:
                stopped_at = stopped_at or time.monotonic()
            if all(j['channel'].exit_status_ready() for j in jobs):
                status = 'failed' if error else 'stopped' if stop else 'completed' if complete else 'failed'
                break
            if stopped_at and time.monotonic() - stopped_at > 12:
                status = 'failed' if error else 'stopped'
                break
            time.sleep(.5)
        if status == 'completed':
            try:
                # El último resumen puede llegar antes que el registro local si
                # un lector lo retenía. Descargar de nuevo antes de evaluar.
                for job in jobs:
                    if job['module'] == 'worker':
                        collect(sftps[job['i']], job['remote'], folder,
                            [f'nodo_{job["i"]}.json', f'nodo_{job["i"]}.jsonl', f'entradas_{job["i"]}.jsonl', f'eventos_{job["i"]}.jsonl'], service=timing_lease,stats=transfers)
                        final_collected.add(job['i'])
                evaluate(folder)
            except Exception as exc:
                write_json(folder / 'evaluacion.json', dict(records_valid=False, complete=True,
                           convergence_evaluated=False, conclusion=f'Error de evaluación: {exc}'))
    except InterruptedError:
        status = 'stopped'
    except Exception as exc:
        error = str(exc) or type(exc).__name__
    finally:
        if timing:
            timing.abort(status)
        for job in jobs:
            try:
                touch(sftps[job['i']], job['remote'] / 'DETENER')
                if job['module'] == 'worker' and job['i'] not in final_collected:
                    collect(sftps[job['i']], job['remote'], folder,
                        [f'nodo_{job["i"]}.json', f'nodo_{job["i"]}.jsonl', f'entradas_{job["i"]}.jsonl', f'eventos_{job["i"]}.jsonl'])
            except Exception:
                pass  # Los registros ya recuperados quedan disponibles aunque falle la red.
            if job['channel'] is not None:
                job['channel'].close()
        heartbeat_stop.set()
        for thread in heartbeat_threads:thread.join(timeout=5)
        for channel in heartbeat_channels.values():channel.close()
        for sftp in sftps.values():
            sftp.close()
        for client in sessions.values():
            client.close()
        manager.store.update_run(run_id, status=status, error=error, ended_at=now())
        write_json(folder/'transferencias.json',dict(transfers,heartbeat_errors=heartbeat_errors,
            incremental_live_logs=True,final_downloads=len(final_collected)))
        with manager.lock:
            manager.active = None
