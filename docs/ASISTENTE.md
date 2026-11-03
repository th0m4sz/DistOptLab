# Diseñar y cargar métodos propios

**Si es tu primera vez, empieza por [Tu primer algoritmo: seguimiento de gradiente](PRIMER_ALGORITMO.md).** Allí tienes cada campo completado, sus ecuaciones explicadas y los pasos para ejecutarlo. La misma guía está dentro de la aplicación en **Primera vez: aprender con un ejemplo**, y cada paso del asistente tiene una ayuda contextual. Este documento es la referencia técnica para consultas posteriores.

Puedes implementar un método compatible con los protocolos disponibles cambiando únicamente tu archivo Python. El asistente añade otra forma de producir ese archivo: declara las ecuaciones en formularios y genera el mismo contrato público. Ninguna opción requiere incorporar ecuaciones económicas al núcleo.

## Recorrido

Pulsa **Diseñar algoritmo paso a paso** para continuar la última edición. Si aún no existe trabajo guardado, el diseño empieza vacío. Para comenzar otro, utiliza **Nuevo diseño vacío** dentro de **Archivos y borradores**.

1. **Inicio:** nombre, identificador, supuestos y comunicación: vecinos de la misma ronda, últimas muestras o coordinador explícito.
2. **Datos:** constantes comunes y datos por agente. Admite números, enteros, texto, booleanos, selectores y JSON para vectores o matrices. Los valores particulares y el grafo se editan después en el formulario del experimento.
3. **Funciones:** expresiones propias con argumentos. Costos, gradientes y fitness son opcionales. Una función puede usar parámetros y funciones declaradas antes. Para dependencia temporal, declara un argumento como `iteracion` y pásale `k` al invocarla.
4. **Actualización:** variables, condiciones iniciales y reglas; añade memoria, variables auxiliares o duales como estados. Puedes añadir proyecciones, condiciones de validez y agregados del coordinador.
5. **Gráficas:** observaciones locales, métricas globales y criterio final opcional. Los estados ya quedan disponibles para graficar, sin declararlos otra vez.
6. **Probar y crear:** inspecciona el Python y pulsa **Probar las ecuaciones** para revisar tres pasos en memoria. Descarga el archivo o pulsa **Crear y usar mi algoritmo**. Después configura el experimento e inicia la ejecución TCP.

Las filas se pueden añadir, quitar y reordenar. **Archivos y borradores** conserva borradores JSON; también admite archivos Python generados por este asistente. **Editar diseño seleccionado** recupera su declaración `ASISTENTE`. Un archivo escrito a mano se edita como Python. Al cambiar manualmente las funciones del Python generado, esas modificaciones no se traducen al formulario: regenerarlo reconstruye las funciones desde `ASISTENTE`.

## Significado preciso de las ecuaciones

Si ya escribes `x + step*F`, utiliza **Valor siguiente**. Si eliges **Derivada → Euler**, escribe solo `F`: la plataforma añade `x + step*F`. Ambas producen el mismo resultado con el mismo paso; Valor siguiente también admite reglas de promedio, proyección o actualizaciones que no provienen de una derivada.

Debajo de las expresiones de actualización, **Ayuda: sumatorias y funciones entre vecinos** explica las sumas, los pesos y el contexto de las comillas. Está disponible en los modos de vecinos. No inserta expresiones ni decide tu ecuación.

En **Archivos y borradores**, **Eliminar borrador seleccionado** retira ese JSON de la lista y lo conserva en `datos/modelos/eliminados/`. **Deshacer eliminación** recupera el último retirado mientras ese diálogo sigue abierto. No elimina el archivo Python del algoritmo ni sus ensayos. Si cierras el diálogo, la copia archivada permanece en esa carpeta.

