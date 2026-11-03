# Función de este módulo: Da un formato legible a los ejes de las gráficas sin cambiar los datos registrados.
"""Escalas legibles sin redondear ni transformar los datos registrados."""
import math


def readable_yaxis(traces):
    values = [v for trace in traces for v in trace.get('y', [])
              if type(v) in (int, float) and math.isfinite(v)]
    axis = dict(tickformat='.6~g', exponentformat='e', showexponent='all', hoverformat='.12~g')
    if not values:
        return axis
    lo, hi = min(values), max(values)
    magnitude = max(abs(lo), abs(hi))
    if 0 < magnitude < 1e-6:
        axis['tickformat'] = '.3e'
    # Una serie casi constante necesita contexto, no ampliar ruido de redondeo.
    if magnitude and hi-lo <= magnitude*1e-10:
        center = (lo+hi)/2
        padding = magnitude*.01
        axis.update(range=[center-padding, center+padding], autorange=False)
    return axis
