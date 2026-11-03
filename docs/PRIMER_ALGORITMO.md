# Tu primer algoritmo: seguimiento de gradiente

**Empieza en «Nuevo experimento» → «Primera vez: aprender con un ejemplo».** Puedes abrir las ecuaciones ya completadas o cargar los tres agentes listos para ejecutar. No tienes que escribir Python para seguir este recorrido.

Vamos a hacer que tres agentes busquen una decisión común que reduzca la suma de sus costos. Cada agente tiene un centro diferente: **1, 3 y 5**. Su costo es $f_i(z)=\frac{1}{2}(z-c_i)^2$ y su gradiente es $\nabla f_i(z)=z-c_i$, donde $c_i$ es el centro del agente $i$. El método combina el promedio de las decisiones con una corrección de gradiente y una variable auxiliar de seguimiento. Es un caso didáctico de seguimiento de gradiente, relacionado con [DIGing](https://arxiv.org/abs/1607.03218), restringido aquí a una red completa y síncrona.

**Dos recorridos distintos:** «Abrir ecuaciones explicadas» enseña cómo está construido el algoritmo. «Cargar ejemplo listo para ejecutar» completa el formulario del experimento con sus tres agentes. Abrir las ecuaciones no ejecuta nada.

La vista previa revisa cálculos básicos; los registros y las gráficas permiten observar el ensayo. El campo de criterio final permanece vacío: este ejemplo no certifica optimalidad ni convergencia.

<!-- paso:1 -->
## 1. Ponle nombre y elige cómo recibe información

### Qué problema de optimización resolvemos

Buscamos **una decisión común z**, un número real, que minimice el coste medio de todos los agentes:

$$\min_{z\in\mathbb{R}} F(z)=\frac{1}{n}\sum_{i=1}^{n}f_i(z),\qquad f_i(z)=\frac{1}{2}(z-c_i)^2.$$

Aquí $c_i$ representa el dato `centro` del agente $i$.

Para los tres centros del ejemplo:

$$\min_{z\in\mathbb{R}}\frac{(z-1)^2+(z-3)^2+(z-5)^2}{6}.$$

Su solución es $z^*=3$: la derivada del objetivo es $F'(z)=z-3$. Minimizar la suma de costes tiene el mismo minimizador que minimizar su promedio; solo cambia la escala del objetivo. La gráfica `suma_costos` muestra la suma, no el promedio.

Cada agente conserva una copia `xᵢ` de esa decisión. La formulación equivalente con copias locales es:

$$\min_{x_1,\ldots,x_n\in\mathbb{R}}\frac{1}{n}\sum_{i=1}^{n}f_i(x_i)$$

$$\text{sujeto a}\quad x_1=x_2=\cdots=x_n.$$

Se busca que todos lleguen a la misma decisión óptima. Si cada uno minimizara su coste por separado, acabaría en su propio centro y no resolvería este problema común. `y` es una variable auxiliar del algoritmo; no otra variable de decisión del problema.

Esta es la estructura del problema (1) de [DIGing](https://arxiv.org/html/1607.03218v3). La referencia `z* = 3` sirve para entender este ejemplo; no se ha añadido una evaluación teórica automática al ejecutor.

En el asistente, cada pestaña es un paso. Abre «Guía del paso» si necesitas instrucciones o el ejemplo explicado; después completa los campos. Puedes saltar entre pasos; tus cambios se mantienen mientras el diálogo esté abierto. Guarda un borrador antes de cerrar si quieres continuar después.

| Campo | Lo que puse | Por qué |
|---|---|---|
| Nombre del algoritmo | Ejemplo guiado · seguimiento de gradiente | Es el nombre que aparece en la lista. |
| Identificador del archivo | `tutorial_gradiente` | Es el nombre interno del archivo. Para practicar usa `mi_gradiente_v1`, porque el ejemplo ya está instalado. |
| Descripción | Tres agentes minimizan la suma de costos; red completa | Explica el método y cuándo tiene sentido usar sus ecuaciones. |
| Información disponible | Síncrono · vecinos de la misma ronda | Cada actualización usa valores de la misma iteración. |

**Pulsa «Continuar: Datos».** El número de agentes y la red se ajustan en el formulario principal, después de generar el algoritmo. Para este ejemplo debes usar **3 agentes y topología Completa**, con enlaces de peso 1.

<!-- paso:2 -->
## 2. Separa datos fijos de variables que cambian

Un **parámetro** lo eliges antes de ejecutar. Una **variable de estado** cambia en cada iteración y se define en el paso 4. Por eso `alpha` y `centro` van aquí, mientras que `x` e `y` van después.

Pulsa **Añadir parámetro común** una vez y **Añadir parámetro local** dos veces:

| Grupo | Nombre en ecuaciones | Etiqueta | Tipo | Valor inicial |
|---|---|---|---|---|
| Comunes | `alpha` | Paso del gradiente (alpha) | Número | `0.1` |
| Cada agente | `centro` | Centro del costo local | Número | `2` |
| Cada agente | `inicio` | Valor inicial de x | Número | `0` |

`alpha` controla cuánto influye el gradiente. `centro` hace que cada agente tenga un costo diferente. `inicio` permite escoger desde dónde arranca su decisión. El valor `2` de centro es **solo el valor predeterminado del formulario**, no el dato definitivo de los tres agentes. En el experimento lo cambiamos por **1, 3 y 5**. La configuración del ejemplo ya trae ese cambio.

En **Restricciones del formulario y opciones** de `alpha` puse mínimo `0.000001`; no fijé máximo. Ese límite de entrada no demuestra estabilidad. Deja los demás campos adicionales vacíos. Escribe decimales con punto: `0.1`.

El «nombre en ecuaciones» debe coincidir exactamente con lo que escribirás después. La etiqueta es solo el texto amigable del formulario: puede tener espacios y tildes.

<!-- paso:3 -->
## 3. Escribe costo y gradiente como funciones

Pulsa **Añadir función** dos veces. Escribe solamente el lado derecho, sin `f(z)=`, sin `return` y sin el símbolo `∇`:

| Nombre | Argumentos | Expresión |
|---|---|---|
| `costo` | `z` | `0.5*(z-centro)**2` |
| `gradiente` | `z` | `z-centro` |

`z` es el valor que le pasamos a la función. Al escribir `costo(x)`, `z` toma el valor de `x`. `centro` se obtiene de los datos del agente. La misma función sirve para todos, aunque sus centros sean diferentes.

Las funciones, escritas matemáticamente, son:

$$f_i(z)=\frac{1}{2}(z-c_i)^2,\qquad \nabla f_i(z)=z-c_i.$$

El gradiente de esta función cuadrática es exactamente `z-centro`; lo escribí explícitamente. El asistente no está deduciendo esa derivada. `**2` significa elevar al cuadrado; `^2` no es la sintaxis admitida.

Una función **calcula algo a partir de un dato**. Todavía no dice cómo cambiará la decisión. Eso corresponde al paso siguiente. Para este método no necesitamos fitness; déjalo fuera.

### Si necesitas fórmulas distintas por agente

Este ejemplo básico usa un solo conjunto de funciones. En **3. Funciones → Usar perfiles de funciones** puedes convertirlo en familias con los mismos nombres y fórmulas diferentes. El perfil se asigna después en cada tarjeta de agente; los nuevos reciben el predeterminado sin cambiar los existentes. No es obligatorio para este recorrido.

La guía principal incluye **Ampliación: funciones distintas por agente**, con otro ejemplo preparado de dos costes y el recorrido de 4 a 6 agentes. Puedes mantener intacto este tutorial básico.

<!-- paso:4 -->
## 4. Define qué recuerda cada agente y cómo lo actualiza

Pulsa **Añadir variable** dos veces. El orden debe ser **x primero, y después**. En ambas elige **Valor siguiente x[k+1]**: las ecuaciones ya son discretas, así que no se aplica Euler ni se usa su paso numérico.

Primera fila:

| Campo | Qué escribí |
|---|---|
| Nombre | `x` |
| Etiqueta | Decisión local x |
| Regla | **Valor siguiente x[k+1]** |
| Condición inicial | `inicio` |
| Actualización | `(x + sum_neighbors("x"))/n - alpha*y` |

Esto representa:

$$x_i[k+1]=\frac{x_i[k]+\sum_{j\in\mathcal{N}_i}x_j[k]}{n}-\alpha y_i[k].$$

$\mathcal{N}_i$ es el conjunto de vecinos del agente $i$. La tabla conserva la sintaxis que se escribe en la plataforma. `sum_neighbors("x")` suma las decisiones recibidas; **no incluye la propia**, por eso sumamos `x`. Dividir entre `n` produce el promedio de todos **solo porque la red del ejemplo es completa**. `alpha*y` es la corrección del seguimiento del gradiente.

Segunda fila:

| Campo | Qué escribí |
|---|---|
| Nombre | `y` |
| Etiqueta | Seguimiento del gradiente y |
| Regla | **Valor siguiente x[k+1]** |
| Condición inicial | `gradiente(x)` |
| Actualización | `(y + sum_neighbors("y"))/n + gradiente(next_x) - gradiente(x)` |

En notación matemática, la segunda fila es:

$$y_i[k+1]=\frac{y_i[k]+\sum_{j\in\mathcal{N}_i}y_j[k]}{n}+\nabla f_i(x_i[k+1])-\nabla f_i(x_i[k]).$$

`gradiente(next_x)` corresponde a $\nabla f_i(x_i[k+1])$ y `gradiente(x)` a $\nabla f_i(x_i[k])$.

`y` guarda información auxiliar entre iteraciones. Mezcla el seguimiento de los vecinos y añade cuánto cambió el gradiente local. **`x` sigue significando el valor anterior; `next_x` es el valor nuevo de la primera fila.** Esa diferencia es necesaria: si escribes `gradiente(x)-gradiente(x)`, la corrección sería cero y estarías implementando otro método.

Las condiciones iniciales también se calculan en orden: primero `x=inicio`, luego `y=gradiente(x)`. No defino proyecciones, coordinador ni condiciones de validez en este ejemplo; deja esas opciones cerradas y vacías.

Para verlo con números: al iniciar el experimento, `x=[0,0,0]` y `y=[-1,-3,-5]`. En el primer paso se obtiene `x=[0.1,0.3,0.5]` y `y=[-2.9,-2.7,-2.5]`. Esto explica cómo leer las ecuaciones, no constituye una prueba de convergencia.

### Cantidad de agentes

`n` es la cantidad total de agentes configurados, incluido el propio. El motor proporciona ese valor automáticamente; no hace falta declararlo en Datos.

### Orden exacto de una iteración

Al comenzar el paso k, se mantiene una copia de los estados actuales. Las filas dinámicas se calculan de arriba abajo:

| Momento | Qué calcula el motor | Qué nombres siguen disponibles |
|---|---|---|
| Entrada | Recibe los estados de la ronda k en modo síncrono | `x = xᵢ[k]`, `y = yᵢ[k]`, vecinos de k |
| Fila x | Calcula `(x + sum_neighbors("x"))/n - alpha*y` | Guarda el resultado como `next_x`; `x` y `y` siguen siendo los anteriores |
| Fila y | Calcula `(y + sum_neighbors("y"))/n + gradiente(next_x) - gradiente(x)` | Usa el `next_x` recién calculado y el `x` anterior; guarda `next_y` |
| Fin | Devuelve el estado nuevo con ambos resultados | En la siguiente iteración, esos resultados pasan a llamarse `x` e `y` |

La función `gradiente` no busca un valor futuro: evalúa la fórmula en el número que le pasas. `gradiente(next_x)` recibe el valor nuevo ya calculado; `gradiente(x)` recibe el anterior. No hay una dependencia circular porque calcular `next_x` necesita `y` actual, no `next_y`. Tampoco se necesita recibir el `next_x` de los vecinos para esta segunda fila.

Ejemplo del agente 1, con centro 1, `alpha=0.1`, `x=[0,0,0]`, `y=[−1,−3,−5]`:

$$x_1[1]=0-0.1\cdot(-1)=0.1.$$

$$\overline{y}[0]=\frac{-1-3-5}{3}=-3.$$

$$\nabla f_1(x_1[1])=0.1-1=-0.9.$$

$$\nabla f_1(x_1[0])=0-1=-1.$$

$$y_1[1]=-3+(-0.9)-(-1)=-2.9.$$

Aquí $x_1[1]$ es `next_x` y $y_1[1]$ es `next_y` en esa primera iteración.

Hasta terminar ambas filas, `x=0` e `y=−1` conservan su significado de valores anteriores. En la siguiente iteración se entra con `x=0.1` e `y=−2.9`. Por eso la fila **x debe ir antes de y**. Si una fila posterior necesitara el nuevo y, podría usar `next_y` una vez calculado.

**No cambies la topología a anillo o estrella conservando este promedio.** Otro grafo requiere una mezcla apropiada; por ejemplo, pesos vecinales y peso propio coherentes con el método.

<!-- paso:5 -->
## 5. Decide qué quieres ver en las gráficas

`x` e `y` ya se registran automáticamente. No hace falta añadirlas otra vez. Pulsa **Añadir medición** para calcular cantidades que quieres observar pero que no necesitan ser estados:

| Nombre | Etiqueta | Expresión |
|---|---|---|
| `costo_local` | Costo local | `costo(x)` |
| `gradiente_local` | Gradiente local | `gradiente(x)` |

Después pulsa **Añadir métrica global**:

| Nombre | Etiqueta | Expresión |
|---|---|---|
| `separacion` | Separación entre decisiones | `max_all("x") - min_all("x")` |
| `suma_costos` | Suma de costos locales | `sum_all("costo(x)")` |

Las mediciones globales se calculan **después** del ensayo; no dan información adicional a los agentes. `separacion` mide cuánto difieren las decisiones. `suma_costos` suma los costos evaluados en las decisiones locales de cada iteración; mientras los agentes no coincidan, no es el costo de una única decisión compartida.

Deja **Criterio final** vacío. Mostrar separación o costo no certifica optimalidad.

<!-- paso:6 -->
## 6. Revisa y crea tu archivo

1. Pulsa **Probar las ecuaciones**. Si falta un nombre o una expresión está mal escrita, aparecerá el error.
2. Examina los estados calculados. Esta prueba breve usa tres agentes con **los valores predeterminados**: todos tienen `centro=2` e `inicio=0`. Por eso su primer paso da `x=0.2` para los tres. No es todavía el experimento con centros 1, 3 y 5.
3. Si estás creando tu copia, vuelve al paso 1 y cambia el identificador a `mi_gradiente_v1`. Después pulsa **Crear y usar mi algoritmo**. No se sobrescribe el ejemplo instalado.
4. En el formulario principal, elige **3 agentes**, **Completa**, **100 iteraciones**, intervalo **0.01** y `alpha=0.1`. En los agentes pon `centro=1`, `3`, `5` e `inicio=0` para todos. Pulsa **Iniciar experimento local**.

Si quieres saltarte esa configuración manual, cierra el asistente y usa **Primera vez → Cargar ejemplo listo para ejecutar**. Ese botón carga el ejemplo original y sus datos completos; no ejecuta nada hasta que pulses Iniciar.

**Qué ocurre con los archivos:** las ecuaciones se guardan en el `.py`; los valores del experimento y sus conexiones van en un `.json`. Puedes usar el mismo algoritmo con varios experimentos, sin volver a escribir sus ecuaciones.

<!-- paso:7 -->
## Ejecuta, observa y practica

En **Ejecución**, utiliza **Añadir gráfica** para crear estos paneles:

| Origen | Variables Y | Agentes | Qué observas |
|---|---|---|---|
| Por agente | Decisión local x | Todos | Cómo cambian las decisiones. |
| Por agente | Seguimiento del gradiente y | Todos | La variable auxiliar. |
| Por agente | Costo local | Todos | El costo de cada agente en su propia decisión. |
| Serie global del evaluador | `separacion` | No aplica | Diferencia entre la mayor y menor decisión. |

Usa **Iteración / índice** como eje X y guarda la disposición. Las métricas globales aparecen al terminar la evaluación. En modo asíncrono no tendrías la misma interpretación de una ronda común; este ejemplo es síncrono.

Para practicar, abre **Editar diseño seleccionado**, cambia el identificador y añade una medición llamada `magnitud_y` con expresión `abs(y)`. Crea esa copia y busca `obs/magnitud_y` en las gráficas. Has añadido una cantidad observable sin modificar el ejecutor.

Después prueba a cambiar los centros o las condiciones iniciales en el formulario principal. Eso cambia el experimento, no el algoritmo. Para cambiar el costo, tendrías que ajustar también su gradiente; el asistente no lo hace automáticamente. Para métodos con otra memoria, añade estados; para métodos con otras cantidades observables, añade mediciones. No todas las expresiones ni protocolos posibles caben en el asistente; la plantilla Python sigue disponible.

## Si algo no sale

| Mensaje o situación | Qué revisar |
|---|---|
| Identificador ya existe | Usa un identificador nuevo para tu copia. |
| Nombre desconocido | Comprueba que el parámetro/función existe y que escribiste el mismo nombre. |
| `next_x` fuera de orden | Mueve la fila `x` antes de `y`. |
| La vista previa da valores iguales | Usa parámetros predeterminados iguales; el ensayo permite datos distintos por agente. |
| No aparece una gráfica global | Espera a que termine la evaluación y cambia Origen a Serie global del evaluador. |
| El resultado cambia al editar el grafo | El promedio de este ejemplo supone una red completa; revisar la comunicación forma parte del diseño matemático. |

La referencia completa del lenguaje está en **ASISTENTE.md** y el contrato de archivos Python en **CONTRATO.md**, dentro de esta misma carpeta de documentación.
