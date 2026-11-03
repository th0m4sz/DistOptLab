# Generado por el asistente. Todas las decisiones matemáticas están en ASISTENTE.
ALGORITMO = {'id': 'consenso_robusto',
 'name': 'Consenso robusto · seguimiento de referencias',
 'description': 'Cada agente sigue el promedio de las referencias mediante estados x y lambda. '
                'Ejemplo con perturbación en la iteración 400 y cambio de referencias en la 1000.',
 'mode': 'sync',
 'parameters': [{'key': 'h', 'label': 'Paso numérico h', 'type': 'number', 'default': 0.02},
                {'key': 'reference_step',
                 'label': 'Iteración de cambio de referencia (-1: nunca)',
                 'type': 'integer',
                 'default': 1000},
                {'key': 'kick_step',
                 'label': 'Iteración de perturbación (-1: nunca)',
                 'type': 'integer',
                 'default': 400}],
 'fields': [{'key': 'r', 'label': 'Referencia inicial r', 'type': 'number', 'default': 1},
            {'key': 'r_after', 'label': 'Nueva referencia r', 'type': 'number', 'default': 2},
            {'key': 'x0', 'label': 'Estado inicial x', 'type': 'number', 'default': 0},
            {'key': 'lambda0', 'label': 'Estado inicial lambda', 'type': 'number', 'default': 0},
            {'key': 'kick', 'label': 'Perturbación de x', 'type': 'number', 'default': 0}],
 'metrics': [['x', 'Estado x'],
             ['lambda_', 'Estado auxiliar lambda'],
             ['reference', 'Referencia r']]}

ASISTENTE = {'version': 1,
 'id': 'consenso_robusto',
 'name': 'Consenso robusto · seguimiento de referencias',
 'description': 'Cada agente sigue el promedio de las referencias mediante estados x y lambda. '
                'Ejemplo con perturbación en la iteración 400 y cambio de referencias en la 1000.',
 'mode': 'sync',
 'parameters': [{'key': 'h', 'label': 'Paso numérico h', 'type': 'number', 'default': 0.02},
                {'key': 'reference_step',
                 'label': 'Iteración de cambio de referencia (-1: nunca)',
                 'type': 'integer',
                 'default': 1000},
                {'key': 'kick_step',
                 'label': 'Iteración de perturbación (-1: nunca)',
                 'type': 'integer',
                 'default': 400}],
 'fields': [{'key': 'r', 'label': 'Referencia inicial r', 'type': 'number', 'default': 1},
            {'key': 'r_after', 'label': 'Nueva referencia r', 'type': 'number', 'default': 2},
            {'key': 'x0', 'label': 'Estado inicial x', 'type': 'number', 'default': 0},
            {'key': 'lambda0', 'label': 'Estado inicial lambda', 'type': 'number', 'default': 0},
            {'key': 'kick', 'label': 'Perturbación de x', 'type': 'number', 'default': 0}],
 'functions': [{'name': 'referencia',
                'args': ['indice'],
                'expression': 'r_after if reference_step >= 0 and indice >= reference_step else '
                              'r'}],
 'states': [{'name': 'x',
             'label': 'Estado x',
             'kind': 'next',
             'initial': 'x0',
             'update': 'x + h*(referencia(k) - x + sum_neighbors("lambda_ - own(\'lambda_\')")) + '
                       '(kick if k+1 == kick_step else 0)',
             'lower': '',
             'upper': ''},
            {'name': 'lambda_',
             'label': 'Estado auxiliar lambda',
             'kind': 'euler',
             'initial': 'lambda0',
             'update': 'sum_neighbors("own(\'x\') - x")',
             'lower': '',
             'upper': ''},
            {'name': 'reference',
             'label': 'Referencia r',
             'kind': 'derived',
             'initial': '',
             'update': 'referencia(k)',
             'lower': '',
             'upper': ''}],
 'coordinator': [],
 'observations': [],
 'global_metrics': [{'name': 'target',
                     'label': 'Promedio de referencias',
                     'expression': 'mean_all("reference")'},
                    {'name': 'mean',
                     'label': 'Promedio de estados x',
                     'expression': 'mean_all("x")'},
                    {'name': 'spread',
                     'label': 'Separación entre agentes',
                     'expression': 'max_all("x")-min_all("x")'},
                    {'name': 'max_reference_error',
                     'label': 'Error máximo respecto al promedio de referencias',
                     'expression': 'max(abs(max_all("x")-target), abs(min_all("x")-target))'}],
 'checks': [{'expression': 'h > 0 and reference_step >= -1 and kick_step >= -1',
             'message': 'Paso positivo e índices de eventos desde -1.'}],
 'criterion': 'max_reference_error < 0.001',
 'integration_step': 'h'}

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
