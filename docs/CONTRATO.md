# Contrato de algoritmo

Los archivos escritos a mano y los generados por el [asistente](ASISTENTE.md) comparten este contrato. El asistente conserva sus ecuaciones en el diccionario literal `ASISTENTE` y sus funciones delegan en `lab.equations.EquationModel`, un intérprete sin ecuaciones particulares de ningún dominio. Editar el formulario reconstruye esas funciones; para código Python personalizado usa la plantilla y conserva sus cambios directamente en el archivo.

El descriptor `ALGORITMO` es un diccionario literal. Campos obligatorios: `id` (letras minúsculas, números y guion bajo, empezando con letra, 3–64 caracteres) y `name`. `mode` puede ser `sync`, `async` o `coordinator`; por defecto `sync`. Para comunicación entre vecinos, el panel del experimento permite seleccionar misma ronda (`sync`) o últimas muestras (`async`), sin regenerar el archivo. Se guarda como `execution_mode` y `rt.mode` indica el modo efectivo. Un archivo con `coordinator` conserva el rol central, pero permite ambos intercambios: `coordinator_exchange: "sync"` (por defecto) o `"async"` (últimas muestras). `rt.coordinator_exchange` indica esa elección y `rt.asynchronous` es verdadero tanto para vecinos asíncronos como para coordinador asíncrono. Cambiar la comunicación no garantiza que las ecuaciones converjan en ambos modos.

`parameters` describe campos comunes; `fields` describe los de cada agente. Ambos aceptan la forma antigua `[clave, etiqueta, valor]` (numérica) o diccionarios:

```python
{'key': 'ganancia', 'label': 'Ganancia', 'default': 0.1, 'type': 'number', 'min': 0}
{'key': 'orden', 'label': 'Orden', 'default': 2, 'type': 'integer', 'min': 1}
{'key': 'activo', 'label': 'Activar término', 'default': True, 'type': 'boolean'}
{'key': 'nombre', 'label': 'Nombre', 'default': '', 'type': 'string'}
{'key': 'regla', 'label': 'Regla', 'default': 'A', 'type': 'select', 'choices': ['A', 'B']}
{'key': 'matriz', 'label': 'Matriz', 'default': [[1, 0], [0, 1]], 'type': 'json'}
```

Los valores iniciales pertenecen al archivo del usuario. La plataforma no genera condiciones particulares para tamaños específicos. Puedes editar los campos o importar una configuración. `steps` y `period_s` en el descriptor solo establecen valores iniciales del formulario.

## Funciones

| Función | Contrato |
|---|---|
| `inicial(rt, i)` | Obligatoria. Devuelve un diccionario JSON con el estado completo del agente. |
| `paso(rt, i, propio, vecinos, k, global_data)` | Obligatoria. Devuelve el nuevo estado propio. `vecinos` contiene los estados de vecinos; en modo coordinador está vacío. |
| `coordinar(rt, k, estados)` | Obligatoria solo en modo coordinador. Recibe estados de los participantes: misma ronda en sync, últimas muestras en async. Devuelve cualquier valor JSON que llega como `global_data`. En intercambio async, k es el índice local del solicitante. |
| `preparar(rt)` | Opcional. Prepara recursos locales del proceso. Puede ejecutarse varias veces, incluida la validación; evita efectos externos. |
| `validar(rt, i, estado)` | Opcional. Lanza una excepción si el estado propio es inválido. Debe ser pura: se usa también en el coordinador y al evaluar registros. El receptor de un mensaje comprueba JSON finito sin ejecutar la validación privada del emisor. |
| `observar(rt, i, estado, k)` | Opcional. Devuelve un diccionario con mediciones adicionales. Sus componentes numéricos se registran bajo `obs/`. No altera el estado comunicado. |
| `evaluar(rt, logs)` | Opcional. Devuelve `(resumen, serie_global)`. `logs[id][k]` es el estado completo. El resumen puede incluir `conclusion` y `converged` booleano. La serie global es una lista de diccionarios tabulares (o `[]`); aparece como origen de gráficas después de evaluar. |
| `verificar(rt, logs, entradas)` | Opcional. Comprobación del autor. Recibe las muestras usadas en modo asíncrono; devuelve un resultado JSON registrado en `verification`. No se interpreta automáticamente como prueba matemática. |

`rt.parameters_values`, `rt.nodes[i]['params']`, `rt.ids`, `rt.neighbors[i]`, `rt.steps`, `rt.period` y `rt.config` dan acceso a parámetros y topología. **Cada agente recibe un archivo `config_agente_ID.json` propio**: contiene los parámetros comunes, la red y únicamente sus parámetros locales. `rt.local_id` identifica al agente; los otros elementos de `rt.nodes` no tienen `params`. Las funciones reciben copias profundas de estados y muestras.

