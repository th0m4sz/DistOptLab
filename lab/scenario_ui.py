# Función de este módulo: Permite configurar fallas de uno o varios agentes sin editar JSON ni ecuaciones.
import copy
from nicegui import ui
from .faults import SCENARIO_VERSION, upgrade_scenario_config
from .presentation import help_details


class ScenarioEditor:
    def __init__(self, draft):
        self.draft = draft
        saved = upgrade_scenario_config(draft).get('faults') or {}
        self.events = saved.get('events', [])
        self.controls = []
        # Un escenario cargado debe dejar sus eventos a la vista.
        self.expansion = ui.expansion('Fallas programadas · opcional', icon='warning_amber',
                                      value=bool(self.events)).classes('w-full border rounded-lg').style('scroll-margin-top:100px')
        with self.expansion:
            self.enabled = ui.switch('Activar escenario de fallas', value=bool(self.events))
            ui.label('Programa qué agentes dejan de participar y cuándo regresan. En placas, el equipo permanece encendido.').classes('muted')
            with ui.column().classes('w-full').bind_visibility_from(self.enabled,'value'):
                ui.label('Los demás continúan sin los datos de los agentes ausentes.').classes('muted')
                ui.label('1. Con qué valores regresan los agentes afectados').classes('font-semibold')
                self.state_policy = ui.select({'keep':'Retomar su último estado',
                                               'reset_returning':'Usar sus condiciones iniciales'},
                    label='Valores para su regreso',value=saved.get('state_policy','keep')).props('outlined').classes('w-full')
                ui.label().bind_text_from(self.state_policy,'value',backward=lambda value:
                    'Al regresar, retoman las variables que tenían al salir. Los demás conservan su evolución.' if value=='keep' else
                    'Solo quienes regresan usan sus condiciones iniciales. Los demás conservan sus valores.').classes('muted')
                help_details('Qué cambia al retirar un agente', 'Su último dato queda fuera de los cálculos hasta que regresa. No se crean enlaces nuevos ni se reinician los demás agentes. '
                             'Una falla permanente no reinicia a nadie. Estas opciones no añaden ecuaciones de recuperación de demanda ni garantizan convergencia.')
                ui.label('2. Quién falla y cuándo').classes('font-semibold')
                self.container = ui.column().classes('w-full')
                ui.button('Añadir falla',icon='add',on_click=self.add).props('outline')
                ui.button('Leer funcionamiento y límites',icon='menu_book',on_click=self.help).props('flat')
                self.render()

    def help(self):
        from pathlib import Path
        with ui.dialog() as dialog,ui.card().style('width:950px;max-width:96vw;max-height:90vh'):
            ui.button('Cerrar',on_click=dialog.close).props('flat')
            ui.markdown((Path(__file__).resolve().parents[1]/'docs/FALLAS.md').read_text(encoding='utf-8')).classes('learning-prose w-full overflow-auto')
        dialog.open()

    def remember(self):
        self.events = [dict(target=c['target'].value,nodes=list(c['nodes'].value or []),
                            start=c['start'].value,end=None if c['permanent'].value else c['end'].value)
                       for c in self.controls]

    def add(self):
        self.remember()
        ids = [n['id'] for n in self.draft['nodes']]
        self.events.append(dict(target='agent',nodes=ids[-1:],start=max(1,int(self.draft.get('steps',100))//2),end=None))
        self.render()

    def remove(self,index):
        self.remember()
        del self.events[index]
        self.render()

    def render(self):
        self.container.clear()
        self.controls = []
        with self.container:
            for index,event in enumerate(self.events):
                with ui.card().classes('w-full gap-3'):
                    with ui.row().classes('w-full items-center'):
                        ui.label(f'Evento {index+1}').classes('font-bold')
                        ui.space()
                        ui.button(icon='delete',on_click=lambda _,i=index:self.remove(i)).props('flat color=negative').tooltip('Eliminar evento')
                    targets={'agent':'Uno o varios agentes'}
                    if self.draft.get('execution_mode')=='coordinator':targets['coordinator']='Coordinador'
                    target=ui.select(targets,label='Qué deja de funcionar',value=event.get('target','agent')).props('outlined').classes('w-full')
                    options={n['id']:f'Agente {n["id"]}' for n in self.draft['nodes']}
                    options.update({i:f'Agente {i} (ya no existe; corrige la selección)' for i in event.get('nodes',[]) if i not in options})
                    nodes=ui.select(options,multiple=True,label='Agentes afectados',value=event.get('nodes',[])).props('outlined use-chips').classes('w-full')
                    nodes.bind_visibility_from(target,'value',backward=lambda v:v=='agent')
                    with ui.element('div').classes('w-full grid grid-cols-1 md:grid-cols-2 gap-3'):
                        start=ui.number('Falla en la iteración',min=1,precision=0,value=event['start']).props('outlined').classes('w-full')
                        end=ui.number('Regresa en la iteración',min=2,precision=0,value=event.get('end') or event['start']+10).props('outlined').classes('w-full')
                    permanent=ui.checkbox('No vuelve durante este experimento',value=event.get('end') is None)
                    end.bind_enabled_from(permanent,'value',backward=lambda value:not value)
                    permanent.bind_enabled_from(target,'value',backward=lambda value:value!='coordinator')
                    target.on_value_change(lambda e,p=permanent:p.set_value(True) if e.value=='coordinator' else None)
                    help_details('Cómo se aplican estos índices', 'Falla en 50 y regresa en 75: no calcula las actualizaciones 50→51 hasta 74→75; vuelve a participar desde 75.')
                    ui.label('El coordinador no tiene reemplazo automático. Si falla, el ensayo se interrumpe y no puede reanudarse por esta opción.').bind_visibility_from(target,'value',backward=lambda value:value=='coordinator').classes('text-sm text-slate-600')
                    self.controls.append(dict(target=target,nodes=nodes,start=start,end=end,permanent=permanent))
            if not self.events:
                ui.label('Añade al menos un evento. Por ejemplo, retirar al agente 4 en el índice 50 de un ensayo de 100 actualizaciones.').classes('text-sm')

    def value(self):
        if not self.enabled.value:
            return None
        self.remember()
        if not self.events:
            raise ValueError('Añade al menos una falla o desactiva el escenario')
        events = copy.deepcopy(self.events)
        for event in events:
            for key in ('start','end'):
                value=event.get(key)
                if value is not None and isinstance(value,(int,float)) and value == int(value):
                    event[key]=int(value)
        return dict(version=SCENARIO_VERSION,state_policy=self.state_policy.value,events=events)
