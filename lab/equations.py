# Función de este módulo: Interpreta las expresiones del asistente: funciones, actualizaciones, sumatorias y observaciones.
"""Constructor de algoritmos por expresiones, sin ecuaciones de un dominio.

El intérprete recorre un AST limitado; no ejecuta eval(), imports ni atributos.
El algoritmo generado usa el mismo contrato Python que un archivo escrito a mano.
"""
import ast
import copy
import functools
import math
import operator
import pprint
import re
from types import SimpleNamespace

from .plugins import fields, inspect_source, json_value
from .profiles import profile_options

REDUCERS = {'sum_neighbors', 'weighted_neighbors', 'mean_neighbors', 'sum_all', 'mean_all', 'max_all', 'min_all'}
MATH = {name: getattr(math, name) for name in ('sin', 'cos', 'tan', 'exp', 'log', 'sqrt', 'tanh', 'floor', 'ceil')}
BUILTINS = set(MATH) | REDUCERS | {'own', 'abs', 'min', 'max', 'sum', 'norm', 'dot', 'matmul', 'clip', 'len', 'all', 'any', 'derivative', 'gradient'}
CONSTANTS = {'pi': math.pi, 'e': math.e}
RESERVED = BUILTINS | set(CONSTANTS) | {'i', 'k', 'n', 'global_data', 'value'}
BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}
COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
           ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def mapped(fn, x):
    return [mapped(fn, v) for v in x] if isinstance(x, list) else fn(x)


def paired(fn, a, b):
    """Álgebra componente a componente; solo escalares se difunden sobre listas."""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            raise ValueError('Dimensiones incompatibles entre vectores o matrices')
        return [paired(fn, x, y) for x, y in zip(a, b)]
    if isinstance(a, list):
        return [paired(fn, x, b) for x in a]
    if isinstance(b, list):
        return [paired(fn, a, y) for y in b]
    if type(a) not in (int, float, bool) or type(b) not in (int, float, bool):
        raise ValueError('La operación requiere valores numéricos')
    if fn is operator.pow and abs(b) > 128:
        raise ValueError('Exponente fuera del límite de expresiones (128)')
    return fn(a, b)


def total(values):
    return functools.reduce(lambda a, b: paired(operator.add, a, b), values, 0)


def scalar_bool(value):
    if type(value) not in (bool, int, float):
        raise ValueError('La condición debe ser escalar; usa all(...) o any(...) para vectores')
    return bool(value)


def identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', name) or name in RESERVED or name.startswith('next_'):
        raise ValueError(f'Nombre inválido o reservado: {name!r}')
    return name


@functools.lru_cache(maxsize=2048)
def parse_expression(source):
    if not isinstance(source, str) or not source.strip() or len(source) > 4000:
        raise ValueError('Escribe una expresión de hasta 4000 caracteres')
    if '^' in source:
        raise ValueError('Para potencias usa **; ^ no significa potencia en estas expresiones')
    try:
        tree = ast.parse(source, mode='eval').body
    except SyntaxError as exc:
        raise ValueError(f'Expresión inválida: {source}') from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 512:
        raise ValueError('Expresión demasiado extensa; divídela en funciones')
    allowed = (ast.Constant, ast.Name, ast.List, ast.Tuple, ast.Dict, ast.Load, ast.BinOp,
               ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Subscript, ast.Call,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd,
               ast.Not, ast.And, ast.Or, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError(f'Operación no admitida: {type(node).__name__}')
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.keywords):
            raise ValueError('Usa funciones por nombre, con argumentos posicionales')
        if isinstance(node, ast.Name) and node.id.startswith('_'):
            raise ValueError('Nombre privado no admitido')
        if isinstance(node, ast.Constant):
            json_value(node.value)
    return tree


