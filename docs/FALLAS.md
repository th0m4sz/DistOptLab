# Fallas programadas de nodos

Esta opción permite comprobar qué ocurre cuando uno o varios agentes dejan de calcular y enviar datos durante un experimento. Puedes programar su regreso o dejarlos fuera hasta terminar.

## Primera prueba

1. Pulsa **Cargar ejemplo de fallas**. Se abre un consenso de cuatro agentes con 600 iteraciones.
2. Revisa la falla del agente 4: sale en la iteración **200** y vuelve en la **400**.
3. En **Valores para su regreso**, deja **Retomar su último estado** para esta primera prueba.
4. Pulsa **Iniciar experimento**. En Ejecución, grafica x por iteración. Las líneas verticales indican la falla y el regreso; el hueco de la curva del agente 4 indica que no estuvo disponible.
5. Después puedes cambiar el agente, las iteraciones o los valores para su regreso y ejecutar otra prueba. Cada ensayo conserva sus propios resultados.

No se alteran las ecuaciones de los algoritmos instalados. Que un algoritmo siga ejecutándose no demuestra que resuelva correctamente el problema después de retirar agentes.

## Qué se simula

La falla suspende los cálculos y hace que el agente deje de ofrecer muestras actuales. La Raspberry Pi permanece encendida y el proceso mantiene el servicio mínimo necesario para supervisar el ensayo y reanudarlo. No es un apagado físico, un reinicio del sistema operativo ni la muerte inesperada de Python. Una desconexión física o pérdida de SSH se sigue registrando como error operativo; no se promete recuperación de esos fallos.

Los eventos se ejecutan **antes de calcular x[k+1]**, cuando el índice local es k. Inicio 50 significa que ya se calculó el estado 50, pero el agente no calcula los pasos 50→51 y siguientes hasta su regreso. El intervalo [50,75) contiene los índices inactivos 50 a 74. El estado de entrada al índice 75 se conserva o se reinicializa según la política elegida. Los identificadores nunca se renumeran.

## Qué hacen los demás

Los agentes no disponibles se excluyen siempre de los cálculos de sus vecinos. Su último dato puede seguir en el historial, pero no se utiliza para actualizar a los demás. Por ejemplo, si 1 se comunicaba con 2 y 4, cuando falla 4 continúa usando solo a 2. Si 4 vuelve, vuelve a utilizarlo. Los enlaces entre los demás permanecen iguales; no se crean enlaces nuevos. Si un agente queda sin vecinos, su sumatoria sobre vecinos queda vacía: si esto permite continuar correctamente depende de su ecuación.

El coordinador, si existe, usa solo a los participantes disponibles. Puede reunir la misma ronda (síncrono) o utilizar las últimas muestras de la etapa (asíncrono). Al comenzar una etapa asíncrona espera una primera muestra de cada participante y descarta las muestras de etapas anteriores. `sum_neighbors`, `mean_neighbors` y `weighted_neighbors` usan esos vecinos. En expresiones del asistente, **n es el número de participantes de ese momento**. Si no queda ninguno disponible, no hay cálculos hasta que vuelva alguno.

## 1. Con qué valores regresan los agentes afectados

**Retomar su último estado:** cada agente que regresa retoma las variables que tenía al salir, por ejemplo x y lambda. Los demás conservan su evolución.

**Usar sus condiciones iniciales:** solo se reinician los agentes que pasan de no disponibles a disponibles en ese instante. Por ejemplo, si falla 4 en 50 y vuelve en 75, en 50 no se reinicia nadie; en 75, solo 4 vuelve a sus condiciones iniciales. Los agentes 1, 2 y 3 siguen desde donde han llegado.

Si 2 y 4 vuelven juntos, se reinician ambos. Si 2 vuelve después de 4, el regreso de 2 no reinicia otra vez a 4. Una falla permanente no reinicia a nadie. Esta opción usa la función `inicial` del algoritmo y recalcula también sus variables algebraicas, como xhat y fitness, para que concuerden con la condición inicial. No modifica automáticamente las condiciones iniciales para satisfacer un balance global.

## 2. Quién falla y cuándo

Pulsa **Añadir falla**, elige los agentes, la iteración de salida y la de regreso. Marca **No vuelve durante este experimento** para una retirada permanente. El reinicio, si está seleccionado, se aplica al regreso; no al desaparecer ni a cada cambio de la red.

## Ejemplo: despacho económico con xhat

La actualización instalada intercambia potencia entre vecinos. En modo síncrono, con enlaces simétricos y sin recortes externos, lo que aumenta un generador lo cede otro: la suma se conserva mientras no cambie el conjunto de participantes. **Conservar una suma no equivale a recuperar la producción de un generador que se retira.**

