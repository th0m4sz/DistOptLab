# Función de este módulo: Carga el archivo Python del algoritmo y conecta sus funciones con el ejecutor.
"""Contrato extensible: descripción sin ejecutar código y estado JSON completo."""
import ast
import copy
from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from types import ModuleType

from .algorithms import Runtime, number, topology_edges
from .profiles import profile_options, assigned_profile

DIRECTORY = Path(__file__).resolve().parents[1] / 'algoritmos'


def json_value(value, label='valor'):
    """JSON estricto, sin pérdida de claves ni conversión silenciosa de objetos."""
    if value is None or type(value) in (str, bool):
        return value
    if type(value) in (int, float):
        number(value, label)
        return value
    if isinstance(value, list):
        return [json_value(v, f'{label}[{i}]') for i, v in enumerate(value)]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {k: json_value(v, f'{label}.{k}') for k, v in value.items()}
    raise ValueError(f'{label}: usa números finitos, texto, booleanos, null, listas u objetos JSON')


def flatten(value, prefix=''):
    """Componentes numéricos, con rutas escapadas como JSON Pointer sin / inicial."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key = key.replace('~', '~0').replace('/', '~1')
            result.update(flatten(item, f'{prefix}/{key}' if prefix else key))
        return result
    if isinstance(value, list):
        result = {}
        for i, item in enumerate(value):
            result.update(flatten(item, f'{prefix}/{i}'))
        return result
    if type(value) in (float, int, bool):
        return {prefix: float(value)}
    return {}


@dataclass
class Field:
    key: str
    label: str
    default: object
    type: str = 'number'
    choices: object = None
    min: object = None
    max: object = None

    def validate(self, value):
        value = json_value(value, self.label)
        if self.type in ('number', 'integer'):
            number(value, self.label)
            if self.type == 'integer':
                if int(value) != value:
                    raise ValueError(f'{self.label}: se requiere un entero')
                value = int(value)
            if self.min is not None and value < self.min or self.max is not None and value > self.max:
                raise ValueError(f'{self.label}: valor fuera de los límites declarados')
        elif self.type == 'boolean' and type(value) is not bool:
            raise ValueError(f'{self.label}: se requiere true o false')
        elif self.type == 'string' and not isinstance(value, str):
            raise ValueError(f'{self.label}: se requiere texto')
        if self.choices is not None and value not in self.choices:
            raise ValueError(f'{self.label}: valor fuera de las opciones declaradas')
        return value


def fields(rows):
    if not isinstance(rows, (list, tuple)):
        raise ValueError('fields y parameters deben ser listas')
    result = []
    for row in rows:
        try:
            f = Field(**row) if isinstance(row, dict) else Field(*row)
        except (TypeError, ValueError) as exc:
            raise ValueError('Descriptor de campo inválido') from exc
        if not isinstance(f.key, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', f.key):
            raise ValueError('Clave de campo inválida')
        if f.type not in ('number', 'integer', 'boolean', 'string', 'json', 'select'):
            raise ValueError(f'Tipo de campo desconocido: {f.type}')
        if f.type == 'select' and (not isinstance(f.choices, list) or not f.choices):
            raise ValueError('Un selector necesita choices')
        f.validate(f.default)
        result.append(f)
    if len({f.key for f in result}) != len(result):
        raise ValueError('Hay campos repetidos')
    return tuple(result)


def inspect_source(source):
    tree = ast.parse(source)
    specs = [node.value for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'ALGORITMO' for t in node.targets)]
    if len(specs) != 1:
        raise ValueError('Declara un diccionario literal ALGORITMO')
    spec = ast.literal_eval(specs[0])
    if not isinstance(spec, dict) or not isinstance(spec.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,63}', spec['id']):
        raise ValueError('Identificador de algoritmo inválido')
    if not isinstance(spec.get('name'), str) or not spec['name'].strip():
        raise ValueError('El algoritmo necesita un nombre')
    if spec.get('mode', 'sync') not in ('sync', 'async', 'coordinator'):
        raise ValueError('Modo no soportado')
    required = {'inicial', 'paso'} | ({'coordinar'} if spec.get('mode') == 'coordinator' else set())
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not required <= names:
        raise ValueError('Faltan funciones: ' + ', '.join(sorted(required - names)))
    fields(spec.get('fields', []))
    fields(spec.get('parameters', []))
    profile_options(spec)
    metrics = spec.get('metrics', [])
    if not isinstance(metrics, (tuple, list)) or any(not isinstance(r, (tuple, list)) or len(r) != 2 or not all(isinstance(v, str) and v for v in r) for r in metrics):
        raise ValueError('metrics debe contener parejas [ruta, etiqueta]')
    if len({r[0] for r in metrics}) != len(metrics):
        raise ValueError('Métricas repetidas')
    return spec


def module_from(path):
    module = ModuleType('algoritmo_local')
    module.__file__ = str(path)
    exec(compile(Path(path).read_text(encoding='utf-8-sig'), str(path), 'exec'), module.__dict__)
    return module


class PluginSpec:
    def __init__(self, path):
        self.path = Path(path)
        self.spec = inspect_source(self.path.read_text(encoding='utf-8-sig'))
        self.id, self.name = self.spec['id'], self.spec['name']
        self.description = self.spec.get('description', '')
        self.parameter_help = self.spec.get('help', '')
        self.mode = self.spec.get('mode', 'sync')
        self.fields = fields(self.spec.get('fields', []))
        self.parameters = fields(self.spec.get('parameters', []))
        self.metrics = tuple(tuple(r) for r in self.spec.get('metrics', []))
        self.function_profiles = profile_options(self.spec)
        self.default_profile = self.spec.get('default_profile')
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def __call__(self, config):
        return PluginRuntime(self, config)

    def make_example(self, n, topology):
        # No importa el módulo ni llama a ejemplo(): cargar un formulario no ejecuta ecuaciones.
        config = dict(schema_version=1, algorithm=self.id, plugin_sha256=self.sha256,
                    name=f'{self.name} · {n} agentes', steps=self.spec.get('steps', 100),
                    period_s=self.spec.get('period_s', .01),
                    parameters={f.key: copy.deepcopy(f.default) for f in self.parameters},
                    nodes=[dict(id=i, host='127.0.0.1', port=15000+i,
                                params={f.key: copy.deepcopy(f.default) for f in self.fields}) for i in range(1, n+1)],
                    topology='coordinador' if self.mode == 'coordinator' else topology,
                    edges=[] if self.mode == 'coordinator' else topology_edges(list(range(1, n+1)), topology),
                    source='Valores iniciales declarados en el archivo cargado.')
        if self.function_profiles:
            for node in config['nodes']:
                node['function_profile'] = self.default_profile
        return config


class PluginRuntime(Runtime):
    def __init__(self, descriptor, config):
        self.descriptor = descriptor
        for key in ('id', 'name', 'description', 'parameter_help', 'mode', 'fields', 'parameters', 'metrics'):
            setattr(self, key, getattr(descriptor, key))
        selected_mode = config.get('execution_mode', descriptor.mode)
        allowed = ('coordinator',) if descriptor.mode == 'coordinator' else ('sync', 'async')
        if selected_mode not in allowed:
            raise ValueError('El rol coordinador requiere execution_mode=coordinator; su intercambio sync/async se elige con coordinator_exchange. Entre vecinos elige sync o async.')
        self.mode = selected_mode
        super().__init__(config)
        self.parameters_values = self.config['parameters']
        for f in self.parameters:
            self.parameters_values[f.key] = f.validate(self.parameters_values[f.key])
        from .parameter_schedule import ParameterSchedule
        self.parameter_schedule = ParameterSchedule(self.config, self.parameters)
        for node in self.nodes.values():
            if self.local_id is None or node['id'] == self.local_id:
                selected = assigned_profile(descriptor.spec, node)
                if selected is not None:
                    node['function_profile'] = selected
                node['params'] = json_value(node['params'], 'Parámetros del agente')
                for f in self.fields:
                    node['params'][f.key] = f.validate(node['params'][f.key])
            timing = node.get('timing', {})
            for key, default in (('period_factor', 1), ('send_delay_ms', 0)):
                if number(timing.get(key, default), key) < 0:
                    raise ValueError(f'{key} no puede ser negativo')
        self.module = module_from(descriptor.path)
        if (self.parameter_schedule.key is not None and not hasattr(self.module, 'ASISTENTE')
                and getattr(self.module, 'PARAMETROS_PROGRAMABLES', False) is not True):
            raise ValueError('Este Python debe declarar PARAMETROS_PROGRAMABLES = True y consultar rt.parameters_at(k) para admitir cambios de demanda')
        if hasattr(self.module, 'preparar'):
            self.module.preparar(self)

    def initial_state(self, node_id):
        return self.check_state(node_id, self.module.inicial(self, node_id))

    def update(self, node_id, own, peers, k=0, global_data=None):
        return self.check_state(node_id, self.module.paso(self, node_id, copy.deepcopy(own),
                                copy.deepcopy(peers), k, copy.deepcopy(global_data)))

    def check_state(self, node_id, state):
        result = self.check_received_state(node_id, state)
        if self.local_id is not None and node_id != self.local_id:
            raise ValueError('La validación matemática de un vecino corresponde a su propio agente')
        if hasattr(self.module, 'validar'):
            self.module.validar(self, node_id, copy.deepcopy(result))
        return result

    def check_received_state(self, node_id, state):
        if not isinstance(state, dict):
            raise ValueError('El estado debe ser un diccionario JSON')
        return json_value(state, f'Estado del agente {node_id}')

    def observe(self, node_id, state, k):
        result = flatten(state)
        if hasattr(self.module, 'observar'):
            extra = self.module.observar(self, node_id, copy.deepcopy(state), k)
            if not isinstance(extra, dict):
                raise ValueError('observar() debe devolver un diccionario')
            result.update({'obs/' + key: v for key, v in flatten(json_value(extra)).items()})
        from .parameter_schedule import reference_values
        result.update(reference_values(self, k))
        return result

    def aggregate(self, k, states):
        return json_value(self.module.coordinar(self, k, states), 'Coordinador')


def discover():
    DIRECTORY.mkdir(exist_ok=True)
    found, errors = {}, {}
    for path in sorted(DIRECTORY.glob('*.py')):
        if path.name.startswith('_'):
            continue
        try:
            spec = PluginSpec(path)
            if spec.id in found:
                raise ValueError(f'Identificador duplicado: {spec.id}')
            found[spec.id] = spec
        except Exception as exc:
            errors[path.name] = str(exc)
    return found, errors


def install(source):
    spec = inspect_source(source)
    found, _ = discover()
    if spec['id'] in found:
        raise ValueError('Ese identificador ya existe; usa otro para conservar su versión')
    # Preserve source bytes across operating systems: presets fingerprint code.
    with (DIRECTORY / (spec['id'] + '.py')).open('x', encoding='utf-8', newline='') as stream:
        stream.write(source)
    return spec['id']
