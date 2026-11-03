# Coordinador síncrono y asíncrono

## Cómo elegirlo

1. Selecciona RCCRD coordinado u otro archivo que declare `mode: coordinator`.
2. En **Comunicación de este experimento**, elige **Coordinador · síncrono (misma ronda)** o **Coordinador · asíncrono (últimas muestras)**.
3. Configura agentes, paso numérico e intervalo mínimo e inicia localmente o en las Raspberry Pi. El archivo y las ecuaciones son los mismos. Guarda la configuración si quieres repetir exactamente esa elección.

La configuración conserva `execution_mode: coordinator` para identificar el rol central y añade `coordinator_exchange: sync` o `async` para su intercambio. Las configuraciones anteriores sin ese campo continúan siendo síncronas. No se permite sustituir el rol coordinador por vecinos: son entradas matemáticas distintas, no una restricción a la asincronía.

## Funcionamiento

En síncrono, el coordinador reúne los estados de todos los participantes de la misma ronda k, calcula `coordinar` una vez y devuelve ese resultado a todos.

En asíncrono, espera al menos una muestra de cada participante al comienzo. Después mantiene la última muestra de cada uno y responde a cada actualización sin esperar nuevas muestras de los otros. Un solicitante puede estar en 100 mientras los otros están en 85, 110 y 92. Cada agente espera su propia respuesta TCP; no existe una barrera de ronda global. El motor no altera el paso matemático para compensar esa diferencia ni limita automáticamente la antigüedad aceptada. Los reintentos de una misma petición reciben la misma respuesta; no vuelven a ejecutar su agregado.

Cuando termina un agente rápido, publica también su estado terminal. El coordinador lo conserva para los que siguen calculando. Esa publicación no ejecuta otra actualización local ni otro agregado. Las sesiones y el servidor se cierran al finalizar o detener el ensayo. Las esperas de comunicación siguen teniendo límites operativos y admiten parada.

El callback sigue siendo `coordinar(rt, k, estados)`. `estados` contiene las muestras de los participantes. En asíncrono, k es **el índice local del solicitante**, no un contador global: cualquier código manual que suponga que todos los estados pertenecen a k debe revisarse. `rt.coordinator_exchange` permite distinguir ambos intercambios; `rt.asynchronous` también incluye la asincronía entre vecinos. No se incluyen ecuaciones de despacho en el transporte.

## Qué cambia en RCCRD

Se mantiene la expresión del agregado robusto y la actualización local del archivo instalado. En asíncrono se evalúan con estados de momentos diferentes. Ejecutarse correctamente no demuestra convergencia, recuperación de demanda o invariancia de límites para todo paso o retardo. Los límites de estado declarados por el algoritmo se siguen comprobando y un fallo matemático no se oculta como un problema de comunicación.

Esta modalidad conserva un coordinador central con acceso a la configuración completa. Los workers siguen recibiendo solo sus parámetros privados y los agregados declarados; no se les entregan coeficientes ajenos. La respuesta de auditoría contiene identificadores, versiones y antigüedad, no los estados completos de los demás.

## Fallas programadas

Se conservan las barreras por etapas del ejecutor de fallas. Los agentes no disponibles se excluyen de los agregados. Al regresar alguno, la nueva etapa espera una primera muestra de cada participante y no reutiliza muestras de antes de la retirada o del reinicio. Dentro de la etapa, el coordinador asíncrono utiliza últimas muestras sin reunir rondas. La condición inicial al regreso se aplica únicamente a quienes regresan, si así se seleccionó.

La falla programada del coordinador interrumpe el ensayo; no hay sustitución automática. Una avería física inesperada no se convierte automáticamente en una retirada del inventario matemático. Esta ampliación no añade detección distribuida de fallas ni modifica esa política.

## Registros y gráficas

`entradas_ID.jsonl` conserva por actualización `k`, `global_data` y `coordinator`, con:

- `sequence`: secuencia de cálculo del agregado en el coordinador; no una ronda común.
- `phase`: etapa del escenario.
- `sources`: identificador de cada participante con su `version` y `age_s`. La versión permite localizar el estado exacto en `nodo_ID.jsonl`. La antigüedad se mide desde que esa versión fue recibida por el coordinador; no es la latencia unidireccional ni la edad física garantizada del estado.

La evaluación comprueba que esas versiones existen, corresponden a participantes disponibles de la etapa y que se incluyó el estado propio enviado. No reejecuta arbitrariamente un coordinador manual para certificar su fórmula.

Para los modelos del asistente, el evaluador asíncrono conserva su agregado terminal en `serie_global.csv`. En **Serie global del evaluador**, cuando existe referencia temporal común, la interfaz muestra también la evolución de esas mismas métricas en cada cambio registrado: usa el último estado disponible de cada agente en ese instante. El eje es tiempo, no una ronda común. La exportación incluye esta evolución completa en `serie_global_evolucion.csv`, además del CSV terminal original. Esto permite abrir los ensayos existentes sin modificarlos ni repetir su ejecución.

**Global por tiempo** permite elegir una cuadrícula de representación (0.1 s por defecto); **Global por índice** agrupa los estados de igual índice local. Son selecciones de muestras diferentes. Sin reloj común, sin modelo del asistente o con métricas propias de un evaluador Python no declaradas en el modelo, se conserva la salida original del evaluador, que puede ser un punto.

Las comparaciones de duración distinguen Coordinador síncrono de Coordinador asíncrono. Los evaluadores Python personalizados siguen siendo responsabilidad del autor y pueden consultar `rt.asynchronous` para evitar supuestos de simultaneidad. Las conclusiones se guardan en `evaluacion.json`; el panel de ejecución muestra el estado operativo y los errores reales, sin el aviso final genérico.
