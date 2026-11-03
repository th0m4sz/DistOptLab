# Generado por el asistente. Todas las decisiones matemáticas están en ASISTENTE.
ALGORITMO = {'id': 'distribuido_ccrd',
 'name': 'RDCF · dinámica de replicadores con factores de capacidad',
 'description': 'RDCF · dinámica de replicadores con factores de capacidad',
 'mode': 'sync',
 'parameters': [{'key': 'alpha',
                 'label': 'paso',
                 'type': 'number',
                 'default': 5e-11},
                {'key': 'B', 'label': 'Constante fitness', 'type': 'number', 'default': 3000},
                {'key': 'demanda',
                 'label': 'Demanda de referencia (kW)',
                 'type': 'number',
                 'default': 800}],
 'fields': [{'key': 'pmin', 'label': 'Potencia minima', 'type': 'number', 'default': 100},
            {'key': 'pmax', 'label': 'Potencia maxima', 'type': 'number', 'default': 500},
            {'key': 'x0', 'label': 'x inicial', 'type': 'number', 'default': 150},
            {'key': 'a', 'label': 'a', 'type': 'number', 'default': 64.67},
            {'key': 'b', 'label': 'b', 'type': 'number', 'default': 795.5},
            {'key': 'c', 'label': 'c', 'type': 'number', 'default': 1.15}],
 'metrics': [['x', 'Potencia(kw)'],
             ['hat', 'Capacidad xhat'],
             ['f', 'Fitness'],
             ['obs/coste_local', 'Costo local']]}

ASISTENTE = {'version': 1,
 'id': 'distribuido_ccrd',
 'name': 'RDCF · dinámica de replicadores con factores de capacidad',
 'description': 'RDCF · dinámica de replicadores con factores de capacidad',
 'mode': 'sync',
 'parameters': [{'key': 'alpha',
                 'label': 'paso',
                 'type': 'number',
                 'default': 5e-11},
                {'key': 'B', 'label': 'Constante fitness', 'type': 'number', 'default': 3000},
                {'key': 'demanda',
                 'label': 'Demanda de referencia (kW)',
                 'type': 'number',
                 'default': 800}],
 'fields': [{'key': 'pmin', 'label': 'Potencia minima', 'type': 'number', 'default': 100},
            {'key': 'pmax', 'label': 'Potencia maxima', 'type': 'number', 'default': 500},
            {'key': 'x0', 'label': 'x inicial', 'type': 'number', 'default': 150},
            {'key': 'a', 'label': 'a', 'type': 'number', 'default': 64.67},
            {'key': 'b', 'label': 'b', 'type': 'number', 'default': 795.5},
            {'key': 'c', 'label': 'c', 'type': 'number', 'default': 1.15}],
 'functions': [{'name': 'xhat', 'args': ['x'], 'expression': '(x-pmin)*(pmax-x)'},
               {'name': 'fitness', 'args': ['x'], 'expression': 'B-(b+2*c*x)'},
               {'name': 'costo', 'args': ['x'], 'expression': 'a+b*x+c*x**2'}],
 'states': [{'name': 'x',
             'label': 'Potencia(kw)',
             'kind': 'euler',
             'initial': 'x0',
             'update': 'hat*weighted_neighbors(\'hat*(own("f")-f)\')',
             'lower': '',
             'upper': ''},
            {'name': 'hat',
             'label': 'Capacidad xhat',
             'kind': 'derived',
             'initial': '',
             'update': 'xhat(x)',
             'lower': '',
             'upper': ''},
            {'name': 'f',
             'label': 'Fitness',
             'kind': 'derived',
             'initial': '',
             'update': 'fitness(x)',
             'lower': '',
             'upper': ''}],
 'coordinator': [],
 'observations': [{'name': 'coste_local', 'label': 'Costo local', 'expression': 'costo(x)'}],
 'global_metrics': [{'name': 'potencia_total',
                     'label': 'Potencia total (kW)',
                     'expression': 'sum_all("x")'},
                    {'name': 'balance',
                     'label': 'Error de balance (kW)',
                     'expression': 'potencia_total-demanda'},
                    {'name': 'coste_total',
                     'label': 'Costo total',
                     'expression': 'sum_all("costo(x)")'},
                    {'name': 'dispersion_fitness',
                     'label': 'Diferencia máxima de fitness',
                     'expression': 'max_all("f")-min_all("f")'}],
 'checks': [{'expression': 'c >= 0 and 0 <= pmin < x0 < pmax and alpha > 0',
             'message': 'Revisa límites, condición inicial, convexidad y paso positivo.'},
            {'expression': 'pmin-1e-8 <= x <= pmax+1e-8', 'message': 'Potencia fuera de límites.'}],
 'criterion': '',
 'integration_step': 'alpha'}

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