def check_expression(source, names, functions, reductions=()):
    tree = parse_expression(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in names | set(functions) | BUILTINS | set(CONSTANTS):
            raise ValueError(f'Nombre desconocido o fuera de orden: {node.id}')
        if isinstance(node, ast.Call):
            name = node.func.id
            if name not in BUILTINS | set(functions):
                raise ValueError(f'Función desconocida: {name}')
            if name in functions and len(node.args) != len(functions[name].get('args', ['z'])):
                raise ValueError(f'{name}: número incorrecto de argumentos')
            if name in REDUCERS or name == 'own':
                if name not in reductions:
                    raise ValueError(f'{name} no está disponible en esta fase')
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise ValueError(f'{name} requiere una expresión entre comillas')
            if name in ('derivative', 'gradient'):
                if len(node.args) not in (2, 3) or not isinstance(node.args[0], ast.Constant) or node.args[0].value not in functions:
                    raise ValueError(f'{name} requiere el nombre de una función declarada, el punto y un epsilon opcional')
    return tree


def blank_model():
    return dict(version=1, id='', name='', description='', mode='sync', parameters=[], fields=[],
                functions=[], states=[], coordinator=[], observations=[], global_metrics=[], checks=[],
                criterion='', integration_step='0.01')


def validate_model(model, *, _profiled=False):
    model = json_value(copy.deepcopy(model))
    if model.get('version') != 1:
        raise ValueError('Versión de modelo del asistente no admitida')
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,63}', model.get('id', '')) or not model.get('name', '').strip():
        raise ValueError('Indica nombre e identificador (3–64 letras minúsculas, números o guion bajo)')
    if model.get('mode') not in ('sync', 'async', 'coordinator'):
        raise ValueError('Modo de comunicación inválido')
    options = profile_options(model)
    if options:
        if model.get('functions'):
            raise ValueError('Con perfiles, define las funciones dentro de cada perfil')
        for profile in model['function_profiles']:
            variant = copy.deepcopy(model)
            variant.pop('function_profiles')
            variant.pop('default_profile', None)
            variant['functions'] = profile.get('functions', [])
            try:
                checked = validate_model(variant, _profiled=True)
            except ValueError as exc:
                raise ValueError(f'Perfil {profile["name"]}: {exc}') from exc
            profile['functions'] = checked['functions']
        # El contrato común ya se verificó con cada conjunto de funciones.
        for group in ('parameters', 'fields', 'states', 'coordinator', 'observations', 'global_metrics', 'checks'):
            model[group] = checked[group]
        model['functions'] = []
        return model
    for group in ('parameters', 'fields', 'functions', 'states', 'coordinator', 'observations', 'global_metrics', 'checks'):
        if not isinstance(model.get(group, []), list):
            raise ValueError(f'{group}: se requiere una lista')
        model.setdefault(group, [])
        if len(model[group]) > 200:
            raise ValueError(f'{group}: el asistente admite hasta 200 filas; usa Python para modelos mayores')
    params = [f.key for f in fields(model['parameters'])]
    local = [f.key for f in fields(model['fields'])]
    states = [r['name'] for r in model['states']]
    fnames = [r['name'] for r in model['functions']]
    names = params + local + states + fnames
    for name in names:
        identifier(name)
    if len(names) != len(set(names)):
        raise ValueError('Parámetros, estados y funciones necesitan nombres distintos')
    if not states or not any(r.get('kind', 'next') != 'derived' for r in model['states']):
        raise ValueError('Añade al menos una variable de estado con actualización')
    functions = {}
    basics = set(params + local) | {'i', 'k', 'n'}
    for row in model['functions']:
        args = row.get('args', ['z'])
        if not isinstance(args, list) or not args or len(args) != len(set(args)):
            raise ValueError('Declara argumentos distintos para cada función')
        for arg in args:
            identifier(arg)
        check_expression(row['expression'], (basics - {'k'}) | set(args), functions)
        functions[row['name']] = row
    neighbors = {'sum_neighbors', 'mean_neighbors', 'weighted_neighbors'} if model['mode'] != 'coordinator' else set()
    all_reductions = {'sum_all', 'mean_all', 'max_all', 'min_all'}
    dynamic = [r for r in model['states'] if r.get('kind', 'next') != 'derived']
    derived = [r for r in model['states'] if r.get('kind') == 'derived']
    initial_names = set(basics)
    for row in dynamic + derived:
        if row.get('kind', 'next') not in ('next', 'euler', 'derived'):
            raise ValueError('Tipo de actualización no admitido')
        if row.get('kind') == 'derived' and (row.get('lower') or row.get('upper')):
            raise ValueError('Una variable algebraica no tiene proyección automática; usa clip en su expresión')
        check_expression(row['update'] if row.get('kind') == 'derived' else row['initial'], initial_names, functions)
        initial_names.add(row['name'])
    update_names = basics | set(states) | {'global_data'}
    check_expression(model.get('integration_step', '0.01'), basics, functions)
    for row in dynamic:
        check_expression(row['update'], update_names, functions, neighbors)
        for bound in ('lower', 'upper'):
            if row.get(bound):
                check_expression(row[bound], update_names | {'value'}, functions)
        update_names.add('next_' + row['name'])
    for group in ('coordinator', 'global_metrics', 'observations'):
        seen = set()
        scope = basics | set(states) if group == 'observations' else set(params) | {'k', 'n'}
        for row in model[group]:
            identifier(row['name'])
            if group == 'global_metrics' and row['name'] in ('round', 'wall_s'):
                raise ValueError('round y wall_s son columnas reservadas de la serie global')
            if row['name'] in seen or group != 'observations' and row['name'] in scope:
                raise ValueError(f'Nombre repetido o ambiguo en {group}: {row["name"]}')
            check_expression(row['expression'], scope, functions if group == 'observations' else {},
                             all_reductions if group != 'observations' else ())
            seen.add(row['name'])
            if group != 'observations':
                scope.add(row['name'])
    if model['mode'] != 'coordinator' and model['coordinator']:
        raise ValueError('Las ecuaciones de coordinador requieren modo coordinador')
    if model['mode'] == 'coordinator' and not model['coordinator']:
        raise ValueError('Define qué calcula el coordinador')
    for row in model['checks']:
        check_expression(row['expression'], (basics | set(states)) - {'k'}, functions)
    if model.get('criterion', '').strip():
        check_expression(model['criterion'], set(params) | {'k', 'n'} | {r['name'] for r in model['global_metrics']}, {}, all_reductions)
    # Comprobar también las expresiones encerradas en reducciones, en el contexto del emisor.
    def nested(source):
        for node in ast.walk(parse_expression(source)):
            if isinstance(node, ast.Call) and node.func.id in REDUCERS:
                inner = check_expression(node.args[0].value, basics | set(states), functions,
                                         {'own'} if node.func.id.endswith('neighbors') else ())
                if _profiled and node.func.id.endswith('neighbors'):
                    def check_remote(tree):
                        if isinstance(tree, ast.Call):
                            if tree.func.id == 'own':
                                return
                            if tree.func.id in functions or tree.func.id in ('derivative', 'gradient'):
                                raise ValueError('El perfil del vecino es local: comunica el resultado como estado y suma ese estado recibido')
                        for child in ast.iter_child_nodes(tree):
                            check_remote(child)
                    check_remote(inner)
                for call in ast.walk(inner):
                    if isinstance(call, ast.Call) and call.func.id == 'own':
                        check_expression(call.args[0].value, basics | set(states), functions)
    for group in ('states', 'coordinator', 'global_metrics', 'observations'):
        for row in model[group]:
            nested(row['update'] if group == 'states' else row['expression'])
    if model.get('criterion', '').strip():
        nested(model['criterion'])
    return model


