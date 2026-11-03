# Generado por el asistente. Todas las decisiones matemáticas están en ASISTENTE.
ALGORITMO = {'id': 'tutorial_gradiente',
 'name': 'Ejemplo guiado · seguimiento de gradiente',
 'description': 'Tres agentes minimizan la suma de sus costos cuadráticos. Tutorial con red '
                'completa y promedios uniformes. Consulta la guía antes de cambiar la topología.',
 'mode': 'sync',
 'parameters': [{'key': 'alpha',
                 'label': 'Paso del gradiente (alpha)',
                 'type': 'number',
                 'default': 0.1,
                 'min': 1e-06}],
 'fields': [{'key': 'centro', 'label': 'Centro del costo local', 'type': 'number', 'default': 2},
            {'key': 'inicio', 'label': 'Valor inicial de x', 'type': 'number', 'default': 0}],
 'metrics': [['x', 'Decisión local x'],
             ['y', 'Seguimiento del gradiente y'],
             ['obs/costo_local', 'Costo local'],
             ['obs/gradiente_local', 'Gradiente local']]}

ASISTENTE = {'version': 1,
 'id': 'tutorial_gradiente',
 'name': 'Ejemplo guiado · seguimiento de gradiente',
 'description': 'Tres agentes minimizan la suma de sus costos cuadráticos. Tutorial con red '
                'completa y promedios uniformes. Consulta la guía antes de cambiar la topología.',
 'mode': 'sync',
 'parameters': [{'key': 'alpha',
                 'label': 'Paso del gradiente (alpha)',
                 'type': 'number',
                 'default': 0.1,
                 'min': 1e-06}],
 'fields': [{'key': 'centro', 'label': 'Centro del costo local', 'type': 'number', 'default': 2},
            {'key': 'inicio', 'label': 'Valor inicial de x', 'type': 'number', 'default': 0}],
 'functions': [{'name': 'costo', 'args': ['z'], 'expression': '0.5*(z-centro)**2'},
               {'name': 'gradiente', 'args': ['z'], 'expression': 'z-centro'}],
 'states': [{'name': 'x',
             'label': 'Decisión local x',
             'kind': 'next',
             'initial': 'inicio',
             'update': '(x + sum_neighbors("x"))/n - alpha*y',
             'lower': '',
             'upper': ''},
            {'name': 'y',
             'label': 'Seguimiento del gradiente y',
             'kind': 'next',
             'initial': 'gradiente(x)',
             'update': '(y + sum_neighbors("y"))/n + gradiente(next_x) - gradiente(x)',
             'lower': '',
             'upper': ''}],
 'coordinator': [],
 'observations': [{'name': 'costo_local', 'label': 'Costo local', 'expression': 'costo(x)'},
                  {'name': 'gradiente_local',
                   'label': 'Gradiente local',
                   'expression': 'gradiente(x)'}],
 'global_metrics': [{'name': 'separacion',
                     'label': 'Separación entre decisiones',
                     'expression': 'max_all("x") - min_all("x")'},
                    {'name': 'suma_costos',
                     'label': 'Suma de costos locales',
                     'expression': 'sum_all("costo(x)")'}],
 'checks': [],
 'criterion': '',
 'integration_step': '0.01'}

from lab.equations import EquationModel

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
