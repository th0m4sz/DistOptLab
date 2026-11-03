# Función de este módulo: Permite preparar, revisar y descargar una figura para publicación.
import base64
import copy
from nicegui import ui, run
from .figure_export import default_options, package, render


def open_figure_export(figure, provenance):
    figure = copy.deepcopy(figure)  # La vista en vivo no debe alterar la figura que se está editando.
    defaults = default_options(figure)
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-5xl gap-3'):
        ui.label('Exportar figura para artículo').classes('section-title')
        if any(s.get('status')!='completed' for s in provenance.get('sources', {}).values()):
            ui.label('Esta selección incluye ensayos sin terminar correctamente. La figura contiene registros parciales.').classes('note')
        if 'duration_rows' in provenance:
            ui.label('Las barras de error indican el margen estimado de alineación de relojes; no representan variabilidad entre repeticiones ni intervalos de confianza.').classes('note')
        with ui.row().classes('w-full'):
            xlabel = ui.input('Etiqueta eje X', value=defaults['xlabel']).props('outlined dense').classes('flex-1')
            ylabel = ui.input('Etiqueta eje Y', value=defaults['ylabel']).props('outlined dense').classes('flex-1')
        with ui.row().classes('w-full'):
            width = ui.number('Ancho (mm)', value=defaults['width_mm'], min=60,max=300).props('outlined dense').classes('flex-1')
            height = ui.number('Alto (mm)', value=defaults['height_mm'], min=40,max=400).props('outlined dense').classes('flex-1')
        with ui.expansion('Ajustes de apariencia', icon='tune').classes('w-full'):
            font = ui.number('Letra (pt)', value=9,min=6,max=20).props('outlined dense')
            gray = ui.checkbox('Blanco y negro',value=False)
        names = []
        with ui.expansion('Nombres de las series', icon='label').classes('w-full'):
            for i,name in enumerate(defaults['names']):
                names.append(ui.input(f'Serie {i+1}',value=name).props('outlined dense').classes('w-full'))
        category_fields = {}
        if defaults['categories']:
            with ui.expansion('Etiquetas de las barras', icon='bar_chart').classes('w-full'):
                ui.label('Identifica cada condición, por ejemplo Sync · Laptop · Ring. Usa etiquetas distintas.').classes('text-sm')
                for index, labels in defaults['categories'].items():
                    category_fields[index] = [ui.input(f'Barra {int(index)+1}/{j+1}',value=label).props('outlined dense').classes('w-full') for j,label in enumerate(labels)]
        output = ui.column().classes('w-full')

        async def generate():
            button.disable()
            button.props('loading')
            output.clear()
            options = dict(title='', xlabel=xlabel.value, ylabel=ylabel.value,
                           width_mm=width.value,height_mm=height.value,font_pt=font.value,dpi=300,
                           legend='upper_right',legend_columns=1,grayscale=gray.value,
                           names=[n.value for n in names],
                           categories={i:[field.value for field in fields] for i,fields in category_fields.items()})
            try:
                preview_options = dict(options, dpi=120)
                images = await run.io_bound(render, figure, preview_options, ('png',))
                if images is None:
                    return
                with output:
                    if images['warnings']:
                        ui.label('Revisa la vista previa; si hay texto cortado, aumenta el tamaño o acorta las etiquetas. '+ '; '.join(images['warnings'])).classes('note')
                    ui.image('data:image/png;base64,'+base64.b64encode(images['png']).decode()).classes('w-full')
                    ui.label('Descargas de esta vista previa. Si editas opciones, pulsa de nuevo Generar vista previa.').classes('text-sm')
                    cache = {}
                    async def download(fmt):
                        for control in downloads:
                            control.disable()
                        try:
                            if fmt not in cache:
                                if fmt == 'zip':
                                    generated = await run.io_bound(package, figure, options, provenance)
                                    if generated is None:
                                        return
                                    cache.update(generated)
                                else:
                                    generated = await run.io_bound(render, figure, options, (fmt,))
                                    if generated is None:
                                        return
                                    cache.update(generated)
                            ui.download.content(cache[fmt], 'figure.'+fmt)
                        except Exception as exc:
                            ui.notify(f'No se pudo descargar: {exc}', type='negative')
                        finally:
                            for control in downloads:
                                control.enable()
                    downloads = []
                    with ui.row():
                        for fmt, label in [('pdf','PDF vectorial'),('svg','SVG vectorial'),('png','PNG'),('zip','ZIP reproducible')]:
                            downloads.append(ui.button(label, icon='download', on_click=lambda f=fmt: download(f)).props('outline'))
            except Exception as exc:
                ui.notify(f'No se pudo exportar la figura: {exc}',type='negative')
            finally:
                button.enable()
                button.props(remove='loading')
        with ui.row():
            button = ui.button('Generar vista previa', icon='image', on_click=generate)
            ui.button('Cerrar',on_click=dialog.close).props('flat')
    dialog.open()