class Interpreter:
    def __init__(self, model, rt, i=None, state=None, peers=None, k=0, global_data=None, all_states=None, own_context=None, remote=False, all_rounds=None):
        self.model, self.rt, self.i = model, rt, i
        self.state, self.peers, self.k, self.all_states = state or {}, peers or {}, k, all_states
        self.own_context = own_context
        self.remote = remote
        # Solo la reconstrucción temporal del evaluador aporta índices distintos.
        # Los workers conservan el contexto y el aislamiento anteriores.
        self.all_rounds = all_rounds or {}
        schedule = getattr(rt, 'parameter_schedule', None)
        if schedule is not None and schedule.key is None:
            schedule = None
        indices = [v for j,v in self.all_rounds.items() if all_states is None or j in all_states]
        parameters = (schedule.across(indices) if k is None and self.all_rounds
                      else schedule.at(0 if k is None else k)) if schedule else rt.parameters_values
        self.env = dict(CONSTANTS, **parameters)
        if i is not None and not remote:
            self.env.update(rt.nodes[i].get('params', {}))
        self.function_env = {**self.env, 'i': i, 'n': len(getattr(rt, 'active_ids', rt.ids))}
        self.env.update(self.state)
        self.env.update(i=i, k=k, n=len(getattr(rt, 'active_ids', rt.ids)), global_data=global_data or {})
        self.profiled_remote = remote and bool(model.get('function_profiles'))
        functions = model['functions']
        if model.get('function_profiles'):
            selected = rt.nodes[i].get('function_profile', model['default_profile']) if i is not None and not remote else model['default_profile']
            profile = next((p for p in model['function_profiles'] if p['id'] == selected), None)
            if profile is None:
                raise ValueError(f'Agente {i}: perfil de funciones desconocido {selected!r}')
            functions = profile['functions']
        self.functions = {r['name']: r for r in functions}
        self.budget = 100000

    def evaluate(self, source):
        try:
            return json_value(self.visit(parse_expression(source)))
        except Exception as exc:
            raise ValueError(f'Expresión {source!r}, agente {self.i}, k={self.k}: {exc}') from exc

    def visit(self, node):
        self.budget -= 1
        if self.budget < 0:
            raise ValueError('Se excedió el límite de cálculo por expresión')
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if self.remote and node.id not in self.env:
                raise ValueError(f'{node.id}: no está en los datos recibidos. Calcula el valor en su agente y comunícalo como estado; no se consultan parámetros privados del vecino')
            return self.env[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.visit(x) for x in node.elts]
        if isinstance(node, ast.Dict):
            return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.BinOp):
            return paired(BINOPS[type(node.op)], self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.UnaryOp):
            value = self.visit(node.operand)
            return not scalar_bool(value) if isinstance(node.op, ast.Not) else mapped(operator.neg if isinstance(node.op, ast.USub) else operator.pos, value)
        if isinstance(node, ast.BoolOp):
            for item in node.values:
                value = scalar_bool(self.visit(item))
                if isinstance(node.op, ast.And) and not value or isinstance(node.op, ast.Or) and value:
                    return value
            return value
        if isinstance(node, ast.Compare):
            left = self.visit(node.left)
            result = True
            for op, comp in zip(node.ops, node.comparators):
                right = self.visit(comp)
                result = paired(operator.and_, result, paired(COMPARE[type(op)], left, right))
                left = right
            return result
        if isinstance(node, ast.IfExp):
            return self.visit(node.body if scalar_bool(self.visit(node.test)) else node.orelse)
        if isinstance(node, ast.Subscript):
            value, index = self.visit(node.value), self.visit(node.slice)
            if not isinstance(value, (list, dict)):
                raise ValueError('Solo se indexan listas y diccionarios')
            return value[index]
        if isinstance(node, ast.Call):
            return self.call(node.func.id, [self.visit(x) for x in node.args])
        raise ValueError('Expresión no admitida')

    def call(self, name, args):
        if name == 'own':
            if self.own_context is None:
                raise ValueError('own solo está disponible dentro de una sumatoria sobre vecinos')
            return self.own_context.evaluate(args[0])
        if name in self.functions:
            if self.profiled_remote:
                raise ValueError('El perfil del vecino es local: calcula la función en el emisor y comunica su resultado como estado')
            row = self.functions[name]
            if len(args) != len(row['args']):
                raise ValueError(f'{name}: número incorrecto de argumentos')
            previous = self.env
            self.env = {**self.function_env, **dict(zip(row['args'], args))}
            try:
                return self.visit(parse_expression(row['expression']))
            finally:
                self.env = previous
        if name in MATH or name == 'abs':
            if len(args) != 1:
                raise ValueError(f'{name} necesita un argumento')
            return mapped(abs if name == 'abs' else MATH[name], args[0])
        if name in ('sum', 'min', 'max'):
            items = args[0] if len(args) == 1 and isinstance(args[0], list) else args
            if name == 'sum':
                return total(items)
            return functools.reduce(lambda a, b: paired(min if name == 'min' else max, a, b), items)
        if name in ('len', 'all', 'any'):
            if len(args) != 1 or not isinstance(args[0], list):
                raise ValueError(f'{name} necesita una lista')
            if name == 'len':
                return len(args[0])
            return (all if name == 'all' else any)(scalar_bool(v) for v in args[0])
        if name == 'norm':
            def flat(v):
                return [x for item in v for x in flat(item)] if isinstance(v, list) else [v]
            return math.sqrt(math.fsum(x*x for x in flat(args[0])))
        if name == 'dot':
            a, b = args
            if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b) or any(isinstance(v, list) for v in a+b):
                raise ValueError('dot necesita vectores de igual longitud')
            return total(paired(operator.mul, a, b))
        if name == 'matmul':
            a, b = args
            return [self.call('dot', [row, b]) for row in a]
        if name == 'clip':
            x, lo, hi = args
            return paired(min, paired(max, x, lo), hi)
        if name in ('derivative', 'gradient'):
            fn, point = args[:2]
            eps = args[2] if len(args) == 3 else 1e-6
            if type(eps) not in (float, int) or not math.isfinite(eps) or eps <= 0:
                raise ValueError('epsilon debe ser positivo y finito')
            if name == 'derivative':
                if type(point) not in (int, float):
                    raise ValueError('derivative requiere un punto escalar')
                return (self.call(fn, [point+eps])-self.call(fn, [point-eps]))/(2*eps)
            if not isinstance(point, list) or any(type(v) not in (float, int) for v in point):
                raise ValueError('gradient requiere un vector de números')
            result = []
            for index in range(len(point)):
                plus, minus = point.copy(), point.copy()
                plus[index] += eps
                minus[index] -= eps
                result.append((self.call(fn, [plus])-self.call(fn, [minus]))/(2*eps))
            return result
        if name in REDUCERS:
            states = self.peers if name.endswith('neighbors') else self.all_states
            if states is None:
                raise ValueError('La reducción global solo existe en coordinador o evaluación')
            values = []
            for j, state in states.items():
                other = Interpreter(self.model, self.rt, j, state, k=self.all_rounds.get(j, self.k),
                                    own_context=self if name.endswith('neighbors') else None,
                                    remote=name.endswith('neighbors'))
                value = other.evaluate(args[0])
                if name == 'weighted_neighbors':
                    value = paired(operator.mul, self.rt.neighbors[self.i][j], value)
                values.append(value)
            if name.startswith('mean') and not values:
                raise ValueError('No se puede promediar un conjunto vacío')
            if name.startswith('max') or name.startswith('min'):
                return functools.reduce(lambda a, b: paired(max if name.startswith('max') else min, a, b), values)
            return paired(operator.truediv, total(values), len(values)) if name.startswith('mean') else total(values)
        raise ValueError(f'Función no admitida: {name}')


