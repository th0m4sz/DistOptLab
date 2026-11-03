# Configuraciones de seis nodos para ECC 2027

Estas configuraciones utilizan el paso y los datos del piloto local. Se importan desde la plataforma como cualquier configuración JSON. No cambian los ejemplos personales guardados.

Los dos algoritmos de despacho usan los seis generadores de la tabla 1, página impresa 228 (página 20 del PDF `refs/notas_documento_base.pdf`), con demanda constante de 1150 kW. Las potencias iniciales elegidas para estas pruebas son 300, 200, 200, 180, 30 y 240 kW; suman la demanda y están dentro de los límites. Estas condiciones iniciales son una elección del protocolo, no valores publicados en la tabla.

| Generator | a ($/h) | b ($/kWh) | c ($/kW²h) | Minimum (kW) | Maximum (kW) | Initial (kW) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DG1 | 64.67 | 795.5 | 1.15 | 100 | 500 | 300 |
| DG2 | 65.46 | 1448.6 | 0.82 | 82 | 362 | 200 |
| DG3 | 190.92 | 838.1 | 1.53 | 65 | 315 | 200 |
| DG4 | 39.19 | 696.1 | 2.46 | 50 | 271 | 180 |
| DG5 | 104.44 | 1150.5 | 0 | 0 | 60 | 30 |
| DG6 | 28.77 | 903.2 | 0.71 | 20 | 260 | 240 |

Se reutilizan los parámetros físicos y económicos de esa tabla. Los algoritmos cargados siguen usando sus ecuaciones de xhat; no se incorpora la función de barrera ni el cambio de disponibilidad solar del artículo.

El consenso utiliza referencias 1, 3, 5, 7, 9 y 11, cuyo promedio es 6. Todos los estados x y lambda empiezan en cero. Se desactivan el cambio de referencia y la perturbación inicial del ejemplo anterior.

Cada algoritmo tiene un archivo síncrono y otro asíncrono. Los algoritmos entre vecinos usan anillo; RCCRD utiliza coordinador explícito. Todos solicitan un intervalo mínimo de 0.001 s, sin retardos artificiales y sin fallas programadas. El seguimiento de gradiente queda fuera de esta campaña.

La comparación de intervalos se reproduce con `python -m herramientas.piloto_ecc2027 --output datos/estudios/ecc2027/piloto_intervalos`. No ejecutes otros experimentos mientras se mide: los ensayos del piloto se lanzan uno a uno.

La herramienta reanuda los casos pendientes de esa carpeta y conserva los ya registrados, incluidos los fallidos. Para ejecutar una campaña nueva, elige otra carpeta con `--output`. `--plot-only --trajectories` regenera las figuras desde los registros existentes, sin ejecutar agentes.
