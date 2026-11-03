"""Ejemplo manual autocontenido para cargar en la plataforma flexible.

Solo usa la biblioteca estándar. No requiere ASISTENTE ni módulos económicos
de la plataforma. El ejecutor crea los agentes y el proceso coordinador.
"""
import math


ALGORITMO = {
    'id': 'rccrd_python_autocontenido',
    'name': 'CCRD / RCCRD coordinado · Python manual',
    'description': 'Fitness medio ponderado por capacidad; corrección robusta opcional del balance.',
    'mode': 'coordinator',
    'steps': 1000,
    'period_s': 0.01,
    'parameters': [
        {'key': 'robust', 'label': 'Robusto (0: CCRD; 1: RCCRD)', 'type': 'integer', 'default': 1},
        {'key': 'h', 'label': 'Paso numérico h', 'type': 'number', 'default': 1e-6},
        {'key': 'demand_kw', 'label': 'Demanda total', 'type': 'number', 'default': 800},
        {'key': 'B', 'label': 'Constante del fitness', 'type': 'number', 'default': 3000},
    ],
    'fields': [
        {'key': 'pmin', 'label': 'Potencia mínima', 'type': 'number', 'default': 100},
        {'key': 'pmax', 'label': 'Potencia máxima', 'type': 'number', 'default': 500},
        {'key': 'a', 'label': 'Costo constante', 'type': 'number', 'default': 0},
        {'key': 'b', 'label': 'Coeficiente lineal', 'type': 'number', 'default': 795.5},
        {'key': 'c', 'label': 'Coeficiente cuadrático', 'type': 'number', 'default': 1.15},
        {'key': 'x0', 'label': 'Potencia inicial', 'type': 'number', 'default': 150},
    ],
    'metrics': [
        ['x', 'Potencia'], ['fitness', 'Fitness'],
        ['hat', 'Factor de capacidad'], ['obs/coste_local', 'Costo local'],
    ],
}


def preparar(rt):
    """Comprueba los datos del ensayo, sin calcular un despacho central."""
    params = rt.parameters_values
    if params['robust'] not in (0, 1) or params['h'] <= 0:
        raise ValueError('Robusto debe ser 0 o 1 y h debe ser positivo')
    # El worker solo tiene sus datos. La factibilidad global se comprueba
    # en el gestor/coordinador, cuyo contexto tiene local_id = None.
    ids = rt.ids if rt.local_id is None else [rt.local_id]
    nodes = [rt.nodes[i]['params'] for i in ids]
    if rt.local_id is None:
        minimum = math.fsum(p['pmin'] for p in nodes)
        maximum = math.fsum(p['pmax'] for p in nodes)
        if not minimum < params['demand_kw'] < maximum:
            raise ValueError('La demanda debe estar entre la suma de mínimos y máximos')
    for p in nodes:
        if p['c'] < 0 or not p['pmin'] < p['x0'] < p['pmax']:
            raise ValueError('Usa c >= 0 y una potencia inicial estrictamente entre límites')
        if params['B'] <= p['b'] + 2*p['c']*p['pmax']:
            raise ValueError('Aumenta B para mantener positivo el fitness')


def estado(rt, i, x):
    """Calcula las cantidades locales que se comunican al coordinador."""
    p = rt.nodes[i]['params']
    return {
        'x': x,
        'fitness': rt.parameters_values['B'] - (p['b'] + 2*p['c']*x),
        'hat': (x - p['pmin']) * (p['pmax'] - x),
    }


def coste(rt, i, x):
    p = rt.nodes[i]['params']
    return p['a'] + p['b']*x + p['c']*x**2


def inicial(rt, i):
    return estado(rt, i, rt.nodes[i]['params']['x0'])


def coordinar(rt, k, estados):
    """El coordinador recibe los estados de una misma ronda."""
    denominator = math.fsum(s['hat'] for s in estados.values())
    if denominator <= 0:
        raise ValueError('No queda capacidad interior para calcular la media')
    base = math.fsum(s['hat']*s['fitness'] for s in estados.values()) / denominator
    mean = base
    if rt.parameters_values['robust']:
        minimum = math.fsum(rt.nodes[i]['params']['pmin'] for i in rt.ids)
        available = math.fsum(s['x'] - rt.nodes[i]['params']['pmin']
                              for i, s in estados.items())
        target = rt.parameters_values['demand_kw'] - minimum
        mean = base * available / target
    return {'media_base': base, 'fitness_mean': mean}


def paso(rt, i, propio, vecinos, k, global_data):
    """Euler explícito: el paso h ya está incluido en esta fórmula."""
    x = propio['x'] + rt.parameters_values['h'] * propio['hat'] * (
        propio['fitness'] - global_data['fitness_mean'])
    return estado(rt, i, x)


def validar(rt, i, state):
    p = rt.nodes[i]['params']
    if not p['pmin'] - 1e-8 <= state['x'] <= p['pmax'] + 1e-8:
        raise ValueError('Euler salió de los límites: reduce h; no se recorta la potencia')
    expected = estado(rt, i, state['x'])
    for key in ('fitness', 'hat'):
        if not math.isclose(state[key], expected[key], rel_tol=1e-12, abs_tol=1e-7):
            raise ValueError('Estado local incoherente: ' + key)


def observar(rt, i, state, k):
    return {'coste_local': coste(rt, i, state['x'])}


def evaluar(rt, logs):
    """Produce gráficas globales posteriores; no certifica optimalidad."""
    series = []
    for k in range(rt.steps + 1):
        total = math.fsum(logs[i][k]['x'] for i in rt.ids)
        series.append({
            'round': k,
            'total': total,
            'balance': total - rt.parameters_values['demand_kw'],
            'coste_total': math.fsum(coste(rt, i, logs[i][k]['x']) for i in rt.ids),
        })
    return {'conclusion': 'Ensayo registrado; sin criterio de optimalidad declarado.'}, series
