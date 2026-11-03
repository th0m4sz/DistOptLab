# Cambios de demanda durante un experimento

En **Nuevo experimento → Configura el experimento**, debajo de los parámetros comunes, abre **Cambio de demanda · opcional**.

1. Activa **Programar cambios de demanda**.
2. Selecciona el parámetro que representa la demanda: por ejemplo, Demanda total en RCCRD.
3. Pulsa **Añadir cambio de demanda** e indica **Aplicar desde el índice** y **Nueva demanda**. Puedes añadir hasta 30 cambios con índices distintos.
4. Inicia el ensayo. Guardar configuración y el ejemplo predeterminado conservan esta programación. Desactivarla recupera la referencia constante del formulario.

El valor anterior al primer cambio es el indicado en los parámetros comunes. Los valores son absolutos: 900 significa demanda nueva de 900, no un incremento de 900. Un cambio en 500 se utiliza al calcular la actualización 500 → 501. No cambia las condiciones iniciales, el estado acumulado, las funciones de coste ni el paso numérico.

## Qué hace cada método

En modelos del asistente, el parámetro toma su valor vigente en las expresiones de actualización, las funciones auxiliares, el coordinador, las observaciones y las métricas del evaluador con índice conocido. Las condiciones iniciales y las comprobaciones estáticas conservan su contexto inicial; no son un mecanismo para imponer seguimiento de demanda variable.

El RCCRD instalado utiliza `demand_kw` en su agregado del coordinador. Con la corrección robusta activa, esta expresión recibe el nuevo valor. Las ecuaciones del archivo no se modifican.

En el `distribuido_ccrd` instalado, `demanda` solo aparece en el balance de evaluación. Cambiarla modifica la referencia del error, pero no las potencias calculadas: la plataforma no introduce una corrección de seguimiento que el método no declaró. Lo mismo ocurre con RCCRD si su corrección se desactiva. Ningún motor puede garantizar seguimiento ante una demanda inviable o un paso inadecuado.

## Síncrono y asíncrono

La programación es **por índice**, no por segundos. En síncrono, todos usan la referencia de esa ronda. En asíncrono, cada agente utiliza la referencia correspondiente a su índice local. En coordinador asíncrono, el agregado utiliza el índice del solicitante, junto con las últimas muestras disponibles. El cambio no añade una barrera de ronda ni un reloj global.

En una reconstrucción por tiempo, los agentes activos pueden estar a ambos lados de un cambio. En ese intervalo, la demanda global y las métricas que dependen de ella quedan vacías si sus referencias locales difieren; la generación total sigue disponible. Cuando vuelven a usar el mismo valor de referencia, el balance se representa de nuevo. No se elige arbitrariamente la referencia del más rápido.

## Registros y gráficas

- `config.json → demand_schedule`: parámetro, índices y valores programados. El valor inicial permanece en `parameters`.
- **Demanda de referencia**: nueva variable seleccionable por agente o en las series globales. Se dibuja con escalones.
- En gráficas por índice se marcan los cambios programados. En segundos se usan las marcas registradas; no se convierte un índice en segundos multiplicándolo por el paso matemático.
- CSV, JSONL y ZIP conservan la referencia como `reference/NOMBRE`. Los registros de agentes incluyen su referencia local. Las vistas locales enviadas a las Raspberry Pi incluyen la programación común y siguen excluyendo parámetros privados de otros agentes.

Ejemplo de configuración (no se añade si la opción está desactivada):

```json
"demand_schedule": {
  "version": 1,
  "parameter": "demand_kw",
  "events": [{"at": 500, "value": 900}, {"at": 800, "value": 850}]
}
```

## Python propio

La plataforma no reescribe un algoritmo manual. Para habilitar la opción, el archivo declara `PARAMETROS_PROGRAMABLES = True` a nivel superior y utiliza `rt.parameters_at(k)` dentro de `paso` o `coordinar`. Este método devuelve los parámetros comunes vigentes sin modificar la configuración inicial. `rt.parameters_values` conserva los valores iniciales; una copia guardada en `preparar` no se actualizará automáticamente.

El archivo debe implementar su propio seguimiento y su evaluación. Declarar la bandera sin utilizar el método no adapta sus ecuaciones. La plantilla comentada recuerda esta diferencia. Los modelos del asistente lo admiten directamente.
