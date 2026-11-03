# Función de este módulo: Transporta estados por TCP para últimas muestras y para el coordinador explícito.
"""TCP para últimas muestras y para agregación por un coordinador explícito.

Se mantiene el protocolo por rondas del motor anterior para modo sync. Este
módulo no contiene ecuaciones: transporta estados y verifica su identidad.
"""
import copy
import json
import math
import socket
import socketserver
import threading
import time
from .faults import ScenarioInterrupted


def encode(value):
    return (json.dumps(value,allow_nan=False,separators=(',',':'))+'\n').encode()


def read(stream):
    line = stream.readline(1_048_577)
    if not line:
        raise EOFError('Conexión cerrada')
    if len(line)>1_048_576 or not line.endswith(b'\n'):
        raise ValueError('Mensaje demasiado grande o incompleto')
    value = json.loads(line)
    if not isinstance(value,dict):
        raise ValueError('Se esperaba un objeto JSON')
    return value


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.connection.settimeout(2)
        try:
            while True:
                request = read(self.rfile)
                try:
                    reply = self.server.respond(request)
                except Exception as exc:
                    reply = dict(status='error',reason=str(exc))
                self.wfile.write(encode(reply))
                self.wfile.flush()
        except (OSError,EOFError,ValueError):
            return


def serve(address, respond):
    server = Server(address,Handler)
    server.respond = respond
    threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
    return server


class Endpoint:
    def __init__(self,runtime,run_id):
        self.runtime, self.run_id = runtime,run_id
        self.lock = threading.Lock()

    def identity(self,request):
        if request.get('run') != self.run_id or request.get('config') != self.runtime.fingerprint or request.get('protocol') != 2:
            raise ValueError('Identidad del ensayo incorrecta')

    def reply(self,**values):
        return dict(protocol=2,run=self.run_id,config=self.runtime.fingerprint,**values)


class Latest(Endpoint):
    def __init__(self,runtime,i,run_id):
        super().__init__(runtime,run_id)
        self.i, self.k, self.state, self.error = i,0,{},None
        self.phases = {}
        self.changed=threading.Condition(self.lock)

    def publish(self,k,state):
        with self.lock:
            self.k,self.state = k,dict(state)
            if self.runtime.fault_plan.enabled:
                self.phases[self.runtime.fault_plan.phase(k)] = (k,dict(state))
                for old in sorted(self.phases)[:-2]:
                    del self.phases[old]
            self.changed.notify_all()

    def fail(self,message):
        with self.lock:
            self.error = message
            self.changed.notify_all()

    def respond(self,request):
        self.identity(request)
        if type(request.get('from')) is not int or request['from'] not in self.runtime.neighbors[self.i]:
            raise ValueError('El solicitante no es vecino')
        with self.lock:
            after=request.get('after_version')
            if after is not None and (type(after) is not int or not 0<=after<=self.runtime.steps):
                raise ValueError('Versión de recepción inválida')
            phase=request.get('phase',0)
            # Solo espera el hilo de recepción TCP. snapshot() del agente
            # continúa usando la última muestra disponible, sin barrera.
            if after is not None and not self.error:
                def changed():
                    if self.error:return True
                    if self.runtime.fault_plan.enabled:
                        return phase not in self.phases or self.phases[phase][0]!=after
                    return self.k!=after
                self.changed.wait_for(changed,timeout=.1)
            if self.error:
                raise ValueError(self.error)
            if self.runtime.fault_plan.enabled:
                phase = request.get('phase', 0)
                if type(phase) is not int or phase not in self.runtime.fault_plan.boundaries:
                    raise ValueError('Etapa no válida')
                if self.runtime.fault_plan.offline(self.i, phase) or phase not in self.phases:
                    return self.reply(status='unavailable', node=self.i)
                version,state = self.phases[phase]
                return self.reply(status='ok',node=self.i,version=version,state=state,phase=phase)
            return self.reply(status='ok',node=self.i,version=self.k,state=dict(self.state))


