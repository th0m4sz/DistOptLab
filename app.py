"""Interfaz local del laboratorio. Ejecutar con .venv/Scripts/python app.py.

Recorrido: main crea el almacén y el gestor; setup registra la página; index
construye sus cuatro pestañas. Los botones delegan en lab/, sin resolver el
algoritmo en la interfaz. Ver docs/CONTRATO.md para empezar a leer.
"""
import argparse
import copy
import csv
import json
import math
import hashlib
import time
from pathlib import Path
import uuid

from nicegui import app, run, ui

from lab.algorithms import REGISTRY, LOAD_ERRORS, build, example, refresh_registry, topology_edges
from lab.topology import format_edges, format_matrix, parse_edges, parse_matrix
from lab.plugins import PluginSpec, install, DIRECTORY
from lab.devices import probe_all, open_ssh, check_access_all
from lab.credentials import (supported, has_password, save_password, forget_password,
                             connection_password, target as credential_target)
from lab.results import chart_series, catalog, global_catalog, evaluator_rows
from lab.monitoring import folder_revision, RefreshGate
from lab.presentation import VISUAL_CSS, help_details, section_heading
from lab.temporal_results import time_basis, timing_text
from lab.benchmark_results import COLUMNS, duration_rows, duration_csv
from lab.figure_export_ui import open_figure_export
from lab.figure_export import COLORS
from lab.runner import LocalRunner
from lab.storage import Store, read_json, write_json
from lab.designer_ui import open_designer
from lab.learning_ui import open_learning, EXAMPLE
from lab.equations import model_from_source
from lab.plotting import readable_yaxis
from lab.scenario_ui import ScenarioEditor
from lab.demand_ui import DemandEditor
from lab.faults import upgrade_scenario_config
from lab.algorithm_library import load_default, save_default, remove_algorithm, restore_algorithm

ROOT = Path(__file__).resolve().parent
refresh_registry()
ADD_ALGORITHM = '__add_python_algorithm__'  # Acción del selector; no es un algoritmo ejecutable.
STATUS = {'faulted':'Falla simulada', 'waiting_phase':'Esperando cambio de etapa', 'fault_interrupted':'Interrumpido por falla programada', 'pending': 'Pendiente', 'starting': 'Preparando', 'running': 'En ejecución',
          'stopping': 'Deteniendo', 'stopped': 'Detenido', 'completed': 'Terminado',
          'failed': 'Fallido', 'interrupted': 'Interrumpido'}
PALETTE = COLORS
CSS = '''
body {background:#f4f6f8;color:#1c3042;font-family:'Segoe UI',sans-serif}
.nicegui-content{padding:0;gap:0}.page-wrap{max-width:1320px;width:100%;margin:auto;padding:28px 32px 44px}
.q-header{background:#fff!important;color:#20384b!important;border-bottom:1px solid #e1e8ed;box-shadow:none}
.q-footer{background:#fff!important;border-top:1px solid #e1e8ed}
.brand{font-weight:700;font-size:19px;letter-spacing:-.4px}.eyebrow{font-size:11px;letter-spacing:1.8px;font-weight:700;color:#617888;text-transform:uppercase}
.hero-title{font-size:32px;line-height:1.2;font-weight:650;letter-spacing:-1px}.muted{color:#637786;font-size:14px;line-height:1.65}
.q-card{border:1px solid #e0e7ed;border-radius:14px;box-shadow:none;padding:22px}
.section-title{font-size:18px;font-weight:650}.q-tab{text-transform:none;font-size:15px;min-height:52px}
.q-tabs{background:#fff;border:1px solid #e1e8ed;border-radius:12px;padding:0 8px}.q-tab-panels,.q-tab-panel{background:transparent;padding:0}
.q-btn{text-transform:none;border-radius:8px;font-weight:600;letter-spacing:0}.q-field--outlined .q-field__control{border-radius:8px}
.algorithm-designer .q-tab{min-height:40px}.algorithm-designer .q-card{padding:16px}
.q-table th{font-weight:650;color:#576d7e;background:#f7f9fb}.q-table__container{border-radius:10px;box-shadow:none;border:1px solid #e4eaf0}
.metric-value{font-size:28px;font-weight:650;letter-spacing:-.7px}.pill{background:#eaf5f2;color:#237a68;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:600}
.note{background:#edf4f8;color:#476579;border-radius:10px;padding:12px 16px;font-size:13px;line-height:1.6}
.learning-prose{font-size:14px;line-height:1.6;overflow-wrap:anywhere;min-width:0}
.learning-prose h1{font-size:23px;line-height:1.3;margin:16px 0 12px}
.learning-prose h2{font-size:19px;line-height:1.35;font-weight:700;margin:26px 0 14px;padding:10px 14px;background:#e8f3f4;color:#155b65;border-left:4px solid #087f8c;border-radius:0 8px 8px 0}
.learning-prose h3{font-size:16px;line-height:1.4;margin:18px 0 8px}
.learning-prose p,.learning-prose ul,.learning-prose ol{margin:8px 0}
.learning-prose table{display:block;max-width:100%;overflow-x:auto;font-size:13px}
.learning-prose th,.learning-prose td{padding:7px 10px}
.learning-prose pre{max-width:100%;overflow-x:auto;font-size:13px;line-height:1.5}
.learning-prose code{font-size:13px}
.learning-prose math{font-family:'Cambria Math','STIX Two Math',math;font-size:1.1em}
.learning-prose .guide-equation{margin:16px 0;padding:8px 0;max-width:100%;overflow-x:auto}
.learning-prose math[display="block"]{margin:0}
@media(max-width:800px){.page-wrap{padding:20px 14px}.hero-title{font-size:26px}.q-card{padding:16px}}
'''
CSS += VISUAL_CSS


def display_run_name(name):
    return name


class FieldControl:
    """Traduce el editor visual al tipo declarado por el algoritmo."""
    def __init__(self, field, value):
        self.field = field
        if field.type == 'json':
            self.control = ui.textarea(field.label, value=json.dumps(value, ensure_ascii=False, indent=2)).props('outlined autogrow').classes('w-full')
        elif field.type == 'boolean':
            self.control = ui.checkbox(field.label, value=value)
        elif field.choices is not None:
            self.control = ui.select(field.choices, label=field.label, value=value).props('outlined').classes('w-full')
        elif field.type == 'string':
            self.control = ui.input(field.label, value=value).props('outlined').classes('w-full')
        else:
            self.control = ui.number(field.label, value=value, min=field.min, max=field.max,
                                     precision=0 if field.type == 'integer' else None).props('outlined').classes('w-full')

    @property
    def value(self):
        value = self.control.value
        if self.field.type == 'json':
            try:
                value = json.loads(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f'{self.field.label}: JSON inválido') from exc
        return self.field.validate(value)


def graph_svg(config):
    """Dibuja agentes y enlaces de una configuración previamente validada."""
    ids = [n['id'] for n in config['nodes']]
    n = len(ids)
    if config.get('topology') == 'estrella':
        coords = {ids[0]: (180, 140)}
        for index, i in enumerate(ids[1:]):
            angle = 2 * math.pi * index / (n - 1) - math.pi / 2
            coords[i] = (180 + 112 * math.cos(angle), 140 + 100 * math.sin(angle))
    else:
        coords = {i: (180 + 115 * math.cos(2 * math.pi * k / n - math.pi / 2),
                      140 + 100 * math.sin(2 * math.pi * k / n - math.pi / 2)) for k, i in enumerate(ids)}
    parts = ['<svg viewBox="0 0 360 280" role="img" aria-label="Topología de comunicación entre agentes" style="width:100%;max-height:290px">']
    if config.get('topology')=='coordinador':
        for x,y in coords.values():
            parts.append(f'<line x1="180" y1="140" x2="{x}" y2="{y}" stroke="#ea8c3d" stroke-width="2"/>')
        parts.append('<circle cx="180" cy="140" r="22" fill="#ea8c3d"/><text x="180" y="145" text-anchor="middle" fill="white">C</text>')
    for edge in config['edges']:
        if edge[0] in coords and edge[1] in coords:
            x1, y1 = coords[edge[0]]
            x2, y2 = coords[edge[1]]
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#bad0d9" stroke-width="2"/>')
    radius = 19 if n <= 12 else 11
    for i, (x, y) in coords.items():
        parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="#087f8c" stroke="white" stroke-width="4"/>')
        parts.append(f'<text x="{x}" y="{y + 4}" text-anchor="middle" fill="white" font-size="12" font-family="sans-serif">{i}</text>')
    return ''.join(parts) + '</svg>'


def chart_layout(label='Valor', mode='sync', traces=None):
    """Aspecto compartido de las gráficas; uirevision conserva el zoom del usuario."""
    return dict(template='plotly_white', margin=dict(l=65, r=20, t=20, b=65),
                xaxis=dict(title=dict(text='Tiempo real desde el inicio (s)' if mode=='async' else 'Iteración'), gridcolor='#edf1f4'),
                yaxis=dict(title=dict(text=label), gridcolor='#edf1f4', **readable_yaxis(traces or [])), colorway=PALETTE,
                legend=dict(orientation='v', x=.99, y=.99, xanchor='right', yanchor='top',
                            font=dict(size=10), bgcolor='white', bordercolor='black', borderwidth=.5), height=350,
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family='Segoe UI', color='#486175'), uirevision='keep')


