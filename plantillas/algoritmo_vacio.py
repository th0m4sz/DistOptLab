"""Tu algoritmo completo puede vivir en este archivo; no necesita ASISTENTE.

Completa ALGORITMO, inicial() y paso(), y carga el .py desde el menú Algoritmo.
El ejecutor llama a tus funciones y gestiona procesos, comunicación y registros.
No es un programa independiente: se ejecuta dentro de la plataforma flexible.
Las funciones opcionales se muestran comentadas al final. Consulta docs/CONTRATO.md.
"""

# ALGORITMO debe ser un diccionario literal: no lo construyas mediante funciones.
# Tipos de campos: number (número), integer (entero), boolean (True/False),
# string (texto), json (listas/diccionarios) o select (elección con choices).
# key es el nombre para tu código; label es el texto visible; default es el valor
# inicial del formulario. min/max son límites opcionales para number/integer.

ALGORITMO = {
    'id': 'mi_metodo',  # 3–64 letras minúsculas, números o _; empieza con letra.
    'name': 'Mi método',
    'description': 'Describe aquí tu metodología.',
    'mode': 'sync',  # sync: misma ronda; async: últimas muestras de vecinos.
                    # coordinator: requiere coordinar(); en el experimento eliges misma ronda
                    # o últimas muestras (coordinator_exchange = sync / async).
    'parameters': [  # Valores comunes, accesibles mediante rt.parameters_values.
        # {'key': 'h', 'label': 'Paso numérico', 'type': 'number', 'default': 0.01, 'min': 0},
        # {'key': 'activo', 'label': 'Activar término', 'type': 'boolean', 'default': True},
        # {'key': 'regla', 'label': 'Regla', 'type': 'select', 'default': 'A', 'choices': ['A', 'B']},
    ],
    'fields': [  # Valores editables por agente, accesibles en rt.nodes[i]['params'].
        # {'key': 'x0', 'label': 'Valor inicial', 'type': 'number', 'default': 0.0},
        # {'key': 'vector0', 'label': 'Vector inicial', 'type': 'json', 'default': [0.0, 0.0]},
    ],
    # OPCIONAL: descomenta este bloque si necesitas fórmulas distintas por agente.
    # Los id son claves estables; name es el texto del selector del experimento.
    # 'function_profiles': [
    #     {'id': 'cuadratico', 'name': 'Cuadrático'},
    #     {'id': 'cuarto_grado', 'name': 'Cuadrático + cuarto grado'},
    # ],
    # 'default_profile': 'cuadratico',  # Lo reciben los agentes nuevos.
    'metrics': [],  # Solo etiquetas opcionales: [['x', 'Decisión'], ['vector/0', 'Componente 1']].
}

# rt es el contexto que proporciona la plataforma; no tienes que crearlo.
# rt.ids: identificadores de agentes; rt.neighbors[i]: {id_vecino: peso}.
# En un agente, rt.local_id == i y solo rt.nodes[i] contiene 'params'.
# De los otros nodos conoces su dirección, no sus parámetros locales.
# rt.steps: número de actualizaciones; rt.period: pausa real mínima en segundos.
# Un paso matemático h/alpha lo defines tú: rt.period no integra las ecuaciones.
# Cambios de demanda opcionales: declara PARAMETROS_PROGRAMABLES = True a nivel
# del archivo SOLO si tu implementación consulta rt.parameters_at(k) en paso()
# y/o coordinar(). Devuelve los parámetros comunes vigentes en el índice k.
# rt.parameters_values sigue siendo la configuración inicial; no guardes una
# copia de la demanda en preparar() si necesitas que cambie durante el ensayo.
# Esto cambia la referencia, no añade un mecanismo de seguimiento a tu método.