class Connection:
    """Conexión persistente; los reintentos los controla cada política de ejecución."""
    def __init__(self,address,runtime,run_id,i):
        self.address,self.runtime,self.run_id,self.i = address,runtime,run_id,i
        self.sock = self.stream = None

    def close(self):
        if self.stream:
            self.stream.close()
        if self.sock:
            self.sock.close()
        self.stream=self.sock=None

    def request(self,**data):
        try:
            if self.sock is None:
                self.sock=socket.create_connection(self.address,timeout=.5)
                self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                self.stream=self.sock.makefile('rb')
            self.sock.sendall(encode(dict(protocol=2,run=self.run_id,config=self.runtime.fingerprint,**{'from':self.i},**data)))
            reply=read(self.stream)
            if reply.get('status')=='error':
                raise ValueError(reply.get('reason','Error remoto'))
            if reply.get('run')!=self.run_id or reply.get('config')!=self.runtime.fingerprint or reply.get('protocol')!=2:
                raise ValueError('Respuesta de otro ensayo')
            if reply.get('status') not in ('ok','wait','unavailable','interrupted'):
                raise ValueError('Estado de respuesta desconocido')
            return reply
        except (OSError,EOFError):
            self.close()
            raise


class Inbox:
    """Un hilo de recepción por vecino evita frenar el cálculo por cada consulta.

Después de recibir una primera muestra, snapshot() nunca espera la ronda k.
Un corte permite seguir usando el dato almacenado. Se registra desde cuándo
se observó esa versión (age_s); no se confunde con latencia de red unidireccional.
"""
    def __init__(self,runtime,i,run_id):
        self.runtime,self.i = runtime,i
        self.stop=threading.Event()
        self.lock=threading.Lock()
        self.cache,self.errors = {},{}
        self.phase = 0
        self.phase_cache = {}
        self.threads=[]
        for j in runtime.neighbors[i]:
            node=runtime.nodes[j]
            connection=Connection((node['host'],node['port']),runtime,run_id,i)
            thread=threading.Thread(target=self.receive,args=(j,connection),daemon=True)
            self.threads.append(thread)
            thread.start()

    def receive(self,j,connection):
        # El retardo pertenece al emisor j. Se espera en este hilo de
        # comunicación; el bucle matemático del receptor continúa usando la
        # última muestra almacenada, como corresponde al modo asíncrono.
        send_delay = self.runtime.nodes[j].get('timing', {}).get('send_delay_ms', 0) / 1000
        try:
            while not self.stop.is_set():
                try:
                    with self.lock:
                        requested_phase = self.phase
                    if self.runtime.fault_plan.enabled and (self.runtime.fault_plan.offline(self.i, requested_phase)
                                                            or self.runtime.fault_plan.offline(j, requested_phase)):
                        self.stop.wait(.005)
                        continue
                    with self.lock:
                        cached=self.phase_cache.get((requested_phase,j)) if self.runtime.fault_plan.enabled else self.cache.get(j)
                    request={'after_version':cached['version']} if cached else {}
                    if self.runtime.fault_plan.enabled:request['phase']=requested_phase
                    reply=connection.request(**request)
                    if reply.get("status") == "unavailable" and self.runtime.fault_plan.enabled:
                        self.stop.wait(.001)
                        continue
                    if reply.get('node')!=j or type(reply.get('version')) is not int or reply['version']<0 or reply['version']>self.runtime.steps:
                        raise ValueError('Identidad o versión de vecino inválida')
                    state=self.runtime.check_received_state(j,reply['state'])
                    with self.lock:
                        previous=self.cache.get(j)
                        is_new=not previous or reply['version']!=previous['version']
                    if is_new and send_delay and self.stop.wait(send_delay):
                        return
                    with self.lock:
                        old=self.cache.get(j)
                        if old and reply['version']<old['version']:
                            raise ValueError('El vecino retrocedió de versión')
                        # Mantener seen si la versión no cambia: refrescar la misma
                        # muestra no significa que el vecino haya vuelto a calcular.
                        seen=old['seen'] if old and old['version']==reply['version'] else time.monotonic()
                        self.cache[j]=dict(state=state,version=reply['version'],seen=seen)
                        if self.runtime.fault_plan.enabled:
                            if reply.get('phase') != requested_phase:
                                raise ValueError('Respuesta de otra etapa')
                            self.phase_cache[(requested_phase,j)] = copy.deepcopy(self.cache[j])
                except (OSError,EOFError):
                    pass  # Desconexión transitoria: conservar la última muestra.
                except Exception as exc:
                    with self.lock:
                        self.errors[j]=str(exc)
                    return
                self.stop.wait(.001)
        finally:
            connection.close()

    def scenario_snapshot(self, phase, neighbors):
        with self.lock:
            self.phase = phase
            if self.errors:
                raise ValueError(str(self.errors))
            source = {j:self.phase_cache.get((phase,j)) for j in neighbors}
            if any(v is None for v in source.values()):
                return None
            result = copy.deepcopy(source)
        current=time.monotonic()
        for value in result.values():
            value["age_s"]=current-value.pop("seen")
        return result

    def snapshot(self):
        with self.lock:
            if self.errors:
                raise ValueError(str(self.errors))
            if len(self.cache)!=len(self.runtime.neighbors[self.i]):
                return None
            result=copy.deepcopy(self.cache)
        now=time.monotonic()
        for value in result.values():
            value['age_s']=now-value.pop('seen')
        return result

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=1)


