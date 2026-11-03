# Función de este módulo: Exporta figuras científicas y sus datos, sin ejecutar algoritmos.
"""Renderizador autónomo: también se incluye en el ZIP para reproducir la figura."""
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
import threading
import warnings
import zipfile

LOCK = threading.Lock()  # Matplotlib comparte ajustes globales entre hilos.
COLORS = ['#0072B2', '#D55E00', '#009E73', '#AA4499', '#222222', '#56B4E9', '#E69F00', '#882255', '#44AA99', '#999933']
STYLES = ['-', '--', '-.', ':']
LEGEND_STYLE = dict(loc='upper right', frameon=True, framealpha=1, facecolor='white', edgecolor='black', fancybox=False,
                    borderpad=.3, labelspacing=.3, handlelength=1.6, handletextpad=.5)
LEGEND_LINEWIDTH = .4


def add_legend(ax, **options):
    """Leyenda compartida con marco negro fino, independiente de otros bordes."""
    legend = ax.legend(**dict(LEGEND_STYLE, **options))
    legend.get_frame().set_linewidth(LEGEND_LINEWIDTH)
    return legend


def default_options(figure):
    def title(axis):
        value = figure.get('layout', {}).get(axis, {}).get('title', '')
        return value.get('text', '') if isinstance(value, dict) else value
    names = [t.get('name', f'Series {i+1}') for i,t in enumerate(figure['data'])]
    short = [re.sub(r'(Agente \d+) · .*', r'\1', name) for name in names]
    names = short if len(set(short)) == len(short) else names
    return dict(title='', xlabel=title('xaxis'), ylabel=title('yaxis'),
                width_mm=180, height_mm=90, font_pt=9, dpi=300, legend='upper_right',
                legend_columns=1, grayscale=False,
                names=names,
                categories={str(i):list(t['y']) for i,t in enumerate(figure['data']) if t.get('type')=='bar'})


def _number(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) else math.nan


def render(figure, options, formats=('png', 'pdf', 'svg')):
    """Mantiene todos los puntos, los huecos y los escalones hv (último estado)."""
    from matplotlib import rc_context
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    if not figure.get('data'):
        raise ValueError('Selecciona primero variables con datos.')
    for key, lo, hi in [('width_mm', 60, 300), ('height_mm', 40, 400), ('font_pt', 6, 20), ('dpi', 72, 600)]:
        value = options[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'{key}: debe estar entre {lo} y {hi}.')
    if len(options['names']) != len(figure['data']):
        raise ValueError('Debe haber una etiqueta por serie.')
    if not options['xlabel'].strip() or not options['ylabel'].strip():
        raise ValueError('Escribe las etiquetas de ambos ejes y sus unidades, cuando correspondan.')
    if options['legend'] != 'none' and any(not n.strip() for n in options['names']):
        raise ValueError('Completa los nombres de las series de la leyenda.')
    result = {}
    with LOCK, rc_context({'font.family':'DejaVu Sans', 'font.size':options['font_pt'],
                           'pdf.fonttype':42, 'ps.fonttype':42, 'svg.fonttype':'path',
                           'path.simplify':False, 'text.usetex':False}), warnings.catch_warnings(record=True) as caught:
        fig = Figure(figsize=(options['width_mm']/25.4, options['height_mm']/25.4), layout='constrained')
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        for i, trace in enumerate(figure['data']):
            color = 'black' if options['grayscale'] else COLORS[i % len(COLORS)]
            label = options['names'][i]
            if trace.get('type') == 'bar':
                if trace.get('orientation') != 'h':
                    raise ValueError('Esta exportación de barras requiere orientación horizontal.')
                categories = options.get('categories', {}).get(str(i), trace['y'])
                if len(categories)!=len(trace['y']) or len(set(categories))!=len(categories):
                    raise ValueError('Cada barra debe tener una etiqueta distinta.')
                ax.barh(categories, trace['x'], label=label, color=color,
                        xerr=trace.get('error_x', {}).get('array'), capsize=2,
                        hatch='//' if options['grayscale'] else None)
                ax.invert_yaxis()
            else:
                if trace.get('type', 'scatter') != 'scatter':
                    raise ValueError('Tipo de gráfica no admitido por el exportador.')
                x, y = [_number(v) for v in trace['x']], [_number(v) for v in trace['y']]
                mode = trace.get('mode', 'lines')
                # En color todas las curvas son continuas. Los trazos solo
                # distinguen series al elegir explícitamente blanco y negro.
                style = STYLES[i % len(STYLES)] if options['grayscale'] else '-'
                ax.plot(x, y, label=label, color=color, linewidth=1.2,
                        linestyle=style if 'lines' in mode else 'None',
                        marker='o' if 'markers' in mode else None, markersize=2.5,
                        drawstyle='steps-post' if trace.get('line', {}).get('shape')=='hv' else 'default')
        ax.set(xlabel=options['xlabel'], ylabel=options['ylabel'], title=options['title'])
        ax.grid(True, linewidth=.4, alpha=.3)
        ax.set_axisbelow(True)
        for key, setter in [('xaxis', ax.set_xlim), ('yaxis', ax.set_ylim)]:
            limits = figure.get('layout', {}).get(key, {}).get('range')
            if limits is not None:
                setter(limits)
        for shape in figure.get('layout', {}).get('shapes', []):
            if shape.get('type')=='line' and shape.get('xref')=='x' and shape.get('x0')==shape.get('x1'):
                ax.axvline(shape['x0'], color='0.4', linewidth=.8, linestyle=':')
        for annotation in figure.get('layout', {}).get('annotations', []):
            if annotation.get('xref')=='x' and annotation.get('yref')=='paper':
                ax.text(annotation['x'], .98, annotation.get('text',''), transform=ax.get_xaxis_transform(),
                        va='top', rotation=90, fontsize=options['font_pt'])
        where = options['legend']
        if where != 'none':
            kwargs = dict(LEGEND_STYLE, ncol=int(options['legend_columns']))
            if where == 'upper_right':
                kwargs.update(loc='upper right')
            elif where == 'bottom':
                kwargs.update(loc='upper center', bbox_to_anchor=(.5, -.22))
            elif where == 'right':
                kwargs.update(loc='center left', bbox_to_anchor=(1.02, .5))
            else:
                kwargs.update(loc='best')
            add_legend(ax, **kwargs)
        for fmt in formats:
            if fmt not in ('png', 'pdf', 'svg'):
                raise ValueError('Formato no permitido.')
            stream = io.BytesIO()
            fig.savefig(stream, format=fmt, dpi=options['dpi'], facecolor='white')
            result[fmt] = stream.getvalue()
        result['warnings'] = list(dict.fromkeys(str(w.message) for w in caught))
        fig.clear()
    return result


