# Función de este módulo: Construye el asistente paso a paso y genera el archivo Python del algoritmo diseñado.
"""Asistente visual: crea archivos del contrato público, nunca modifica el ejecutor."""
import copy
import json
import uuid
from pathlib import Path

from nicegui import ui, run

from .equations import blank_model, generate_source, model_from_source, preview_model
from .plugins import install
from .function_profiles_ui import FunctionProfilesEditor
from .storage import write_json, read_json
from .learning_ui import step_help, neighbor_help
from .presentation import help_details
from .drafts import remove_draft, restore_draft, latest_recovery, save_recovery


class RowsEditor:
    def __init__(self, title, columns, rows, hint, button, *, mode_control=None):
        self.columns, self.rows, self.controls = columns, copy.deepcopy(rows), []
        self.mode_control = mode_control
        self.on_change = None
        with ui.column().classes('w-full gap-3'):
            ui.label(title).classes('section-title')
            ui.label(hint).classes('muted')
            self.area = ui.column().classes('w-full gap-3')
            ui.button(button, icon='add', on_click=self.add).props('outline')
        self.render()

    def get(self):
        return [{key: control.value for key, control in row.items()} for row in self.controls]

    def render(self):
        self.area.clear()
        self.controls = []
        with self.area:
            if not self.rows:
                ui.label('Sin elementos definidos.').classes('text-sm text-slate-500')
            for index, row in enumerate(self.rows):
                with ui.card().classes('editor-row w-full gap-3'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label(f'{index+1}. {row.get("label") or row.get("name") or row.get("key") or "Nuevo elemento"}').classes('font-semibold')
                        with ui.row().classes('gap-1'):
                            ui.button(icon='arrow_upward', on_click=lambda i=index: self.move(i, -1)).props('flat dense').tooltip('Subir').set_enabled(index > 0)
                            ui.button(icon='arrow_downward', on_click=lambda i=index: self.move(i, 1)).props('flat dense').tooltip('Bajar').set_enabled(index < len(self.rows)-1)
                            ui.button('Quitar', icon='close', on_click=lambda i=index: self.remove(i)).props('flat dense')
                    controls = {}
                    def add_controls(columns):
                        for key, label, options, default in columns:
                            value = row.get(key, default)
                            if options:
                                controls[key] = ui.select(options, label=label, value=value).props('outlined dense').classes('w-full')
                            elif key in ('expression', 'update', 'initial'):
                                controls[key] = ui.textarea(label, value=value).props('outlined autogrow rows=1').classes('w-full md:col-span-2 font-mono')
                            else:
                                controls[key] = ui.input(label, value=value).props('outlined dense').classes('w-full')
                            if key == 'kind':
                                ui.label().bind_text_from(controls[key], 'value', backward=lambda kind: {
                                    'next': 'Escribe la fórmula completa de x[k+1], incluido el paso si lo usas. La plataforma no añade otro paso.',
                                    'euler': 'Escribe solo la tasa dx/dt. La plataforma calcula x + h·expresión con el paso de Euler configurado.',
                                    'derived': 'Variable algebraica: se recalcula con los estados nuevos; no se integra ni necesita un valor inicial propio.',
                                }.get(kind, '')).classes('rule-help md:col-span-2')
                            if key == 'update' and self.mode_control is not None:
                                neighbor_help(self.mode_control)
                    advanced = {'choices', 'min', 'max', 'lower', 'upper'}
                    with ui.element('div').classes('w-full grid grid-cols-1 md:grid-cols-2 gap-3'):
                        add_controls([c for c in self.columns if c[0] not in advanced])
                    extra = [c for c in self.columns if c[0] in advanced]
                    if extra:
                        projection = any(c[0] in ('lower', 'upper') for c in extra)
                        title = 'Proyección de la actualización (opcional)' if projection else 'Restricciones del formulario y opciones'
                        with ui.expansion(title, icon='tune').classes('w-full'):
                            ui.label('Recorta el valor nuevo a estos límites. No es lo mismo que comprobar una condición; déjalo vacío si tu método ya maneja los límites.' if projection else 'Mínimo y máximo restringen lo que se puede introducir en este campo del formulario. No limitan la variable de estado ni crean pmin o pmax en tus ecuaciones.').classes('text-sm text-slate-600')
                            with ui.element('div').classes('w-full grid grid-cols-1 md:grid-cols-2 gap-3'):
                                add_controls(extra)
                    if 'choices' in controls:
                        controls['choices'].bind_visibility_from(controls['type'], 'value', backward=lambda value: value == 'select')
                    if 'kind' in controls:
                        controls['initial'].bind_visibility_from(controls['kind'], 'value', backward=lambda value: value != 'derived')
                    self.controls.append(controls)
                    if self.on_change:
                        for control in controls.values():
                            control.on_value_change(lambda _: self.on_change())
        if self.on_change:
            self.on_change()

    def add(self):
        self.rows = self.get() + [{k: default for k, _, _, default in self.columns}]
        self.render()

    def remove(self, index):
        self.rows = self.get()
        self.rows.pop(index)
        self.render()

    def move(self, index, delta):
        self.rows = self.get()
        target = index + delta
        if 0 <= target < len(self.rows):
            self.rows[index], self.rows[target] = self.rows[target], self.rows[index]
        self.render()


def open_designer(store, on_created, initial=None, draft_file=None):
    """Recupera la edición y guarda una copia automática por diálogo."""
    draft_path = store.root / 'modelos'
    recovered = False
    if initial is None:
        initial, draft_file = latest_recovery(draft_path)
        if initial is None:
            candidates = sorted(draft_path.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            if candidates:
                draft_file = candidates[0]
                initial = read_json(draft_file)
        recovered = initial is not None
    model = copy.deepcopy(initial if initial is not None else blank_model())
    if draft_file is None and model.get('id'):
        existing = draft_path / f'{model["id"]}.json'
        if existing.parent.resolve() == draft_path.resolve() and existing.is_file():
            draft_file = existing
    editors, basics = {}, {}
    editing = {'path': draft_file, 'last': None}
    recovery_path = draft_path / 'recuperacion' / f'{uuid.uuid4().hex}.json'
    removed = {'path': None}

    def error(exc):
        ui.notify(str(exc), type='negative', timeout=10000, close_button=True)

    def field_rows(rows):
        if model.get('_form'):
            return copy.deepcopy(rows)
        from .plugins import fields
        return [dict(key=f.key, label=f.label, type=f.type,
                     default=f.default if f.type == 'string' else json.dumps(f.default, ensure_ascii=False),
                     min='' if f.min is None else str(f.min), max='' if f.max is None else str(f.max),
                     choices=json.dumps(f.choices or [], ensure_ascii=False)) for f in fields(rows)]

    def raw_model():
        result = blank_model()
        result.update({key: widget.value for key, widget in basics.items()})
        for group, editor in editors.items():
            result[group] = editor.get()
        if 'functions' in editors:
            result.update(editors['functions'].metadata())
        result['_form'] = True
        return result

    def autosave():
        try:
            current = raw_model()
            if current != editing['last']:
                save_recovery(recovery_path, current, editing['path'])
                editing['last'] = copy.deepcopy(current)
                save_status.set_text('Edición guardada automáticamente en esta laptop.')
        except (OSError, ValueError) as exc:
            save_status.set_text(f'No se pudo guardar la edición: {exc}')

    def close():
        autosave()
        autosave_timer.cancel()
        files_dialog.close()
        dialog.close()

    def collect():
        result = raw_model()
        result.pop('_form')
        for group in ('parameters', 'fields'):
            for row in result[group]:
                try:
                    row['default'] = row['default'] if row['type'] == 'string' else json.loads(row['default'])
                    if row['type'] == 'select':
                        row['choices'] = json.loads(row['choices'])
                    else:
                        row.pop('choices', None)
                    for bound in ('min', 'max'):
                        if row.get(bound, '').strip():
                            row[bound] = float(row[bound])
                        else:
                            row.pop(bound, None)
                except ValueError as exc:
                    raise ValueError(f'{row["key"]}: valor inicial u opciones inválidos. Usa números, true/false o JSON para listas.') from exc
        groups = [result['functions']] + [p['functions'] for p in result.get('function_profiles', [])]
        for functions in groups:
            for row in functions:
                row['args'] = [value.strip() for value in row['args'].split(',') if value.strip()]
        if result['mode'] != 'coordinator':
            result['coordinator'] = []
        return result

    def download_model():
        try:
            ui.download(json.dumps(collect(), ensure_ascii=False, indent=2).encode(), filename='modelo_algoritmo.json')
        except Exception as exc:
            error(exc)

    def save_draft():
        try:
            current = collect()
            path = editing['path'] or draft_path / f'modelo_{uuid.uuid4().hex[:10]}.json'
            if Path(path).resolve().parent != draft_path.resolve():
                raise ValueError('El borrador debe pertenecer a esta carpeta de modelos')
            write_json(path, current)
            editing['path'] = path
            editing['last'] = None
            autosave()
            ui.notify('Borrador guardado. Puedes abrirlo con “Recuperar borrador”.', type='positive')
            saved.set_options(saved_options(), value=str(path))
        except Exception as exc:
            error(exc)

    def saved_options():
        result = {}
        for path in sorted(draft_path.glob('*.json')):
            try:
                value = read_json(path)
                if isinstance(value, dict):
                    result[str(path)] = f'{value.get("name") or "Sin nombre"} · {path.stem}'
            except (OSError, ValueError):
                continue
        return result

    def delete_selected():
        if not saved.value:
            ui.notify('Selecciona el borrador que quieres eliminar.', type='info')
            return
        try:
            removed['path'] = remove_draft(draft_path, saved.value)
            saved.set_options(saved_options(), value=None)
            undo_delete.set_visibility(True)
            ui.notify('Borrador retirado de la lista. Puedes deshacer la eliminación.', type='positive')
        except (OSError, ValueError) as exc:
            error(exc)

    def undo_selected():
        try:
            path = restore_draft(draft_path, removed['path'])
            saved.set_options(saved_options(), value=str(path))
            removed['path'] = None
            undo_delete.set_visibility(False)
            ui.notify('Borrador recuperado.', type='positive')
        except (OSError, ValueError, TypeError) as exc:
            error(exc)

    def reopen(value, path=None):
        close()
        open_designer(store, on_created, value, path)

    async def import_model(event):
        try:
            source = await event.file.text()
            value = model_from_source(source) if event.file.name.endswith('.py') else json.loads(source)
            if not isinstance(value, dict) or value.get('version') != 1:
                raise ValueError('No es un modelo del asistente versión 1')
            reopen(value)
        except Exception as exc:
            error(exc)

    with ui.dialog().props('persistent') as dialog, ui.card().classes('algorithm-designer gap-2').style('padding:16px;width:1440px;max-width:98vw;height:96dvh;max-height:96dvh;overflow:hidden'):
        with ui.row().classes('w-full items-center shrink-0'):
            ui.label('Diseñar un algoritmo').classes('section-title')
            ui.space()
            ui.button('Archivos y borradores', icon='folder_open', on_click=lambda: files_dialog.open()).props('flat dense no-caps').style('min-height:36px')
            ui.button('Cerrar', on_click=close).props('flat dense no-caps').style('min-height:36px')
        save_status = ui.label('Edición recuperada. Tus borradores guardados se conservan.' if recovered else 'La edición se conserva automáticamente mientras escribes.').classes('text-sm text-slate-600 shrink-0')
        with ui.dialog() as files_dialog, ui.card().classes('gap-3').style('width:760px;max-width:94vw;max-height:85dvh;overflow:auto'):
            with ui.row().classes('w-full items-center'):
                ui.label('Archivos y borradores').classes('section-title')
                ui.space()
                ui.button('Volver al editor', icon='close', on_click=files_dialog.close).props('flat no-caps')
            with ui.row().classes('w-full gap-3'):
                ui.button('Guardar borrador', icon='save', on_click=save_draft).props('outline')
                ui.button('Nuevo diseño vacío', icon='add', on_click=lambda: reopen(blank_model())).props('flat')
                ui.button('Descargar diseño JSON', icon='download', on_click=download_model).props('flat')
            saved = ui.select(saved_options(), label='Recuperar borrador', value=str(draft_file) if draft_file else None).props('outlined').classes('w-full')
            with ui.row().classes('gap-2'):
                ui.button('Abrir borrador seleccionado', on_click=lambda: reopen(read_json(saved.value), saved.value) if saved.value else None).props('flat')
                ui.button('Eliminar borrador seleccionado', icon='delete_outline', on_click=delete_selected).props('flat color=negative')
                undo_delete = ui.button('Deshacer eliminación', icon='undo', on_click=undo_selected).props('flat')
                undo_delete.set_visibility(False)
            ui.upload(label='Importar diseño JSON o Python generado', auto_upload=True, max_file_size=1_000_000,
                      on_upload=import_model).props('accept=.json,.py').classes('w-full')
        with ui.tabs().props('dense no-caps align=left').classes('w-full shrink-0 border-b') as steps:
            tabs = [ui.tab(title) for title in ('1. Inicio', '2. Datos', '3. Funciones', '4. Actualización', '5. Gráficas', '6. Probar y crear')]
        with ui.tab_panels(steps, value=tabs[0]).classes('w-full').style('min-height:0;flex:1;overflow-y:auto;overscroll-behavior:contain'):
            with ui.tab_panel(tabs[0]):
                step_help(0)
                ui.label('¿Qué método quieres implementar?').classes('section-title')
                basics['name'] = ui.input('Nombre del algoritmo', value=model.get('name', '')).props('outlined').classes('w-full')
                basics['id'] = ui.input('Identificador del archivo', value=model.get('id', '')).props('outlined').classes('w-full')
                ui.label('Usa 3–64 letras minúsculas, números y guion bajo. Para una nueva versión, utiliza otro identificador.').classes('text-sm text-slate-500')
                basics['description'] = ui.textarea('Descripción', value=model.get('description', '')).props('outlined autogrow').classes('w-full')
                basics['mode'] = ui.select({'sync': 'Síncrono · vecinos de la misma ronda', 'async': 'Asíncrono · últimas muestras de vecinos', 'coordinator': 'Coordinador explícito · intercambio síncrono o asíncrono'},
                                          label='Información disponible al actualizar', value=model.get('mode', 'sync')).props('outlined').classes('w-full')
                help_details('Qué puedes definir en este diseño', 'Un costo o un fitness no son obligatorios. Puedes usar gradientes, variables duales, memoria o funciones propias. Cada variable que necesita memoria debe formar parte del estado. '
                             'El grafo y los valores particulares de cada agente se ajustan después de generar el archivo. El asistente no define redes dirigidas ni topologías arbitrarias que cambian durante el ensayo; los escenarios de fallas se configuran en el experimento.')
            with ui.tab_panel(tabs[1]):
                step_help(1)
                columns = [('key', 'Nombre en ecuaciones', None, ''), ('label', 'Etiqueta del formulario', None, ''),
                           ('type', 'Tipo de dato', {'number': 'Número', 'integer': 'Entero', 'boolean': 'Booleano', 'string': 'Texto', 'json': 'Vector / matriz / JSON', 'select': 'Opciones'}, 'number'),
                           ('default', 'Valor inicial', None, '0'), ('choices', 'Opciones JSON (solo selector)', None, '[]'),
                           ('min', 'Mínimo del parámetro (opcional)', None, ''), ('max', 'Máximo del parámetro (opcional)', None, '')]
                editors['parameters'] = RowsEditor('Parámetros comunes', columns, field_rows(model.get('parameters', [])),
                    'Constantes compartidas o configurables: ganancias, tolerancias, tamaños, referencias. Usa true/false para booleanos y [1, 2] para un vector.', 'Añadir parámetro común')
                ui.separator()
                editors['fields'] = RowsEditor('Parámetros de cada agente', columns, field_rows(model.get('fields', [])),
                    'Datos locales: coeficientes, límites, referencias o estados iniciales. El valor de aquí se puede cambiar por agente en el formulario del experimento.', 'Añadir parámetro local')
            with ui.tab_panel(tabs[2]):
                step_help(2)
                with ui.expansion('Guía: funciones distintas por agente', icon='account_tree').classes('w-full border rounded-lg'):
                    from .learning_ui import guide_markdown
                    guide_markdown((Path(__file__).resolve().parents[1] / 'docs' / 'PERFILES_FUNCIONES.md').read_text(encoding='utf-8')).classes('w-full px-3 learning-prose')
                editors['functions'] = FunctionProfilesEditor(model, RowsEditor)
                help_details('Operadores, vectores y gradientes', 'Operadores: + - * / **; listas: [1, 2]; acceso: x[0]. Con vectores, las operaciones son por componente. Disponibles: sin, cos, exp, log, sqrt, tanh, abs, min, max, sum, norm, dot, matmul, clip. '
                             'Si conoces el gradiente, escríbelo como función. derivative("funcion", x) y gradient("funcion", vector) usan diferencias finitas centrales; epsilon opcional es el tercer argumento.')
            with ui.tab_panel(tabs[3]):
                step_help(3)
                with ui.expansion('Solo si partes de una ecuación continua: paso de Euler', icon='functions').classes('w-full'):
                    basics['integration_step'] = ui.input('Paso numérico para Euler (expresión)', value=model.get('integration_step', '0.01')).props('outlined').classes('w-full')
                    ui.label('Si elegiste Valor siguiente, este campo no se usa. Euler transforma dx/dt = F en x siguiente = x + h·F; debes elegir un h apropiado. No es la pausa real entre actualizaciones.').classes('note w-full')
                editors['states'] = RowsEditor('Variables y reglas de actualización', [
                    ('name', 'Nombre de variable', None, ''), ('label', 'Etiqueta para gráficas', None, ''),
                    ('kind', 'Regla', {'next': 'Valor siguiente x[k+1]', 'euler': 'Derivada dx/dt → Euler', 'derived': 'Variable algebraica (recalcular)'}, 'next'),
                    ('initial', 'Condición inicial', None, ''), ('update', 'Expresión de actualización o derivada', None, ''),
                    ('lower', 'Proyección inferior opcional', None, ''), ('upper', 'Proyección superior opcional', None, '')], model.get('states', []),
                    'Nombres sin adornos (x, y, memoria). x siempre es el estado anterior; next_x es el valor nuevo de una fila anterior. Las algebraicas se calculan después del resto. Iniciales se calculan de arriba abajo.', 'Añadir variable', mode_control=basics['mode'])
                help_details('Sumatorias y símbolos disponibles', 'Vecinos: sum_neighbors("x"), weighted_neighbors("x"), mean_neighbors("x"). No incluyen al propio agente. weighted_neighbors usa los pesos de los enlaces, sin normalizarlos. Puedes escribir una expresión dentro de las comillas. k empieza en 0; i es el identificador; n es el número de agentes. La ayuda junto a cada expresión incluye ejemplos.')
                with ui.expansion('Ecuaciones del coordinador', icon='hub', value=model.get('mode') == 'coordinator').classes('w-full') as coordinator_section:
                    coordinator_section.bind_visibility_from(basics['mode'], 'value', backward=lambda value: value == 'coordinator')
                    editors['coordinator'] = RowsEditor('Agregados del coordinador', [
                        ('name', 'Nombre del agregado', None, ''), ('expression', 'Expresión global', None, '')], model.get('coordinator', []),
                        'Solo en modo coordinador. sum_all("x"), mean_all("x"), min_all y max_all incluyen todos los agentes. El paso local recibe cada resultado como global_data["nombre"]. Filas posteriores pueden usar agregados anteriores.', 'Añadir agregado')
                with ui.expansion('Condiciones de validez', icon='rule').classes('w-full'):
                    editors['checks'] = RowsEditor('Comprobaciones del estado', [
                        ('expression', 'Condición que debe cumplirse', None, ''), ('message', 'Mensaje si no se cumple', None, '')], model.get('checks', []),
                        'Se comprueban en el estado inicial y en cada actualización. No son un criterio de óptimo. Una proyección recorta explícitamente; una condición detiene el ensayo al incumplirse.', 'Añadir condición')
            with ui.tab_panel(tabs[4]):
                step_help(4)
                editors['observations'] = RowsEditor('Mediciones por agente', [
                    ('name', 'Nombre de medición', None, ''), ('label', 'Etiqueta', None, ''), ('expression', 'Expresión a registrar', None, '')], model.get('observations', []),
                    'Todos los estados ya se registran y se pueden graficar. Añade aquí costos, fitness, normas o errores derivados que no necesitan circular entre vecinos. Aparecen como obs/nombre.', 'Añadir medición')
                ui.separator()
                editors['global_metrics'] = RowsEditor('Mediciones globales posteriores', [
                    ('name', 'Nombre de métrica', None, ''), ('label', 'Etiqueta', None, ''), ('expression', 'Expresión global escalar', None, '')], model.get('global_metrics', []),
                    'Usa sum_all, mean_all, min_all, max_all sobre expresiones locales. No entran en las ecuaciones de los agentes. En modo asíncrono solo se calculan sobre los estados terminales.', 'Añadir métrica global')
                basics['criterion'] = ui.input('Criterio final opcional (condición)', value=model.get('criterion', '')).props('outlined').classes('w-full')
                help_details('Cómo definir el criterio final', 'Puede usar métricas globales y tolerancias que hayas declarado. Su cumplimiento no demuestra por sí solo optimalidad ni estabilidad. Déjalo vacío si no has definido un criterio.')
            with ui.tab_panel(tabs[5]):
                step_help(5)
                ui.label('Comprueba las ecuaciones antes de crear el archivo').classes('section-title')
                ui.label('La vista previa usa al menos 3 agentes (uno por perfil cuando hay más), parámetros iniciales, grafo completo de pesos 1 y 3 pasos en memoria. Comprueba cálculos básicos; la ejecución TCP real se inicia después desde el formulario habitual.').classes('muted')
                output = ui.column().classes('w-full gap-3')

                async def review():
                    output.clear()
                    try:
                        current = collect()
                        source = generate_source(current)
                        with output:
                            ui.label('Expresiones válidas. Reglas que se ejecutarán:').classes('font-semibold')
                            for row in current['states']:
                                rhs = f'{row["name"]} + ({current["integration_step"]}) * ({row["update"]})' if row.get('kind') == 'euler' else row['update']
                                ui.label(f'{row["name"]} → {rhs}' + (' (algebraica)' if row.get('kind') == 'derived' else '')).classes('font-mono text-sm break-all')
                            with ui.expansion('Ver Python generado', icon='code').classes('w-full'):
                                ui.code(source, language='python').classes('w-full')
                        result = await run.io_bound(preview_model, current)
                        if result is not None:
                            with output:
                                ui.label(result['note']).classes('text-positive')
                                ui.table(columns=[dict(name=k, field=k, label=label, align='left') for k, label in
                                    [('round', 'Paso'), ('node', 'Agente'), ('profile', 'Perfil'), ('state', 'Estado calculado')]],
                                    rows=[dict(round=r['round'], node=i, profile=next((p['name'] for p in current.get('function_profiles', []) if p['id'] == result['profiles'][i]), 'Común'), state=json.dumps(value, ensure_ascii=False))
                                          for r in result['rows'] for i, value in r['states'].items()], pagination=4).classes('w-full')
                                ui.label(result['report']['conclusion']).classes('muted')
                                with ui.expansion('Ver todos los resultados de la prueba', icon='data_object').classes('w-full'):
                                    ui.code(json.dumps(result, ensure_ascii=False, indent=2), language='json').classes('w-full')
                    except Exception as exc:
                        with output:
                            ui.label(str(exc)).classes('text-negative whitespace-pre-wrap')
                        error(exc)

                def download_python():
                    try:
                        current = collect()
                        ui.download(generate_source(current).encode(), filename=current['id'] + '.py')
                    except Exception as exc:
                        error(exc)

                def create():
                    try:
                        current = collect()
                        algorithm_id = install(generate_source(current))
                        write_json(draft_path / f'{algorithm_id}.json', current)
                        editing['path'] = draft_path / f'{algorithm_id}.json'
                        editing['last'] = None
                        on_created(algorithm_id)
                        close()
                        ui.notify('Algoritmo creado. Ajusta agentes y parámetros antes de iniciar.', type='positive')
                    except Exception as exc:
                        error(exc)

                with ui.row().classes('gap-3'):
                    ui.button('Probar las ecuaciones', icon='fact_check', on_click=review).props('outline')
                    ui.button('Descargar Python', icon='download', on_click=download_python).props('flat')
                    ui.button('Crear y usar mi algoritmo', icon='check', on_click=create).props('unelevated')
        with ui.row().classes('editor-footer w-full justify-between items-center shrink-0 gap-2 border-t pt-2'):
            def position():
                return next((i for i, tab in enumerate(tabs) if steps.value in (tab, tab.props['name'])), 0)
            def move(delta):
                steps.set_value(tabs[max(0, min(len(tabs)-1, position()+delta))])
            previous = ui.button('Anterior', icon='arrow_back', on_click=lambda: move(-1)).props('flat dense no-caps').style('min-height:36px')
            progress = ui.label().classes('text-sm text-slate-500')
            following = ui.button('Continuar', icon='arrow_forward', on_click=lambda: move(1)).props('unelevated dense no-caps').style('min-height:36px')
            def navigation():
                p = position()
                previous.set_enabled(p > 0)
                following.set_visibility(p < 5)
                following.set_text('Continuar: ' + ['Datos', 'Funciones', 'Actualización', 'Gráficas', 'Probar y crear', ''][p])
                progress.set_text(f'Paso {p+1} de 6' + (' · las funciones y mediciones son opcionales' if p in (2, 4) else ''))
            steps.on_value_change(lambda _: navigation())
            navigation()
        autosave_timer = ui.timer(0.5, autosave)
        for editor in editors.values():
            editor.on_change = autosave
        for widget in list(basics.values()) + [w for editor in editors.values() for row in editor.controls for w in row.values()]:
            widget.on_value_change(lambda _: autosave())
        autosave()
    dialog.open()