class Coordinator(Endpoint):
    """Intercambio por ronda o por últimas muestras, independiente de las ecuaciones."""
    def __init__(self,runtime,run_id):
        super().__init__(runtime,run_id)
        self.rounds,self.results={},{}
        self.latest=-1
        self.samples, self.async_results = {}, {}
        self.sequence = 0
        self.changed=threading.Condition(self.lock)

    def respond_latest(self, i, k, state, publish_only=False):
        plan = self.runtime.fault_plan
        phase = plan.phase(k) if plan.enabled else 0
        expected = plan.participants(k) if plan.enabled else self.runtime.ids
        if i not in expected:
            raise ValueError('Un agente retirado intentó participar')
        with self.lock:
            cache = self.samples.setdefault(phase, {})
            old = cache.get(i)
            if old and (k < old['version'] or (k == old['version'] and state != old['state'])):
                raise ValueError('Versión de agente retrocedida o estado modificado')
            if not old or k != old['version']:
                cache[i] = dict(version=k, state=copy.deepcopy(state), seen=time.monotonic())
            if publish_only:
                if k != self.runtime.steps:
                    raise ValueError('La publicación final requiere el último índice')
                return self.reply(status='ok', round=k, published=True)
            if not all(j in cache for j in expected):
                return self.reply(status='wait')
            token = (phase, i, k)
            if token not in self.async_results:
                if plan.enabled:
                    from .faults import set_context
                    set_context(self.runtime, k)
                aggregate = self.runtime.aggregate(k, {j:copy.deepcopy(cache[j]['state']) for j in expected})
                stamp = time.monotonic()
                sources = {str(j):dict(version=cache[j]['version'], age_s=max(0,stamp-cache[j]['seen'])) for j in expected}
                self.sequence += 1
                self.async_results[token] = self.reply(status='ok',round=k,aggregate=aggregate,
                    coordinator=dict(sequence=self.sequence,phase=phase,sources=sources))
                # Reintentos de una misma petición reciben exactamente su respuesta.
                for key in list(self.async_results):
                    if key[0] != phase or (key[1] == i and key[2] < k-1):
                        del self.async_results[key]
                for old_phase in list(self.samples):
                    if old_phase != phase:
                        del self.samples[old_phase]
            return copy.deepcopy(self.async_results[token])

    def respond(self,request):
        self.identity(request)
        i,k=request.get('from'),request.get('round')
        latest = self.runtime.coordinator_exchange == 'async'
        if type(i) is not int or i not in self.runtime.nodes or type(k) is not int or not 0<=k<self.runtime.steps+int(latest):
            raise ValueError('Agente o ronda inválida')
        plan = self.runtime.fault_plan
        if plan.enabled and plan.offline('coordinator', k):
            return self.reply(status='interrupted', round=k,
                              reason='La falla programada impide reunir la ronda del coordinador')
        state=self.runtime.check_state(i,request['state'])
        if latest:
            return self.respond_latest(i,k,state,request.get('publish_only') is True)
        with self.lock:
            if k<self.latest-2 or k>self.latest+1:
                raise ValueError('Ronda del coordinador fuera de secuencia')
            states=self.rounds.setdefault(k,{})
            if i in states and state!=states[i]:
                raise ValueError('Un agente cambió una instantánea ya enviada')
            states[i]=state
            expected = self.runtime.fault_plan.participants(k) if self.runtime.fault_plan.enabled else self.runtime.ids
            if i not in expected:
                raise ValueError("Un agente retirado intentó participar en esta ronda")
            if set(states)==set(expected) and k not in self.results:
                if self.runtime.fault_plan.enabled:
                    from .faults import set_context
                    set_context(self.runtime, k)
                self.results[k]=self.runtime.aggregate(k,copy.deepcopy(states))
                self.latest=max(self.latest,k)
                self.changed.notify_all()
                for old in list(self.rounds):
                    if old<k-2:
                        del self.rounds[old]
                        self.results.pop(old,None)
            if k not in self.results:
                self.changed.wait_for(lambda:k in self.results,timeout=.1)
            return self.reply(status='ok',round=k,aggregate=self.results[k]) if k in self.results else self.reply(status='wait')


