# Configuraciones públicas

Estos cinco JSON acompañan a los archivos de `algoritmos/`. Una instalación nueva los carga automáticamente al seleccionar su algoritmo. Los ejemplos privados guardados en `datos/ejemplos_predeterminados/` tienen prioridad.

Consenso robusto, distribuido con xhat y RCCRD conservan los datos matemáticos de los ejemplos guardados al preparar esta entrega, incluidos los coeficientes distintos por agente. Gradiente y perfiles conservan sus configuraciones didácticas. Solo se han retirado asignaciones de dispositivos y metadatos de conexiones; se utilizan direcciones de loopback para probarlos localmente.

No se guardan aquí nuevos cambios hechos desde la interfaz. Para actualizar deliberadamente estas copias, ejecuta desde la raíz:

```powershell
.venv\Scripts\python.exe -m herramientas.publicar_ejemplos
```

El comando prepara archivos locales, no sube nada a GitHub. Revisa sus diferencias antes de versionarlos.