El gestor, el evaluador posterior y el coordinador explícito conservan la configuración completa; en esos contextos `rt.local_id` es `None`. En `preparar(rt)`, usa esa distinción si necesitas una comprobación global y una preparación local. Un archivo antiguo que consulte parámetros ajenos desde un agente debe adaptar esa parte: no se devuelve la configuración completa como alternativa. Esto separa los datos entregados al algoritmo; no aísla permisos del sistema operativo. El Python cargado sigue siendo código del usuario con acceso a sus archivos.

## Estados y gráficas

Un estado puede contener, por ejemplo, `{'posicion': [1, 2], 'memoria': {'integral': 3}, 'fase': 'inicio'}`. Se conserva entero y aparecen las curvas `posicion/0`, `posicion/1` y `memoria/integral`. `fase` queda en el registro, sin curva. Booleanos se representan con 0 y 1. `/` dentro de una clave se escapa como `~1`, y `~` como `~0`.

`metrics` es opcional y solo asigna etiquetas: `[['posicion/0', 'Componente horizontal']]`. No limita qué se guarda o muestra. Nuevas claves o componentes aparecen automáticamente; una variable ausente en una ronda deja un hueco en su curva. Los paneles permiten varias variables Y; para unidades distintas conviene separarlas en paneles. También se pueden construir trayectorias Y contra X eligiendo otra variable como eje X.

Los estados deben usar tipos JSON estándar: convierte arrays de NumPy con `.tolist()` y escalares con `.item()`. NaN, infinito, números complejos y objetos Python arbitrarios no se transportan directamente. Representa un complejo con dos componentes si tu método lo necesita.

## Configuración y transporte

La configuración usa `schema_version: 1`, `algorithm`, `name`, `steps`, `period_s`, `parameters`, `nodes` y `edges`. Cada nodo tiene `id`, `host`, `port`, `params` y, opcionalmente, `timing`. El ejecutor local asigna puertos libres. Los enlaces son `[i, j]` o `[i, j, peso_positivo]`. En modo coordinador, `edges` debe ser `[]`.

`require_connected: true` exige conectividad; por defecto se permite un grafo desconectado, cuya pertinencia decide el algoritmo. `nodes[].timing.period_factor` multiplica la pausa asíncrona; `nodes[].timing.send_delay_ms` añade un retardo de recepción experimental. Ningún nombre dentro de `params` tiene significado reservado para el transporte.

En `sync`, los vecinos corresponden a la ronda k. En `async`, cada agente usa las últimas muestras; k es un índice local, no una ronda global. Se registra versión y antigüedad observada en `entradas_ID.jsonl`. El periodo es una pausa mínima real, no el paso de integración de las ecuaciones. Los tres modos avanzan por iteraciones, no por eventos arbitrarios.

## Persistencia y evaluación

Cada ensayo conserva `algoritmo.py` y su SHA-256, configuración, huellas del ejecutor, consolas y `nodo_ID.jsonl` con `round`, `wall_s`, `node`, `state` y `values`. Al completar o exportar se genera CSV con la unión de variables y celdas vacías donde no existían. Los nombres CSV usan `value/` para evitar colisiones con las columnas internas.