def package(figure, options, provenance):
    images = render(figure, options)
    csv_stream = io.StringIO(newline='')
    writer = csv.writer(csv_stream)
    writer.writerow(['series_index', 'series', 'sample_index', 'x', 'y', 'x_error'])
    for i,t in enumerate(figure['data']):
        errors = t.get('error_x', {}).get('array', [])
        for k,(x,y) in enumerate(zip(t['x'],t['y'])):
            category = options.get('categories', {}).get(str(i), [])
            writer.writerow([i+1,options['names'][i],k,x,category[k] if category else y,errors[k] if k<len(errors) else ''])
    data = csv_stream.getvalue().encode('utf-8-sig')
    payload = dict(figure=figure, options=options, provenance=provenance,
                   data_sha256=hashlib.sha256(data).hexdigest())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for fmt in ('png','pdf','svg'):
            z.writestr('figure.'+fmt, images[fmt])
        z.writestr('data.csv', data)
        z.writestr('figure.json', json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        z.writestr('reproduce.py', Path(__file__).read_bytes())
        z.writestr('README.txt', 'Figura exportada desde registros, sin volver a ejecutar el algoritmo.\n'
                   'PDF y SVG son vectoriales. PNG utiliza la resolución elegida.\n'
                   'Reproducción: instalar matplotlib==3.10.8 y ejecutar python reproduce.py en esta carpeta.\n'
                   'Se conservan puntos, huecos y escalones; la reconstrucción global temporal utiliza el intervalo declarado.\n'
                   'El zoom interactivo y ocultar series mediante clic en la leyenda no cambian esta exportación.\n'
                   'Conserva también el ZIP de los ensayos originales. Esta figura no certifica conformidad editorial.\n')
    images['zip'] = buf.getvalue()
    return images


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    source = json.loads((root/'figure.json').read_text(encoding='utf-8'))
    for extension, content in render(source['figure'], source['options']).items():
        if extension != 'warnings':
            (root/('reproduced.'+extension)).write_bytes(content)
