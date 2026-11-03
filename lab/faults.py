# Función de este módulo: Valida fallas programadas y coordina sus etapas sin calcular estados del algoritmo.
"""Escenarios deterministas por índice de actualización, con barreras solo entre etapas."""
import copy
from .storage import read_json, write_json

# Margen operativo para comunicación y cambios de etapa, nunca un paso numérico.
SCENARIO_WAIT_S = 30
SCENARIO_VERSION = 2


def upgrade_scenario_config(config):
    """Adapta una configuración para un NUEVO ensayo; nunca modifica el historial.

    El formato 1 permitía otra respuesta y reiniciar a todos. Ambos comportamientos
    se retiraron: su importación usa retirada y reinicio exclusivo al regresar.
    """
    result = copy.deepcopy(config)
    value = result.get('faults')
    if not isinstance(value, dict) or value.get('version', 1) != 1:
        return result
    if value.get('policy', 'withdraw') not in ('withdraw', 'observe'):
        raise ValueError('Respuesta de fallas antigua no válida')
    state = value.get('state_policy', 'keep')
    if state not in ('keep', 'reset'):
        raise ValueError('Tratamiento de estados antiguo no válido')
    value.pop('policy', None)
    value.update(version=SCENARIO_VERSION,
                 state_policy='reset_returning' if state == 'reset' else 'keep')
    return result


class ScenarioInterrupted(Exception):
    """La comunicación requerida no puede continuar por una falla programada."""


class FaultPlan:
    def __init__(self, config):
        value = config.get('faults') or {}
        if not isinstance(value, dict):
            raise ValueError('El escenario de fallas debe ser un objeto JSON')
        self.enabled = bool(value.get('events'))
        self.ids = sorted(n['id'] for n in config['nodes'])
        self.steps = config['steps']
        self.state_policy = value.get('state_policy', 'keep')
        self.events = copy.deepcopy(value.get('events', []))
        if not isinstance(self.events, list) or len(self.events) > 128:
            raise ValueError('Declara como máximo 128 eventos de falla')
        if value and value.get('version') != SCENARIO_VERSION:
            raise ValueError('Configuración de fallas antigua: ábrela en el formulario para actualizarla antes de ejecutar')
        if 'policy' in value:
            raise ValueError('La respuesta de fallas ya no es configurable: los agentes no disponibles se excluyen siempre')
        if self.state_policy not in ('keep', 'reset_returning'):
            raise ValueError('Al regresar, elige conservar el estado o reiniciar solo los agentes reincorporados')
        occupied = {}
        for index, event in enumerate(self.events):
            if not isinstance(event, dict):
                raise ValueError(f'Evento {index+1}: se requiere un objeto JSON')
            start, end = event.get('start'), event.get('end')
            if type(start) is not int or not 1 <= start < self.steps:
                raise ValueError(f'Evento {index+1}: el inicio debe ser un entero entre 1 e iteraciones−1')
            if end is not None and (type(end) is not int or not start < end <= self.steps):
                raise ValueError(f'Evento {index+1}: la reincorporación debe ser posterior al inicio y no superar las iteraciones')
            target = event.get('target', 'agent')
            nodes = event.get('nodes', [])
            if target == 'coordinator':
                if config.get('execution_mode', 'sync') != 'coordinator':
                    raise ValueError('Solo un algoritmo coordinado permite fallar su coordinador')
                if end is not None:
                    raise ValueError('La falla del coordinador debe ser permanente: no hay recuperación automática de rondas bloqueadas')
                keys = ['coordinator']
            elif target == 'agent' and isinstance(nodes, list) and nodes and all(type(i) is int and i in self.ids for i in nodes) and len(set(nodes)) == len(nodes):
                keys = nodes
            else:
                raise ValueError(f'Evento {index+1}: selecciona agentes existentes sin repetirlos')
            event.update(id=f'evento_{index+1}', target=target)
            for key in keys:
                for a, b in occupied.setdefault(key, []):
                    if start < b and a < (end if end is not None else self.steps+1):
                        raise ValueError(f'Hay eventos superpuestos para {key}')
                occupied[key].append((start, end if end is not None else self.steps+1))
        self.boundaries = sorted({0} | {e['start'] for e in self.events} | {e['end'] for e in self.events if e.get('end') is not None})

    def phase(self, k):
        return max(b for b in self.boundaries if b <= k)

    def offline(self, node, k):
        return any(e['start'] <= k and (e.get('end') is None or k < e['end']) and
                   ((node == 'coordinator' and e['target'] == 'coordinator') or
                    (e['target'] == 'agent' and node in e['nodes'])) for e in self.events)

    def active(self, k):
        return [i for i in self.ids if not self.offline(i, k)]

    def participants(self, k):
        return self.active(k)


def set_context(runtime, k):
    plan = runtime.fault_plan
    runtime.scenario_round = k
    runtime.active_ids = plan.participants(k)
    runtime.available_ids = plan.active(k)
    runtime.active_neighbors = {i: {j: w for j, w in ns.items() if j in runtime.active_ids}
                                for i, ns in runtime.neighbors.items()}


def release_phase(folder, runtime, states, send=None):
    """El gestor libera una frontera cuando todos los agentes llegaron; nunca envía soluciones."""
    if not runtime.fault_plan.enabled or len(states) != len(runtime.ids):
        return
    ready = {s.get('phase_ready', -1) for s in states}
    if len(ready) != 1:
        return
    k = ready.pop()
    current = read_json(folder / 'FASE.json', {'released': -1})['released']
    if k in runtime.fault_plan.boundaries and k > current:
        value = dict(released=k)
        write_json(folder / 'FASE.json', value)
        (folder/f'FASE_{k}.LISTA').touch()
        if send:
            send(value)


def finished(states):
    return bool(states) and all(s['status'] in ('completed', 'fault_interrupted') for s in states)
