# Función de este módulo: Construye los controles para editar familias de funciones y sus perfiles.
"""Edición opcional de familias de funciones; conserva el formulario sencillo."""
import copy
import uuid

from nicegui import ui
from .presentation import help_details


class FunctionProfilesEditor:
    def __init__(self, model, editor_class):
        self.editor_class = editor_class
        self.on_change = None
        self.controls = []
        self.profiles = copy.deepcopy(model.get('function_profiles', []))
        self.default = model.get('default_profile')
        self.functions = copy.deepcopy(model.get('functions', []))
        self.rows = []
        self.area = ui.column().classes('w-full gap-3')
        self.render()

    def notify(self):
        if self.on_change:
            self.on_change()

    def function_editor(self, functions):
        editor = self.editor_class('Funciones matemáticas opcionales', [
            ('name', 'Nombre de función', None, ''),
            ('args', 'Argumentos, separados por coma', None, 'z'),
            ('expression', 'Expresión de la función', None, '')],
            [{**r, 'args': r['args'] if isinstance(r.get('args'), str)
              else ', '.join(r.get('args', ['z']))} for r in functions],
            'Una función guarda una fórmula local. Para enviar su resultado, úsala en un estado algebraico del paso 4. '
            'Puede usar parámetros y funciones anteriores. Para dependencia temporal, recibe k como argumento.',
            'Añadir función')
        editor.on_change = self.notify
        for row in editor.controls:
            for control in row.values():
                control.on_value_change(lambda _: self.notify())
        return editor

    def snapshot(self):
        if self.profiles:
            self.profiles = [dict(id=key, name=name.value, functions=editor.get())
                             for key, name, editor in self.rows]
        else:
            self.functions = self.base.get()

    def get(self):
        return [] if self.profiles else self.base.get()

    def metadata(self):
        if not self.profiles:
            return {}
        return dict(default_profile=self.default, function_profiles=[
            dict(id=key, name=name.value, functions=editor.get()) for key, name, editor in self.rows])

    def activate(self):
        self.snapshot()
        self.default = 'general'
        self.profiles = [dict(id=self.default, name='General', functions=self.functions)]
        self.render()
        self.notify()

    def duplicate(self, key):
        if len(self.profiles) >= 30:
            ui.notify('El asistente admite hasta 30 perfiles.', type='warning')
            return
        self.snapshot()
        original = next(p for p in self.profiles if p['id'] == key)
        self.profiles.append(dict(id='perfil_' + uuid.uuid4().hex[:10],
                                 name=original['name'] + ' · copia', functions=copy.deepcopy(original['functions'])))
        self.render()
        self.notify()

    def remove(self, key):
        self.snapshot()
        if len(self.profiles) == 1:
            return
        self.profiles = [p for p in self.profiles if p['id'] != key]
        if self.default == key:
            self.default = self.profiles[0]['id']
        self.render()
        self.notify()

    def rename(self):
        self.selector.set_options({key: name.value or 'Sin nombre' for key, name, _ in self.rows}, value=self.default)
        self.notify()

    def render(self):
        self.area.clear()
        self.rows = []
        with self.area:
            if not self.profiles:
                self.base = self.function_editor(self.functions)
                ui.label('Todos usan estas fórmulas con sus propios datos. Para fórmulas distintas, puedes crear perfiles.').classes('muted')
                ui.button('Usar perfiles de funciones', icon='account_tree', on_click=self.activate).props('outline')
                return
            ui.label('Perfiles de funciones locales').classes('section-title')
            help_details('Cómo comparten las reglas los distintos perfiles', 'Cada perfil define sus fórmulas. Conserva los nombres y argumentos que uses en las reglas '
                     'compartidas (por ejemplo costo(z) y gradiente(z)). La actualización del paso 4 es común. '
                     'No es obligatorio tener coste ni fitness.')
            def choose(event):
                self.default = event.value
                self.notify()
            self.selector = ui.select({p['id']: p['name'] or 'Sin nombre' for p in self.profiles},
                                      value=self.default, label='Perfil predeterminado para agentes nuevos',
                                      on_change=choose).props('outlined').classes('w-full')
            ui.label('Asigna los perfiles por agente en el experimento. Los agentes nuevos reciben el perfil predeterminado.').classes('muted')
            for profile in self.profiles:
                with ui.card().classes('w-full gap-3 bg-teal-50'):
                    name = ui.input('Nombre del perfil', value=profile['name']).props('outlined').classes('w-full')
                    editor = self.function_editor(profile.get('functions', []))
                    self.rows.append((profile['id'], name, editor))
                    name.on_value_change(lambda _: self.rename())
                    with ui.row():
                        ui.button('Duplicar perfil', icon='content_copy', on_click=lambda key=profile['id']: self.duplicate(key)).props('outline')
                        ui.button('Eliminar perfil', icon='delete_outline', on_click=lambda key=profile['id']: self.remove(key)).props('flat').set_enabled(len(self.profiles) > 1)