Los nuevos ensayos añaden `monotonic_s` a los registros y `timing_protocol: 1` a la configuración. El motor acuerda un inicio después de la preparación y guarda `tiempos.json`; el CSV añade `experiment_s` respecto a ese inicio. No requiere nuevas funciones en el algoritmo ni modifica `paso`. La duración funciona también en Python manual. La curva global temporal necesita métricas del asistente; no se llama repetidamente a `evaluar` para inventar métricas intermedias. Véase [protocolo de tiempos](EJECUCION_PLACAS.md#medir-y-comparar-el-tiempo-de-ejecución).

La evaluación básica comprueba secuencia e identidad de los registros, estados finales y trazas asíncronas. No vuelve a ejecutar implícitamente las ecuaciones: eso sería incorrecto para métodos aleatorios, con memoria o dependientes de entradas externas. El autor aporta su criterio mediante las funciones opcionales. Una evaluación fallida se informa y conserva los datos, sin presentar convergencia como verificada.

El archivo de un ensayo no depende de que el algoritmo siga instalado para visualizarlo o exportarlo. Para repetir desde el formulario se necesita instalar la misma versión (SHA-256) del archivo. Modificar un archivo después de configurarlo requiere volver a seleccionarlo y generar una configuración nueva.


## Perfiles opcionales de funciones locales

`ALGORITMO` puede declarar `function_profiles: [{'id': 'cuadratico', 'name': 'Cuadrático'}, {'id': 'otro', 'name': 'Otra familia'}]` y `default_profile: 'cuadratico'`. Los identificadores son únicos, comienzan con letra y solo incluyen letras, números y guion bajo (hasta 64 caracteres, máximo 30 perfiles). La interfaz crea un selector por agente; la asignación se guarda como `nodes[].function_profile`, fuera de `params`. Al aumentar agentes conserva los existentes y asigna el predeterminado a los nuevos. Una asignación desconocida se rechaza. Si falta la asignación se usa el predeterminado.

En Python escrito a mano, lee `rt.nodes[i]['function_profile']` y selecciona tú la función local correspondiente. El descriptor genera la selección y valida sus valores, pero no reescribe el cuerpo de tu código ni requiere `ASISTENTE`. En un archivo generado, `ASISTENTE.function_profiles` contiene además la lista `functions` de cada perfil; `EquationModel` selecciona las fórmulas automáticamente. Con perfiles, la lista superior `functions` se deja vacía.

En los workers solamente el nodo propio lleva `function_profile`; los vecinos no incluyen esa asignación ni `params`. El código compartido contiene todas las fórmulas disponibles. El evaluador posterior y el coordinador explícito sí tienen las asignaciones completas. Los algoritmos antiguos sin perfiles conservan su comportamiento.

Consulta [el recorrido con dos perfiles](PERFILES_FUNCIONES.md) para funciones, comunicación, gráficas y límites de esta opción.

## Biblioteca y ejemplos predeterminados

Guardar como ejemplo predeterminado conserva los parámetros comunes, los datos y perfiles de cada agente, la topología y la comunicación del algoritmo seleccionado. Al seleccionarlo nuevamente se carga ese ejemplo; Cargar ejemplo predeterminado permite recuperarlo directamente. Al aumentar agentes se conservan los existentes y los nuevos usan los valores y el perfil por defecto del archivo; revisa sus datos. El ejemplo pertenece a la versión del archivo, y debe guardarse nuevamente si cambias el código.

Eliminar algoritmo del menú retira su archivo y su ejemplo a una carpeta recuperable dentro de datos/algoritmos_eliminados. Recuperar algoritmo eliminado los devuelve sin sobrescribir otro algoritmo con la misma identidad. Los ensayos anteriores conservan sus archivos y resultados.

## Ejecución en placas

Consulta [Cómo se ejecuta en las placas](EJECUCION_PLACAS.md) para estudiar el recorrido de archivos, verificar las vistas locales y conocer los límites del aislamiento y de la conservación de resultados.

Las mismas funciones del contrato se ejecutan en Linux/Python mediante SSH/SFTP; las ecuaciones no se cambian. El archivo del algoritmo debe ser autocontenido o disponer de sus dependencias en cada Pi. Cada worker recibe su vista local; el coordinador explícito recibe el contexto completo y se ejecuta en la primera placa asignada. execution_target indica local o remote y clock_scope distingue shared_laptop de per_agent. En remote, wall_s es el tiempo desde el inicio de ese proceso, sin atribuir sincronización a relojes diferentes.

## Variante con fallas programadas

El contrato anterior se conserva sin escenarios. Para retiradas, reincorporaciones y callbacks `al_cambiar_red` y `evaluar_escenario`, consulta [Fallas programadas](FALLAS.md). `rt.ids` conserva la lista original; `rt.active_ids` contiene los participantes de la etapa. No se proporciona compensación matemática automática.

En escenarios de formato 2, los agentes no disponibles siempre se excluyen de las entradas. El estado de regreso puede conservarse (`keep`) o reconstruirse con `inicial` solo en los agentes que se reincorporan (`reset_returning`). El callback recibe `reinitialized` para distinguir ambos casos; el reinicio automático no afecta a los demás participantes.
## Referencias programadas

Los modelos del asistente admiten `config.demand_schedule`: un parámetro común numérico y hasta 30 eventos con índice `at` único y valor absoluto `value`. No se incorpora ninguna ley de control. La configuración inicial y la huella permanecen inmutables.

En Python manual declara `PARAMETROS_PROGRAMABLES = True` únicamente cuando `paso`/`coordinar` consulten `rt.parameters_at(k)`. `rt.parameters_values` conserva los valores iniciales. Los índices son locales en asíncrono. Consulta [DEMANDA_VARIABLE.md](DEMANDA_VARIABLE.md) para las semánticas de evaluación temporal y registro.

