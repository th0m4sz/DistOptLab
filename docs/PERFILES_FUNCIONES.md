# Funciones distintas por agente

Los perfiles son opcionales. Un archivo sin perfiles sigue usando las mismas fórmulas para todos, con los datos particulares de cada agente. No exige coste, gradiente ni fitness: puedes usar perfiles para otras funciones auxiliares o seguir trabajando sin ellos, por ejemplo en consenso.

## Problema de optimización del ejemplo con perfiles

Todos buscan una misma decisión real `z` que minimice el promedio de los costes locales. Con los cuatro agentes preparados (centros 1, 3, 5, 7), el objetivo es:

$$\min_{z\in\mathbb{R}} F(z)=\frac{1}{4}\sum_{i=1}^{4}f_i(z).$$

$$f_i(z)=\frac{1}{2}(z-c_i)^2\qquad (i=1,3).$$

$$f_i(z)=\frac{1}{2}(z-c_i)^2+0.01(z-c_i)^4\qquad (i=2,4).$$

Los centros son $c_1=1$, $c_2=3$, $c_3=5$ y $c_4=7$.

Los agentes 1 y 3 usan el perfil cuadrático; 2 y 4 incluyen el término de cuarto grado. La formulación con copias locales es:

$$\min_{x_1,\ldots,x_n\in\mathbb{R}}\frac{1}{n}\sum_{i=1}^{n}f_i(x_i)\qquad\text{sujeto a}\quad x_1=\cdots=x_n.$$

 Cada `xᵢ` aproxima esa misma decisión; `yᵢ` es memoria auxiliar para seguir el gradiente. No son cuatro problemas independientes ni un balance de potencias.

Al pasar de 4 a 6 agentes se añaden dos costes al objetivo y cambia la normalización a `1/6`. Los costes nuevos dependen de los perfiles y datos que asignes; el óptimo también puede cambiar. La métrica `suma_costos` registra la suma de costes en las decisiones locales, no `F(z)` evaluado en una única decisión común mientras aún difieran.

Aquí `n` es la cantidad configurada de agentes y la mezcla es `Wᵢⱼ=1/n` sobre una red completa. Se calcula primero `next_x` con los estados actuales y después `next_y`, usando tanto `gradiente(next_x)` como `gradiente(x)`. Las funciones se evalúan con el perfil local. El tutorial básico, paso 4, explica el orden con números.

El término de cuarto grado no tiene gradiente globalmente Lipschitz en toda ℝ. Por eso este ejemplo de perfiles ilustra la implementación y no atribuye automáticamente a estos costes las garantías globales de convergencia del teorema de DIGing.

## Dónde se configura cada cosa

1. **2. Datos:** declara las constantes que pueden usar tus fórmulas. Cada agente conserva sus propios valores.
2. **3. Funciones:** pulsa **Usar perfiles de funciones**. Tus funciones actuales pasan al perfil **General**. Ponle un nombre y pulsa **Duplicar perfil** para crear otra familia; cambia sus expresiones. La copia conserva los nombres para que puedas seguir llamándolas desde las mismas reglas.
3. En ese mismo paso, elige el **Perfil predeterminado para agentes nuevos**.
4. **4. Actualización:** escribe una sola regla compartida. `gradiente(x)` llama al gradiente del perfil del agente que actualiza. Los estados, comprobaciones y mediciones siguen siendo comunes.
5. **6. Probar y crear:** la vista previa incluye todos los perfiles, al menos una vez, usando los datos predeterminados y una red completa. Comprueba expresiones; no demuestra convergencia. Crea el archivo con un identificador nuevo para conservar el original.
6. En **Nuevo experimento → Parámetros de cada agente**, selecciona **Perfil de funciones · agente N** y ajusta sus datos. Guarda la configuración para reutilizar exactamente esas asignaciones.

Los perfiles se definen una vez en el archivo. La selección de cada agente pertenece al experimento. Para cambiar una asignación no necesitas volver al asistente ni modificar Python.

## Ejemplo desde el principio: dos costes distintos

En la guía abre **Ampliación: funciones distintas por agente**. **Abrir ecuaciones con perfiles** permite inspeccionarlas; **Cargar ejemplo de dos perfiles** instala y carga el ejemplo preparado, sin reemplazar tus algoritmos.

En **2. Datos** hay `alpha = 0.05` común y `centro`, `inicio`, `beta` locales. `beta = 0.01` solo se usa en la segunda familia; sigue apareciendo en todos los agentes porque el esquema de datos es compartido. No interviene en la fórmula cuadrática.

En **3. Funciones** están estos dos perfiles:

| Perfil | `costo(z)` | `gradiente(z)` |
|---|---|---|
| Cuadrático | `0.5*(z-centro)**2` | `z-centro` |
| Cuadrático + cuarto grado | `0.5*(z-centro)**2 + beta*(z-centro)**4` | `z-centro + 4*beta*(z-centro)**3` |

En notación matemática, el perfil cuadrático usa:

