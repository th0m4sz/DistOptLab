# Función de este módulo: Edita cambios de demanda sin modificar el archivo del algoritmo.
import ast
import copy
from nicegui import ui
from .presentation import help_details


class DemandEditor:
    def __init__(self, spec, draft):
        self.spec, self.draft, self.controls = spec, draft, []
        saved = draft.get('demand_schedule') or {}
        self.events = copy.deepcopy(saved.get('events', []))
        fields = [f for f in spec.parameters if f.type in ('number', 'integer')]
        supported = False
        for node in ast.parse(spec.path.read_text(encoding='utf-8-sig')).body:
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if 'ASISTENTE' in names and isinstance(node.value, ast.Dict):
                    supported = True
                if 'PARAMETROS_PROGRAMABLES' in names and isinstance(node.value, ast.Constant) and node.value.value is True:
                    supported = True
        preferred = next((f.key for f in fields if 'demanda' in f.label.casefold() or f.key in ('demanda','demand_kw')), None)
        options = {f.key:f.label for f in fields}
        with ui.expansion('Cambio de demanda · opcional', icon='trending_up', value=bool(saved)).classes('w-full'):
            if not fields or not supported:
                ui.label('Disponible para modelos del asistente con parámetros comunes numéricos. En Python propio, declara PARAMETROS_PROGRAMABLES = True y consulta rt.parameters_at(k).').classes('muted')
                self.enabled = None
                return
            self.enabled = ui.switch('Programar cambios de demanda', value=bool(saved))
            with ui.column().classes('w-full gap-3').bind_visibility_from(self.enabled, 'value'):
                self.parameter = ui.select(options, label='Parámetro que representa la demanda',
                                           value=saved.get('parameter') or preferred).props('outlined').classes('w-full')
                ui.label('El valor inicial es el indicado en Parámetros del algoritmo. Cada cambio lo sustituye desde el índice elegido.').classes('muted')
                self.area = ui.column().classes('w-full gap-3')
                ui.button('Añadir cambio de demanda', icon='add', on_click=self.add).props('outline')
                help_details('Cómo se aplica el cambio', 'Un cambio en k=500 se usa desde la actualización 500 → 501. No reinicia agentes ni modifica estados o ganancias. '
                             'En asíncrono, cada agente o petición al coordinador lo aplica al alcanzar su índice local; no es un cambio simultáneo por segundos. '
                             'Solo afecta a las ecuaciones que utilizan el parámetro elegido. Si la demanda aparece únicamente en las métricas, cambia la referencia del balance, no la potencia calculada. '
                             'En la reconstrucción temporal, la referencia y las métricas que la utilizan quedan vacías mientras los agentes activos utilizan valores de demanda distintos.')
                self.render()

    def remember(self):
        self.events = [dict(at=c['at'].value, value=c['value'].value) for c in self.controls]

    def add(self):
        self.remember()
        if len(self.events) >= 30:
            ui.notify('Se admiten hasta 30 cambios por experimento.', type='warning')
            return
        key = self.parameter.value
        self.events.append(dict(at=max(1, int(self.draft.get('steps',100))//2),
                                value=self.draft['parameters'].get(key, 0)))
        self.render()

    def remove(self, index):
        self.remember()
        self.events.pop(index)
        self.render()

    def render(self):
        self.area.clear()
        self.controls = []
        with self.area:
            if not self.events:
                ui.label('Añade un cambio e indica su índice y la nueva demanda.').classes('muted')
            for index, event in enumerate(self.events):
                with ui.card().classes('agent-card w-full gap-3'):
                    with ui.row().classes('w-full items-center'):
                        ui.label(f'Cambio {index+1}').classes('font-semibold')
                        ui.space()
                        ui.button('Quitar cambio', icon='close', on_click=lambda _, j=index:self.remove(j)).props('flat')
                    with ui.element('div').classes('w-full grid grid-cols-1 sm:grid-cols-2 gap-3'):
                        at = ui.number('Aplicar desde el índice', value=event['at'], min=1, precision=0).props('outlined').classes('w-full')
                        value = ui.number('Nueva demanda', value=event['value']).props('outlined').classes('w-full')
                    self.controls.append(dict(at=at, value=value))

    def value(self):
        if self.enabled is None or not self.enabled.value:
            return None
        self.remember()
        events = copy.deepcopy(self.events)
        for event in events:
            at = event['at']
            if type(at) in (int,float) and at == int(at):
                event['at'] = int(at)
        return dict(version=1, parameter=self.parameter.value, events=events)
