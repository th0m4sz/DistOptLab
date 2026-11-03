# Función de este módulo: Acuerda el inicio y documenta tiempos y alineación de relojes sin calcular estados del algoritmo.
"""Protocolo de medición v1. Las consultas de reloj ocurren antes y después del cálculo."""
import json
from pathlib import Path
import time
import uuid
from concurrent.futures import ThreadPoolExecutor


class LoopMetrics:
    """Costes observados del bucle; no cambian el reloj ni el paso del algoritmo."""
    def __init__(self):
        self.parts={k:0.0 for k in ['exchange_s','update_s','record_s','pacing_s','control_wait_s']}
        self.started=self.cpu_started=self.ended=self.cpu_ended=None

    def begin(self):
        self.started=time.perf_counter();self.cpu_started=time.process_time()

    def add(self,name,started):
        self.parts[name]+=time.perf_counter()-started

    def end(self):
        self.ended=time.perf_counter();self.cpu_ended=time.process_time()

    def summary(self,updates):
        elapsed=(self.ended or time.perf_counter())-self.started if self.started is not None else 0.0
        cpu=(self.cpu_ended if self.cpu_ended is not None else time.process_time())-self.cpu_started if self.cpu_started is not None else 0.0
        return dict(self.parts,updates=updates,loop_elapsed_s=elapsed,process_cpu_s=cpu,
                    other_s=max(0.0,elapsed-sum(self.parts.values())))

from .storage import read_json, write_json


def control_read(path):
    """SFTP puede estar escribiendo el archivo: un mensaje parcial aún no está listo."""
    try:
        return read_json(path)
    except json.JSONDecodeError:
        return None


class WorkerTiming:
    def __init__(self, config, folder, node, run_id):
        self.enabled = config.get('timing_protocol') == 1
        self.folder, self.node, self.run_id = Path(folder), node, run_id
        self.started = None
        self.last_query = None

    def service(self):
        if not self.enabled:
            return
        query = control_read(self.folder / f'tiempo_{self.node}_consulta.json')
        if not query or query.get('run_id') != self.run_id or query.get('nonce') == self.last_query:
            return
        stamp = time.monotonic()
        write_json(self.folder / f'tiempo_{self.node}_respuesta.json',
                   dict(run_id=self.run_id, nonce=query['nonce'], monotonic_s=stamp))
        self.last_query = query['nonce']

    def wait_start(self, check_stop):
        if not self.enabled:
            return
        info = time.get_clock_info('monotonic')
        write_json(self.folder / f'tiempo_{self.node}_listo.json', dict(
            run_id=self.run_id, node=self.node, clock=info.implementation,
            resolution_s=info.resolution, ready_monotonic_s=time.monotonic()))
        deadline = time.monotonic() + 120
        while True:
            check_stop()
            self.service()
            release = control_read(self.folder / 'tiempo_inicio.json')
            if release and release.get('run_id') == self.run_id:
                self.started = time.monotonic()
                return
            if time.monotonic() > deadline:
                raise TimeoutError('No llegó la señal de inicio de la medición')
            time.sleep(.005)

    def finish(self, last_sample, status):
        if self.enabled:
            write_json(self.folder / f'tiempo_{self.node}_final.json', dict(
                run_id=self.run_id, node=self.node, status=status,
                started_monotonic_s=self.started, last_sample_monotonic_s=last_sample,
                finished_monotonic_s=time.monotonic()))


