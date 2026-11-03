# Función de este módulo: Construye el algoritmo, valida su configuración y prepara los datos propios de cada agente.
"""Contrato de estado y configuración; cada algoritmo declara su forma de ejecución."""
from dataclasses import dataclass
import copy
import hashlib
import json
import math



def number(value, label):
    """Rechaza valores vacíos, booleanos, infinito y NaN antes de calcular."""
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{label}: se requiere un número finito')
    return float(value)


@dataclass(frozen=True)
class Field:
    """Describe un campo del formulario: clave interna, etiqueta y valor inicial."""
    key: str
    label: str
    default: float


class Runtime:
    """Interfaz que usa el agente; independiente de interfaz gráfica y almacenamiento."""
    id = ''
    name = ''
    description = ''
    parameter_help = ''  # Explicación de los parámetros específicos de este modelo.
    mode = 'sync'  # sync, async o coordinator; el algoritmo declara su ejecución.
    fields = ()      # Parámetros propios de cada agente.
    parameters = ()  # Parámetros comunes del experimento.
    metrics = ()     # Claves del estado que se guardarán en CSV y se dibujarán.
    evaluator = None  # Ruta de una función importada solo en el análisis posterior.

    def __init__(self, config):
        self.config = copy.deepcopy(config)
        self.coordinator_exchange = config.get('coordinator_exchange', 'sync')
        if self.coordinator_exchange not in ('sync', 'async'):
            raise ValueError('Intercambio del coordinador inválido: elige sync o async')
        if self.mode != 'coordinator' and self.coordinator_exchange != 'sync':
            raise ValueError('El intercambio del coordinador requiere un algoritmo con coordinador')
        self.asynchronous = self.mode == 'async' or (self.mode == 'coordinator' and self.coordinator_exchange == 'async')
        if config.get('schema_version') != 1:
            raise ValueError('Versión de configuración no soportada')
        if config.get('algorithm') != self.id:
            raise ValueError('El algoritmo y su configuración no coinciden')
        if not isinstance(config.get('name'), str) or not config['name'].strip():
            raise ValueError('Escribe un nombre para el experimento')
        self.steps = config['steps']
        if type(self.steps) is not int or self.steps < 1:
            raise ValueError('Las iteraciones deben ser un entero positivo')
        self.period = number(config['period_s'], 'Periodo')
        if self.period < 0:
            raise ValueError('El periodo no puede ser negativo')
        # Los workers reciben una vista local; el gestor conserva el ensayo completo.
        view = config.get('agent_view')
        self.local_id = view.get('node_id') if isinstance(view, dict) else None
        if view is not None and (type(self.local_id) is not int or self.local_id < 1):
            raise ValueError('Vista local de agente inválida')
        self.nodes = {}
        endpoints = set()
        for node in self.config['nodes']:
            i = node['id']
            if type(i) is not int or i < 1 or i in self.nodes:
                raise ValueError('Los identificadores de agente deben ser únicos y positivos')
            if not isinstance(node['host'], str) or not node['host'].strip():
                raise ValueError('Cada agente necesita un host')
            if type(node['port']) is not int or not 1 <= node['port'] <= 65535:
                raise ValueError('Puerto de agente inválido')
            if (node['host'], node['port']) in endpoints:
                raise ValueError('Dos agentes comparten el mismo host y puerto')
            endpoints.add((node['host'], node['port']))
            self.nodes[i] = node
        self.ids = sorted(self.nodes)
        from .faults import FaultPlan
        self.fault_plan = FaultPlan(dict(config, execution_mode=self.mode))
        self.active_ids = self.ids[:]
        self.available_ids = self.ids[:]
        self.scenario_round = 0
        if len(self.ids) < 1:
            raise ValueError('Se necesita al menos un agente')
        if view is not None:
            if self.local_id not in self.nodes or 'params' not in self.nodes[self.local_id]:
                raise ValueError('Faltan los parámetros del agente local')
            if any('params' in node or 'function_profile' in node for i, node in self.nodes.items() if i != self.local_id):
                raise ValueError('La vista local no debe incluir parámetros ajenos')
        self.neighbors = {i: {} for i in self.ids}
        if self.mode=='coordinator' and config['edges']:
            raise ValueError('El modo coordinador no utiliza enlaces entre vecinos: deja edges vacío')
        for edge in config['edges']:
            if len(edge) not in (2, 3):
                raise ValueError('Cada enlace contiene dos agentes y, opcionalmente, un peso')
            i, j = edge[:2]
            w = number(edge[2] if len(edge) == 3 else 1, 'Peso')
            if type(i) is not int or type(j) is not int or i == j or i not in self.nodes or j not in self.nodes or w <= 0:
                raise ValueError('Enlace inválido')
            if j in self.neighbors[i]:
                raise ValueError('Enlace duplicado')
            self.neighbors[i][j] = self.neighbors[j][i] = w
        self.active_neighbors = copy.deepcopy(self.neighbors)
        # Recorrido del grafo: comprobar conectividad antes de abrir conexiones.
        # Esto no garantiza que un algoritmo alcance su óptimo en ese grafo.
        seen, pending = set(), [self.ids[0]]
        while pending:
            i = pending.pop()
            if i not in seen:
                seen.add(i)
                pending.extend(self.neighbors[i])
        if self.mode != 'coordinator' and config.get('require_connected', False) and seen != set(self.ids):
            raise ValueError('La topología debe conectar a todos los agentes')
        # La huella permite rechazar mensajes de otra configuración, incluso
        # si coinciden los identificadores de sus agentes.
        if view is None:
            self.fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()
        else:
            # Cada vista es distinta, pero sus mensajes pertenecen al mismo ensayo.
            digest = view.get('experiment_sha256', '')
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Huella del ensayo inválida en la vista local')
            self.fingerprint = digest

    def initial_state(self, node_id):
        """Devuelve el estado inicial del agente indicado como diccionario numérico."""
        raise NotImplementedError

    def parameters_at(self, k):
        """Parámetros comunes para este índice, sin modificar la configuración."""
        if self.parameter_schedule.key is None:
            return copy.deepcopy(self.parameters_values)
        return self.parameter_schedule.at(k)

    def update(self, node_id, own, peers, k=0, global_data=None):
        """Calcula el estado propio en k+1 usando own y vecinos de la ronda k.

        peers tiene la forma {id_vecino: estado}. No debe calcular ni modificar
        los estados de los otros agentes. Debe ser determinista para verificarse.
        """
        raise NotImplementedError

    def check_state(self, node_id, state):
        """Valida el estado propio o un registro en el contexto de evaluación."""
        raise NotImplementedError

    def check_received_state(self, node_id, state):
        """Valida el formato de un mensaje sin consultar parámetros privados."""
        raise NotImplementedError


