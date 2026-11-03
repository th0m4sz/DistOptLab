# Generado por el asistente. Todas las decisiones matemáticas están en ASISTENTE.
ALGORITMO = {'id': 'rccrd_coordinado',
 'name': 'RCCRD coordinado',
 'description': 'despacho 3 generadores, coordinador central.',
 'mode': 'coordinator',
 'parameters': [{'key': 'robust',
                 'label': 'activa correcion robusta',
                 'type': 'integer',
                 'default': 1},
                {'key': 'h', 'label': 'paso numerico', 'type': 'number', 'default': 1e-06},
                {'key': 'demand_kw', 'label': 'Demanda total', 'type': 'number', 'default': 800},
                {'key': 'B', 'label': 'constante del fitness', 'type': 'number', 'default': 3000}],
 'fields': [{'key': 'pmin', 'label': 'potencia minima', 'type': 'number', 'default': 100},
            {'key': 'pmax', 'label': 'potencia maxima', 'type': 'number', 'default': 500},
            {'key': 'a', 'label': 'costo constante', 'type': 'number', 'default': 0},
            {'key': 'b', 'label': 'coeficiente lineal', 'type': 'number', 'default': 795.5},
            {'key': 'c', 'label': 'coeficiente cuadratico', 'type': 'number', 'default': 1.15},
            {'key': 'x0', 'label': 'potencia inicial', 'type': 'number', 'default': 150}],
 'metrics': [['x', 'Potencia'],
             ['fitness', 'Fitness'],
             ['hat', 'factor capacidad'],
             ['obs/coste_local', 'costo local']]}

ASISTENTE = {'version': 1,
 'id': 'rccrd_coordinado',
 'name': 'RCCRD coordinado',
 'description': 'despacho 3 generadores, coordinador central.',
 'mode': 'coordinator',
 'parameters': [{'key': 'robust',
                 'label': 'activa correcion robusta',
                 'type': 'integer',
                 'default': 1},
                {'key': 'h', 'label': 'paso numerico', 'type': 'number', 'default': 1e-06},
                {'key': 'demand_kw', 'label': 'Demanda total', 'type': 'number', 'default': 800},
                {'key': 'B', 'label': 'constante del fitness', 'type': 'number', 'default': 3000}],
 'fields': [{'key': 'pmin', 'label': 'potencia minima', 'type': 'number', 'default': 100},
            {'key': 'pmax', 'label': 'potencia maxima', 'type': 'number', 'default': 500},
            {'key': 'a', 'label': 'costo constante', 'type': 'number', 'default': 0},
            {'key': 'b', 'label': 'coeficiente lineal', 'type': 'number', 'default': 795.5},
            {'key': 'c', 'label': 'coeficiente cuadratico', 'type': 'number', 'default': 1.15},
            {'key': 'x0', 'label': 'potencia inicial', 'type': 'number', 'default': 150}],
 'functions': [{'name': 'marginal', 'args': ['z'], 'expression': 'b+2*c*z'},
               {'name': 'coste', 'args': ['z'], 'expression': 'a+b*z+c*z**2'}],
 'states': [{'name': 'x',
             'label': 'Potencia',
             'kind': 'euler',
             'initial': 'x0',
             'update': 'hat*(fitness-global_data["fitness_mean"])',
             'lower': '',
             'upper': ''},
            {'name': 'fitness',
             'label': 'Fitness',
             'kind': 'derived',
             'initial': '',
             'update': 'B-marginal(x)',
             'lower': '',
             'upper': ''},
            {'name': 'hat',
             'label': 'factor capacidad',
             'kind': 'derived',
             'initial': '',
             'update': '(x-pmin)*(pmax-x)',
             'lower': '',
             'upper': ''}],
 'coordinator': [{'name': 'media_base', 'expression': 'sum_all("hat*fitness")/sum_all("hat")'},
                 {'name': 'fitness_mean',
                  'expression': 'media_base*sum_all("x-pmin")/(demand_kw-sum_all("pmin")) if '
                                'robust else media_base'}],
 'observations': [{'name': 'coste_local', 'label': 'costo local', 'expression': 'coste(x)'}],
 'global_metrics': [{'name': 'total', 'label': 'generacion total', 'expression': 'sum_all("x")'},
                    {'name': 'balance',
                     'label': 'error de balance',
                     'expression': 'total-demand_kw'},
                    {'name': 'coste_total',
                     'label': 'costo total',
                     'expression': 'sum_all("coste(x)")'}],
 'checks': [{'expression': 'pmin-1e-8 <= x <= pmax+1e-8',
             'message': 'Euler salió de los límites: reduce h'},
            {'expression': 'c >= 0 and pmin < x0 < pmax',
             'message': 'Revisa el costo y la potencia inicial'},
            {'expression': 'B > marginal(pmax)\t',
             'message': 'Aumenta B para mantener positivo el fitness'}],
 'criterion': '',
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