| Elemento | Interpretación |
|---|---|
| `x` en una actualización dinámica | Valor propio anterior. Las filas no lo sobrescriben durante esa ronda. |
| `next_x` | Valor nuevo, incluida la proyección, de una fila dinámica anterior. Permite métodos con actualizaciones dependientes. |
| Valor siguiente | Escribes directamente el lado derecho de `x[k+1]`. |
| Derivada / Euler | Escribes `F`; se calcula `x + h*F`. `h` es el paso numérico declarado, independiente de la pausa real del proceso. |
| Variable algebraica | Se recalcula con los estados dinámicos nuevos, después de actualizarlos. En la inicialización se calcula después de los estados dinámicos. |
| Proyecciones inferior/superior | Recortan cada actualización; pueden ser escalares o vectores compatibles. No proyectan automáticamente la condición inicial. Para algebraicas usa `clip`. |
| Condiciones de validez | Invariantes sin dependencia de `k`, evaluadas inicialmente y tras actualizar. Su incumplimiento detiene el ensayo. No son una prueba de óptimo. |
| `i`, `k`, `n` | Identificador del agente, índice de actualización desde cero y cantidad de agentes. |

Las condiciones iniciales se evalúan en orden: una puede usar estados inicializados antes. Las algebraicas solo pueden depender de estados dinámicos y algebraicas anteriores. Para conservar un valor de otra iteración, declara una variable de memoria explícita. El orden puede cambiarse con las flechas de cada fila.

Las expresiones usan sintaxis Python: `**` para potencias, `[1, 2]` para vectores, `x[0]` para componentes, `a if condicion else b` para casos. No admiten imports, atributos, bucles ni código arbitrario. `+`, `-`, `*`, `/`, `**` y comparaciones operan por componente; un escalar se difunde sobre una lista. `dot(a,b)` es producto interno y `matmul(A,x)` es matriz por vector. Usa `all(condicion_vectorial)` o `any(...)` cuando necesites una condición escalar.

Disponibles: `sin`, `cos`, `tan`, `exp`, `log`, `sqrt`, `tanh`, `floor`, `ceil`, `abs`, `sum`, `min`, `max`, `len`, `all`, `any`, `norm`, `dot`, `matmul`, `clip`, `pi` y `e`. `norm` calcula norma euclídea de los componentes. Puedes escribir el gradiente exacto como función. `derivative("funcion", punto)` y `gradient("funcion", vector)` aproximan por diferencias centrales, con epsilon opcional como tercer argumento (por defecto `1e-6`); requieren una función de un argumento y no hacen diferenciación simbólica.

## Información local y global

`sum_neighbors("x")`, `mean_neighbors("x")` y `weighted_neighbors("x")` reducen estados recibidos. No incluyen al propio agente. Los pesos son los de los enlaces y **no se normalizan**. Si el método necesita una matriz estocástica debes elegir pesos y término propio que cumplan esa condición. Promediar un conjunto vacío es un error. Sumarlo devuelve cero.

La expresión entre comillas opera sobre los estados recibidos de cada emisor y las constantes comunes. No puede consultar sus parámetros privados, ni siquiera en la vista previa. Si `funcion(x)` necesita coeficientes locales, el emisor debe calcular su resultado como estado algebraico y comunicar ese número.

Para una interacción entre el agente propio y cada vecino, puedes escribir `sum_neighbors('own("x") - x')`. Dentro de esa suma, `own("expresión")` usa el estado anterior y los parámetros del agente que actualiza; el resto usa los datos recibidos. `own("f(x)")` admite una función local declarada, pero una llamada a `f(x)` fuera de `own` no tiene los coeficientes privados del vecino. `own` solo existe dentro de las reducciones sobre vecinos; no permite usar valores `next_x` ni anidar sumatorias.

Una función `fitness(x)` puede producir el estado `f`; el vecino recibe `f` y la sumatoria usa `own("f")-f`. Aquí `f` es el número recibido, no una llamada que recalcula una función con coeficientes ajenos. El ejemplo CCRD comunica `x`, `hat` y `f`. Cada agente recibe una configuración propia sin los parámetros locales ajenos, tanto en modo síncrono como asíncrono o coordinado. El gestor, el evaluador posterior y el coordinador explícito conservan el contexto completo. La separación es del contexto de cálculo; los procesos Python locales siguen teniendo permisos del mismo usuario sobre los archivos.