class EquationModel:
    def __init__(self, model, rt):
        self.model, self.rt = validate_model(model), rt
        self.dynamic = [r for r in self.model['states'] if r.get('kind', 'next') != 'derived']
        self.derived = [r for r in self.model['states'] if r.get('kind') == 'derived']

    def initial(self, i):
        ctx = Interpreter(self.model, self.rt, i)
        state = {}
        for row in self.dynamic + self.derived:
            value = ctx.evaluate(row['update'] if row.get('kind') == 'derived' else row['initial'])
            state[row['name']] = value
            ctx.env[row['name']] = value
        self.check(i, state)
        return state

    def step(self, i, own, peers, k, aggregate):
        ctx = Interpreter(self.model, self.rt, i, own, peers, k, aggregate)
        state = {}
        for row in self.dynamic:
            value = ctx.evaluate(row['update'])
            if row.get('kind') == 'euler':
                h = ctx.evaluate(self.model.get('integration_step', '0.01'))
                if type(h) not in (int, float) or h <= 0:
                    raise ValueError('El paso Euler debe ser positivo')
                value = paired(operator.add, own[row['name']], paired(operator.mul, h, value))
            ctx.env['value'] = value
            lo = ctx.evaluate(row['lower']) if row.get('lower') else None
            hi = ctx.evaluate(row['upper']) if row.get('upper') else None
            if lo is not None and hi is not None:
                valid = paired(operator.le, lo, hi)
                def every(v):
                    return all(every(x) for x in v) if isinstance(v, list) else bool(v)
                if not every(valid):
                    raise ValueError('El límite inferior supera al superior')
            if lo is not None:
                value = paired(max, value, lo)
            if hi is not None:
                value = paired(min, value, hi)
            state[row['name']] = json_value(value)
            ctx.env['next_' + row['name']] = value
        # Las variables algebraicas se recalculan con el nuevo estado, no se integran.
        ctx.env.update(state)
        ctx.env['k'] = k+1
        for row in self.derived:
            value = ctx.evaluate(row['update'])
            state[row['name']] = value
            ctx.env[row['name']] = value
        self.check(i, state)
        return state

    def check(self, i, state):
        # Validaciones son invariantes de estado; no dependen de ronda o vecinos.
        ctx = Interpreter(self.model, self.rt, i, state)
        for row in self.model['checks']:
            if not scalar_bool(ctx.evaluate(row['expression'])):
                raise ValueError(row.get('message') or 'No se cumple la condición del estado')

    def observe(self, i, state, k):
        ctx = Interpreter(self.model, self.rt, i, state, k=k)
        return {r['name']: ctx.evaluate(r['expression']) for r in self.model['observations']}

    def aggregate(self, k, states):
        ctx = Interpreter(self.model, self.rt, k=k, all_states=states)
        result = {}
        for row in self.model['coordinator']:
            result[row['name']] = ctx.evaluate(row['expression'])
            ctx.env[row['name']] = result[row['name']]
        return result

    def evaluate(self, logs):
        from .parameter_schedule import reference_values
        model, rt = self.model, self.rt
        # No inventar una trayectoria global síncrona a partir de índices asíncronos.
        rounds = [rt.steps] if getattr(rt,'asynchronous',rt.mode=='async') else range(rt.steps+1)
        series, final_ctx = [], None
        for k in rounds:
            ctx = Interpreter(model, rt, k=k, all_states={i: logs[i][k] for i in rt.ids})
            row = {'round': k, **reference_values(rt, k)}
            for metric in model['global_metrics']:
                value = ctx.evaluate(metric['expression'])
                if type(value) not in (int, float, bool):
                    raise ValueError('Las métricas globales deben ser escalares')
                row[metric['name']] = value
                ctx.env[metric['name']] = value
            series.append(row)
            final_ctx = ctx
        report = {'conclusion': 'Ejecución registrada; no se ha definido un criterio final.'}
        if model.get('criterion', '').strip():
            report['converged'] = scalar_bool(final_ctx.evaluate(model['criterion']))
            report['conclusion'] = 'Criterio final declarado ' + ('cumplido.' if report['converged'] else 'no cumplido.')
        if getattr(rt,'asynchronous',rt.mode=='async'):
            report['conclusion'] += ' Las métricas globales corresponden solo a los estados terminales, no a instantes simultáneos.'
        return report, series if model['global_metrics'] else []


