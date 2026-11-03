# Función de este módulo: Gestiona los ensayos y arranca los procesos cuando los agentes se ejecutan en la laptop.
"""El gestor inicia procesos y lee archivos. No determina estados del algoritmo."""
import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import zipfile

from .algorithms import agent_config, build, build_saved
from .results import evaluate, export_csv
from .storage import InstanceLock, now, read_json, write_json
from .timing import TimingSession

ROOT = Path(__file__).resolve().parents[1]


def code_manifest():
    """Guarda huellas del motor y del gestor para identificar el código utilizado."""
    paths = list((ROOT / 'lab').glob('*.py')) + [ROOT / 'app.py']
    files = {str(p.relative_to(ROOT.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    digest = hashlib.sha256(str(sorted(files.items())).encode()).hexdigest()
    return digest, files


def allocate_ports(count):
    """Pide al sistema puertos TCP locales distintos para los agentes.

    Las reservas se liberan antes de lanzar los procesos. Si otro programa toma
    un puerto en ese intervalo, el agente fallará y el gestor registrará el error.
    """
    holders = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            holders.append(sock)
        return [s.getsockname()[1] for s in holders]
    finally:
        for sock in holders:
            sock.close()


class LocalRunner:
    """Administra una ejecución a la vez y conserva datos aunque falle un agente."""
    def __init__(self, store):
        self.store = store
        self.instance_lock = InstanceLock(store.root / 'gestor.lock')
        self.lock = threading.RLock()
        self.active = None
        self.processes = []
        self.thread = None
        # Una ejecución previa de un gestor cerrado no se presenta como terminada.
        for record in store.list_runs():
            if record['status'] in ('starting', 'running', 'stopping'):
                folder = store.folder(record['id'])
                (folder / 'DETENER').touch()
                store.update_run(record['id'], status='interrupted', ended_at=now(),
                                 error='Se cerró el gestor. Se conservaron los archivos disponibles.')

    def start(self, config):
        """Valida y archiva una copia; devuelve el ID sin bloquear la interfaz."""
        with self.lock:
            if self.active:
                raise ValueError('Ya hay un experimento activo. Deténlo o espera a que termine.')
            from .faults import upgrade_scenario_config
            config = upgrade_scenario_config(config)
            config['execution_target'] = 'local'
            config['clock_scope'] = 'shared_laptop'
            config['timing_protocol'] = 1
            # La ejecución local nunca usa los hosts del inventario.
            reserved_ports=allocate_ports(len(config['nodes'])+1)
            for node, port in zip(config['nodes'], reserved_ports):
                node['host'], node['port'] = '127.0.0.1', port
            runtime = build(config)
            config['execution_mode'] = runtime.mode
            config['clock_origin'] = time.monotonic()
            if runtime.mode == 'coordinator':
                config['coordinator'] = dict(host='127.0.0.1',port=reserved_ports[-1])
            plugin_bytes = None
            if hasattr(runtime,'descriptor'):
                plugin_bytes=runtime.descriptor.path.read_bytes()
                config['plugin_sha256']=hashlib.sha256(plugin_bytes).hexdigest()
                config['algorithm_name']=runtime.name
            # La huella también incluye modo, reloj y endpoint del coordinador.
            runtime=build(config)
            digest, manifest = code_manifest()
            run_id = self.store.create_run(config, digest)
            if plugin_bytes is not None:
                (self.store.folder(run_id)/'algoritmo.py').write_bytes(plugin_bytes)
                runtime=build_saved(config,self.store.folder(run_id))
            write_json(self.store.folder(run_id) / 'software.json',
                       dict(python=sys.version, code_sha256=digest, files=manifest))
            self.active = run_id
            self.processes = []
            self.thread = threading.Thread(target=self._execute, args=(run_id, runtime), daemon=True)
            self.thread.start()
            return run_id

    def start_remote(self, config, devices, sessions):
        """Las sesiones SSH autenticadas viven solo durante este ensayo."""
        from .remote_runner import start_remote
        return start_remote(self, config, devices, sessions)

    def _execute(self, run_id, runtime):
        """Lanza procesos, vigila su salida y evalúa los registros al finalizar."""
        folder = self.store.folder(run_id)
        streams = []
        error = None
        status = 'failed'
        coordinator_process = None
        timing = TimingSession(folder, runtime.ids, run_id)
        try:
            if runtime.mode == 'coordinator':
                stream=(folder/'consola_coordinador.txt').open('w',encoding='utf-8')
                streams.append(stream)
                coordinator_process=subprocess.Popen([sys.executable,'-m','lab.coordinator','--folder',str(folder),'--run-id',run_id],
                    cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            for i in runtime.ids:
                if (folder / 'DETENER').exists():
                    break
                stream = (folder / f'consola_{i}.txt').open('w', encoding='utf-8')
                streams.append(stream)
                # Cada agente recibe exclusivamente sus parámetros privados.
                local_path = folder / f'config_agente_{i}.json'
                write_json(local_path, agent_config(runtime, i))
                # Pasar argumentos en lista evita interpretar nombres como comandos.
                cmd = [sys.executable, '-m', 'lab.worker', '--config', str(local_path),
                       '--id', str(i), '--run-id', run_id, '--folder', str(folder)]
                process = subprocess.Popen(cmd, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                self.processes.append(process)
            timing.begin()
            self.store.update_run(run_id, status='running')
            # Vigilancia operativa para no dejar procesos bloqueados indefinidamente.
            # Este límite no constituye un criterio matemático de convergencia.
            factor=max(n.get('timing', {}).get('period_factor', 1) for n in runtime.nodes.values()) if runtime.asynchronous else 1
            limit = time.monotonic() + max(120, runtime.steps * (runtime.period*factor + .1) + 30)
            stop_at = None
            while any(p.poll() is None for p in self.processes):
                states=self.states(run_id)
                from .faults import release_phase, finished
                release_phase(folder, runtime, states)
                if all(s['status']=='completed' for s in states):
                    timing.complete()
                if (runtime.fault_plan.enabled and (finished(states) or any(s['status']=='fault_interrupted' for s in states))) or all(s['status']=='completed' for s in states):
                    (folder/'FINALIZAR').touch()
                if coordinator_process and coordinator_process.poll() is not None and not (folder/'FINALIZAR').exists() and not (folder/'DETENER').exists():
                    error='Falló el coordinador del algoritmo. Revisa su consola.'
                    (folder/'DETENER').touch()
                if any(s['status']=='failed' for s in states):
                    error='Falló un agente. Revisa su estado y su archivo de consola.'
                    (folder/'DETENER').touch()
                if time.monotonic() > limit:
                    error = 'Se agotó el tiempo máximo del experimento'
                    (folder / 'DETENER').touch()
                if any(p.poll() not in (None, 0) for p in self.processes) and not (folder / 'DETENER').exists():
                    error = 'Falló un agente. Revisa su estado y su archivo de consola.'
                    (folder / 'DETENER').touch()
                if (folder / 'DETENER').exists():
                    if stop_at is None:
                        stop_at = time.monotonic()
                    # Primero se solicita una parada cooperativa mediante DETENER.
                    # Si un proceso no responde, se fuerza su cierre tras ocho segundos.
                    if time.monotonic() - stop_at > 8:
                        for p in self.processes:
                            if p.poll() is None:
                                p.terminate()
                time.sleep(.1)
            if error:
                status = 'failed'
            elif (folder / 'DETENER').exists():
                status = 'stopped'
            elif len(self.processes) == len(runtime.ids) and all(p.returncode == 0 for p in self.processes):
                # La referencia central se consulta después de terminar todos los
                # agentes. Su resultado nunca entra en sus actualizaciones.
                try:
                    evaluate(folder)
                except Exception as exc:
                    write_json(folder / 'evaluacion.json', dict(records_valid=False, complete=True,
                        convergence_evaluated=False, conclusion=f'Error de evaluación: {exc}'))
                status = 'completed'
            else:
                error = 'No terminaron correctamente todos los agentes'
        except Exception as exc:
            error = str(exc)
            if isinstance(exc, InterruptedError) or (folder/'DETENER').exists():
                status = 'stopped'
            (folder / 'DETENER').touch()
        finally:
            timing.abort(status)
            (folder/'FINALIZAR').touch()
            for p in self.processes + ([coordinator_process] if coordinator_process else []):
                if p.poll() is None:
                    p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            for stream in streams:
                stream.close()
            self.store.update_run(run_id, status=status, error=error, ended_at=now())
            with self.lock:
                self.active = None

    def stop(self):
        """Solicita la parada del ensayo activo; conserva sus resultados parciales."""
        with self.lock:
            if self.active:
                (self.store.folder(self.active) / 'DETENER').touch()
                self.store.update_run(self.active, status='stopping')

    def shutdown(self):
        """Intenta cerrar agentes y libera la carpeta al apagar la aplicación."""
        self.stop()
        if self.thread:
            self.thread.join(timeout=12)
        if self.thread is None or not self.thread.is_alive():
            self.instance_lock.close()

    def states(self, run_id):
        """Lee resúmenes; un proceso recién lanzado puede aún no haber escrito el suyo."""
        folder = self.store.folder(run_id)
        config = read_json(folder / 'config.json')
        return [read_json(folder / f'nodo_{n["id"]}.json',
                         dict(node=n['id'], pid='—', connection='Preparando proceso', status='pending',
                              round=0, steps=config['steps'], state={}, error=None))
                for n in config['nodes']]

    def export(self, run_id):
        """Empaqueta un ensayo detenido o terminado, sin mezclar inventario ni claves."""
        folder = self.store.folder(run_id)
        record = read_json(folder / 'ejecucion.json')
        if record['status'] in ('starting', 'running', 'stopping'):
            raise ValueError('Espera a que termine o detén el ensayo antes de exportarlo')
        export_csv(folder)
        target = self.store.root / 'exportaciones' / f'{run_id}.zip'
        target.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in folder.iterdir():
                if path.is_file() and path.suffix in ('.json', '.csv', '.txt', '.py', '.jsonl'):
                    archive.write(path, path.name)
        return target
