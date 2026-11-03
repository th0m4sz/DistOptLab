# Cómo se ejecuta un algoritmo en las Raspberry Pi

Los algoritmos con coordinador admiten intercambio síncrono o asíncrono tanto localmente como en placas. Se elige en Comunicación de este experimento. [Funcionamiento y límites](COORDINADOR_ASINCRONO.md).

## Medir y comparar el tiempo de ejecución

1. Ejecuta un ensayo nuevo, local o en placas. La medición se incorpora automáticamente al motor y funciona con algoritmos del asistente y Python manuales; no debes cambiar sus ecuaciones.
2. En **Ejecución**, el encabezado muestra **Hasta la última muestra** y **Confirmación del gestor**. El historial incluye la primera duración. Es tiempo para completar el trabajo, no tiempo de convergencia certificado.
3. Para cada agente selecciona **Eje X → Tiempo de ejecución (s)**. Para métricas globales del asistente, selecciona **Origen → Global por tiempo (último estado)**. El intervalo base es 0.1 s y puede cambiarse; cambia la representación, no el ritmo del algoritmo. Los saltos representan estados retenidos, no interpolación ni suavizado.
4. En **Historial → Comparar con otro ensayo**, selecciona los dos ensayos del mismo algoritmo, el origen y la variable. Ambos comparten el mismo eje en segundos. También puedes comparar por índice. Los tiempos antiguos desde lanzamiento no se mezclan con los nuevos desde todos preparados.
5. **Exportar resultados ZIP** incluye los registros y mediciones descritos abajo. La gráfica por índice y la evaluación original siguen disponibles por separado.

### Qué se cronometra

El gestor espera a que todos los agentes tengan inicializados su estado y comunicaciones. En asíncrono ya han recibido una primera muestra de sus vecinos. Antes de dar la señal de inicio registra `origin_monotonic_s` usando `time.monotonic()` de la laptop. La señal inicial no añade barreras a cada iteración asíncrona: cada agente sigue actualizando a su ritmo. Tampoco garantiza que todos reciban la señal en el mismo instante; se registra la dispersión de arranques.

En escenarios de fallas sigue existiendo la barrera inicial de etapa y las barreras de cambios de disponibilidad. Esas esperas forman parte del tiempo de ejecución. Las fallas y cambios de referencia definidos por índice no necesariamente ocurren en el mismo segundo entre modalidades.

- **Hasta la última muestra**: máximo de las marcas temporales finales de los agentes, trasladadas a la referencia de la laptop. Incluye comunicaciones, esperas entre actualizaciones y trabajo de registro durante el ensayo; termina en la última muestra, no en el cierre de los procesos.
- **Confirmación del gestor**: reloj de la laptop cuando detecta que todos completaron menos el origen. Incluye el retardo del sondeo y de las transferencias de resultados. Se captura antes de las comprobaciones finales de reloj. El sondeo remoto espera 0.5 s más el coste de transferencia; el local, 0.1 s. No usar el refresco visual del navegador como cronómetro.
- Se excluyen envío previo de archivos, calibración inicial, evaluación matemática posterior, generación de gráficas y calibración final. No es tiempo de CPU puro. No se multiplica el paso de Euler por las iteraciones para obtener estos segundos.

### Cómo se relacionan los relojes de las placas

`lab/timing.py` implementa un intercambio de consulta/respuesta por los mismos canales SFTP autenticados. Ocurre antes de liberar el cálculo y después de terminarlo; no añade consultas de reloj por iteración. El agente responde con su reloj monotónico, sin parámetros ni estados de otros agentes.

Para cada consulta se conservan el envío `a` y recepción `b` de la laptop y la marca `m` de la placa. Se estima `offset = (a+b)/2 - m`, con semiancho de ida y vuelta `(b-a)/2`. La conversión es `experiment_s = monotonic_s + offset - origin_monotonic_s`. Se guardan cinco consultas iniciales y se elige la de menor ida y vuelta. No se ajusta el reloj del sistema operativo ni se presupone que las latencias de ida y vuelta sean iguales: el semiancho describe la incertidumbre del intercambio.