class TimingSession:
    """El gestor usa un único reloj. read/write apuntan al disco local o a SFTP.

    En remoto, cada muestra m queda entre los instantes de envío a y recepción b
    de la laptop. offset=(a+b)/2-m; semiancho=(b-a)/2. Se conserva toda la evidencia.
    No se supone simetría de red para el intervalo de esa muestra. Entre muestras
    la alineación es una estimación: no certifica sincronización física exacta.
    """
    def __init__(self, folder, ids, run_id, remote=False, read=None, write=None, heartbeat=None):
        self.folder, self.ids, self.run_id = Path(folder), list(ids), run_id
        self.remote = remote
        self.read = read or (lambda i, name: control_read(self.folder / name))
        self.write = write or (lambda i, name, value: write_json(self.folder / name, value))
        self.heartbeat = heartbeat or (lambda: None)
        self.done = False
        self.data = dict(version=1, run_id=run_id, status='preparing',
                         basis='laptop_monotonic', remote=remote, nodes={},
                         origin_definition='Antes de enviar la señal de inicio, con todos los agentes preparados.',
                         end_definition='Última muestra registrada por el último agente; incluye comunicación y esperas del algoritmo.',
                         observed_definition='Hasta que el gestor detecta que todos completaron; incluye sondeo y transferencia de notificaciones.',
                         alignment_method='minimum_round_trip_offset' if remote else 'shared_system_clock',
                         drift_note='Offset inicial constante; contraste final. El margen es estimado, no una garantía entre calibraciones.')
        self.save()

    def save(self):
        write_json(self.folder / 'tiempos.json', self.data)

    def check_stop(self):
        if (self.folder / 'DETENER').exists():
            raise InterruptedError('Detenido durante la preparación temporal')
        self.heartbeat()

    def calibrate(self, node, count=5):
        samples = []
        for _ in range(count):
            self.check_stop()
            nonce = uuid.uuid4().hex
            before = time.monotonic()
            self.write(node, f'tiempo_{node}_consulta.json', dict(run_id=self.run_id, nonce=nonce))
            deadline = before + 10
            while True:
                self.check_stop()
                reply = self.read(node, f'tiempo_{node}_respuesta.json')
                after = time.monotonic()
                if reply and reply.get('run_id') == self.run_id and reply.get('nonce') == nonce:
                    remote_time = float(reply['monotonic_s'])
                    samples.append(dict(send_s=before, receive_s=after, remote_s=remote_time,
                                        offset_s=(before+after)/2-remote_time,
                                        half_round_trip_s=(after-before)/2))
                    break
                if after > deadline:
                    raise TimeoutError(f'No respondió el reloj del agente {node}')
                time.sleep(.005)
        return dict(best=min(samples, key=lambda s: s['half_round_trip_s']), samples=samples)

    def begin(self):
        deadline = time.monotonic() + 90
        pending = set(self.ids)
        while pending:
            self.check_stop()
            for node in list(pending):
                ready = self.read(node, f'tiempo_{node}_listo.json')
                if ready and ready.get('run_id') == self.run_id:
                    self.data['nodes'][str(node)] = dict(ready=ready)
                    pending.remove(node)
                else:
                    status = self.read(node, f'nodo_{node}.json') or {}
                    if status.get('status') in ('failed', 'stopped'):
                        raise RuntimeError(f'El agente {node} falló antes de iniciar: {status.get("error", "")}')
            if time.monotonic() > deadline:
                raise TimeoutError('No todos los agentes quedaron preparados para medir el tiempo')
            if pending:
                time.sleep(.02)
        for node in self.ids:
            entry = self.data['nodes'][str(node)]
            if self.remote:
                entry['calibration_start'] = self.calibrate(node)
                best = entry['calibration_start']['best']
                entry.update(offset_s=best['offset_s'], alignment_margin_s=best['half_round_trip_s'])
            else:
                entry.update(offset_s=0.0, alignment_margin_s=entry['ready']['resolution_s'])
        self.data.update(status='running', origin_monotonic_s=time.monotonic())
        # Persistir antes de liberar; el pequeño coste se incluye y es verificable.
        self.save()
        if self.remote:
            self.data['release_method']='parallel_sftp'
            self.save()
            with ThreadPoolExecutor(max_workers=len(self.ids)) as pool:
                list(pool.map(lambda node:self.write(node,'tiempo_inicio.json',dict(run_id=self.run_id)),self.ids))
        else:
            self.write(self.ids[0],'tiempo_inicio.json',dict(run_id=self.run_id))

    def complete(self):
        if self.done:
            return
        observed = time.monotonic()
        origin = self.data['origin_monotonic_s']
        self.data['observed_duration_s'] = observed-origin
        for node in self.ids:
            entry = self.data['nodes'][str(node)]
            final = self.read(node, f'tiempo_{node}_final.json')
            if not final or final.get('run_id') != self.run_id or final.get('status') != 'completed':
                raise ValueError(f'Falta la marca final válida del agente {node}')
            entry['final'] = final
            if self.remote:
                try:
                    entry['calibration_end'] = self.calibrate(node, count=3)
                    end = entry['calibration_end']['best']
                    entry['offset_change_s'] = end['offset_s']-entry['offset_s']
                    entry['alignment_margin_s'] = max(entry['alignment_margin_s'],
                        abs(entry['offset_change_s'])+end['half_round_trip_s'])
                except (OSError, ValueError, TimeoutError) as exc:
                    entry['calibration_end_error'] = str(exc)
            entry['start_s'] = max(0.0, final['started_monotonic_s']+entry['offset_s']-origin)
            entry['last_sample_s'] = max(0.0, final['last_sample_monotonic_s']+entry['offset_s']-origin)
        entries = list(self.data['nodes'].values())
        self.data.update(status='completed', duration_s=max(e['last_sample_s'] for e in entries),
                         alignment_margin_s=max(e['alignment_margin_s'] for e in entries),
                         start_spread_s=max(e['start_s'] for e in entries)-min(e['start_s'] for e in entries))
        self.done = True
        self.save()

    def abort(self, status):
        if not self.done:
            self.data['status'] = status
            self.save()