**Función y estado son cosas distintas:** la función conserva la fórmula; el estado contiene el resultado que se comunica y grafica. La función es opcional: puedes escribir su fórmula directamente en el estado algebraico. No añadas otra observación con el mismo resultado si ya está en un estado; produciría una curva duplicada. El ejemplo CCRD ofrece una sola curva de fitness y una de capacidad.

Las restricciones mínimo/máximo de un **parámetro** validan la entrada del formulario. Una **proyección** recorta el estado después de actualizarlo. Declarar `pmin` y `pmax` por sí solo no activa ninguna de las dos. Si el método maneja su capacidad mediante ecuaciones, deja la proyección vacía.

Las gráficas muestran números muy pequeños mediante exponentes explícitos (por ejemplo, `3.6e-12`) y dan margen a series casi constantes para no ampliar ruido numérico. No redondean los datos almacenados. `round` es el índice de actualización; se conserva en el CSV y como eje **Iteración / índice**, pero no aparece entre las métricas Y globales.

La edición del asistente se guarda automáticamente en `datos/modelos/recuperacion/`, incluso si un campo contiene una expresión o un JSON aún incompletos. Al abrir **Diseñar algoritmo paso a paso** se recupera la última edición; si no existe, se abre el borrador guardado más reciente. **Nuevo diseño vacío** inicia otro trabajo y conserva la copia anterior. **Guardar borrador** actualiza el borrador abierto, sin crear un duplicado en cada pulsación. Los datos válidos del formulario de experimento también se conservan en `datos/ultimo_experimento.json` para recuperarlos al recargar la página.

`sum_all("x")`, `mean_all`, `min_all` y `max_all` están disponibles en el coordinador y la evaluación global, nunca de forma implícita en el paso local. El coordinador devuelve agregados en `global_data["nombre"]`. En el formulario del experimento se elige si reúne una misma ronda o utiliza las últimas muestras de los participantes; no hace falta cambiar las expresiones. En asíncrono, k en `coordinar` es el índice del solicitante. [Detalles y trazas](COORDINADOR_ASINCRONO.md). Sus filas pueden usar agregados anteriores. Las métricas globales también se evalúan en orden, pero solo después del ensayo y no realimentan al algoritmo.

En modo asíncrono, `k` es local. La evaluación generada ofrece métricas globales **solo sobre estados terminales**, que no representan un instante simultáneo; no inventa una curva global sincronizada. Las curvas individuales conservan sus índices y tiempos registrados.

## Gráficas

En **Ejecución**, pulsa **Añadir gráfica** tantas veces como necesites. Cada panel permite seleccionar origen local/global, variables Y, agentes y eje X (índice, tiempo u otra variable). Vectores y matrices se separan por componente. Las observaciones aparecen como `obs/nombre`. Guarda la disposición y exporta los datos completos cuando los necesites. Las métricas globales aparecen después de la evaluación.

Para un despacho, el archivo del usuario puede declarar potencia, fitness, variables auxiliares y observaciones de costo, además de balance y costo total como métricas globales. Esos nombres no tienen ningún tratamiento especial en la plataforma.

## Compatibilidad con los archivos anteriores

Un `.py` autocontenido puede incluir ecuaciones, funciones auxiliares, evaluación y observaciones usando el contrato de [CONTRATO.md](CONTRATO.md). Se comprobó con CCRD/RCCRD. El archivo anterior `ccrd_coordinado.py` depende de `lab.allocation` para evaluar: copiarlo literalmente conserva esa dependencia. La adaptación realizada en la prueba incorpora esa evaluación al propio archivo y restringe su preparación global al gestor/coordinador mediante `rt.local_id is None`; no añade un módulo económico al núcleo. Un agente ya no puede recorrer coeficientes ajenos desde `preparar`. `ejemplo()` no se ejecuta al cargar: declara los valores en `ALGORITMO` o importa una configuración.

