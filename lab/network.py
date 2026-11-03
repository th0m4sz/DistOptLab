# Función de este módulo: Comunica agentes por TCP en modo síncrono: publica estados y solicita la ronda exacta del vecino.
"""TCP JSON por lineas, snapshots inmutables por ronda, sin coordinador."""
import json
import socket
import socketserver
import threading
import time
import copy
import queue
from collections import deque
from .faults import ScenarioInterrupted

MAX_LINE = 1_048_576


class ProtocolError(RuntimeError):
    """Indica que un mensaje recibido no cumple las reglas del protocolo."""
    pass


def encode(message):
    """Convierte un diccionario de Python en una linea JSON para enviarla."""
    return (json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def read_message(stream):
    """Lee una linea recibida y la convierte nuevamente en diccionario."""
    line = stream.readline(MAX_LINE + 1)
    if not line:
        raise EOFError("Conexion cerrada")
    if len(line) > MAX_LINE or not line.endswith(b"\n"):
        raise ProtocolError("Mensaje demasiado largo o sin delimitador")
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ProtocolError("Se esperaba objeto JSON")
    return message


class SnapshotStore:
    """Guarda los estados recientes que esta placa ofrece a sus vecinos."""

    def __init__(self, model, node_id, run_id):
        self.model, self.node_id, self.run_id = model, node_id, run_id

        # Varios vecinos pueden preguntar al mismo tiempo; el candado evita choques.
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.history = {}
        self.failed = None
        self.interrupted = None

    def publish(self, k, state):
        """Publica el estado de esta placa para la ronda k."""
        with self.lock:
            self.history[k] = dict(state)
            # Vecinos adyacentes difieren como maximo una ronda. Retenemos margen.
            for old in list(self.history):
                if old < k - 2:
                    del self.history[old]
            self.changed.notify_all()

    def fail(self, message):
        """Marca el nodo como fallido para avisar a sus vecinos."""
        with self.lock:
            self.failed = message
            self.changed.notify_all()

    def interrupt(self, message):
        """Propaga el cierre previsto del escenario sin confundirlo con un error."""
        with self.lock:
            self.interrupted = message
            self.changed.notify_all()

    def respond(self, request):
        """Construye la respuesta a la solicitud de un vecino."""
        with self.lock:
            # Rechazar placas que ejecuten otro ensayo o configuracion.
            if (request.get("protocol") != 1 or request.get("config") != self.model.fingerprint
                    or request.get("run") != self.run_id):
                return {"status": "error", "reason": "Configuracion, protocolo o run-id diferente"}

            # Solo un vecino declarado en la topologia puede pedir datos.
            sender = request.get("from")
            if type(sender) is not int or sender not in self.model.neighbors[self.node_id]:
                return {"status": "error", "reason": "Solicitante no es vecino"}
            k = request.get("round")
            if type(k) is not int or k < 0:
                return {"status": "error", "reason": "Ronda invalida"}

            # El hilo TCP espera una publicación, sin bloquear al agente que
            # calcula. Se sigue entregando exclusivamente la ronda solicitada.
            if k not in self.history and not self.failed and not self.interrupted:
                self.changed.wait_for(lambda: k in self.history or self.failed or self.interrupted,
                                      timeout=.1)

            # Informar si este nodo ya se detuvo por un error.
            if self.failed:
                return {"status": "error", "reason": "Nodo detenido: " + self.failed}

            if self.model.fault_plan.enabled:
                control = dict(protocol=1, run=self.run_id, config=self.model.fingerprint,
                               node=self.node_id, round=k)
                if self.interrupted:
                    return dict(control, status='interrupted', reason=self.interrupted)
                if self.model.fault_plan.offline(self.node_id, k):
                    return dict(control, status='unavailable', reason='Agente en falla programada')
            # Entregar el estado si la ronda solicitada ya esta disponible.
            if k in self.history:
                return {"status": "ok", "protocol": 1, "run": self.run_id,
                        "config": self.model.fingerprint, "node": self.node_id,
                        "round": k, "state": self.history[k]}
            if self.history and k < min(self.history):
                return {"status": "error", "reason": "Ronda expirada; reiniciar TODOS con otro run-id"}

            # El vecino debe volver a preguntar porque esta placa aun no llega a k.
            return {"status": "wait"}


class RoundExchange:
    """Publica cada ronda por TCP; el paso espera localmente esa ronda de todos sus vecinos."""
    def __init__(self,model,node_id,run_id):
        self.model,self.node_id,self.run_id=model,node_id,run_id
        self.lock=threading.Condition()
        self.stop=threading.Event()
        self.history={i:{} for i in model.neighbors[node_id]}
        self.error=None;self.current_k=0
        self.sockets=set();self.queues={i:queue.Queue() for i in self.history}
        self.threads=[]
        for i in self.history:
            thread=threading.Thread(target=self._send,args=(i,),daemon=True)
            self.threads.append(thread);thread.start()

    def _active(self,peer,k):
        plan=self.model.fault_plan
        return not plan.enabled or (not plan.offline(self.node_id,k) and not plan.offline(peer,k))

    def publish(self,k,state):
        with self.lock:self.current_k=k
        message=dict(protocol=3,run=self.run_id,config=self.model.fingerprint,
                     **{'from':self.node_id},round=k,state=copy.deepcopy(state))
        for peer,pending in self.queues.items():
            if self._active(peer,k):pending.put(message)

    def _send(self,peer):
        sock=None;recent=deque(maxlen=3);last=None
        address=self.model.nodes[peer]
        try:
            while not self.stop.is_set():
                try:message=self.queues[peer].get(timeout=.2)
                except queue.Empty:message=last
                if message is None:continue
                with self.lock:current=self.current_k
                if not self._active(peer,current):continue
                if self.model.fault_plan.enabled and self.model.fault_plan.phase(message['round'])!=self.model.fault_plan.phase(current):continue
                while not self.stop.is_set():
                    try:
                        if sock is None:
                            sock=socket.create_connection((address['host'],address['port']),timeout=.5)
                            sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                            for previous in recent:sock.sendall(encode(previous))
                        sock.sendall(encode(message))
                        if last is None or message['round']!=last['round']:recent.append(message)
                        last=message
                        break
                    except OSError:
                        if sock:sock.close()
                        sock=None
                        self.stop.wait(.05)
        finally:
            if sock:sock.close()

    def attach(self,sock):
        with self.lock:
            if self.stop.is_set():
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            else:self.sockets.add(sock)

    def detach(self,sock):
        with self.lock:self.sockets.discard(sock)

    def respond(self,message):
        peer,k=message.get('from'),message.get('round')
        if (message.get('protocol')!=3 or message.get('run')!=self.run_id or
                message.get('config')!=self.model.fingerprint or type(peer) is not int or peer not in self.history or
                type(k) is not int or not 0<=k<=self.model.steps):
            raise ProtocolError('Publicación de ronda o vecino inválida')
        state=self.model.check_received_state(peer,message.get('state'))
        with self.lock:
            history=self.history[peer]
            if k in history and history[k]!=state:
                self.error='Un vecino cambió una ronda publicada'
            elif not history or k>=max(history)-2:
                history[k]=copy.deepcopy(state)
                for old in list(history):
                    if old<max(history)-2:del history[old]
            self.lock.notify_all()
        return None

    def fetch(self,k,timeout,check_stop=None,neighbors=None):
        ids=list(self.history if neighbors is None else neighbors)
        deadline=time.monotonic()+timeout
        with self.lock:
            while not all(k in self.history[i] for i in ids):
                if self.error:raise ProtocolError(self.error)
                if check_stop:check_stop()
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    missing=[i for i in ids if k not in self.history[i]]
                    raise TimeoutError(f'No llegó la ronda {k} de los vecinos {missing}')
                self.lock.wait(min(.05,remaining))
            if self.error:raise ProtocolError(self.error)
            return {i:copy.deepcopy(self.history[i][k]) for i in ids}

    def fail(self,message):
        with self.lock:self.error=message;self.lock.notify_all()

    def interrupt(self,message):self.fail(message)

    def close(self):
        self.stop.set()
        with self.lock:sockets=list(self.sockets)
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        for thread in self.threads:thread.join(timeout=1)


class PeerServer(socketserver.ThreadingTCPServer):
    """Servidor TCP que puede atender a varios vecinos simultaneamente."""
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


class Handler(socketserver.StreamRequestHandler):
    """Atiende una conexion entrante de otra placa."""

    def handle(self):
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connection.settimeout(5)
        attached=False
        try:
            while True:
                # Leer solicitud, buscar la respuesta y devolverla por TCP.
                request = read_message(self.rfile)
                reply=self.server.store.respond(request)
                if reply is None:
                    if not attached:
                        self.server.store.attach(self.connection);attached=True
                        self.connection.settimeout(None)
                else:
                    self.wfile.write(encode(reply))
                    self.wfile.flush()
        except (OSError, EOFError, ValueError, ProtocolError):
            return
        finally:
            if attached:self.server.store.detach(self.connection)


def serve(store, bind="0.0.0.0"):
    """Inicia en segundo plano el servidor de esta placa."""
    # Cada placa escucha en el host y puerto definidos para su nodo.
    address = (bind, store.model.nodes[store.node_id]["port"])
    server = PeerServer(address, Handler)
    server.store = store

    # El hilo permite que nodo.py siga calculando mientras el servidor responde.
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    return server


class PeerClient:
    """Cliente usado por esta placa para consultar a uno de sus vecinos."""

    def __init__(self, model, own_id, peer_id, run_id):
        self.model, self.own_id, self.peer_id, self.run_id = model, own_id, peer_id, run_id

        # Direccion .local y puerto del vecino.
        p = model.nodes[peer_id]
        self.address = (p["host"], p["port"])
        self.sock = self.stream = None

    def close(self):
        """Cierra la conexion actual con el vecino."""
        if self.stream:
            self.stream.close()
        if self.sock:
            self.sock.close()
        self.stream = self.sock = None

    def fetch(self, k, timeout, check_stop=None):
        """Solicita al vecino su estado de la ronda k y espera hasta recibirlo."""
        deadline = time.monotonic() + timeout
        last_error = "el vecino aun no publica la ronda"

        # La solicitud identifica ensayo, configuracion, remitente y ronda.
        request = {"protocol": 1, "config": self.model.fingerprint, "run": self.run_id,
                   "from": self.own_id, "round": k}
        while time.monotonic() < deadline:
            if check_stop:
                check_stop()
            try:
                remaining = max(.001, deadline - time.monotonic())
                if self.sock is None:
                    # Abrir la conexion TCP la primera vez o despues de un corte.
                    self.sock = socket.create_connection(self.address, timeout=min(1, remaining))
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.stream = self.sock.makefile("rb")
                self.sock.settimeout(min(1, remaining))
                self.sock.sendall(encode(request))
                reply = read_message(self.stream)

                # Un error remoto detiene el ensayo para no mezclar datos incorrectos.
                if reply.get("status") == "error":
                    raise ProtocolError(f"Vecino {self.peer_id}: {reply.get('reason')}")
                if reply.get('status') in ('unavailable', 'interrupted'):
                    if (not self.model.fault_plan.enabled or reply.get('protocol') != 1
                            or reply.get('config') != self.model.fingerprint or reply.get('run') != self.run_id
                            or reply.get('node') != self.peer_id or reply.get('round') != k
                            or (reply['status'] == 'unavailable' and not self.model.fault_plan.offline(self.peer_id, k))):
                        raise ProtocolError('Aviso de falla programada no válido')
                    raise ScenarioInterrupted(f'Agente {self.peer_id}, ronda {k}: {reply.get("reason")}')
                if reply.get("status") == "ok":
                    # Confirmar que la respuesta pertenece al vecino y ronda esperados.
                    if (reply.get("protocol") != 1 or reply.get("config") != self.model.fingerprint
                            or reply.get("run") != self.run_id or reply.get("node") != self.peer_id
                            or type(reply.get("round")) is not int or reply["round"] != k):
                        raise ProtocolError("Identidad o ronda de respuesta incorrecta")
                    try:
                        # El emisor valida sus ecuaciones; aquí se comprueba JSON finito.
                        return self.model.check_received_state(self.peer_id, reply["state"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ProtocolError("Estado remoto invalido") from exc
                if reply.get("status") != "wait":
                    raise ProtocolError("Respuesta desconocida")
            except (OSError, EOFError) as exc:
                # Si se corta la conexion, cerrarla e intentar nuevamente.
                last_error = str(exc)
                self.close()
            except (ValueError, KeyError, TypeError) as exc:
                raise ProtocolError("JSON remoto invalido") from exc
            time.sleep(.005)

        # No se recibio el estado antes de agotar el tiempo permitido.
        if check_stop:
            check_stop()
        raise TimeoutError(f"Vecino {self.peer_id}, ronda {k}: {last_error}")