Se conserva el offset inicial para toda la trayectoria. Al finalizar se hacen tres consultas de contraste. El margen mostrado es el mayor entre el semiancho inicial y el cambio absoluto de offset más el semiancho final. Es una estimación del margen de alineación a partir de los extremos, **no una garantía de deriva máxima durante todo el ensayo**, ni una certificación de simultaneidad física. Si falta el contraste final se informa. Para ensayos largos o diferencias del orden de ese margen, hace falta mejorar o validar la instrumentación antes de afirmar una ventaja temporal. Aumentar los puntos del gráfico no mejora esta precisión.

Localmente se comparte el reloj monotónico del sistema y el offset es cero. El estado inicial, ya preparado antes de la señal, se representa en t=0. Estimaciones negativas por incertidumbre remota también se limitan a cero; las marcas crudas permiten auditarlo. Si la duración es comparable al margen, no se puede resolver con fiabilidad esa diferencia.

### Reconstrucción y archivos verificables

La curva global usa, para cada instante, la última muestra registrada **hasta ese instante**, nunca una futura ni una mezcla por igualdad de índices. Solo excluye estados marcados inactivos; no inventa potencias cero. Mientras un agente sigue en marcha no se extiende la curva más allá de lo disponible en sus registros; uno ya terminado conserva su estado final. Se mantienen las transiciones de disponibilidad además de la cuadrícula. No exige una observación simultánea: es una reconstrucción de los estados registrados y conserva su antigüedad.

En una métrica del asistente, dentro de `sum_all("...")`, `mean_all("...")` y otras reducciones, `k` es el índice de la muestra seleccionada de ese agente. Fuera de esas reducciones no hay un k común cuando los agentes difieren; expresiones que necesitan ese k quedan vacías. Las funciones, perfiles y parámetros de cada agente se aplican en el evaluador de la laptop. No se envían esos datos a los otros agentes. Un Python manual dispone de duración y curvas temporales por agente; para esta reconstrucción global necesita declarar métricas en el modelo del asistente. Su función `evaluar` mantiene su contrato anterior.

| Archivo | Evidencia |
| --- | --- |
| `nodo_ID.jsonl` | Estados completos, índice y `monotonic_s` original; `wall_s` conserva su significado anterior. |
| `nodo_ID.csv` | Observaciones, índice, `wall_s`, marca original y `experiment_s` cuando hay referencia común. |
| `tiempos.json` | Inicio común, todas las muestras de calibración, offset elegido, contraste final, duración y definición de límites. |
| `tiempos_agentes.csv` | Inicio y última muestra de cada agente, margen y cambio de offset. |
| `serie_global_por_tiempo.csv` | Métricas reconstruidas; tiempo, índices mínimo/máximo, agentes activos y antigüedad máxima de las muestras. Exportación automática con intervalo base 0.1 s. |
| `software.json`, `config.json`, `algoritmo.py` | Versión de código y configuración utilizadas, incluyendo paso, esperas y modalidad. |

Para recalcular la duración desde los JSONL y comprobar su consistencia con las calibraciones, desde la carpeta de la plataforma:

```powershell
.venv\Scripts\python.exe -m herramientas.medir_resultados datos\experimentos\ID_DEL_ENSAYO --intervalo 0.1
```

El comando regenera el CSV temporal sin ejecutar actualizaciones. En Linux usa `.venv/bin/python`. También acepta la carpeta de un ZIP de resultados descomprimido. El límite de reconstrucción es 20000 intervalos; para ensayos más largos elige un intervalo mayor. Si se supera durante la exportación automática se conserva el resto y se explica en `exportacion_temporal.json`.

Un artículo debe distinguir duración para un número de actualizaciones y tiempo para alcanzar un error definido. Mantén condiciones comparables, repite ensayos, informa dispersión y publica los registros y este procedimiento. El sistema no crea automáticamente un nuevo criterio de convergencia ni afirma que una ejecución más corta sea más precisa.

## Comparar curvas globales por índice

En **Ejecución → Origen → Global por índice (curva reconstruida)** puedes observar las métricas globales declaradas en el asistente a lo largo del ensayo. Se combinan los estados registrados por cada agente en su índice local k, excluyendo los que figuran inactivos en ese índice. Se conservan los cambios de disponibilidad y se muestra una selección de hasta aproximadamente 800 índices para ensayos largos. Las expresiones no evaluables quedan vacías.

En asíncrono, los estados con el mismo índice pueden haberse producido en momentos diferentes: esta curva permite comparar evolución por número de actualizaciones, pero no representa una medición simultánea de potencia ni permite medir cuánto tarda físicamente la red en converger. No se interpolan estados ni se cambia el resultado formal del evaluador. Los Python manuales necesitan métricas declaradas mediante el modelo del asistente para esta reconstrucción; su evaluador original sigue disponible.