def generate_source(model):
    model = validate_model(model)
    descriptor = dict(id=model['id'], name=model['name'], description=model.get('description', ''),
                      mode=model['mode'], parameters=model['parameters'], fields=model['fields'],
                      metrics=[[r['name'], r.get('label') or r['name']] for r in model['states']] +
                              [['obs/' + r['name'], r.get('label') or r['name']] for r in model['observations']])
    if model.get('function_profiles'):
        descriptor['function_profiles'] = [{key: p[key] for key in ('id', 'name')} for p in model['function_profiles']]
        descriptor['default_profile'] = model['default_profile']
    source = '# Generado por el asistente. Todas las decisiones matemáticas están en ASISTENTE.\n'
    source += 'ALGORITMO = ' + pprint.pformat(descriptor, sort_dicts=False, width=100) + '\n\n'
    source += 'ASISTENTE = ' + pprint.pformat(model, sort_dicts=False, width=100) + '\n\n'
    source += '''from lab.equations import EquationModel

def preparar(rt):
    rt.equations = EquationModel(ASISTENTE, rt)

def inicial(rt, i):
    return rt.equations.initial(i)

def paso(rt, i, propio, vecinos, k, global_data):
    return rt.equations.step(i, propio, vecinos, k, global_data)

def coordinar(rt, k, estados):
    return rt.equations.aggregate(k, estados)

def validar(rt, i, estado):
    rt.equations.check(i, estado)

def observar(rt, i, estado, k):
    return rt.equations.observe(i, estado, k)

def evaluar(rt, logs):
    return rt.equations.evaluate(logs)
'''
    inspect_source(source)
    return source