def inicial(rt, i):
    """Obligatoria: devuelve el estado inicial COMPLETO del agente i."""
    # i es un identificador entero, no necesariamente una posición en una lista.
    # Si declaraste x0: valor = rt.nodes[i]['params']['x0'].
    # Ejemplo de estructura: {'x': 0.0, 'vector': [1.0, 2.0], 'memoria': {'suma': 0.0}}.
    # Aquí no declaras type: el tipo es el del valor Python que devuelves.
    # Usa claves de texto y valores JSON: int/float finitos, bool, str, None,
    # listas o diccionarios. NumPy requiere .tolist() para arrays y .item() para escalares.
    # Se detectan los componentes numéricos para las gráficas; el texto solo se registra.
    raise NotImplementedError('Define aquí tu estado inicial')


def paso(rt, i, propio, vecinos, k, global_data):
    """Obligatoria: calcula y devuelve el nuevo estado COMPLETO de este agente."""
    # propio: tu estado anterior; vecinos: {id_vecino: estado_recibido}.
    # k: índice de actualización, desde 0; en async los índices vecinos pueden diferir.
    # En coordinator, vecinos está vacío y global_data contiene lo que retornó coordinar().
    # En sync/async, global_data es None. No uses un agregado si tu modo no lo proporciona.
    # Parámetro común: rt.parameters_values['clave']; local: rt.nodes[i]['params']['clave'].
    # Escribe aquí la regla completa del valor siguiente. El ejecutor no añade Euler.
    # Conserva en el retorno las variables de memoria que todavía necesites;
    # puedes añadir variables, pero una clave que no retornes deja de estar en el estado.
    raise NotImplementedError('Define aquí tus ecuaciones')


# FUNCIONES OPCIONALES: descomenta solo las que necesites y completa su cuerpo.
# Se definen EN ESTE ARCHIVO; no se importan de otro algoritmo.
# También puedes añadir funciones auxiliares propias y llamarlas desde arriba.

# def preparar(rt):
#     # Preparación de cada proceso; puede repetirse durante la validación del ensayo.
#     # rt.local_id: ID propio en un agente; None en gestor/coordinador/evaluación.
#     # En un agente prepara solo sus datos; no recorras parámetros de otros nodos.
#     # Puedes guardar recursos en rt.mi_recurso. No confíes en compartirlos entre procesos.
#     pass

# def coordinar(rt, k, estados):
#     # Obligatoria SOLO en coordinator. estados = {id: estado}.
#     # Intercambio sync: misma ronda; async: últimas muestras de los participantes.
#     # En async, k es el índice local del solicitante, no un contador global.
#     # rt.coordinator_exchange indica la opción; rt.asynchronous incluye ambos modos async.
#     # El resultado JSON llegará como global_data a cada agente.
#     return {}  # Sustituye por tus agregados.

# def validar(rt, i, estado):
#     # Comprueba estado/forma/rangos y lanza ValueError si algo no cumple.
#     # En el agente valida solo su estado; después se usa también al evaluar registros.
#     # Los receptores verifican el formato JSON, sin acceder a parámetros ajenos.
#     pass

# def observar(rt, i, estado, k):
#     # Mediciones adicionales: {'energia': ...}. Aparecerán como obs/energia.
#     # El estado ya se grafica sin esta función; las observaciones no se comunican.
#     return {}

# def evaluar(rt, logs):
#     # Se llama tras completar el ensayo. logs[i][k] es el estado registrado.
#     # Devuelve (resumen dict, serie_global list). Solo declara converged si tienes un criterio.
#     # En async, índices iguales no significan un mismo instante: no los sumes como una ronda.
#     return {'conclusion': 'Describe tu resultado'}, []

# def verificar(rt, logs, entradas):
#     # Comprobación propia posterior; entradas contiene las muestras usadas en async.
#     # Devuelve un resultado JSON. No certifica automáticamente corrección matemática.
#     return {}