La vista se calcula también con los registros parciales disponibles, hasta el último índice que tengan todos. Al exportar se añade `serie_global_por_indice.csv` sin reemplazar `serie_global.csv`. La vista por índice conserva ese eje; para segundos utiliza Global por tiempo. Las nuevas disposiciones por agente abren con Tiempo de ejecución cuando existe el protocolo temporal; las disposiciones guardadas conservan su elección. Los ensayos antiguos locales admiten tiempo desde lanzamiento con preparación; los antiguos en placas no tienen alineación recuperable y requieren repetirse para obtener tiempo común.

## Recorrido desde la interfaz

1. Conecta laptop y Raspberry Pi a la misma red y habilita SSH en las placas. En la terminal de cada placa (por ejemplo, Raspberry Pi Connect), ejecuta `hostname -I`: muestra las IP. Usa la dirección de la red compartida con la laptop. `hostname` muestra el nombre, que puedes probar seguido de `.local`; `whoami` muestra el usuario. No escribas `ssh`, `http://` ni varias IP en el campo de dirección.
2. En **Dispositivos → Agregar dispositivo**, registra nombre para identificarla, IP o nombre, usuario SSH y contraseña. El puerto suele ser 22. **Guardar y verificar** registra la placa y, en una sola sesión SSH, autentica, comprueba Python 3.10 o posterior y acceso SFTP. Un error conserva la placa para corregir sus datos; una contraseña nueva solo se guarda cuando la comprobación completa funciona.
3. Para placas existentes, pulsa **Verificar acceso de todas** o marca varias y pulsa **Verificar seleccionadas**. Se usan las contraseñas guardadas, con hasta cuatro comprobaciones simultáneas. Cada placa tiene su resultado independiente; una sin contraseña no impide comprobar las otras. No se hace un sondeo TCP previo ni se reintenta una contraseña rechazada. **Diagnóstico de red · opcional** queda para distinguir problemas de resolución o servicio; no es un paso obligatorio ni autentica.
4. En el experimento elige ejecución en Raspberry Pi y asigna una placa distinta a cada agente. El agente es una entidad del algoritmo; la placa es el equipo que lo ejecuta. La misma placa puede representar otro agente en un ensayo posterior.
5. Al iniciar, las contraseñas guardadas ya están seleccionadas y sus campos quedan ocultos. Para usar una temporal diferente, desmarca **Usar contraseña guardada** en ese agente. El gestor abre sesiones nuevas y comprueba acceso, Python y puertos disponibles: la comprobación anterior no es una sesión permanente ni garantiza que la placa siga accesible. No hace falta repetir manualmente la verificación antes de cada ensayo. No instala paquetes ni modifica servicios.
6. La laptop genera una configuración local por agente, envía los archivos mediante SFTP y arranca un proceso Python por SSH en cada placa. Los procesos calculan sus estados y se comunican directamente por TCP con sus vecinos. La laptop recoge registros por SFTP para mostrar las gráficas y evaluar el resultado.

## Contraseñas e identidad SSH

En Windows, **Recordar contraseña en este equipo** usa el Administrador de credenciales del usuario, fuera de JSON, OneDrive y exportaciones. Ese almacén no es un archivo de clave privada SSH. La contraseña guardada nunca se precarga en el navegador. Al editar, dejar el campo vacío reutiliza la guardada para la misma conexión; escribir otra permite probarla y reemplazarla solo si el acceso funciona. Desmarca Recordar para eliminarla o quita el dispositivo del inventario. Cambiar host, puerto o usuario requiere escribirla una vez para la nueva conexión. En otros sistemas se permite una contraseña temporal. Los formularios no solicitan archivos de claves privadas.

Se utiliza confianza en el primer acceso: se acepta la primera clave de host recibida y se guarda en `datos/known_hosts` después de autenticar. Es más ágil, pero presupone que la dirección pertenece a la placa prevista en esa primera conexión; no demuestra independientemente su identidad. Si una clave conocida cambia, la conexión se rechaza **antes de autenticar** y se muestran las huellas actual y guardada. No se reemplaza automáticamente. Puede ocurrir por reinstalar una placa, reutilizar una IP para otro equipo o una suplantación; verifica el equipo antes de corregir manualmente la identidad almacenada.