def setup(store, runner):
    """Conecta las pantallas con un almacén y un gestor compartidos por la app."""
    @app.get('/health')
    def health():
        return {'service': 'distoptlab', 'version': '0.1', 'data': str(store.root)}

    @ui.page('/')
    def index():
        # Estas variables pertenecen a la pestaña del navegador. Recargarla
        # reconstruye el formulario, pero no cancela el gestor ni sus procesos.
        ui.add_css(CSS)
        ui.colors(primary='#087f8c', secondary='#20384b', accent='#ea8c3d', positive='#237a68')
        refresh_registry()
        draft = example(next(iter(REGISTRY))) if REGISTRY else dict(algorithm=None, nodes=[], edges=[], topology='anillo')
        if draft['algorithm']:
            try:
                preset = load_default(store.root, REGISTRY[draft['algorithm']])
                if preset is not None:
                    draft = preset
            except (ValueError, KeyError, TypeError):
                pass  # El último experimento válido aún puede recuperarse abajo.
        saved_experiment = read_json(store.root / 'ultimo_experimento.json')
        if saved_experiment and saved_experiment.get('algorithm') in REGISTRY:
            try:
                saved_experiment = upgrade_scenario_config(saved_experiment)
                build(saved_experiment)
                draft = saved_experiment
            except (ValueError, KeyError, TypeError):
                pass
        controls = {'nodes': {}, 'parameters': {}}
        selected = {'run': None, 'metric': None, 'last_record': None}
        panels = []
        monitor_gate = RefreshGate()
        history_refresh = {'at': 0.0}
        device_results = {}
        form_state = {'loading': False, 'edge_format': 'enlaces'}

        with ui.header().classes('lab-header items-center gap-3'):
            ui.icon('hub', size='23px').classes('text-primary brand-mark')
            ui.label('DistOptLab').classes('brand')
            ui.space()
            ui.label('Entorno local').classes('header-context')
        with ui.column().classes('page-wrap gap-6'):
            with ui.row().classes('w-full items-end justify-between gap-4'):
                with ui.column().classes('gap-2'):
                    ui.label('Laboratorio de algoritmos').classes('eyebrow')
                    ui.label('Experimentos distribuidos').classes('hero-title').props('role=heading aria-level=1')
                ui.label('Diseña, ejecuta y compara').classes('muted')
            with ui.tabs().classes('w-full main-tabs') as tabs:
                new_tab = ui.tab('Nuevo experimento', icon='add_circle_outline')
                devices_tab = ui.tab('Dispositivos', icon='developer_board')
                monitor_tab = ui.tab('Ejecución', icon='monitoring')
                history_tab = ui.tab('Resultados', icon='folder_open')

            def notify_error(exc):
                ui.notify(str(exc), type='negative', timeout=7000, close_button=True)

            def gather(validate=True):
                """Convierte el formulario en una configuración y valida antes de ejecutar."""
                if not draft['algorithm']:
                    raise ValueError('Carga primero tu algoritmo Python')
                config = copy.deepcopy(draft)
                config['name'] = controls['name'].value.strip()
                raw_steps = controls['steps'].value
                if raw_steps is None or int(raw_steps) != raw_steps:
                    raise ValueError('Las iteraciones deben ser un entero')
                config['steps'] = int(raw_steps)
                config['period_s'] = controls['period'].value
                config['execution_mode'] = 'coordinator' if REGISTRY[config['algorithm']].mode == 'coordinator' else controls['mode'].value
                if config['execution_mode'] == 'coordinator':
                    config['coordinator_exchange'] = controls['mode'].value
                else:
                    config.pop('coordinator_exchange',None)
                config['execution_target'] = controls['target'].value
                scenario = controls['faults'].value()
                if scenario:
                    config['faults'] = scenario
                else:
                    config.pop('faults',None)
                for node in config['nodes']:
                    node['device_id'] = controls['assignments'][node['id']].value
                config['parameters'].update({key: field.value for key, field in controls['parameters'].items()})
                demand = controls['demand_schedule'].value()
                if demand:
                    config['demand_schedule'] = demand
                else:
                    config.pop('demand_schedule', None)
                for node in config['nodes']:
                    node['params'].update({key: field.value for key, field in controls['nodes'][node['id']].items()})
                    if node['id'] in controls.get('profiles', {}):
                        node['function_profile'] = controls['profiles'][node['id']].value
                if REGISTRY[config['algorithm']].mode == 'coordinator':
                    edges = []
                else:
                    edges = (parse_matrix(controls['matrix'].value, [node['id'] for node in config['nodes']])
                             if form_state['edge_format'] == 'matriz' else parse_edges(controls['edges'].value))
                if edges != config['edges']:
                    config['topology'] = 'personalizada'
                config['edges'] = edges
                if validate:
                    build(config)
                return config

            def start():
                """Solicita el arranque al gestor y abre la pantalla de seguimiento."""
                try:
                    config = gather()
                    if config['execution_target'] == 'remote':
                        remote_dialog(config)
                        return
                    run_id = runner.start(config)
                    select_run(run_id)
                    tabs.set_value(monitor_tab)
                    ui.notify('Experimento iniciado: un proceso TCP por agente.', type='positive')
                except Exception as exc:
                    notify_error(exc)

            def remote_dialog(config):
                devices = {d['id']: d for d in store.devices()}
                assignments = {n['id']: devices.get(n.get('device_id')) for n in config['nodes']}
                if any(d is None for d in assignments.values()):
                    raise ValueError('Asigna una placa registrada a cada agente')
                if len({d['id'] for d in assignments.values()}) != len(assignments):
                    raise ValueError('Selecciona una placa diferente para cada agente')
                with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl gap-3'):
                    ui.label('Conectar y ejecutar en Raspberry Pi').classes('section-title')
                    ui.label('Se enviarán el motor, el algoritmo y los datos propios de cada agente. Puedes usar las contraseñas guardadas en Dispositivos.').classes('muted')
                    credentials = {}
                    for i, device in assignments.items():
                        ui.label(f'Agente {i}: {device["name"]} · {device["user"]}@{device["host"]}')
                        password = ui.input(f'Contraseña SSH · agente {i}', password=True, password_toggle_button=True).props('outlined').classes('w-full')
                        saved_password = has_password(device)
                        use_saved = ui.checkbox(f'Usar contraseña guardada · agente {i}', value=saved_password)
                        use_saved.set_visibility(saved_password)
                        password.bind_visibility_from(use_saved, 'value', backward=lambda saved: not saved)
                        credentials[i] = (password, use_saved)
                    detail = ui.label().classes('text-sm text-slate-600')
                    def clear():
                        for password, use_saved in credentials.values():
                            password.set_value('')
                    async def deploy():
                        button.disable()
                        clients = {}
                        try:
                            for i, device in assignments.items():
                                detail.set_text(f'Autenticando agente {i}…')
                                password, use_saved = credentials[i]
                                def connect_device(device=device, entered=password.value, saved=use_saved.value):
                                    secret = connection_password(device, '' if saved else entered, saved)
                                    if not secret:
                                        raise ValueError(f'{device["name"]}: introduce su contraseña o guárdala en Dispositivos.')
                                    return open_ssh(device, store.root/'known_hosts', secret, accept_new=True)
                                clients[i] = await run.io_bound(connect_device)
                                password.set_value('')
                            detail.set_text('Comprobando Python y preparando el ensayo…')
                            run_id = await run.io_bound(runner.start_remote, config, assignments, clients)
                            clients = {}  # El gestor toma propiedad y cerrará las sesiones.
                            dialog.close()
                            select_run(run_id)
                            tabs.set_value(monitor_tab)
                            ui.notify('Despliegue iniciado. Los agentes se comunicarán directamente entre placas.', type='positive')
                        except Exception as exc:
                            detail.set_text(str(exc))
                        finally:
                            clear()
                            for client in clients.values():
                                client.close()
                            button.enable()
                    button = ui.button('Conectar y ejecutar', icon='play_arrow', on_click=deploy).props('unelevated')
                    ui.button('Cancelar', on_click=lambda: (clear(), dialog.close())).props('flat')
                dialog.on('hide', clear)
                dialog.open()

            def save_config():
                """Guarda parámetros reproducibles y ofrece descargar el mismo JSON."""
                try:
                    config = gather()
                    path = store.root / 'configuraciones' / f'config_{uuid.uuid4().hex[:10]}.json'
                    write_json(path, config)
                    ui.download.file(path, filename='configuracion_experimento.json')
                    ui.notify('Configuración guardada en la laptop.', type='positive')
                except Exception as exc:
                    notify_error(exc)

            async def import_config(event):
                """Valida el JSON recibido antes de incorporarlo al formulario."""
                try:
                    text = await event.file.text()
                    config = upgrade_scenario_config(json.loads(text))
                    build(config)
                    load_draft(config)
                    ui.notify('Configuración cargada. Puedes revisarla antes de ejecutar.', type='positive')
                except Exception as exc:
                    notify_error(exc)

            async def import_algorithm(event):
                """Instala un archivo nuevo. Su descripción se comprueba con AST, sin ejecutarlo."""
                try:
                    source=await event.file.text()
                    algorithm_id=install(source)
                    refresh_registry()
                    # La descripción genera el formulario sin importar el código.
                    algorithm_select.set_options(algorithm_options())
                    topology='anillo' if topology_select.value=='coordinador' else topology_select.value
                    load_draft(example(algorithm_id,int(count_input.value),topology))
                    ui.notify('Algoritmo añadido. Revisa sus parámetros y ejecuta un ensayo.',type='positive')
                    return True
                except Exception as exc:
                    notify_error(exc)
                    return False

            def save_algorithm_example():
                try:
                    save_default(store.root, gather())
                    ui.notify('Ejemplo predeterminado guardado: cantidad, datos de cada agente, perfiles, comunicación y conexiones.', type='positive')
                except Exception as exc:
                    notify_error(exc)

            def load_algorithm_example():
                try:
                    spec = REGISTRY[draft['algorithm']]
                    preset = load_default(store.root, spec)
                    if preset is None:
                        ui.notify('Este algoritmo aún no tiene un ejemplo guardado. Ajusta sus datos y pulsa Guardar como ejemplo predeterminado.', type='info')
                        return
                    load_draft(preset)
                except Exception as exc:
                    notify_error(exc)

            def delete_algorithm():
                try:
                    if runner.active:
                        raise ValueError('Espera a que termine el experimento o deténlo antes de retirar un algoritmo')
                    spec = REGISTRY.get(draft['algorithm'])
                    if spec is None:
                        raise ValueError('Selecciona el algoritmo que quieres retirar del menú')
                    remove_algorithm(store.root, spec)
                    refresh_registry()
                    form_state['loading'] = True
                    try:
                        algorithm_select.set_options(algorithm_options(), value=None)
                    finally:
                        form_state['loading'] = False
                    if REGISTRY:
                        next_id = next(iter(REGISTRY))
                        preset = load_default(store.root, REGISTRY[next_id])
                        load_draft(preset if preset is not None else example(next_id, int(count_input.value), 'anillo'))
                    else:
                        draft.clear()
                        draft.update(algorithm=None, nodes=[], edges=[], topology='anillo')
                        settings.refresh()
                        connections.refresh()
                        preview.refresh()
                        write_json(store.root / 'ultimo_experimento.json', None)
                    ui.notify(f'{spec.name}: retirado del menú. Sus ensayos se conservan; puedes recuperarlo con Recuperar algoritmo eliminado.', type='positive', timeout=9000)
                except Exception as exc:
                    notify_error(exc)

            def recover_algorithm():
                options = {}
                for path in (store.root / 'algoritmos_eliminados').glob('*/retirada.json'):
                    try:
                        row = read_json(path)
                        source = path.parent / row['filename']
                        if source.is_file():
                            options[str(path.parent)] = PluginSpec(source).name + ' · ' + path.parent.name[:8]
                    except (OSError, ValueError, KeyError):
                        continue
                if not options:
                    ui.notify('No hay algoritmos retirados para recuperar.', type='info')
                    return
                with ui.dialog() as dialog, ui.card().classes('w-full').style('max-width:700px'):
                    ui.label('Recuperar algoritmo eliminado').classes('section-title')
                    choice = ui.select(options, label='Algoritmo retirado').props('outlined').classes('w-full')
                    def recover():
                        try:
                            if not choice.value:
                                raise ValueError('Selecciona un algoritmo retirado')
                            algorithm_id = restore_algorithm(store.root, choice.value)
                            refresh_registry()
                            algorithm_select.set_options(algorithm_options())
                            preset = load_default(store.root, REGISTRY[algorithm_id])
                            load_draft(preset if preset is not None else example(algorithm_id, int(count_input.value), 'anillo'))
                            dialog.close()
                            ui.notify('Algoritmo y ejemplo predeterminado recuperados.', type='positive')
                        except Exception as exc:
                            notify_error(exc)
                    ui.button('Recuperar', on_click=recover).props('unelevated')
                    ui.button('Cerrar', on_click=dialog.close).props('flat')
                dialog.open()

            def change_execution_mode(event):
                if form_state['loading'] or event.value is None:
                    return
                draft['execution_mode'] = 'coordinator' if REGISTRY[draft['algorithm']].mode == 'coordinator' else event.value
                if draft['execution_mode'] == 'coordinator':
                    draft['coordinator_exchange'] = event.value
                else:
                    draft.pop('coordinator_exchange',None)
                preview.refresh()

            def algorithm_options():
                """Muestra la acción de cargar código al final del menú de algoritmos."""
                return {**{key: spec.name for key, spec in REGISTRY.items()},
                        ADD_ALGORITHM: '＋ Añadir algoritmo Python…'}

            def designer_created(algorithm_id):
                refresh_registry()
                algorithm_select.set_options(algorithm_options())
                topology = topology_select.value if topology_select.value != 'coordinador' else 'anillo'
                load_draft(example(algorithm_id, int(count_input.value), topology))

            def design_algorithm(edit=False):
                try:
                    model = None
                    if edit:
                        if draft['algorithm'] not in REGISTRY:
                            raise ValueError('Selecciona primero un algoritmo generado con el asistente')
                        model = model_from_source(REGISTRY[draft['algorithm']].path.read_text(encoding='utf-8-sig'))
                    open_designer(store, designer_created, model)
                except Exception as exc:
                    notify_error(exc)

            def learning():
                def load_example(profiles=False):
                    try:
                        from lab.plugins import PluginSpec
                        folder = EXAMPLE.parent / 'perfiles' if profiles else EXAMPLE
                        source_path = folder / ('tutorial_perfiles.py' if profiles else 'tutorial_gradiente.py')
                        supplied = PluginSpec(source_path)
                        refresh_registry()
                        if supplied.id not in REGISTRY:
                            install(source_path.read_text(encoding='utf-8'))
                            refresh_registry()
                        if REGISTRY[supplied.id].sha256 != supplied.sha256:
                            raise ValueError('El identificador del tutorial pertenece a otra versión. Conserva ese archivo con otro identificador antes de cargar este ejemplo.')
                        config = read_json(folder / 'configuracion.json')
                        build(config)
                        algorithm_select.set_options(algorithm_options())
                        load_draft(config)
                        ui.notify(('Ejemplo cargado: 4 agentes, dos perfiles y red completa. Revisa la asignación de cada agente.' if profiles else 'Ejemplo cargado: 3 agentes, red completa y centros 1, 3 y 5. Revisa los datos y pulsa Iniciar experimento local.'), type='positive', timeout=9000)
                        return True
                    except Exception as exc:
                        notify_error(exc)
                        return False
                open_learning(load_example, lambda: open_designer(store, designer_created, read_json(EXAMPLE / 'modelo.json')),
                              lambda: load_example(True),
                              lambda: open_designer(store, designer_created, read_json(EXAMPLE.parent / 'perfiles' / 'modelo.json')))

            def show_algorithm_dialog():
                with ui.dialog() as dialog, ui.card().classes('w-full max-w-xl gap-4'):
                    ui.label('Añadir algoritmo Python').classes('section-title')
                    ui.label('Carga un archivo .py que defina sus parámetros, estado y ecuaciones. '
                             'Puede comunicarse con vecinos o usar un coordinador.').classes('muted')
                    ui.label('El código se ejecuta con los permisos de tu usuario. Carga archivos propios o de confianza.').classes('text-xs text-slate-500')

                    async def upload_and_close(event):
                        if await import_algorithm(event):
                            dialog.close()

                    ui.upload(label='Cargar archivo .py', auto_upload=True,
                              max_file_size=1_000_000, on_upload=upload_and_close).props('accept=.py').classes('w-full')
                    with ui.row().classes('gap-2 flex-wrap'):
                        ui.button('Descargar plantilla comentada', icon='download',
                                  on_click=lambda: ui.download.file(ROOT/'plantillas'/'algoritmo_vacio.py', filename='mi_algoritmo.py')).props('flat')
                        ui.button('Descargar código del algoritmo actual', icon='download',
                                  on_click=lambda: ui.download.file(REGISTRY[draft['algorithm']].path)
                                  if draft['algorithm'] in REGISTRY
                                  else ui.notify('Carga primero un algoritmo.')).props('flat')
                        ui.button('Cerrar', on_click=dialog.close).props('flat')
                dialog.open()

            def load_draft(config, *, refresh=True):
                """Sustituye el borrador y reconstruye los campos específicos del algoritmo."""
                old_scenario = isinstance(config.get('faults'),dict) and bool(config['faults']) and config['faults'].get('version',1)==1
                config = upgrade_scenario_config(config)
                if config.get('algorithm') not in REGISTRY:
                    raise ValueError('Carga el archivo de este algoritmo antes de abrir su configuración')
                config.setdefault('execution_mode', REGISTRY[config['algorithm']].mode)
                draft.clear()
                draft.update(config)
                form_state['loading'] = True
                try:
                    algorithm_select.set_value(config['algorithm'])
                    count_input.set_value(len(config['nodes']))
                    coordinated=REGISTRY[config['algorithm']].mode=='coordinator'
                    choices={'coordinador':'Agentes conectados al coordinador'} if coordinated else {'anillo':'Anillo','estrella':'Estrella','completa':'Completa','personalizada':'Personalizada'}
                    topology_select.set_options(choices,value='coordinador' if coordinated else config.get('topology') if config.get('topology') in choices else 'personalizada')
                    topology_select.set_enabled(not coordinated)
                    topology_hint.set_visibility(not coordinated)
                finally:
                    form_state['loading'] = False
                if refresh:
                    settings.refresh()
                    connections.refresh()
                    preview.refresh()
                if old_scenario:
                    ui.notify('Configuración de fallas actualizada: los no disponibles se excluyen siempre; '
                              'las condiciones iniciales se aplican solo a quienes regresan. '
                              'El ensayo histórico conserva sus registros.',timeout=9000,close_button=True)

            async def load_fault_example():
                """Carga y muestra el escenario; informa también si no pudo abrirse."""
                try:
                    config = read_json(ROOT/'ejemplos/fallas/consenso_con_fallas.json')
                    if not config:
                        raise ValueError('No se encontró el ejemplo de fallas')
                    build(config)
                    load_draft(config, refresh=False)
                    # Esperar la reconstrucción evita enfocar el editor anterior,
                    # que NiceGUI acaba de eliminar durante el refresco.
                    await settings.refresh()
                    await connections.refresh()
                    await preview.refresh()
                    editor = controls['faults']
                    editor.expansion.open()
                    ui.notify('Ejemplo cargado: 4 agentes, 600 iteraciones. '
                              'El agente 4 falla en el índice 200 y regresa en el 400. '
                              'Revisa los campos y pulsa Iniciar experimento.',
                              type='positive', timeout=9000, close_button=True)
                    await ui.run_javascript(
                        f'document.getElementById("c{editor.expansion.id}")'
                        '?.scrollIntoView({block:"start", behavior:"smooth"})')
                except Exception as exc:
                    notify_error(exc)

            def remember_fields():
                """Conserva las ediciones visibles antes de reconstruir agentes."""
                if not draft['algorithm']:
                    return
                draft['name'] = controls['name'].value
                draft['steps'] = controls['steps'].value
                draft['period_s'] = controls['period'].value
                draft['execution_mode'] = 'coordinator' if REGISTRY[draft['algorithm']].mode == 'coordinator' else controls['mode'].value
                if draft['execution_mode'] == 'coordinator':
                    draft['coordinator_exchange'] = controls['mode'].value
                else:
                    draft.pop('coordinator_exchange',None)
                draft['execution_target'] = controls['target'].value
                scenario = controls['faults'].value()
                if scenario:
                    draft['faults'] = scenario
                else:
                    draft.pop('faults',None)
                for node in draft['nodes']:
                    node['device_id'] = controls['assignments'][node['id']].value
                draft['parameters'].update({key: field.value for key, field in controls['parameters'].items()})
                demand = controls['demand_schedule'].value()
                if demand:
                    draft['demand_schedule'] = demand
                else:
                    draft.pop('demand_schedule', None)
                for node in draft['nodes']:
                    node['params'].update({key: field.value for key, field in controls['nodes'][node['id']].items()})
                    if node['id'] in controls.get('profiles', {}):
                        node['function_profile'] = controls['profiles'][node['id']].value

            def change_algorithm(event):
                if form_state['loading'] or event.value == draft['algorithm']:
                    return
                if event.value == ADD_ALGORITHM:
                    # La acción abre una ventana, pero el selector sigue mostrando
                    # el algoritmo que está configurado hasta cargar otro archivo.
                    form_state['loading'] = True
                    try:
                        algorithm_select.set_value(draft['algorithm'])
                    finally:
                        form_state['loading'] = False
                    show_algorithm_dialog()
                    return
                try:
                    n = int(count_input.value)
                    topology = topology_select.value
                    if topology == 'coordinador':
                        topology = 'anillo'
                    preset = load_default(store.root, REGISTRY[event.value])
                    load_draft(preset if preset is not None else example(event.value, n, topology))
                except Exception as exc:
                    notify_error(exc)

            def change_count(event):
                if not draft['algorithm'] or form_state['loading'] or event.value is None or event.value == len(draft['nodes']):
                    return
                try:
                    n = int(event.value)
                    if n != event.value or n < 1:
                        raise ValueError('El número de agentes debe ser un entero positivo')
                    remember_fields()
                    old_nodes = copy.deepcopy(draft['nodes'])
                    nodes = old_nodes[:n]
                    if n > len(nodes):
                        sample = example(draft['algorithm'], n, 'anillo')
                        existing_ids = {node['id'] for node in nodes}
                        next_id = max(existing_ids, default=0) + 1
                        for source in sample['nodes'][len(nodes):]:
                            node = copy.deepcopy(source)
                            node['id'] = next_id
                            node['port'] = 15000 + next_id
                            nodes.append(node)
                            next_id += 1
                    draft['nodes'] = nodes
                    ids = [node['id'] for node in nodes]
                    if REGISTRY[draft['algorithm']].mode == 'coordinator':
                        draft['edges'] = []
                    elif topology_select.value != 'personalizada':
                        draft['edges'] = topology_edges(ids, topology_select.value)
                    else:
                        # Mantener enlaces editados y conectar los componentes que
                        # queden al añadir o retirar agentes.
                        previous = parse_edges(controls['edges'].value) if form_state['edge_format'] == 'enlaces' else parse_matrix(controls['matrix'].value, [node['id'] for node in old_nodes])
                        draft['edges'] = [edge for edge in previous if edge[0] in ids and edge[1] in ids]
                        groups = {i: i for i in ids}

                        def root(i):
                            while groups[i] != i:
                                i = groups[i]
                            return i

                        for i, j, *_ in draft['edges']:
                            groups[root(j)] = root(i)
                        for i, j in zip(ids, ids[1:]):
                            if root(i) != root(j):
                                draft['edges'].append([i, j])
                                groups[root(j)] = root(i)
                    settings.refresh()
                    connections.refresh()
                    preview.refresh()
                except Exception as exc:
                    notify_error(exc)

            def change_topology(event):
                if not draft['algorithm'] or form_state['loading'] or event.value is None or event.value == draft.get('topology'):
                    return
                if not draft['algorithm'] or REGISTRY[draft['algorithm']].mode == 'coordinator':
                    return
                ids = [node['id'] for node in draft['nodes']]
                draft['topology'] = event.value
                draft['edges'] = topology_edges(ids, event.value)
                connections.refresh()
                preview.refresh()

            @ui.refreshable
            def preview():
                if not draft['algorithm']:
                    with ui.card().classes('w-full gap-3'):
                        ui.icon('extension', size='36px').classes('text-primary')
                        ui.label('Tu metodología, tus variables').classes('section-title')
                        ui.label('Carga tu archivo para definir parámetros, estados y cálculos. La plataforma se ocupa de comunicar y registrar.').classes('muted')
                    return
                spec = REGISTRY[draft['algorithm']]
                with ui.card().classes('w-full gap-3'):
                    ui.label('Comunicación entre agentes').classes('section-title')
                    ui.html(graph_svg(draft), sanitize=False).classes('w-full')
                    with ui.row().classes('w-full justify-around'):
                        for value, label in [(len(draft['nodes']), 'agentes'), (len(draft['nodes']) if spec.mode=='coordinator' else len(draft['edges']), 'enlaces')]:
                            with ui.column().classes('items-center gap-0'):
                                ui.label(str(value)).classes('metric-value')
                                ui.label(label).classes('muted')
                    ui.separator().classes('my-2')
                    ui.label('TCP entre Raspberry Pi' if draft.get('execution_target') == 'remote' else 'Modo local con TCP').classes('font-semibold')
                    ui.label({'sync':'Cada agente es un proceso independiente. Espera los estados de la misma ronda de sus vecinos.',
                              'async':'Cada agente es un proceso independiente. Calcula usando las últimas muestras, sin esperar una ronda común.',
                              'coordinator':('C conserva las últimas muestras de los participantes y responde sin reunir rondas.' if draft.get('coordinator_exchange')=='async' else 'C es un proceso coordinador del algoritmo. Reúne estados de la misma ronda y devuelve el agregado.')}[draft.get('execution_mode', spec.mode)]).classes('muted')
                with ui.card().classes('w-full gap-2 mt-4'):
                    ui.icon('science', size='24px').classes('text-primary')
                    ui.label('Algoritmo cargado').classes('font-semibold')
                    ui.label(spec.description).classes('muted')
                    ui.label(draft.get('source', 'Configuración importada por el usuario.')).classes('text-xs text-slate-500')

            @ui.refreshable
            def connections():
                """Ofrece dos editores del mismo grafo, guardado siempre como edges."""
                if not draft['algorithm'] or REGISTRY[draft['algorithm']].mode == 'coordinator':
                    return
                with ui.expansion('Editar conexiones', icon='share', value=draft.get('topology') == 'personalizada').classes('w-full'):
                    ui.label('Los enlaces son bidireccionales. Un peso multiplica la influencia matemática; '
                             'no representa costo ni tiempo de comunicación.').classes('muted')
                    edge_format = ui.select({'enlaces': 'Lista de enlaces', 'matriz': 'Matriz de adyacencia'},
                                            label='Forma de edición', value=form_state['edge_format']).props('outlined dense').classes('w-full')
                    ids = [node['id'] for node in draft['nodes']]
                    matrix_order = ui.label('Orden de filas y columnas: ' + ', '.join(f'agente {i}' for i in ids)).classes('text-xs text-slate-500')
                    controls['edges'] = ui.textarea('Enlaces: origen,destino[,peso]', value=format_edges(draft['edges'])).props('outlined').classes('w-full')
                    controls['matrix'] = ui.textarea('Matriz de adyacencia', value=format_matrix(ids, draft['edges'])).props('outlined').classes('w-full')
                    controls['edges'].set_visibility(form_state['edge_format'] == 'enlaces')
                    controls['matrix'].set_visibility(form_state['edge_format'] == 'matriz')
                    matrix_help = ui.label('En la matriz, 0 significa sin enlace y un valor positivo es el peso. '
                                           'La diagonal debe ser 0 y la matriz simétrica. Puedes separar filas con Enter o “;”, como en MATLAB.').classes('text-xs text-slate-500')
                    matrix_order.set_visibility(form_state['edge_format'] == 'matriz')
                    matrix_help.set_visibility(form_state['edge_format'] == 'matriz')

                    def change_format(event):
                        previous = form_state['edge_format']
                        if event.value == previous:
                            return
                        try:
                            edges = (parse_matrix(controls['matrix'].value, ids) if previous == 'matriz'
                                     else parse_edges(controls['edges'].value))
                            if edges != draft['edges']:
                                draft['topology'] = 'personalizada'
                                form_state['loading'] = True
                                try:
                                    topology_select.set_value('personalizada')
                                finally:
                                    form_state['loading'] = False
                            draft['edges'] = edges
                            if event.value == 'matriz':
                                controls['matrix'].set_value(format_matrix(ids, edges))
                            else:
                                controls['edges'].set_value(format_edges(edges))
                            form_state['edge_format'] = event.value
                            controls['edges'].set_visibility(event.value == 'enlaces')
                            controls['matrix'].set_visibility(event.value == 'matriz')
                            matrix_order.set_visibility(event.value == 'matriz')
                            matrix_help.set_visibility(event.value == 'matriz')
                            preview.refresh()
                        except Exception as exc:
                            notify_error(exc)
                            edge_format.set_value(previous)

                    edge_format.on_value_change(change_format)

                    def check_edges():
                        try:
                            config = gather()
                            draft['edges'], draft['topology'] = config['edges'], config['topology']
                            controls['edges'].set_value(format_edges(config['edges']))
                            controls['matrix'].set_value(format_matrix(ids, config['edges']))
                            if config['topology'] != topology_select.value:
                                form_state['loading'] = True
                                try:
                                    topology_select.set_value('personalizada')
                                finally:
                                    form_state['loading'] = False
                            preview.refresh()
                            ui.notify('Conexiones válidas; dibujo actualizado.', type='positive')
                        except Exception as exc:
                            notify_error(exc)

                    ui.button('Validar y actualizar dibujo', on_click=check_edges).props('flat')

            @ui.refreshable
            def settings():
                # fields y parameters pertenecen al adaptador del algoritmo.
                # Por eso otro algoritmo puede generar su formulario automáticamente.
                if not draft['algorithm']:
                    with ui.card().classes('w-full gap-4'):
                        ui.label('No hay algoritmos cargados').classes('section-title')
                        ui.label('Selecciona “Añadir algoritmo Python…” en el menú Algoritmo para cargar tu archivo o descargar una plantilla vacía.').classes('muted')
                        ui.button('Diseñar algoritmo paso a paso', icon='edit_note', on_click=lambda: design_algorithm()).props('outline')
                        for filename, error in LOAD_ERRORS.items():
                            ui.label(f'{filename}: {error}').classes('text-negative')
                    return
                spec = REGISTRY[draft['algorithm']]
                controls['nodes'], controls['parameters'], controls['profiles'] = {}, {}, {}
                with ui.card().classes('w-full gap-4'):
                    section_heading(2, 'Configura el experimento')
                    controls['name'] = ui.input('Nombre del experimento', value=draft['name']).props('outlined').classes('w-full')
                    ui.label('Ejecución').classes('field-group-label')
                    with ui.row().classes('w-full gap-4'):
                        controls['steps'] = ui.number('Iteraciones', value=draft['steps'], min=1, precision=0).props('outlined').classes('flex-1')
                        controls['period'] = ui.number('Intervalo mínimo entre actualizaciones (s)', value=draft['period_s'], min=0, step=.001).props('outlined').classes('flex-1')
                    help_details('Iteraciones, espera y paso numérico',
                             'Las iteraciones indican cuántas veces ejecuta cada agente su ecuación, no una duración. '
                             'El intervalo mínimo es el tiempo real desde el inicio de una actualización hasta el inicio de la siguiente. '
                             'Si el cálculo y la comunicación terminan antes, el agente espera el tiempo restante. '
                             'Si tardan más, continúa cuando puede. Con 0 no añade una pausa voluntaria. '
                             'Este valor no cambia el paso numérico h o α.')
                    controls['target'] = ui.select({'local':'Laptop (procesos locales)', 'remote':'Raspberry Pi (SSH y TCP)'},
                        label='Dónde ejecutar', value=draft.get('execution_target','local'), on_change=lambda e: (draft.update(execution_target=e.value), preview.refresh())).props('outlined').classes('w-full')
                    ui.label('Asigna una placa distinta a cada agente.').bind_visibility_from(controls['target'],'value',backward=lambda v:v=='remote').classes('muted')
                    controls['assignments'] = {}
                    device_options = {d['id']:f'{d["name"]} · {d["host"]}' for d in store.devices()}
                    for node in draft['nodes']:
                        controls['assignments'][node['id']] = ui.select(device_options,label=f'Placa del agente {node["id"]}',
                            value=node.get('device_id') if node.get('device_id') in device_options else None).props('outlined').classes('w-full').bind_visibility_from(controls['target'],'value',backward=lambda v:v=='remote')
                    controls['mode'] = ui.select(
                        {'sync': 'Coordinador · síncrono (misma ronda)', 'async': 'Coordinador · asíncrono (últimas muestras)'} if spec.mode == 'coordinator' else
                        {'sync': 'Misma ronda (síncrono)', 'async': 'Últimas muestras de vecinos (asíncrono)'},
                        label='Comunicación de este experimento', value=(draft.get('coordinator_exchange','sync') if spec.mode == 'coordinator' else draft.get('execution_mode', spec.mode)),
                        on_change=change_execution_mode).props('outlined').classes('w-full')
                    ui.label().bind_text_from(controls['mode'], 'value', backward=lambda mode: {
                        'sync': ('El coordinador reúne los estados de la misma ronda antes de responder.' if spec.mode=='coordinator' else 'Cada agente espera los estados de la misma ronda de sus vecinos.'),
                        'async': ('Tras recibir una primera muestra de cada participante, responde con las últimas disponibles sin reunir rondas.' if spec.mode=='coordinator' else 'Cada agente usa las últimas muestras recibidas de sus vecinos, aunque sean de índices anteriores.'),
                                            }[mode]).classes('text-xs text-slate-500')
                    # La explicación del dominio pertenece al adaptador: otros algoritmos
                    # no tienen por qué usar costos ni siquiera representar generadores.
                    ui.label('Parámetros del algoritmo').classes('field-group-label')
                    if spec.parameter_help:
                        help_details('Cómo interpretar estos parámetros', spec.parameter_help)
                    with ui.row().classes('w-full gap-3'):
                        for field in spec.parameters:
                            controls['parameters'][field.key] = FieldControl(field, draft['parameters'][field.key])
                    controls['demand_schedule'] = DemandEditor(spec, draft)
                    controls['faults'] = ScenarioEditor(draft)
                    with ui.expansion('Parámetros de cada agente', icon='tune', value=True).classes('w-full'):
                        ui.label('Puedes editar los valores antes de iniciar.').classes('muted mb-3')
                        if spec.function_profiles:
                            ui.label('Agentes nuevos: perfil ' + spec.function_profiles[spec.default_profile] + '. Puedes cambiarlo individualmente abajo.').classes('note w-full')
                        for node in draft['nodes']:
                            with ui.card().classes('agent-card w-full gap-3 mb-3'):
                                ui.label(f'Agente {node["id"]}').classes('font-semibold')
                                if spec.function_profiles:
                                    controls['profiles'][node['id']] = ui.select(spec.function_profiles,
                                        label=f'Perfil de funciones · agente {node["id"]}',
                                        value=node.get('function_profile', spec.default_profile)).props('outlined').classes('w-full')
                                # Una cuadrícula permite leer etiquetas largas y se adapta
                                # al ancho de la ventana sin recortar el texto flotante.
                                with ui.element('div').classes('w-full grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3'):
                                    fields = {}
                                    for field in spec.fields:
                                        fields[field.key] = FieldControl(field, node['params'][field.key])
                                controls['nodes'][node['id']] = fields
                    with ui.row().classes('actions-strip w-full gap-3 items-center'):
                        ui.button('Iniciar experimento', icon='play_arrow', on_click=start).props('unelevated').classes('px-5 py-2')
                        ui.button('Guardar configuración', icon='download', on_click=save_config).props('outline')
                    with ui.expansion('Ejemplo predeterminado', icon='bookmark_border').classes('w-full'):
                        ui.label('Conserva parámetros, perfiles y valores por agente para volver a usarlos. Los agentes adicionales reciben los valores iniciales del archivo.').classes('muted')
                        with ui.row().classes('w-full gap-3'):
                            ui.button('Guardar como ejemplo predeterminado', icon='bookmark_add', on_click=save_algorithm_example).props('outline')
                            ui.button('Cargar ejemplo predeterminado', icon='bookmark', on_click=load_algorithm_example).props('flat')

            with ui.tab_panels(tabs, value=new_tab).classes('w-full'):
                with ui.tab_panel(new_tab):
                    with ui.card().classes('guide-banner w-full mb-5'):
                        with ui.row().classes('w-full items-center gap-4'):
                            ui.icon('auto_stories', size='24px').classes('guide-icon')
                            with ui.column().classes('gap-1 flex-1'):
                                ui.label('Guía y ejemplos').classes('section-title')
                                ui.label('Un recorrido con ecuaciones explicadas para empezar.').classes('muted')
                            with ui.row().classes('gap-2 flex-wrap'):
                                ui.button('Ver ejemplo guiado', icon='school', on_click=learning).props('unelevated')
                                ui.button('Cargar ejemplo de fallas', icon='warning_amber', on_click=load_fault_example).props('flat')
                    with ui.element('div').classes('experiment-layout'):
                        with ui.column().classes('experiment-main gap-5'):
                            with ui.card().classes('w-full gap-4'):
                                section_heading(1, 'Selecciona tu algoritmo')
                                algorithm_select = ui.select(algorithm_options(), label='Algoritmo', value=draft['algorithm'], on_change=change_algorithm).props('outlined').classes('w-full')
                                with ui.row().classes('gap-2'):
                                    ui.button('Diseñar algoritmo paso a paso', icon='edit_note', on_click=lambda: design_algorithm()).props('unelevated')
                                    ui.button('Editar diseño seleccionado', icon='edit', on_click=lambda: design_algorithm(True)).props('flat')
                                with ui.expansion('Administrar algoritmos', icon='inventory_2').classes('w-full'):
                                    with ui.row().classes('w-full gap-2'):
                                        ui.button('Eliminar algoritmo del menú', icon='delete_outline', on_click=delete_algorithm).props('flat color=negative')
                                        ui.button('Recuperar algoritmo eliminado', icon='restore', on_click=recover_algorithm).props('flat')
                                with ui.row().classes('w-full gap-3 items-center'):
                                    count_input = ui.number('Número de agentes', value=len(draft['nodes']) or 4, min=1, precision=0, on_change=change_count).props('outlined').classes('flex-1')
                                    topology_select = ui.select({'anillo': 'Anillo', 'estrella': 'Estrella', 'completa': 'Completa',
                                                                 'personalizada': 'Personalizada'}, label='Topología', value='anillo', on_change=change_topology).props('outlined').classes('flex-1')
                                topology_hint=ui.label('Personaliza los enlaces en «Editar conexiones». Los agentes existentes conservan sus datos al cambiar la cantidad.').classes('muted')
                                connections()
                                with ui.expansion('Abrir una configuración guardada', icon='upload_file').classes('w-full'):
                                    ui.label('Archivo JSON exportado con “Guardar configuración”. Define parámetros y enlaces '
                                             'de un algoritmo instalado; no incorpora código nuevo.').classes('muted')
                                    ui.upload(label='Seleccionar JSON', auto_upload=True, max_file_size=1_000_000, on_upload=import_config).props('accept=.json').classes('w-full')
                            settings()
                        with ui.column().classes('experiment-aside gap-0'):
                            preview()

                with ui.tab_panel(devices_tab):
                    with ui.card().classes('w-full gap-4'):
                        with ui.row().classes('w-full items-center justify-between'):
                            with ui.column().classes('gap-1'):
                                ui.label('Tus dispositivos').classes('section-title').props('role=heading aria-level=2')
                                ui.label('Usa un nombre como pi-2.local, otro hostname o una dirección IP.').classes('muted')
                            ui.button('Agregar dispositivo', icon='add', on_click=lambda: edit_device()).props('unelevated')
                        with ui.expansion('Preparar y conectar las placas', icon='route').classes('w-full'):
                            for title, explanation in [
                                ('1. Prepara la red', 'Conecta laptop y placas a la misma red. Habilita SSH en cada Raspberry Pi.'),
                                ('2. Registra y verifica', 'Agrega la IP o nombre, usuario y contraseña. El acceso se comprueba al guardar.'),
                                ('3. Asigna los agentes', 'En Nuevo experimento elige Raspberry Pi y asigna una placa distinta a cada agente.')]:
                                with ui.column().classes('gap-1'):
                                    ui.label(title).classes('font-semibold text-sm')
                                    ui.label(explanation)
                        with ui.expansion('Cómo encontrar la dirección y el usuario de una placa', icon='help_outline').classes('w-full'):
                            ui.label('Abre la terminal de esa Raspberry Pi, por ejemplo desde Raspberry Pi Connect, y ejecuta:').classes('text-sm')
                            ui.code('hostname -I\nhostname\nwhoami', language='bash').classes('w-full')
                            ui.label('hostname -I muestra sus IP: usa la dirección de la red compartida con tu laptop. '
                                     'hostname muestra el nombre; puedes probarlo seguido de .local. whoami muestra el usuario SSH. '
                                     'Pi Connect no entrega automáticamente tu contraseña a esta aplicación.').classes('text-sm')
                        device_access_busy = {'value': False}
                        access_summary = ui.label('Verifica varias placas a la vez con las contraseñas guardadas.').classes('muted')
                        with ui.row().classes('gap-3 flex-wrap'):
                            access_all_button = ui.button('Verificar acceso de todas', icon='verified_user', on_click=lambda: verify_devices()).props('unelevated')
                            access_selected_button = ui.button('Verificar seleccionadas', icon='checklist', on_click=lambda: verify_devices(selected_only=True)).props('outline')
                        device_table = ui.table(columns=[
                            dict(name=k, label=label, field=k, align='left', sortable=True)
                            for k, label in [('name', 'Dispositivo'), ('host', 'Host / IP'), ('user', 'Usuario'),
                                             ('port', 'Puerto SSH'), ('password_status', 'Contraseña'), ('status', 'Acceso'), ('detail', 'Detalle')]],
                            rows=[], row_key='id', selection='multiple').classes('w-full').props('wrap-cells')
                        with ui.row().classes('gap-3 flex-wrap'):
                            ui.button('Editar seleccionado', on_click=lambda: edit_selected()).props('flat')
                            ui.button('Quitar del inventario', on_click=lambda: remove_selected()).props('flat color=negative')
                        with ui.expansion('Diagnóstico de red · opcional', icon='wifi').classes('w-full'):
                            probe_button = ui.button('Comprobar solo red y SSH', on_click=lambda: check_devices()).props('outline')
                            ui.label('Solo revisa el servicio; no comprueba la contraseña. Se aplica a las seleccionadas o a todas si no seleccionas ninguna.').classes('text-xs text-slate-500')
                            ui.button('Agregar ejemplos pi-1.local a pi-6.local', on_click=lambda: seed_devices()).props('flat size=sm')
                        help_details('Identidad SSH y contraseñas guardadas', 'Guardar y verificar comprueba el acceso al registrar la placa. Puedes repetirlo si cambia la red; no necesitas un diagnóstico previo. '
                                     'La primera identidad SSH se recuerda tras autenticar. Si una identidad conocida cambia, se bloquea la conexión y se avisa.')

                with ui.tab_panel(monitor_tab):
                    with ui.card().classes('w-full gap-4'):
                        with ui.row().classes('w-full items-center gap-4'):
                            ui.label('Seguimiento del experimento').classes('section-title').props('role=heading aria-level=2')
                            ui.space()
                            stop_button = ui.button('Detener experimento', icon='stop', on_click=lambda: runner.stop()).props('outline color=negative')
                        run_select = ui.select({}, label='Experimento', on_change=lambda e: select_run(e.value) if e.value else None).props('outlined').classes('w-full')
                        run_status = ui.label('Inicia un experimento o selecciona uno del historial.').classes('run-status')
                        with ui.expansion('Medición del tiempo', icon='schedule').classes('help-details w-full'):
                            timing_label = ui.label().classes('help-copy w-full')
                        progress = ui.linear_progress(value=0, show_value=False).classes('w-full')
                        error_label = ui.label().classes('note error-note w-full')
                        error_label.set_visibility(False)
                        scenario_label = ui.label().classes('context-line w-full')
                        scenario_label.set_visibility(False)
                        coordinator_label = ui.label().classes('context-line w-full')
                        coordinator_label.set_visibility(False)
                        with ui.row().classes('gap-3'):
                            ui.button('Añadir gráfica', icon='add_chart', on_click=lambda: add_panel()).props('outline')
                            ui.button('Guardar disposición de gráficas', icon='save', on_click=lambda: save_panels()).props('flat')
                        charts = ui.column().classes('w-full gap-4')
                        node_table = ui.table(columns=[dict(name=k, label=label, field=k, align='left') for k, label in
                            [('node', 'Agente'), ('device_name', 'Equipo / placa'), ('pid', 'PID'), ('connection', 'Conexión del proceso'),
                             ('status_text', 'Estado'), ('round', 'Índice lógico'), ('computed_steps', 'Actualizaciones calculadas'), ('availability', 'Disponible'), ('value', 'Estado completo'), ('error', 'Detalle')]],
                            rows=[], row_key='node').classes('w-full')
                        with ui.row().classes('gap-3'):
                            ui.button('Exportar resultados ZIP', icon='download', on_click=lambda: download_run()).props('outline')
                            ui.button('Repetir configuración', icon='replay', on_click=lambda: repeat_run()).props('flat')

                with ui.tab_panel(history_tab):
                    with ui.card().classes('w-full gap-4'):
                        ui.label('Historial de experimentos').classes('section-title').props('role=heading aria-level=2')
                        ui.label('Cada ejecución conserva sus parámetros, mediciones y evaluación.').classes('muted')
                        history_table = ui.table(columns=[dict(name=k, label=label, field=k, align='left', sortable=True) for k, label in
                            [('name', 'Experimento'), ('algorithm_name', 'Algoritmo'), ('nodes', 'Agentes'), ('status_text', 'Ejecución'),
                             ('validation', 'Evaluación'), ('duration_text', 'Duración medida'), ('date', 'Fecha (UTC)')]], rows=[], row_key='id', selection='single', pagination=10).classes('history-table w-full').props('wrap-cells')
                        with ui.row().classes('gap-3'):
                            ui.button('Ver seleccionado', icon='visibility', on_click=lambda: open_history()).props('unelevated')
                            ui.button('Comparar con otro ensayo', icon='compare_arrows', on_click=lambda: compare_dialog()).props('outline')
                            ui.button('Comparar duraciones', icon='timer', on_click=lambda: duration_dialog()).props('outline')
                            ui.button('Eliminar seleccionado', icon='delete', on_click=lambda: delete_history()).props('outline color=negative')
                            ui.button('Actualizar', icon='refresh', on_click=lambda: refresh_history()).props('flat')
                        history_empty = ui.label('Todavía no hay experimentos. Crea uno en “Nuevo experimento”.').classes('muted py-8')

        def refresh_devices():
            selected_ids = {row['id'] for row in device_table.selected}
            rows = []
            for device in store.devices():
                row = dict(device_results.get(device['id'], dict(**device, status='Sin comprobar', detail='')))
                row['password_status'] = 'Guardada en Windows' if has_password(device) else 'Sin guardar'
                rows.append(row)
            device_table.rows = rows
            device_table.selected = [row for row in rows if row['id'] in selected_ids]
            device_table.update()

        def devices_busy():
            if device_access_busy['value']:
                ui.notify('Hay una comprobación en curso. Espera a que termine.', type='warning')
                return True
            return False

        def edit_device(device=None):
            if devices_busy():
                return
            device = device or dict(name='', host='', user='admin', port=22)
            credential_origins = [dict(device)] if device.get('id') else []
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-3'):
                ui.label('Agregar placa' if not device.get('id') else 'Editar placa').classes('section-title')
                name = ui.input('1. Nombre para identificarla', value=device['name'], placeholder='Raspberry Pi 2').props('outlined').classes('w-full')
                host = ui.input('2. IP o nombre de la placa', value=device['host'], placeholder='pi-2.local').props('outlined').classes('w-full')
                ui.label('En la terminal de la placa: hostname -I muestra la IP; hostname muestra su nombre. Escribe solo una dirección, sin ssh ni http://.').classes('text-xs text-slate-500')
                with ui.row().classes('w-full'):
                    user = ui.input('3. Usuario SSH', value=device['user']).props('outlined').classes('flex-1')
                    port = ui.number('Puerto SSH', value=device['port'], precision=0, min=1, max=65535).props('outlined').classes('w-32')
                ui.label('whoami muestra el usuario. El puerto SSH suele ser 22; es distinto del puerto del algoritmo.').classes('text-xs text-slate-500')
                existing = bool(device.get('id') and has_password(device))
                secret = ui.input('4. Contraseña SSH', password=True, password_toggle_button=True,
                                  placeholder='Vacío: usar la guardada' if existing else 'Contraseña del usuario de la placa').props('outlined').classes('w-full')
                remember = ui.checkbox('Recordar contraseña en este equipo', value=existing or supported())
                remember.set_enabled(supported())
                ui.label('Se guarda en el almacén protegido de Windows, fuera del inventario y los ensayos. '
                         'Si cambias IP, puerto o usuario, escribe la contraseña para esa conexión. '
                         'Una contraseña nueva solo se guarda si el acceso funciona.').classes('text-xs text-slate-500')
                detail = ui.label('Al guardar se comprobarán SSH, Python y transferencia SFTP.').classes('text-sm break-words')

                async def save():
                    nonlocal device
                    if devices_busy():
                        return
                    save_button.disable()
                    attempted = False
                    try:
                        from lab.devices import validate_device
                        candidate = validate_device(dict(id=device.get('id'), name=name.value, host=host.value,
                                                          user=user.value, port=port.value))
                        entered = secret.value
                        password = connection_password(candidate, entered)
                        if not password:
                            raise ValueError('Introduce la contraseña SSH. Si cambió la dirección, escríbela una vez para esa conexión.')
                        previous = device
                        device = store.save_device(candidate)
                        if previous.get('id'):
                            credential_origins.append(previous)
                        device_results.pop(device['id'], None)
                        refresh_devices()
                        if draft['algorithm']:
                            remember_fields()
                            settings.refresh()
                        detail.set_text('Dispositivo guardado. Comprobando su acceso…')
                        attempted = True
                        results = await verify_devices(devices=[device], passwords={device['id']: password}, use_saved=False, notify=False)
                        if results is None:
                            return
                        result = results[0]
                        ok = result['status'] == 'Acceso comprobado'
                        if ok and remember.value:
                            save_password(device, password)
                        elif not remember.value:
                            forget_password(device)
                        if ok:
                            for origin in credential_origins:
                                if credential_target(origin) != credential_target(device):
                                    forget_password(origin)
                        refresh_devices()
                        secret.set_value('')
                        if ok:
                            dialog.close()
                            ui.notify('Placa guardada y acceso comprobado.', type='positive')
                        else:
                            detail.set_text('Placa guardada, pero el acceso no está listo: '+result['detail']+
                                            ' La contraseña introducida no se guardó. Corrige los datos y vuelve a guardar.')
                    except Exception as exc:
                        detail.set_text(str(exc))
                    finally:
                        if attempted:
                            secret.set_value('')
                        save_button.enable()
                with ui.row():
                    save_button = ui.button('Guardar y verificar', icon='verified_user', on_click=save).props('unelevated')
                    ui.button('Cancelar', on_click=dialog.close).props('flat')
            dialog.on('hide', lambda: secret.set_value(''))
            dialog.open()

        def chosen_device():
            if len(device_table.selected) != 1:
                raise ValueError('Selecciona una sola placa para editarla o quitarla del inventario')
            return next(d for d in store.devices() if d['id'] == device_table.selected[0]['id'])

        def edit_selected():
            try:
                edit_device(chosen_device())
            except Exception as exc:
                notify_error(exc)

        def remove_selected():
            if devices_busy():
                return
            try:
                device = chosen_device()
                with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-4'):
                    ui.label('Quitar dispositivo del inventario').classes('section-title')
                    ui.label(f'{device["name"]} · {device["host"]}').classes('font-semibold break-words')
                    ui.label('Se eliminará su registro de la plataforma.').classes('muted')

                    def confirm_remove():
                        try:
                            forget_password(device)
                            store.delete_device(device['id'])
                            device_results.pop(device['id'], None)
                            refresh_devices()
                            dialog.close()
                            ui.notify('Dispositivo retirado del inventario.', type='positive')
                        except Exception as exc:
                            notify_error(exc)

                    with ui.row():
                        ui.button('Quitar dispositivo', icon='delete', on_click=confirm_remove).props('unelevated color=negative')
                        ui.button('Cancelar', on_click=dialog.close).props('flat')
                dialog.open()
            except Exception as exc:
                notify_error(exc)

        def seed_devices():
            if devices_busy():
                return
            for i in range(1, 7):
                if not any(d['host'] == f'pi-{i}.local' and d['port'] == 22 for d in store.devices()):
                    store.save_device(dict(name=f'Raspberry Pi {i}', host=f'pi-{i}.local', user='admin', port=22))
            refresh_devices()

        def device_check_controls(busy):
            device_access_busy['value'] = busy
            for button in (access_all_button, access_selected_button, probe_button):
                button.set_enabled(not busy)
            if busy:
                access_all_button.props('loading')
            else:
                access_all_button.props(remove='loading')

        async def verify_devices(selected_only=False, *, devices=None, passwords=None, use_saved=True, notify=True):
            if devices_busy():
                return None
            if devices is None:
                ids = {row['id'] for row in device_table.selected}
                devices = [d for d in store.devices() if not selected_only or d['id'] in ids]
            if not devices:
                ui.notify('Selecciona una o varias placas.' if selected_only else 'Agrega primero una placa.', type='warning')
                return None
            device_check_controls(True)
            try:
                access_summary.set_text(f'Verificando {len(devices)} placa(s): SSH, Python y SFTP. No necesitas introducir de nuevo las contraseñas guardadas…')
                for device in devices:
                    device_results[device['id']] = dict(**device, status='Comprobando…', detail='')
                refresh_devices()
                results = await run.io_bound(check_access_all, devices, store.root/'known_hosts', passwords, use_saved=use_saved)
                if results is None:
                    for device in devices:
                        device_results[device['id']] = dict(**device, status='Sin comprobar', detail='Comprobación cancelada; puedes volver a intentarlo.')
                    refresh_devices()
                    access_summary.set_text('Comprobación cancelada; puedes volver a intentarlo.')
                    return None
                current = {d['id']: d for d in store.devices()}
                for result in results:
                    if current.get(result['id']) == {key: result[key] for key in ('id','name','host','port','user')}:
                        device_results[result['id']] = result
                refresh_devices()
                ok = sum(r['status']=='Acceso comprobado' for r in results)
                missing = sum(r['status']=='Falta contraseña' for r in results)
                failed = len(results)-ok-missing
                summary = f'{ok} con acceso comprobado · {missing} sin contraseña · {failed} con error. Revisa el detalle de cada placa.'
                access_summary.set_text(summary)
                if notify:
                    ui.notify(summary, type='positive' if ok==len(results) else 'warning')
                return results
            except Exception:
                # No devolver excepciones internas que pudieran contener datos
                # suministrados por una biblioteca de autenticación.
                for device in devices:
                    device_results[device['id']] = dict(**device, status='Error de acceso', detail='No se pudo completar la comprobación. Reintenta o revisa la conexión.')
                refresh_devices()
                access_summary.set_text('La comprobación no pudo completarse. Puedes volver a intentarlo.')
                return None
            finally:
                device_check_controls(False)

        async def check_devices():
            if devices_busy():
                return
            ids = {row['id'] for row in device_table.selected}
            devices = [d for d in store.devices() if not ids or d['id'] in ids]
            if not devices:
                ui.notify('Agrega primero una placa.', type='warning')
                return
            device_check_controls(True)
            probe_button.props('loading')
            try:
                results = await run.io_bound(probe_all, devices)
                if results is None:
                    return
                device_results.update({r['id']: r for r in results})
                refresh_devices()
                access_summary.set_text('Diagnóstico de red terminado. SSH disponible no confirma la contraseña; Verificar acceso sí comprueba la autenticación, Python y SFTP.')
            finally:
                device_check_controls(False)
                probe_button.props(remove='loading')

        def panel_settings(panel):
            return dict(scope=panel['scope'].value, metrics=list(panel['metrics'].value or []),
                        x_axis=panel['x'].value, agents=list(panel['agents'].value or []), kind=panel['kind'].value,
                        interval=panel['interval'].value)

        async def export_runs(requests, layout):
            """Lee la selección completa; el muestreo del monitor no entra en el archivo."""
            def snapshot():
                traces, sources = [], {}
                for request in requests:
                    folder = store.folder(request['run_id'])
                    for trace in chart_series(folder, request['metric'], max_points=10**12, **request['settings']):
                        trace['name'] = request.get('prefix','') + trace['name'] + request.get('suffix','')
                        if request.get('dash'):
                            trace.setdefault('line', {})['dash'] = request['dash']
                        traces.append(trace)
                    record = read_json(folder/'ejecucion.json')
                    sources[request['run_id']] = dict(status=record['status'],
                        config_sha256=hashlib.sha256((folder/'config.json').read_bytes()).hexdigest(),
                        algorithm_sha256=hashlib.sha256((folder/'algoritmo.py').read_bytes()).hexdigest(),
                        timing=timing_text(folder))
                full_layout = copy.deepcopy(layout)
                full_layout['yaxis'].pop('range', None)
                full_layout['yaxis'].pop('autorange', None)
                full_layout['yaxis'].update(readable_yaxis(traces))
                return dict(data=traces, layout=full_layout), dict(requests=requests, sources=sources)
            try:
                result = await run.io_bound(snapshot)
                if result is not None:
                    open_figure_export(*result)
            except Exception as exc:
                notify_error(exc)

        async def export_panel(panel):
            if not selected['run'] or not panel['metrics'].value:
                ui.notify('Selecciona un ensayo y al menos una variable.',type='warning')
                return
            view = panel_settings(panel)
            opts = panel['metrics'].options
            layout = copy.deepcopy(panel['plot'].figure['layout'])
            layout['xaxis']['title'] = dict(text=panel['x'].options.get(view['x_axis'], view['x_axis']))
            layout['yaxis']['title'] = dict(text=' / '.join(opts.get(m,m) for m in view['metrics']))
            requests = [dict(run_id=selected['run'], metric=m, suffix=' · '+opts.get(m,m),
                             settings=dict(x_axis=view['x_axis'], agents=view['agents'], kind=view['kind'],
                                           scope=view['scope'], interval=view['interval'])) for m in view['metrics']]
            await export_runs(requests, layout)

        def add_panel(settings=None):
            settings = settings or {}
            panel = {}
            with charts, ui.card().classes('chart-card w-full gap-3') as card:
                panel['card'] = card
                with ui.row().classes('chart-controls w-full items-center gap-3'):
                    panel['scope'] = ui.select({'agents': 'Por agente', 'global_time': 'Global por tiempo (último estado)', 'global': 'Serie global del evaluador', 'global_index': 'Global por índice (curva reconstruida)'}, label='Origen', value=settings.get('scope', 'agents')).props('outlined dense').classes('w-64')
                    panel['metrics'] = ui.select([], multiple=True, label='Variables Y').props('outlined dense use-chips').classes('flex-1')
                    ui.button(icon='close', on_click=lambda: remove_panel(panel)).props('flat round').tooltip('Quitar gráfica')
                with ui.row().classes('w-full gap-3'):
                    panel['x'] = ui.select({'@round': 'Iteración / índice', '@wall_s': 'Tiempo real (s)'}, label='Eje X', value='@round').props('outlined dense').classes('flex-1')
                    panel['agents'] = ui.select([], multiple=True, label='Agentes').props('outlined dense use-chips').classes('flex-1')
                    panel['kind'] = ui.select({'lines': 'Líneas', 'markers': 'Puntos', 'lines+markers': 'Líneas y puntos'}, label='Tipo', value=settings.get('kind', 'lines')).props('outlined dense').classes('w-44')
                    panel['interval'] = ui.select({.01:'0.01 s',.1:'0.1 s',.5:'0.5 s',1.0:'1 s',5.0:'5 s'}, label='Muestra global cada', value=settings.get('interval',.1)).props('outlined dense').classes('w-44')
                    panel['interval'].set_visibility(False)
                panel['notice'] = ui.label().classes('text-sm text-slate-600')
                panel['plot'] = ui.plotly(dict(data=[], layout=chart_layout())).classes('w-full')
                ui.button('Exportar figura', icon='file_download', on_click=lambda: export_panel(panel)).props('outline')
            panel['pending'] = settings
            panels.append(panel)

        def remove_panel(panel):
            panels.remove(panel)
            panel['card'].delete()

        def save_panels():
            if not selected['run']:
                ui.notify('Selecciona un experimento.', type='warning')
                return
            write_json(store.folder(selected['run']) / 'vistas.json', [panel_settings(p) for p in panels])
            ui.notify('Disposición guardada para este experimento.', type='positive')

        def select_run(run_id):
            if not run_id or run_id == selected['run']:
                return
            folder = store.folder(run_id)
            config = read_json(folder / 'config.json')
            if not config:
                return
            selected['run'] = run_id
            for panel in list(panels):
                remove_panel(panel)
            for settings in read_json(folder / 'vistas.json', [dict(x_axis='@experiment_s' if config.get('timing_protocol')==1 else '@round')]):
                add_panel(settings)
            if run_id in run_select.options:
                run_select.set_value(run_id)

        def history_data():
            # Estado operativo y evaluación matemática son columnas diferentes:
            # terminar todas las iteraciones no demuestra alcanzar el objetivo.
            records = store.list_runs()
            rows = []
            for record in records:
                report = read_json(store.folder(record['id']) / 'evaluacion.json')
                validation = 'Sin evaluación completa'
                if report:
                    validation = ('Criterio declarado cumplido' if report.get('converged') else 'Criterio no cumplido') if report.get('convergence_evaluated') else 'Sin criterio de convergencia'
                    if not report.get('records_valid'):
                        validation = report.get('conclusion', 'Error de evaluación')
                row = dict(record)
                timing = read_json(store.folder(record['id'])/'tiempos.json', {})
                row.update(name=display_run_name(record['name']),
                                 algorithm_name=REGISTRY[record['algorithm']].name if record['algorithm'] in REGISTRY else record['algorithm'],
                                 status_text=STATUS.get(record['status'], record['status']),
                                 validation=validation,
                                 duration_text=f"{timing['duration_s']:.3f} s" if timing.get('status')=='completed' else 'Sin medición completa',
                                 date=record['created_at'][:19].replace('T', ' '))
                rows.append(row)
            options = {r['id']: f'{display_run_name(r["name"])} · {r["id"]}' for r in records}
            return rows, options

        def apply_history(data):
            rows, options = data
            if rows != history_table.rows:
                history_table.rows = rows
                history_table.update()
            history_empty.set_visibility(not rows)
            if options != run_select.options:
                run_select.set_options(options, value=selected['run'] if selected['run'] in options else None)
            history_refresh['at'] = time.monotonic()

        def refresh_history():
            apply_history(history_data())

        def open_history():
            if not history_table.selected:
                ui.notify('Selecciona un experimento en la tabla.', type='warning')
                return
            select_run(history_table.selected[0]['id'])
            tabs.set_value(monitor_tab)

        def delete_history():
            """Pide confirmación mostrando el ensayo concreto que se eliminará."""
            if not history_table.selected:
                ui.notify('Selecciona un experimento en la tabla.', type='warning')
                return
            record = history_table.selected[0]
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-4'):
                ui.label('Eliminar resultados del experimento').classes('section-title')
                ui.label(record['name']).classes('font-semibold break-words')
                ui.label(record['id']).classes('text-xs text-slate-500 break-all')
                ui.label('Se eliminarán la configuración, las mediciones, las gráficas y la evaluación guardadas. Esta acción no se puede deshacer.').classes('note w-full')

                def confirm_delete():
                    try:
                        store.delete_run(record['id'])
                        if selected['run'] == record['id']:
                            selected.update(run=None, metric=None)
                            run_status.set_text('Selecciona otro experimento o inicia uno nuevo.')
                            error_label.set_visibility(False)
                            node_table.rows = []
                            node_table.update()
                            for panel in list(panels):
                                remove_panel(panel)
                        history_table.selected = []
                        refresh_history()
                        dialog.close()
                        ui.notify('Resultados eliminados.', type='positive')
                    except Exception as exc:
                        notify_error(exc)

                with ui.row():
                    ui.button('Eliminar definitivamente', icon='delete', on_click=confirm_delete).props('unelevated color=negative')
                    ui.button('Cancelar', on_click=dialog.close).props('flat')
            dialog.open()

        def download_run():
            try:
                if not selected['run']:
                    raise ValueError('Selecciona un experimento')
                ui.download.file(runner.export(selected['run']))
            except Exception as exc:
                notify_error(exc)

        def repeat_run():
            # Solo copia parámetros al formulario. El nuevo ID nace al ejecutar.
            if not selected['run']:
                ui.notify('Selecciona un experimento.', type='warning')
                return
            config = read_json(store.folder(selected['run']) / 'config.json')
            config['name'] = display_run_name(config['name']) + ' · repetición'
            try:
                load_draft(config)
                tabs.set_value(new_tab)
            except Exception as exc:
                notify_error(exc)

        def duration_dialog():
            records = store.list_runs()
            options = {r['id']: f'{display_run_name(r["name"])} · {r["id"]}' for r in records}
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-6xl gap-4'):
                ui.label('Comparar duraciones de ejecución').classes('section-title')
                ui.label('Selecciona varios ensayos, incluso de distintos algoritmos. La duración mide desde la liberación del inicio hasta la última muestra de todos los agentes; no incluye el despliegue.').classes('muted')
                chosen = ui.select(options, multiple=True, label='Experimentos', value=[]).props('outlined use-chips').classes('w-full')
                output = ui.column().classes('w-full')

                def show_durations():
                    output.clear()
                    with output:
                        rows = duration_rows([store.folder(r) for r in chosen.value])
                        if not rows:
                            ui.label('Selecciona los ensayos que quieras comparar.')
                            return
                        columns = [dict(name=k, label=label, field=k, sortable=True, align='left') for k, label in COLUMNS]
                        visible = [{k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()} for row in rows]
                        ui.table(columns=columns, rows=visible, row_key='id', pagination=10).classes('w-full')
                        measured = [row for row in rows if row['duration_s'] is not None]
                        if measured:
                            labels = [f'Ensayo {r["reference"]}' for r in measured]
                            details = [f'{r["algorithm"]} · {r["target"]} · {r["mode"]} · {r["topology"]} · {r["id"]}' for r in measured]
                            duration_figure = dict(data=[dict(type='bar', name='Duración', orientation='h', x=[r['duration_s'] for r in measured], y=labels,
                                                     text=[f'{r["duration_s"]:.3f} s' for r in measured], textposition='auto',
                                                     hovertext=details, hovertemplate='%{hovertext}<br>%{x:.6f} s<extra></extra>',
                                                     error_x=dict(type='data', array=[r['margin_s'] or 0 for r in measured], visible=True))],
                                           layout=dict(height=max(320, 40*len(measured)+100), margin=dict(l=20,r=30,t=20,b=50),
                                                       xaxis=dict(title=dict(text='Duración de ejecución (s)'), rangemode='tozero'),
                                                       yaxis=dict(title=dict(text='Ensayo'), automargin=True, autorange='reversed')))
                            ui.plotly(duration_figure).classes('w-full')
                            ui.button('Exportar figura', icon='file_download', on_click=lambda: open_figure_export(duration_figure, dict(duration_rows=rows))).props('outline')
                        ui.label('Las celdas vacías indican que falta una medición completa: no se representan como cero. Confirmación es el tiempo hasta que la laptop detecta el final; puede incluir consultas y transferencias. Las barras de error muestran el margen estimado de alineación de relojes.').classes('text-sm')
                        ui.label('Menor duración no garantiza igual precisión. Para comparar modalidades, conserva algoritmo, agentes, parámetros, iteraciones y esperas; revisa el error final y repite cada configuración. Cada fila corresponde a una ejecución, sin promediar configuraciones diferentes.').classes('note')
                        ui.button('Descargar tabla CSV', icon='download', on_click=lambda: ui.download.content(duration_csv(rows).encode('utf-8-sig'), 'comparacion_duraciones.csv')).props('outline')
                with ui.row():
                    ui.button('Ver duraciones', on_click=show_durations)
                    ui.button('Seleccionar todos', on_click=lambda: chosen.set_value(list(options))).props('flat')
                    ui.button('Cerrar', on_click=dialog.close).props('flat')
            dialog.open()

        def compare_dialog():
            """Superpone variables de dos ensayos del mismo algoritmo para compararlos."""
            records = store.list_runs()
            options = {r['id']: f'{display_run_name(r["name"])} · {r["id"]}' for r in records}
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl gap-4'):
                ui.label('Comparar dos experimentos').classes('section-title')
                with ui.row().classes('w-full gap-4'):
                    first = ui.select(options, label='Primer experimento').props('outlined').classes('flex-1')
                    second = ui.select(options, label='Segundo experimento').props('outlined').classes('flex-1')
                comparison_metric = ui.select([], label='Variable compartida').props('outlined').classes('w-full')
                variable_hint = ui.label('Selecciona dos experimentos para ver sus variables compartidas.').classes('text-sm')
                with ui.row().classes('w-full gap-3'):
                    comparison_scope = ui.select({'agents':'Por agente', 'global_time':'Global por tiempo', 'global_index':'Global por índice'}, label='Origen', value='agents').props('outlined dense').classes('flex-1')
                    comparison_axis = ui.select({'@experiment_s':'Tiempo de ejecución (s)', '@round':'Iteración / índice'}, label='Eje X para ambos', value='@experiment_s').props('outlined dense').classes('flex-1')
                    comparison_interval = ui.select({.01:'0.01 s',.1:'0.1 s',.5:'0.5 s',1.0:'1 s',5.0:'5 s'}, label='Muestra global cada', value=.1).props('outlined dense').classes('w-44')
                comparison = ui.column().classes('w-full')

                def refresh_variables():
                    comparison.clear()
                    scope = comparison_scope.value
                    comparison_axis.set_enabled(scope=='agents')
                    comparison_interval.set_enabled(scope=='global_time')
                    if scope!='agents':
                        comparison_axis.set_value('@experiment_s' if scope=='global_time' else '@round')
                    choices = {}
                    message = 'Selecciona dos experimentos diferentes para ver sus variables compartidas.'
                    if first.value and second.value and first.value!=second.value:
                        folders = [store.folder(x) for x in (first.value, second.value)]
                        configs = [read_json(f/'config.json') for f in folders]
                        if configs[0]['algorithm']!=configs[1]['algorithm']:
                            message = 'Para comparar variables, selecciona ensayos del mismo algoritmo. Para distintos algoritmos usa Comparar duraciones.'
                        else:
                            try:
                                # El catálogo por índice permite elegir variables aunque un ensayo antiguo no tenga reloj común.
                                catalogs = [catalog(f) if scope=='agents' else global_catalog(f, reconstructed=True) for f in folders]
                                choices = {k:catalogs[0][k] for k in sorted(catalogs[0].keys() & catalogs[1].keys())}
                                message = 'Elige la variable y pulsa Comparar.' if choices else 'No hay variables comunes registradas en este origen.'
                            except (ValueError, OSError) as exc:
                                message = str(exc)
                    value = comparison_metric.value if comparison_metric.value in choices else next(iter(choices), None)
                    comparison_metric.set_options(choices, value=value)
                    comparison_metric.set_enabled(bool(choices))
                    variable_hint.set_text(message)

                for control in (first, second, comparison_scope):
                    control.on_value_change(lambda _: refresh_variables())
                refresh_variables()

                def compare():
                    comparison.clear()
                    with comparison:
                        if not first.value or not second.value or first.value == second.value:
                            ui.label('Selecciona dos experimentos diferentes.').classes('muted')
                            return
                        configs = [read_json(store.folder(x) / 'config.json') for x in (first.value, second.value)]
                        if configs[0]['algorithm'] != configs[1]['algorithm']:
                            ui.label('Selecciona el mismo algoritmo para comparar variables con el mismo significado.').classes('muted')
                            return
                        scope = comparison_scope.value
                        axis = '@experiment_s' if scope=='global_time' else '@round' if scope=='global_index' else comparison_axis.value
                        comparison_axis.set_enabled(scope=='agents')
                        comparison_axis.set_value(axis)
                        comparison_interval.set_enabled(scope=='global_time')
                        folders = [store.folder(x) for x in (first.value, second.value)]
                        bases = [time_basis(f) for f in folders]
                        for prefix, f in zip(('A','B'), folders):
                            ui.label(prefix+': '+timing_text(f)).classes('text-sm')
                        if axis=='@experiment_s' and (not all(bases) or bases[0]['kind']!=bases[1]['kind']):
                            ui.label('Para comparar por tiempo se necesita la misma definición del inicio en ambos ensayos. Ejecuta nuevamente los ensayos sin medición común, o selecciona índices.').classes('note')
                            return
                        if not comparison_metric.value:
                            ui.label('No hay variables comunes registradas.')
                            return
                        metric = comparison_metric.value
                        label = comparison_metric.options[metric]
                        traces = []
                        for run_id, prefix in [(first.value, 'A'), (second.value, 'B')]:
                            for trace in chart_series(store.folder(run_id), metric, scope=scope, x_axis=axis, interval=comparison_interval.value):
                                trace['name'] = prefix + ' · ' + trace['name']
                                traces.append(trace)
                        layout = chart_layout(label,configs[0].get('execution_mode','sync'), traces)
                        layout['xaxis']['title']['text'] = bases[0]['label'] if axis=='@experiment_s' else 'Iteración / índice local'
                        ui.plotly(dict(data=traces, layout=layout)).classes('w-full')
                        export_requests = [dict(run_id=rid, metric=metric, prefix=prefix+' · ',
                            dash=None,
                            settings=dict(scope=scope, x_axis=axis, interval=comparison_interval.value))
                            for rid,prefix in [(first.value,'A'),(second.value,'B')]]
                        ui.button('Exportar figura', icon='file_download',
                                  on_click=lambda: export_runs(export_requests, layout)).props('outline')
                        ui.label('La duración hasta completar las actualizaciones no demuestra igual precisión. Compara también una métrica de error. Las curvas temporales conservan el último estado registrado; no interpolan valores.').classes('text-sm')
                        if any(c.get('faults',{}).get('events') for c in configs):
                            ui.label('Las fallas de estos escenarios se programan por índice, por lo que pueden ocurrir en segundos diferentes.').classes('note')
                        for prefix, run_id, config in zip(('A', 'B'), (first.value, second.value), configs):
                            report = read_json(store.folder(run_id) / 'evaluacion.json')
                            ui.label(f'{prefix}: {config.get("execution_mode", "sync")} · {len(config["nodes"])} agentes · {config.get("topology", "personalizada")} · '
                                     f'{config["steps"]} iteraciones · intervalo mínimo {config["period_s"]} s').classes('muted')
                            ui.label(report['conclusion'] if report else 'Datos parciales: sin certificación de convergencia.').classes('text-sm')
                with ui.row():
                    ui.button('Comparar', on_click=compare).props('unelevated')
                    ui.button('Cerrar', on_click=dialog.close).props('flat')
            dialog.open()

        async def update_monitor():
            # Las pestañas ocultas no leen JSONL ni envían figuras Plotly. El
            # gestor y los procesos siguen ejecutándose independientemente.
            if tabs.value not in (monitor_tab, history_tab, monitor_tab.props['name'], history_tab.props['name']):
                return
            if time.monotonic()-history_refresh['at'] >= 3:
                history = await run.io_bound(history_data)
                if history is not None:
                    apply_history(history)
            if tabs.value not in (monitor_tab, monitor_tab.props['name']):
                return
            stop_button.set_enabled(runner.active is not None)
            if not selected['run']:
                records = store.list_runs()
                if runner.active or records:
                    select_run(runner.active or records[0]['id'])
                else:
                    return
            run_id = selected['run']
            folder = store.folder(run_id)
            try:
                revision = await run.io_bound(folder_revision, folder)
                views = [panel_settings(p) for p in panels]
                if revision is None or not monitor_gate.needed(run_id, revision, views):
                    return
                def read_monitor():
                    global_values = evaluator_rows(folder)
                    return (read_json(folder / 'ejecucion.json'), runner.states(run_id),
                    read_json(folder / 'evaluacion.json'), catalog(folder), global_catalog(folder), read_json(folder / 'config.json'),
                    read_json(folder / 'despliegue.json', {}), time_basis(folder), timing_text(folder),
                    read_json(folder / 'coordinador.json'),
                    bool(global_values and 'time/experiment_s' in global_values[0]))
                data = await run.io_bound(read_monitor)
                if data is None or selected['run'] != run_id:
                    return
                record, states, report, variables, globals_, config, deployment, basis, timing, coordinator, evaluator_timed = data
                # Usar el nombre archivado al desplegar, aunque luego se renombre
                # o se quite la placa del inventario. Una ejecución local ignora
                # asignaciones de placas que hayan quedado en el formulario.
                def equipment_name(node_id):
                    if record['mode'] != 'remote_tcp':
                        return 'Laptop · proceso local'
                    device = deployment.get('devices', {}).get(str(node_id), {})
                    endpoint = next((n['host'] for n in config['nodes'] if n['id'] == node_id), '')
                    return device.get('name') or endpoint or 'Placa sin identificar'
                place = 'en placas' if record['mode'] == 'remote_tcp' else 'locales'
                display_status = ('fault_interrupted' if record['status']=='completed' and
                                  report and report.get('scenario_outcome')=='interrupted' else record['status'])
                run_status.set_text(f'{STATUS[display_status]} · {record["name"]} · {record["nodes"]} agentes {place}')
                timing_label.set_text(timing)
                progress.set_value(min(s['round'] / s['steps'] for s in states))
                # Las conclusiones matemáticas se conservan en la evaluación y
                # el historial. Aquí se muestran únicamente errores operativos.
                detail = record.get('error')
                if not detail and report and report.get('records_valid') is False:
                    detail = report.get('conclusion')
                faults=config.get('faults') or {}
                scenario_label.set_visibility(bool(faults.get('events')))
                if faults.get('events'):
                    lines=[f"{('Coordinador' if e.get('target')=='coordinator' else 'Agentes '+', '.join(map(str,e['nodes'])))}: falla en {e['start']}, " + (f"regresa en {e['end']}" if e.get('end') is not None else 'sin reincorporación') for e in faults['events']]
                    if faults.get('version',1)==1:
                        scenario_description='Ensayo histórico de fallas (formato anterior; registros originales). '
                    else:
                        scenario_description=('Se excluyen los agentes ausentes. Al regresar: '+
                            ('solo los reincorporados usan sus condiciones iniciales. ' if faults.get('state_policy')=='reset_returning' else 'retoman su último estado. '))
                    scenario_label.set_text('Fallas por iteración · '+scenario_description+' | '.join(lines))
                error_label.set_text(detail or '')
                error_label.set_visibility(bool(detail))
                coordinator_label.set_visibility(bool(coordinator))
                if coordinator:
                    coordinator_node = deployment.get('coordinator_node')
                    host_label = equipment_name(coordinator_node) if record['mode'] == 'remote_tcp' else 'Laptop'
                    coordinator_status = STATUS.get(coordinator['status'], coordinator['status'])
                    exchange_label = 'asíncrono · últimas muestras' if config.get('coordinator_exchange')=='async' else 'síncrono · misma ronda'
                    coordinator_label.set_text(f'Coordinador {exchange_label} · {host_label} · proceso separado · PID {coordinator["pid"]} · {coordinator_status}')
                node_rows = [{**s, 'device_name': equipment_name(s['node']), 'status_text': STATUS.get(s['status'], s['status']),
                    'computed_steps': s.get('computed_steps',s['round']), 'availability':'No' if s.get('active') is False else 'Sí',
                    'value': json.dumps(s['state'], ensure_ascii=False), 'error': s.get('error') or ''} for s in states]
                if node_rows != node_table.rows:
                    node_table.rows = node_rows
                    node_table.update()
                for panel in list(panels):
                    reconstructed = panel['scope'].value == 'global_index'
                    temporal = panel['scope'].value == 'global_time'
                    opts = (await run.io_bound(global_catalog, folder, reconstructed, temporal, panel['interval'].value)) if reconstructed or temporal else (variables if panel['scope'].value == 'agents' else globals_)
                    if opts is None:
                        return
                    panel['notice'].set_text(('Estados de cada agente en su índice local k.' if opts else 'No hay métricas globales disponibles en los registros.'))
                    if temporal:
                        text = 'Último estado registrado de cada agente, a intervalos de tiempo.' if opts else 'Falta una referencia temporal común o métricas globales.'
                        if basis and basis.get('margin_s') is not None and basis['margin_s'] > panel['interval'].value:
                            text += ' El margen de alineación supera el intervalo de representación: más puntos no mejoran la precisión del reloj.'
                        panel['notice'].set_text(text)
                    evaluator_evolution = panel['scope'].value == 'global' and evaluator_timed
                    if evaluator_evolution:
                        panel['notice'].set_text('Métricas del evaluador en cada cambio registrado, usando los últimos estados disponibles.')
                    panel['notice'].set_visibility(reconstructed or temporal or evaluator_evolution)
                    panel['interval'].set_visibility(temporal)
                    pending = panel['pending']
                    if opts != panel['metrics'].options:
                        previous = panel['metrics'].value or pending.get('metrics', [])
                        defaults = [key for key in opts if key not in ('round', 'wall_s') and not key.startswith('reference/')] or list(opts)
                        panel['metrics'].set_options(opts, value=[k for k in previous if k in opts] or defaults[:1])
                    per_agent_clock = config.get('clock_scope') == 'per_agent'
                    time_axes = {} if reconstructed or (per_agent_clock and panel['scope'].value == 'global') else {'@wall_s': 'Tiempo local del agente (s)' if per_agent_clock else 'Tiempo desde lanzamiento (s)'}
                    if (basis or config.get('timing_protocol')==1) and panel['scope'].value=='agents':
                        time_axes = {'@experiment_s':basis['label'] if basis else 'Tiempo de ejecución (s)', **time_axes}
                    xopts = {'@round': 'Índice local k (no tiempo común)' if reconstructed and (config.get('execution_mode')=='async' or config.get('coordinator_exchange')=='async') else 'Iteración / índice', **time_axes, **opts}
                    if temporal:
                        xopts = {'@experiment_s':basis['label'] if basis else 'Tiempo de ejecución (s)'}
                    elif evaluator_evolution:
                        xopts = {'@experiment_s':basis['label'], **opts}
                    if xopts != panel['x'].options or pending:
                        value = pending.get('x_axis', panel['x'].value)
                        panel['x'].set_options(xopts, value=value if value in xopts else next(iter(xopts)))
                    agents = {n['id']: f'Agente {n["id"]}' for n in config['nodes']}
                    if agents != panel['agents'].options:
                        panel['agents'].set_options(agents, value=[i for i in pending.get('agents', list(agents)) if i in agents])
                    panel['agents'].set_enabled(panel['scope'].value == 'agents')
                    if opts:
                        panel['pending'] = {}
                    view = panel_settings(panel)
                    def traces_for_view():
                        traces = []
                        for metric in view['metrics']:
                            for trace in chart_series(folder, metric, x_axis=view['x_axis'], agents=view['agents'], kind=view['kind'], scope=view['scope'], interval=view['interval']):
                                trace['name'] += ' · ' + opts.get(metric, metric)
                                traces.append(trace)
                        return traces
                    traces = await run.io_bound(traces_for_view)
                    if traces is None or selected['run'] != run_id or panel not in panels:
                        return
                    if panel_settings(panel) != view:
                        return  # Una edición durante la lectura se procesa en el siguiente ciclo.
                    layout = chart_layout(' / '.join(opts.get(m, m) for m in view['metrics']), traces=traces)
                    layout['xaxis']['title']['text'] = xopts.get(view['x_axis'], view['x_axis'])
                    if faults.get('events') and view['x_axis']=='@round':
                        layout['shapes']=[dict(type='line',xref='x',yref='paper',x0=v,x1=v,y0=0,y1=1,line=dict(color='#b45309' if kind=='Falla' else '#087f8c',dash='dot',width=1)) for e in faults['events'] for kind,v in [('Falla',e['start']),('Regreso',e.get('end'))] if v is not None]
                        layout['annotations']=[dict(x=v,y=1,xref='x',yref='paper',text=kind,showarrow=False,yanchor='bottom',font=dict(size=11)) for e in faults['events'] for kind,v in [('Falla',e['start']),('Regreso',e.get('end'))] if v is not None]
                    if config.get('demand_schedule') and view['x_axis']=='@round':
                        for change in config['demand_schedule']['events']:
                            layout.setdefault('shapes', []).append(dict(type='line', xref='x', yref='paper',
                                x0=change['at'], x1=change['at'], y0=0, y1=1,
                                line=dict(color='#087f8c', dash='dot', width=1)))
                            layout.setdefault('annotations', []).append(dict(x=change['at'], y=1, xref='x', yref='paper',
                                text='Demanda: '+str(change['value']), showarrow=False, yanchor='bottom', font=dict(size=11)))
                    layout['uirevision'] = run_id + str(view)
                    figure = dict(data=traces, layout=layout)
                    if panel['plot'].figure != figure:
                        panel['plot'].figure = figure
                        panel['plot'].update()
                # No guardar el sello si cambió el ensayo durante una lectura.
                if selected['run'] == run_id:
                    monitor_gate.commit(run_id, revision, [panel_settings(p) for p in panels])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                run_status.set_text(f'No se pudo leer el estado: {exc}')

        if draft['algorithm']:
            load_draft(draft)
        last_saved = {'config': None}
        async def preserve_experiment():
            try:
                config = gather(validate=False)
                if config != last_saved['config']:
                    def save():
                        build(config)
                        write_json(store.root / 'ultimo_experimento.json', config)
                        return True
                    if await run.io_bound(save):
                        last_saved['config'] = copy.deepcopy(config)
            except (OSError, ValueError, KeyError, TypeError):
                # Un campo numérico incompleto no reemplaza la última configuración válida.
                pass
        ui.timer(1.0, preserve_experiment)
        refresh_devices()
        refresh_history()
        ui.timer(1.0, update_monitor)
        with ui.footer().classes('bg-transparent text-slate-500 px-8 py-3 text-xs'):
            ui.label('Datos guardados en esta laptop · sin base de datos ni servicio en la nube')


def main():
    """Arranca un servidor accesible solo desde esta laptop y prepara su cierre."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8778)
    parser.add_argument('--data', type=Path, default=ROOT / 'datos')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    store = Store(args.data)
    runner = LocalRunner(store)
    app.on_shutdown(runner.shutdown)
    setup(store, runner)
    ui.run(host='127.0.0.1', port=args.port, title='DistOptLab',
           language='es', reload=False, show=not args.no_browser, favicon='◉')


if __name__ in {'__main__', '__mp_main__'}:
    main()