def model_from_source(source):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ASISTENTE' for t in node.targets):
            return validate_model(ast.literal_eval(node.value))
    raise ValueError('Este archivo fue escrito a mano; puedes editarlo como Python. No tiene un modelo del asistente.')


def preview_model(model, n=3, steps=3, profile_ids=None):
    """Prueba determinista acotada en memoria; no abre puertos ni guarda ensayos."""
    model = validate_model(model)
    profiles = list(profile_options(model))
    if profiles:
        profile_ids = profile_ids or profiles
        if any(p not in profiles for p in profile_ids):
            raise ValueError('La vista previa contiene un perfil desconocido')
        n = max(n, len(profile_ids))
    rt = SimpleNamespace(parameters_values={f.key: copy.deepcopy(f.default) for f in fields(model['parameters'])},
                         ids=list(range(1, n+1)), steps=steps, mode=model['mode'])
    rt.nodes = {i: {'params': {f.key: copy.deepcopy(f.default) for f in fields(model['fields'])}} for i in rt.ids}
    if profiles:
        for i in rt.ids:
            rt.nodes[i]['function_profile'] = profile_ids[(i-1) % len(profile_ids)]
    rt.neighbors = {i: {j: 1 for j in rt.ids if j != i} if rt.mode != 'coordinator' else {} for i in rt.ids}
    engine = EquationModel(model, rt)
    states = {i: engine.initial(i) for i in rt.ids}
    rows = [{'round': 0, 'states': copy.deepcopy(states)}]
    for k in range(steps):
        aggregate = engine.aggregate(k, states) if rt.mode == 'coordinator' else None
        states = {i: engine.step(i, states[i], {j: states[j] for j in rt.neighbors[i]}, k, aggregate) for i in rt.ids}
        for i in rt.ids:
            engine.observe(i, states[i], k+1)
        rows.append({'round': k+1, 'states': copy.deepcopy(states)})
    logs = {i: [r['states'][i] for r in rows] for i in rt.ids}
    report, series = engine.evaluate(logs)
    return dict(note=f'Vista previa: {n} agentes, grafo completo con pesos 1, {steps} pasos. Incluye todos los perfiles por defecto. En modo asíncrono solo revisa expresiones; no simula retardos. No verifica convergencia.',
                profiles={i: rt.nodes[i].get('function_profile') for i in rt.ids}, rows=rows, report=report, global_series=series)
