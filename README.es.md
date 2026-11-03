# DistOptLab

**Laboratorio de optimización distribuida**. [English](README.md).

DistOptLab es una plataforma experimental de código abierto para diseñar y evaluar algoritmos de optimización distribuida. Integra la definición de algoritmos, su ejecución en un PC o una red de Raspberry Pi y la visualización de los resultados registrados. Permite comparar modos de comunicación y topologías de red, y estudiar la respuesta de los algoritmos ante la retirada y reincorporación programada de nodos.

La interfaz y las guías están en español. Licencia [MIT](LICENSE).

## Instalar y abrir

1. Instala Python 3.11 de 64 bits con el lanzador `py`.
2. Descarga o clona la carpeta y extrae el ZIP completo, si corresponde.
3. Abre `instalar.cmd`: prepara un entorno independiente e instala las versiones fijadas.
4. Abre `iniciar.cmd` y entra a **http://127.0.0.1:8778**. Mantén abierta la terminal; para cerrar, detén los ensayos y pulsa Ctrl+C.

La instalación requiere Internet. El entorno comprobado es Windows x64/Python 3.11. Linux y macOS requieren validación propia; sus comandos se describen en el README en inglés. No copies entornos virtuales entre computadores.

Si el puerto está ocupado por otra copia, ejecuta `.venv\Scripts\python.exe app.py --port 8780` y abre ese puerto. No es necesario conectar placas para probar la aplicación.

`requirements.txt` declara dependencias directas; `requirements-lock.txt` fija también las indirectas. El instalador utiliza el segundo.

## Primera prueba

Abre **Ver ejemplo guiado**, pulsa **Cargar ejemplo listo para ejecutar**, selecciona **Laptop (procesos locales)** e inicia el experimento. En **Ejecución** grafica `x`. **Guardar disposición de gráficas** recuerda los paneles. Los resultados y configuraciones personales se guardan en `datos/`, fuera del repositorio.

Los cinco ejemplos predeterminados están en [ejemplos/predeterminados/](ejemplos/predeterminados/); el código de sus algoritmos está en [algoritmos/](algoritmos/). Incluyen RDCF, RCCRD coordinado, consenso y dos tutoriales, conservando sus parámetros guardados.

**Para usarlos desde la plataforma**, elige el método en el menú **Algoritmo**: su configuración predeterminada se carga automáticamente. Para volver a cargarla después de editar los campos, abre **Ejemplo predeterminado** y pulsa **Cargar ejemplo predeterminado**. Si has guardado un ejemplo propio para ese algoritmo, este tiene prioridad sobre el incluido.

**RDCF** corresponde a *Replicator Dynamics with Capacity Factors* en el artículo; el identificador interno `distribuido_ccrd` se conserva por compatibilidad.

Las [18 configuraciones de seis agentes del artículo](ejemplos/articulo/README.md) están aparte, en `ejemplos/articulo/`, organizadas por escenario, algoritmo, topología y modo de comunicación. Cada caso contiene un `configuracion.json` que puedes cargar abriendo **Abrir una configuración guardada** y pulsando **Seleccionar JSON**. Sus conexiones son locales. Para placas, registra tus dispositivos y asigna los agentes desde el diálogo de ejecución SSH/TCP.

Completar un ensayo no garantiza convergencia ni optimalidad. Seleccionar asíncrono cambia la comunicación; no garantiza que cualquier algoritmo conserve sus propiedades matemáticas. Los archivos Python importados se ejecutan como código: utiliza archivos de confianza.

## Guías esenciales

- [Primer algoritmo](docs/PRIMER_ALGORITMO.md).
- [Editor paso a paso](docs/ASISTENTE.md) y [contrato Python](docs/CONTRATO.md).
- [Perfiles y funciones locales](docs/PERFILES_FUNCIONES.md).
- [Conexión y ejecución en placas](docs/EJECUCION_PLACAS.md).
- [Retirada y reincorporación](docs/FALLAS.md).
- [Cambios programados de parámetros](docs/DEMANDA_VARIABLE.md).

`lab/` contiene el motor y comunicaciones; `algoritmos/` los métodos; `ejemplos/` las configuraciones; `plantillas/` el contrato comentado; `herramientas/` las utilidades de distribución e instalación; `tests/` las pruebas. Para comprobar la copia usa `.venv\Scripts\python.exe -m herramientas.verificar_instalacion` y para ejecutar las pruebas `.venv\Scripts\python.exe -m unittest discover -s tests`.

Puedes crear un acceso con `crear_acceso_directo.cmd` y un ZIP de fuentes con `.venv\Scripts\python.exe -m herramientas.compartir`. Cada destinatario instala su propio entorno. No se incluyen historiales, contraseñas, claves SSH, inventarios, capturas personales ni la carpeta de resultados. Las direcciones de loopback del código son necesarias para las ejecuciones locales, no son IP de tus placas.

Este paquete contiene el software y configuraciones, no el borrador del artículo ni los registros históricos de la campaña. El artículo deberá enlazar un conjunto de datos sanitizado aparte si afirma que publica esas trazas.