Si los cuatro producen 800 kW y se retira el que producía aproximadamente 170 kW, los disponibles quedan produciendo aproximadamente 630 kW. La ecuación conserva esa nueva suma; no contiene un término de error de demanda que la lleve otra vez a 800. Que el ensayo llegue al final con un déficit no es un bloqueo del programa.

Si eliges **Usar sus condiciones iniciales**, al salir 4 no se reinicia a los restantes: mantienen la suma de aproximadamente 630 kW. Si regresa con su condición inicial de 250 kW en vez de sus anteriores 170 kW, la suma cambia por esa diferencia. Esta elección no garantiza recuperar exactamente los 800 kW; esa recuperación depende del método matemático.

Hay además una condición de conectividad efectiva. Al quitar 4 del anillo 1–2–3–4–1 queda la cadena 1–2–3. Si 2 llega a su mínimo, su xhat vale cero. Como el intercambio de esta ecuación se multiplica por el xhat de ambos extremos, 1 y 3 dejan prácticamente de intercambiar potencia a través de 2, aunque la conexión TCP siga funcionando. Pueden detenerse con fitness diferentes. Por eso una red conectada en el dibujo no basta para garantizar el óptimo de esta ecuación con capacidades. Es una consecuencia de la fórmula del algoritmo, no de que la simulación siga bloqueada.

Las notas del documento base distinguen la conservación de recursos de la disponibilidad de un generador. En su ejemplo de disponibilidad, el generador sigue en el modelo y se modifica su fitness mediante un factor de disponibilidad (ecuación 40); eso es diferente de retirar abruptamente un agente con potencia no nula. Incorporar esa respuesta u otra compensación requiere definir las ecuaciones del algoritmo. La plataforma no las añade automáticamente. En asíncrono, tampoco se puede dar por garantizada la conservación exacta de la suma, porque los intercambios usan muestras de momentos diferentes.

## Etapas y comunicación

Todos conocen el escenario desde el inicio. Cada inicio o fin de falla crea una frontera de etapa. El gestor espera confirmación de que los agentes llegaron a ese índice y libera la etapa mediante archivos `FASE_K.LISTA`. No calcula soluciones ni retransmite estados de vecinos. En las Pi utiliza SSH/SFTP para esas señales y para recuperar registros; los estados siguen viajando directamente por TCP.

En **asíncrono**, estas barreras existen solo al cambiar de etapa. Dentro de cada etapa cada agente continúa con sus últimas muestras, sin exigir rondas iguales. Se espera una primera muestra de cada vecino disponible de la nueva etapa para evitar reutilizar estados anteriores a una falla o reincorporación. Por tanto, esta variante ofrece asincronía por etapas, no un ensayo de cambios de red sin coordinación externa.

Los eventos se programan por índice, no por segundos. Su instante real depende del hardware y queda registrado. Programar los mismos eventos reproduce el escenario; las trayectorias asíncronas pueden variar por la planificación de procesos y los retardos. Para auditar se conservan las entradas efectivas.

## Estados y creación de algoritmos

Ninguna elección de valores se realiza automáticamente por razones matemáticas. Un método de seguimiento de gradiente puede necesitar reconstruir sus variables auxiliares; un despacho conservativo puede seguir sin recuperar la potencia perdida aunque conserve conectividad.

Los algoritmos del asistente siguen usando los mismos pasos y ecuaciones. Si su respuesta exige cambios específicos de memoria, se puede añadir este callback en su archivo Python:

```python
def al_cambiar_red(rt, i, propio, evento):
    # Se llama en el agente disponible tras cambiar de etapa, nunca al inicio k=0.
    # propio contiene solo su estado. Devuelve su nuevo estado JSON.
    # evento: k, phase, removed, joined, active_ids, available_ids,
    #         state_policy y reinitialized (True solo si este agente se reinició).
    return propio
```

`rt.ids` conserva los identificadores configurados; **rt.active_ids** contiene los participantes matemáticos de la etapa y **rt.available_ids** los que están disponibles. `rt.active_neighbors[i]` ofrece los pesos de los vecinos participantes; `rt.neighbors` conserva la red declarada. La vista local sigue excluyendo parámetros y perfiles privados ajenos. El escenario revela solo identificadores y cambios de disponibilidad conocidos de antemano; no implementa un detector de fallos distribuido.