Las identidades corresponden al host y puerto SSH. Una IP nueva no demuestra por sí sola que sea la misma placa. Para evitar cambiar direcciones habitualmente, utiliza su nombre `.local` si tu red lo resuelve de forma fiable. Las escrituras de identidades durante un lote se combinan bajo un candado y se publican de forma atómica para no perder las claves de otras placas.

SSH permite iniciar y administrar procesos. SFTP, que funciona sobre SSH, permite transferir archivos. TCP entre agentes transporta los estados del algoritmo; no pasa por la laptop como intermediario. El gestor sigue siendo necesario para supervisar el ensayo: si su señal de actividad falta durante más de 30 segundos, los procesos solicitan la parada.

La señal de actividad se envía cada 2 segundos desde un hilo y un canal SFTP independientes por placa. Las descargas grandes no deben bloquear esa supervisión. Los registros JSONL se recuperan de forma incremental: se conserva el prefijo local completo y solo se solicitan bytes nuevos, en bloques de hasta 64 KiB. Una última descarga completa comprueba el archivo final. `transferencias.json` registra los bytes recibidos, las lecturas y posibles errores de actividad.

El gestor consulta primero los pequeños resúmenes de estado y atiende las fronteras de etapa también entre bloques de descarga. Así puede liberar una retirada o reincorporación alcanzada por todos sin esperar a terminar un registro grande. Este control no calcula estados del algoritmo ni añade una espera por ronda a las actualizaciones asíncronas. Los límites de espera y las comprobaciones de identidad se mantienen.

### Comunicación y coste de cada actualización

En síncrono entre vecinos, `RoundExchange` en `lab/network.py` envía cada estado publicado directamente a los vecinos mediante conexiones TCP persistentes. `fetch(k, ...)` espera en la memoria local hasta recibir **la ronda k de cada vecino activo**. No sustituye una ronda que falta por otra más reciente. Publicar directamente evita solicitar y esperar una respuesta por cada vecino en cada actualización. `SnapshotStore` y `PeerClient` conservan el protocolo de consulta anterior para compatibilidad; los workers actuales usan `RoundExchange`.

En asíncrono, `Inbox` sigue recibiendo las últimas muestras en hilos independientes. Una consulta puede esperar hasta 0.1 s por una publicación nueva **en el hilo de recepción**; el cálculo continúa usando la copia disponible sin esperar versiones iguales. Esto reduce consultas repetidas a un vecino que todavía no ha cambiado. En coordinador síncrono, el hilo que atiende una solicitud puede esperar brevemente al agregado de la ronda; el coordinador asíncrono sigue agregando las últimas muestras recibidas.

La señal inicial se escribe en paralelo en las seis placas. Sigue existiendo una dispersión de arranques medida en `tiempos.json`: no se presupone inicio simultáneo ni se cambian los relojes de Linux.

Al terminar, `nodo_ID.json` incluye `performance`: `exchange_s` mide obtener las entradas y registrar su traza; `update_s`, calcular y validar el nuevo estado; `record_s`, guardar y publicar el estado; `pacing_s`, la pausa mínima; `control_wait_s`, las esperas de etapa; y `other_s`, el resto del bucle. Son tiempos transcurridos observados. `process_cpu_s` mide CPU del proceso, incluidos sus hilos; puede solaparse con las esperas y no se suma a las otras categorías.

Un agente por placa permite cálculo independiente, pero no garantiza menor duración que una laptop. Una Raspberry Pi Zero 2 W tiene CPU y Wi-Fi diferentes; esperar estados, evaluar expresiones y guardar registros también consume tiempo. El intervalo mínimo de 0.001 s es un límite solicitado, no la promesa de completar cada actualización en 1 ms. Para identificar el coste real hay que mirar las mediciones, sin cambiar el paso numérico ni las ecuaciones.

## Archivos que recibe cada agente

Para un ensayo con identificador `20261006_215143_b2831dfd`, el agente 2 recibe una carpeta como:

```text
~/laboratorio_flexible/experimentos/20261006_215143_b2831dfd/agente_2/
    algoritmo.py
    config_agente_2.json
    lab/                   motor Python necesario para ejecutar
    GESTOR_ACTIVO           señal de actividad del gestor
```