Los archivos generados importan el intérprete genérico `lab.equations` de esta plataforma. Son transportables entre instalaciones compatibles de la plataforma flexible; no son programas independientes de ella. Un solver externo o una biblioteca adicional debe estar instalado en el intérprete de la aplicación.

## Base de diseño y límites

Se revisó *Distributed Optimization Under Information Constraints: A Survey*, Liu et al., IEEE TII 22(4), 2026, DOI 10.1109/TII.2025.3645932, como referencia bibliográfica (no se distribuye el PDF). Las páginas PDF 2–3 describen objetivos locales, variables de decisión, intercambio con vecinos y métodos con estados auxiliares o memoria. Esa estructura motivó separar datos, funciones, estados, comunicación y observaciones; no imponer una secuencia costo → fitness. La copia contiene anotaciones de enlaces, sin comentarios o resaltados de texto detectables.

La actualización de seguimiento de gradiente usa el gradiente en el estado **nuevo** y el **anterior**; de ahí la referencia explícita `next_x`. Véase el artículo primario de [Nedić, Olshevsky y Shi sobre DIGing](https://arxiv.org/abs/1607.03218). Se comprobó esta dependencia en pruebas, sin instalar DIGing como algoritmo predeterminado.

El asistente no cubre automáticamente todos los métodos del survey. No deduce convergencia, estabilidad, pesos adecuados ni discretizaciones exactas. Solo automatiza Euler; otras discretizaciones deben escribirse como reglas discretas o en Python. Métodos con subproblemas `argmin`, operadores proximales sin fórmula cerrada o solvers requieren implementarlos en Python; esa necesidad aparece, por ejemplo, en [ADMM, Boyd et al.](https://stanford.edu/~boyd/papers/admm_distr_stats.html). El asistente no incluye aleatoriedad, diferenciación automática ni lectura de datos externos; esas operaciones pertenecen al archivo Python.

La plantilla Python amplía las posibilidades matemáticas dentro del transporte existente. Redes dirigidas, grafos que cambian durante el ensayo y comunicaciones activadas por eventos requieren ampliar el ejecutor. El asistente admite hasta 200 filas por grupo, 4000 caracteres y 512 nodos de sintaxis por expresión. La vista previa usa tres agentes con valores predeterminados, grafo completo y tres pasos: detecta errores básicos, no demuestra convergencia ni simula retardos asíncronos.


## Funciones distintas por agente (opcional)

En **3. Funciones**, **Usar perfiles de funciones** conserva las fórmulas actuales en un perfil. **Duplicar perfil** permite cambiar sus expresiones conservando los nombres que usan las actualizaciones. Selecciona el perfil predeterminado para nuevos agentes. En el formulario del experimento aparece un selector por agente; pasar de 4 a 6 conserva los primeros cuatro y asigna el predeterminado a los nuevos.

Los perfiles y sus fórmulas se guardan en borradores, recuperación automática, JSON y Python generado. La asignación individual se guarda con la configuración del experimento. **Probar ecuaciones** incluye todos los perfiles usando datos predeterminados; revisa también tus valores reales antes de ejecutar. La interfaz sigue admitiendo un único conjunto o ninguna función, sin activar esta opción.

La actualización, los estados, los datos declarados y las mediciones son comunes. La validación comprueba cada perfil frente a esas expresiones. Las funciones locales dentro de sumatorias de vecinos deben calcularse en el emisor y enviarse como estados; `own` permite usar funciones propias. La suma global posterior aplica el coste correcto por agente. No se comprueban automáticamente derivadas, convexidad ni convergencia.

[Guía completa y ejemplo con dos costes, de 4 a 6 agentes](PERFILES_FUNCIONES.md).