# EJEMPLO OPCIONAL DE FUNCIONES POR PERFIL (descomenta y adapta si lo necesitas).
# 1. Activa function_profiles/default_profile en ALGORITMO, arriba.
# 2. Añade a fields estos datos locales (además de los que necesite tu método):
#    {'key': 'centro', 'label': 'Centro', 'type': 'number', 'default': 2.0},
#    {'key': 'beta', 'label': 'Beta', 'type': 'number', 'default': 0.01, 'min': 0},
# 3. Usa estas funciones desde inicial/paso/observar según tus propias ecuaciones.
#    El descriptor crea el selector, pero NO elige funciones dentro de tu Python:
#    esa selección explícita está en coste_y_gradiente(). No necesitas ASISTENTE.
#    Los perfiles no obligan a usar coste, gradiente ni fitness en otros métodos.
#
# def coste_y_gradiente(rt, i, z):
#     p = rt.nodes[i]['params']                # Solo los datos del propio agente.
#     perfil = rt.nodes[i]['function_profile'] # Cadena: id elegido en el formulario.
#     d = z - p['centro']
#     if perfil == 'cuadratico':
#         return 0.5*d**2, d
#     if perfil == 'cuarto_grado':
#         return 0.5*d**2 + p['beta']*d**4, d + 4*p['beta']*d**3
#     raise ValueError(f'Perfil sin implementación: {perfil}')
#
# En paso(), por ejemplo:
#     coste_actual, gradiente_actual = coste_y_gradiente(rt, i, propio['x'])
#     x_nuevo = ...  # Tu regla completa, con los estados actuales recibidos.
#     coste_nuevo, gradiente_nuevo = coste_y_gradiente(rt, i, x_nuevo)
# No existe next_x automático en Python manual: tú guardas x_nuevo en una variable
# y conservas propio['x'] como anterior. Calcula la memoria nueva antes de retornar.
# Si necesitas fitness, define explícitamente cómo se obtiene a partir de tu coste
# o gradiente; el motor no deriva fórmulas ni deduce esa relación matemática.
#
# Para graficar el coste sin enviarlo, sustituye el ejemplo de observar() por:
# def observar(rt, i, estado, k):
#     coste, gradiente = coste_y_gradiente(rt, i, estado['x'])
#     return {'coste_local': coste, 'gradiente_local': gradiente}
#
# Para COMUNICAR un resultado necesario al método, inclúyelo como clave del estado
# devuelto por inicial() y paso(). El vecino usa vecinos[j]['clave_recibida']; no
# llama a coste_y_gradiente(rt, j, ...) ni consulta los parámetros/perfil ajenos.
# Todos deben acordar las claves y tipos de mensajes que usa tu algoritmo.
#
# Al pasar de 4 a 6 agentes, los existentes conservan su asignación; los nuevos
# reciben default_profile y los defaults de fields. Puedes cambiar cada selección
# en el formulario. La configuración guarda esas asignaciones para repetirla.
# El proceso solo recibe su perfil y parámetros; el código de todas las fórmulas
# forma parte del archivo compartido. El evaluador posterior y un coordinador
# explícito sí disponen de la configuración completa, como establece el contrato.

# FALLAS PROGRAMADAS (opcionales; configura el escenario en Nuevo experimento).
# rt.ids conserva todos los IDs configurados. rt.active_ids enumera los
# participantes de esta etapa; rt.available_ids los agentes disponibles.
# vecinos contiene solo vecinos disponibles, sin crear enlaces ni usar datos del
# agente retirado. El reinicio opcional llama a inicial solo para quien regresa;
# los demás conservan su evolución. Una falla permanente no reinicia a nadie.
# No supongas que un promedio, un invariante o tu memoria auxiliar siguen siendo
# correctos al desaparecer participantes. Ver docs/FALLAS.md.
# Si necesitas adaptar tu memoria, añade en este mismo archivo:
# def al_cambiar_red(rt, i, propio, evento):
#     # evento incluye k, removed, joined, active_ids, available_ids,
#     # state_policy y reinitialized (si este agente acaba de reiniciarse).
#     return propio
# Para evaluar participantes variables, usa evaluar_escenario(rt, registros,
# eventos), que devuelve un dict. No se llama al evaluador tradicional en fallas.