$$f_i(z)=\frac{1}{2}(z-c_i)^2,\qquad \nabla f_i(z)=z-c_i.$$

El perfil con cuarto grado usa:

$$f_i(z)=\frac{1}{2}(z-c_i)^2+\beta_i(z-c_i)^4,$$

$$\nabla f_i(z)=z-c_i+4\beta_i(z-c_i)^3.$$

El gradiente es la derivada del coste correspondiente; en este ejemplo está escrito explícitamente. La plataforma no deriva ni verifica automáticamente esa relación.

En **4. Actualización** ambos perfiles usan las mismas dos variables, con regla **Valor siguiente**:

| Variable | Condición inicial | Actualización |
|---|---|---|
| `x` | `inicio` | `(x + sum_neighbors("x"))/n - alpha*y` |
| `y` | `gradiente(x)` | `(y + sum_neighbors("y"))/n + gradiente(next_x) - gradiente(x)` |

Las dos actualizaciones representan:

$$x_i[k+1]=\frac{x_i[k]+\sum_{j\in\mathcal{N}_i}x_j[k]}{n}-\alpha y_i[k].$$

$$y_i[k+1]=\frac{y_i[k]+\sum_{j\in\mathcal{N}_i}y_j[k]}{n}+\nabla f_i(x_i[k+1])-\nabla f_i(x_i[k]).$$

`y` realiza seguimiento del gradiente; no es simplemente el gradiente local en cada instante. `next_x` es el valor nuevo de la fila anterior. Cada agente calcula sus llamadas a `gradiente` con su perfil y sus datos; recibe `x` e `y` de los vecinos. No necesita sus fórmulas ni sus parámetros. Estas ecuaciones de promedio requieren la **red completa** del ejemplo; no basta con cambiarla por un anillo.

En **5. Gráficas**, `costo(x)` y `gradiente(x)` son mediciones locales. La métrica posterior `sum_all("costo(x)")` suma el coste correspondiente a cada agente con su perfil. Ese análisis lo realiza la laptop con los registros y la configuración completa; no comunica costes al algoritmo ni añade un coordinador a sus actualizaciones.

## Del archivo con 4 agentes a un experimento con 6

Al cargar el ejemplo preparado verás:

| Agente | Perfil asignado | Centro |
|---|---|---|
| 1 | Cuadrático | 1 |
| 2 | Cuadrático + cuarto grado | 3 |
| 3 | Cuadrático | 5 |
| 4 | Cuadrático + cuarto grado | 7 |

1. En **Número de agentes**, cambia **4 → 6**. Se conservan las asignaciones y datos de los cuatro primeros.
2. Los agentes **5 y 6** aparecen con **Cuadrático**, el perfil predeterminado, y los datos iniciales declarados: `centro = 2`, `inicio = 0`, `beta = 0.01`. La aplicación no inventa nuevos centros.
3. Si quieres el segundo coste para el agente 6, selecciona **Cuadrático + cuarto grado** en su desplegable. Ajusta los centros y condiciones iniciales que necesite tu ensayo. No tienes que reescribir las ecuaciones.
4. Mantén **topología completa**, guarda la configuración e inicia el experimento. Cambiar población o funciones puede exigir revisar el paso y las hipótesis del método.

Si empezaras con un solo coste y cuatro agentes, simplemente mantendrías un conjunto de funciones, sin activar perfiles. Al pasar a seis todos seguirían usando ese conjunto. Activa perfiles cuando realmente necesites una segunda fórmula.

## Qué se conserva y qué se comprueba

- El borrador y su recuperación automática guardan las familias y el perfil predeterminado. El archivo Python generado también los contiene; no hay que editar otros archivos del motor.
- La configuración y cada ensayo conservan la asignación individual. La vista local entregada a un proceso contiene únicamente sus parámetros y su asignación; no los de otros agentes. El programa compartido contiene las fórmulas disponibles: esto no pretende ocultar su código.
- La validación revisa las reglas, funciones y cantidad de argumentos con cada perfil. Las funciones que utilicen las reglas comunes deben existir en todos; cada perfil puede añadir auxiliares propios.
- Dentro de `sum_neighbors` usa estados recibidos. Con perfiles se rechaza `sum_neighbors("costo(x)")`: el receptor no debe elegir ni calcular el coste del vecino. Si tu método necesita ese valor, el emisor debe calcularlo como estado algebraico y enviar ese estado. `own("costo(x)")` sí calcula tu propio coste.
- La asignación funciona en modos síncrono, asíncrono y coordinador. Cambiar de modo no garantiza que un método matemático siga convergiendo. El ejemplo se entrega síncrono.
- Se comparten el esquema de datos, los estados y las reglas de actualización. Los perfiles cambian funciones, no convierten cada agente en un algoritmo completamente diferente.

Eliminar o renombrar un perfil en un diseño nuevo no modifica archivos instalados ni ensayos anteriores. Los identificadores internos se conservan al cambiar su nombre visible. La instalación exige un identificador nuevo si el archivo ya existe, para preservar las versiones.