Durante la ejecución aparecen `nodo_2.json`, `nodo_2.jsonl` y, en modo asíncrono, `entradas_2.jsonl`. Los registros conservan los estados y las muestras utilizadas. Las señales `DETENER` y `FINALIZAR` permiten cerrar el proceso.

La función `deployment_files()` en [remote_runner.py](../lab/remote_runner.py) selecciona los archivos. `put()` escribe sus bytes en la placa mediante `sftp.open(..., 'wb')`. `execute_remote()` prepara todas las carpetas y luego inicia comandos de esta forma:

```text
python3 -u -m lab.worker --folder <carpeta> --run-id <identificador> --id 2 --config <carpeta>/config_agente_2.json
```

El algoritmo se copia como `algoritmo.py` para conservar la versión exacta de ese ensayo. Las dependencias externas de un algoritmo escrito a mano deben estar instaladas previamente en las placas.

## Qué significa el aislamiento

`agent_config()` en [algorithms.py](../lab/algorithms.py) crea una vista local:

- Incluye los parámetros comunes declarados, las direcciones de los agentes y la topología.
- Incluye los parámetros locales y el perfil de funciones únicamente del agente propio.
- Los otros nodos contienen sus direcciones y metadatos de comunicación, pero no sus parámetros locales ni su asignación de perfil.
- El worker no recibe el `config.json` completo. El runtime rechaza una vista local que contenga parámetros o perfiles ajenos.

Por ejemplo, el agente 2 conoce sus coeficientes de coste; de los otros agentes conoce las direcciones para comunicarse. En `paso(rt, i, propio, vecinos, k, global_data)`, `propio` es su estado y `vecinos` contiene los estados recibidos de los vecinos configurados. Si un vecino transmite su fitness, el agente utiliza ese número sin necesitar sus coeficientes.

[worker.py](../lab/worker.py) crea las conexiones solo para los vecinos declarados. [network.py](../lab/network.py) implementa las muestras de la misma ronda; [transport.py](../lab/transport.py) implementa las últimas muestras asíncronas. Ambos verifican la identidad del ensayo y el identificador de vecino declarado. En síncrono se utilizan estados de la ronda k; en asíncrono se utilizan los últimos estados disponibles, aunque tengan versiones distintas.

Este es aislamiento de configuración y cálculo, no una barrera de seguridad entre usuarios de Linux. El Python ejecutado tiene los permisos del usuario SSH. El código común contiene las fórmulas disponibles, y los estados transmitidos pueden revelar información si el autor decide incluirla. Tampoco se borran ensayos anteriores: un programa que acceda deliberadamente a otros archivos del mismo usuario podría leerlos.

En modo **coordinador explícito**, la primera placa asignada también ejecuta un proceso coordinador separado, con la configuración completa. Su carpeta es `coordinador/`. Ese modo tiene coordinación central por diseño. En modos de vecinos, la evaluación global posterior en la laptop no interviene en las actualizaciones de los agentes.

El panel de Ejecución muestra **Equipo / placa** junto al identificador del agente. Usa el nombre archivado en `despliegue.json` al iniciar ese ensayo, aunque después se renombre o retire el dispositivo del inventario. El aviso del coordinador indica también su placa y PID independiente. En ejecución local muestra Laptop, aunque el formulario conserve asignaciones de placas de un ensayo anterior.

Para comprobar la separación en un ensayo concreto, abre `config_agente_ID.json` en cada placa: solo el nodo ID debe tener `params` y, si se usan perfiles, `function_profile`. Compara también `entradas_ID.jsonl` en asíncrono para ver qué estados de vecinos se utilizaron. La laptop conserva las vistas locales en su carpeta del ensayo, además de la configuración completa para administración y evaluación.

## Carpetas y espacio ocupado

Se crea una carpeta **por ejecución**, aunque repitas algoritmo, nombre y parámetros. El identificador usa `AAAAMMDD_HHMMSS` más ocho caracteres aleatorios para distinguir ejecuciones y evitar sobrescribir resultados. El nombre largo no es lo que consume espacio: lo consumen las copias del motor y los registros, que aumentan con iteraciones y variables.

Las copias quedan tanto en `datos/experimentos/` de la laptop como en `~/laboratorio_flexible/experimentos/` de las placas participantes. Actualmente no hay limpieza automática de las carpetas remotas. **Eliminar un ensayo en el historial borra su copia local, no sus carpetas en las placas.** Los resultados permanecen hasta que se eliminen; pueden llegar a llenar el almacenamiento. Antes de una limpieza manual, espera a que termine el ensayo y conserva los resultados que necesites. Esta guía no ejecuta ninguna eliminación.