def agent_config(runtime, node_id):
    """Configuración mínima del worker: datos comunes, red y parámetros propios.

    La lista explícita impide copiar metadatos o campos privados adicionales del
    formulario. Es separación de datos del runtime, no un sandbox de Python.
    """
    if runtime.local_id is not None or node_id not in runtime.nodes:
        raise ValueError('La vista local se genera desde el ensayo completo')
    public_keys = ('schema_version', 'algorithm', 'name', 'steps', 'period_s',
                   'parameters', 'edges', 'execution_mode', 'coordinator_exchange', 'clock_origin',
                   'plugin_sha256', 'algorithm_name', 'topology', 'require_connected',
                   'execution_target', 'clock_scope', 'faults', 'timing_protocol', 'demand_schedule')
    config = {key: copy.deepcopy(runtime.config[key]) for key in public_keys if key in runtime.config}
    if runtime.mode == 'coordinator':
        endpoint = runtime.config['coordinator']
        config['coordinator'] = {key: endpoint[key] for key in ('host', 'port')}
    config['nodes'] = []
    for i, node in runtime.nodes.items():
        entry = {key: node[key] for key in ('id', 'host', 'port')}
        if i == node_id:
            entry['params'] = copy.deepcopy(node['params'])
            if 'function_profile' in node:
                entry['function_profile'] = node['function_profile']
        if 'timing' in node:
            entry['timing'] = {key: copy.deepcopy(node['timing'][key])
                               for key in ('period_factor', 'send_delay_ms') if key in node['timing']}
        config['nodes'].append(entry)
    config['agent_view'] = dict(node_id=node_id, experiment_sha256=runtime.fingerprint)
    return config


REGISTRY = {}
LOAD_ERRORS = {}

def build(config, plugin_path=None):
    """Selecciona el adaptador instalado y valida la configuración completa."""
    if plugin_path is not None:
        from .plugins import PluginSpec
        spec = PluginSpec(plugin_path)
        if spec.id != config.get('algorithm') or spec.sha256 != config.get('plugin_sha256'):
            raise ValueError('La copia del algoritmo no coincide con la huella del ensayo')
        return spec(config)
    if config.get('algorithm') not in REGISTRY:
        refresh_registry()
    if config.get('algorithm') not in REGISTRY:
        raise ValueError('Algoritmo no instalado')
    try:
        spec = REGISTRY[config['algorithm']]
        if config.get('plugin_sha256') and config['plugin_sha256'] != getattr(spec, 'sha256', None):
            raise ValueError('Esta configuración pertenece a otra versión del archivo de algoritmo')
        return spec(config)
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Configuración incompleta o inválida: {exc}') from exc


def topology_edges(ids, topology):
    """Genera enlaces no dirigidos; cada pareja aparece una sola vez."""
    if topology == 'estrella':
        return [[ids[0], i] for i in ids[1:]]
    if topology == 'anillo':
        return [[ids[i], ids[i + 1]] for i in range(len(ids) - 1)] + ([[ids[0], ids[-1]]] if len(ids) > 2 else [])
    if topology == 'completa':
        return [[i, j] for index, i in enumerate(ids) for j in ids[index + 1:]]
    if topology == 'personalizada':
        # Una cadena conectada sirve de punto de partida editable. El campo
        # edges, no el nombre de la plantilla, define las conexiones reales.
        return [[ids[i], ids[i + 1]] for i in range(len(ids) - 1)]
    raise ValueError('Topología desconocida')


def example(algorithm_id=None, n=4, topology='anillo'):
    """Construye un formulario solo con los valores declarados por el usuario."""
    if type(n) is not int or n < 1:
        raise ValueError('El número de agentes debe ser un entero positivo')
    refresh_registry()
    if algorithm_id not in REGISTRY:
        raise ValueError('Carga primero un archivo de algoritmo')
    return REGISTRY[algorithm_id].make_example(n, topology)


def refresh_registry():
    from .plugins import discover
    found, errors = discover()
    REGISTRY.clear()
    REGISTRY.update(found)
    LOAD_ERRORS.clear()
    LOAD_ERRORS.update(errors)


def build_saved(config, folder):
    from pathlib import Path
    return build(config, Path(folder) / 'algoritmo.py')