El callback se sigue llamando en los agentes disponibles tras cada cambio de red. Puede adaptar memoria según las ecuaciones del autor; el ejecutor no les impone un reinicio. Si el agente que regresa debe reiniciarse, recibe en el callback su estado inicial ya construido.

Para un coordinador Python personalizado, utiliza `estados` o `rt.active_ids`, no asumas que siempre recibirás los IDs originales. Las condiciones necesarias de conectividad, capacidad, pesos, tamaño de paso y estado auxiliar pertenecen al autor del método. La plataforma no añade compensación de demanda, redistribución de recursos ni nuevas conexiones.

## Coordinador

Puedes seleccionar **Coordinador** como objetivo de una falla en un algoritmo coordinado. Se suspende su agregación y se registra una interrupción esperada, cancelando las esperas de sus clientes. No hay elección de líder, respaldo ni sustitución automática. Una reincorporación posterior por índice no permite avanzar por sí sola desde una ronda bloqueada; por ello, la falla del coordinador debe ser permanente.

Retirar un agente de una Pi que también aloja al coordinador **no** retira al coordinador: son procesos separados. Apagar físicamente esa Pi sí perdería ambos y se consideraría un fallo operativo no simulado.

## Archivos para comprobar lo ocurrido

- `config.json → faults`: eventos programados y valores elegidos para el regreso (`state_policy`).
- `nodo_ID.jsonl`: índice lógico, tiempo local, estado, fase y disponibilidad. Los valores gráficos están vacíos durante una falla para no mostrar el último valor como vigente.
- `entradas_ID.jsonl`: muestras efectivamente utilizadas, versiones, etapa, vecinos y agregado recibido si corresponde.
- `eventos_ID.jsonl`: etapa aplicada por cada agente, índice y tiempo local.
- `eventos.json`: plan y cambios registrados consolidados tras evaluar.
- `evaluacion.json`: distingue continuidad o interrupción del algoritmo. No confunde terminar un escenario con converger.

Las métricas globales del asistente se calculan sobre agentes disponibles. En asíncrono se conserva el agregado terminal en `serie_global.csv`. La vista **Serie global del evaluador** añade su evolución en cada instante registrado si hay reloj común, tomando el último estado disponible de cada agente; el ZIP incluye `serie_global_evolucion.csv`. **Global por tiempo** usa una cuadrícula seleccionable. Si todos están inactivos, las métricas quedan sin valor; no se inventa un cero para un máximo, promedio o coste arbitrario. El criterio final tradicional no se evalúa automáticamente, porque estaba formulado para participantes fijos.

Un autor puede proporcionar una evaluación específica:

```python
def evaluar_escenario(rt, registros, eventos):
    # registros: {id: [filas completas con round, state, active, phase, ...]}.
    # eventos: cambios aplicados por cada agente, con sus tiempos locales.
    return {'conclusion': 'Evaluación propia del escenario'}
    # Añade converged: True/False únicamente si compruebas tu criterio matemático.
```

## Límites operativos

Se admiten múltiples nodos, múltiples eventos, eventos simultáneos y reincorporaciones; no se permiten intervalos superpuestos para un mismo objetivo. El grafo mantiene los enlaces originales entre quienes siguen activos: puede quedar desconectado. Las barreras tienen un límite de 30 segundos; no confunden una ausencia programada con una avería inesperada del gestor. No hay alta de agentes nuevos, modificación arbitraria de enlaces, fallos bizantinos ni conmutación automática del coordinador.

Las esperas de comunicación del ejecutor de fallas también tienen un margen máximo de 30 segundos para tolerar pausas temporales del equipo o del almacenamiento. La falla programada conocida se avisa inmediatamente, sin esperar ese margen. Una parada solicitada cancela las consultas pendientes. Se conserva cada actualización en JSONL; el resumen que ve el panel se escribe como máximo aproximadamente cada 0,3 segundos, además de los cambios de disponibilidad, las fronteras entre etapas y el cierre. Esto evita forzar una escritura atómica a disco por cada iteración.

Para desactivar esta función, apaga el interruptor del escenario. Sin eventos, la aplicación utiliza el ejecutor anterior y su evaluación habitual.

## Configuraciones y ensayos anteriores

Los nuevos escenarios usan el formato 2: `state_policy` vale `keep` o `reset_returning`; la exclusión de agentes no disponibles es fija. Al abrir, repetir o importar una configuración anterior se adapta a este comportamiento. El ajuste antiguo de reinicio se convierte en reinicio exclusivo al regresar. Los archivos y resultados de ensayos ya realizados permanecen intactos y se identifican como históricos; no se reinterpretan sus trayectorias ni se presentan como pruebas del comportamiento actual.