## Significado del resultado final

**Criterio final declarado cumplido** significa que la condición escrita por el autor del algoritmo dio verdadero con los resultados finales. La lógica está en `EquationModel.evaluate()` de [equations.py](../lab/equations.py).

En el ejemplo de consenso robusto se declaró:

```text
max_reference_error < 0.001
```

Donde `target` es el promedio de referencias y `max_reference_error` es el mayor error absoluto de los estados x respecto a ese promedio. Por tanto, el mensaje indica que todos los estados finales están a menos de 0.001 del objetivo. No demuestra estabilidad para cualquier condición inicial, robustez frente a cualquier fallo ni optimalidad de cualquier otro algoritmo.

La evaluación de registros comprueba además su integridad y completitud. No vuelve a ejecutar automáticamente las ecuaciones ni aporta una prueba teórica. En asíncrono, las métricas globales del asistente se calculan sobre los estados terminales de los agentes, que no representan necesariamente un instante común.

## Frecuencia del seguimiento

Durante el cálculo, el agente escribe el resumen visual aproximadamente cada 0.3 segundos y siempre al finalizar. El gestor remoto recoge esos resúmenes y registros en ciclos con una pausa de 0.5 segundos; el tiempo de transferencia se suma a esa pausa. La interfaz intenta refrescar cada segundo, también dependiendo de cuánto tarde la lectura y las gráficas. El panel muestra muestras del avance, no cada iteración al instante. El JSONL conserva cada estado registrado. PID identifica el proceso Linux, mientras Iteración indica el avance del algoritmo.

## Comparación del ejemplo de consenso robusto (7 de octubre de 2026)

Se compararon las actualizaciones registradas con `software/plataforma/algoritmos/consenso_robusto.py`: para el anillo de cuatro agentes con pesos 1, el resultado de cada actualización coincidió exactamente, tanto usando vecinos de la misma ronda como las muestras efectivas de los ensayos asíncronos. La regla Valor siguiente para x y Euler para lambda no introduce una diferencia: la expresión de x ya contiene su integración Euler y ambas usan los estados anteriores.

La variante anterior `consenso_robusto_asincrono.py` usaba h = 0.01 e intervalo mínimo = 0.001 s. El ensayo remoto `20261007_000236_84ce2e10` usó h = 0.02 e intervalo 0 y alcanzó magnitudes de x superiores a 25000. Sus versiones vecinas podían diferir del contador local hasta 48 iteraciones. El contador local y la versión vecina no representan un reloj común, pero estas trazas muestran que las ecuaciones se calcularon con muestras de índices diferentes. La ausencia de barrera cambia la recurrencia respecto al caso síncrono.

Reducir h sin aumentar las iteraciones tampoco reproduce la evolución anterior: con 2000 iteraciones, N*h vale 40 para h = 0.02, 0.04 para h = 0.00002 y 0.0000004 para h = 0.0000000002. La perturbación de +5 se suma completa, sin multiplicarse por h. Por eso los pasos muy pequeños dejan estados próximos a sus valores iniciales más esa perturbación.

Una ejecución local temporal del archivo actual, con los mismos cuatro agentes, 2000 iteraciones, h = 0.02 y modo síncrono, reprodujo x finales [1.999507, 2.000966, 1.999128, 2.000399]. Con h = 0.01, intervalo 0.001 s y modo asíncrono, produjo [1.995469, 2.035627, 1.979702, 1.961406]. Esto verifica compatibilidad con un comportamiento cercano al objetivo; no garantiza la misma trayectoria en otra ejecución ni cumple automáticamente la tolerancia 0.001.

Los registros de la plataforma anterior también incluyen una ejecución asíncrona divergente (`20260923_155227_cb8856dd`, cinco agentes, h = 0.01, intervalo 0.001 s). Elegir asíncrono habilita últimas muestras; no adapta automáticamente el paso, las iteraciones o la pausa, ni garantiza convergencia. Además, el archivo generado actual no incorpora la comprobación del límite de h según el grafo que tenía el ejemplo Python anterior. Un grafo con pesos distintos también requiere revisar la diferencia entre sum_neighbors y weighted_neighbors; en el anillo comprobado todos los pesos son 1.