class CoordinatorClient(Connection):
    def publish_final(self,k,state,timeout,check_stop=None):
        """Conserva el estado terminal para agentes lentos, sin otra actualización."""
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if check_stop:
                check_stop()
            try:
                result=self.request(round=k,state=state,publish_only=True)
                if result.get('status')=='ok' and result.get('round')==k and result.get('published') is True:
                    return
                raise ValueError('Confirmación final del coordinador no válida')
            except (OSError,EOFError):
                time.sleep(.001)
        raise TimeoutError('El coordinador no confirmó el estado terminal')

    def fetch(self,k,state,timeout,check_stop=None):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if check_stop:
                check_stop()
            try:
                result=self.request(round=k,state=state)
                if result['status']=='interrupted':
                    plan=self.runtime.fault_plan
                    if (result.get('round')!=k or not plan.enabled or
                            not plan.offline('coordinator',k)):
                        raise ValueError('Aviso de interrupción del coordinador no válido')
                    raise ScenarioInterrupted(result.get('reason','Interrupción por falla programada'))
                if result['status']=='ok':
                    if result.get('round')!=k:
                        raise ValueError('Agregado de otra ronda')
                    if self.runtime.coordinator_exchange == 'async':
                        trace = result.get('coordinator')
                        expected = self.runtime.fault_plan.participants(k) if self.runtime.fault_plan.enabled else self.runtime.ids
                        if not isinstance(trace,dict) or type(trace.get('sequence')) is not int or trace['sequence'] < 1:
                            raise ValueError('Traza de coordinador no válida')
                        if trace.get('phase') != self.runtime.fault_plan.phase(k) or set(trace.get('sources',{})) != {str(j) for j in expected}:
                            raise ValueError('Participantes o etapa del coordinador incorrectos')
                        for j,sample in trace['sources'].items():
                            if (type(sample.get('version')) is not int or not 0<=sample['version']<=self.runtime.steps
                                    or type(sample.get('age_s')) not in (int,float) or not math.isfinite(sample['age_s']) or sample['age_s']<0):
                                raise ValueError('Versión o antigüedad del coordinador incorrecta')
                            if self.runtime.fault_plan.phase(sample['version']) != trace['phase']:
                                raise ValueError('Muestra del coordinador de otra etapa')
                        if trace['sources'][str(self.i)]['version'] != k:
                            raise ValueError('El agregado no incluye el estado enviado por este agente')
                        self.last_trace = copy.deepcopy(trace)
                    return result['aggregate']
            except (OSError,EOFError):
                pass
            time.sleep(.001)
        if check_stop:
            check_stop()
        raise TimeoutError(f'El coordinador no completó la ronda {k}')
