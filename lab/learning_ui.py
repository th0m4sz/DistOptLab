# Función de este módulo: Muestra las explicaciones y ejemplos didácticos del asistente.
"""Ayuda didáctica separada del motor de ecuaciones y del transporte."""
from pathlib import Path
import re
from latex2mathml.converter import convert
from nicegui import ui
from nicegui.elements.markdown import prepare_content

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / 'docs' / 'PRIMER_ALGORITMO.md'
EXAMPLE = ROOT / 'ejemplos' / 'gradiente'

def guide_markdown(content):
    """Guía con MathML local; conserva literalmente las tablas y el código.

    Protegemos las fórmulas antes de Markdown para que sus guiones bajos y
    barras no se interpreten como formato de texto. El HTML final se sanea.
    """
    formulas = []

    def protect(match):
        value = match.group(0)
        if value.startswith('`'):
            return value
        block = value.startswith('$$')
        latex = value[2:-2] if block else value[1:-1]
        token = f'GUIDEMATHPLACEHOLDER{len(formulas)}END'
        math = convert(latex.strip(), display='block' if block else 'inline')
        formulas.append((token, math, block))
        return '\n\n'+token+'\n\n' if block else token

    protected = re.sub(r'```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$', protect, content)
    html = prepare_content(protected, extras='fenced-code-blocks tables')
    for token, math, block in formulas:
        if block:
            html = html.replace(f'<p>{token}</p>', f'<div class="guide-equation">{math}</div>')
        else:
            html = html.replace(token, math)
    return ui.html(html, sanitize=True).classes('nicegui-markdown')

STEP_HELP = [
    ('Identifica tu método', 'Escribe un nombre y elige qué información recibirá cada agente. Si estás empezando, usa el ejemplo explicado de abajo.'),
    ('Declara los datos de entrada', 'Añade un campo por cada constante que quieras ajustar antes del ensayo. Común = igual para todos; local = un valor por agente. Las variables que cambian en el tiempo van en el paso 4.'),
    ('Escribe tus funciones, si las necesitas', 'Una función calcula un resultado: escribe su nombre, el argumento que recibe y solo el lado derecho de la expresión. Puedes omitir este paso si tus reglas no necesitan funciones auxiliares.'),
    ('Define lo que cambia en cada iteración', 'Añade una fila por variable que el agente debe recordar. Escribe con qué valor empieza y cómo calcula el siguiente. Si ya tienes ecuaciones discretas, elige Valor siguiente.'),
    ('Elige qué medir', 'Tus estados ya se pueden graficar. Añade aquí otras cantidades calculadas. Las mediciones no modifican las reglas del paso 4. Puedes omitir este paso.'),
    ('Prueba, crea y ejecuta', 'Primero prueba las ecuaciones. Después crea tu archivo. En la pantalla principal podrás elegir agentes, conexiones y datos antes de iniciar un experimento real.'),
]


def step_help(index, expanded=False):
    title, explanation = STEP_HELP[index]
    text = GUIDE.read_text(encoding='utf-8')
    section = text.split(f'<!-- paso:{index+1} -->', 1)[1].split('<!-- paso:', 1)[0]
    with ui.expansion('Guía del paso · ' + title, icon='help_outline', value=expanded).props('dense').classes('w-full border rounded-lg bg-teal-50'):
        ui.label(explanation).classes('px-3 pt-2 text-sm font-medium')
        ui.label('Ejemplo básico de gradiente y explicación').classes('px-3 pt-2 text-sm text-primary')
        guide_markdown(section).classes('w-full px-3 pb-3 learning-prose')


def neighbor_help(mode_control):
    """Ayuda de sintaxis, sin insertar ni decidir ecuaciones del usuario."""
    with ui.expansion('Ayuda: sumatorias y funciones entre vecinos', icon='help_outline').classes('w-full md:col-span-2') as help_box:
        help_box.bind_visibility_from(mode_control, 'value', backward=lambda mode: mode in ('sync', 'async'))
        ui.label('Para una sumatoria sobre vecinos, usa sum_neighbors. Entre comillas escribe la operación sobre los datos recibidos de cada vecino; no se incluye tu propio agente.').classes('text-sm')
        ui.table(columns=[dict(name=k, field=k, label=label, align='left') for k, label in
                          [('expression', 'Expresión'), ('meaning', 'Qué calcula')]], rows=[
            dict(expression='sum_neighbors("x")', meaning='Suma de los valores x recibidos de tus vecinos.'),
            dict(expression='sum_neighbors("x*y")', meaning='Multiplica los valores x e y recibidos de cada vecino y suma los productos.'),
            dict(expression='sum_neighbors("q")', meaning='Suma q recibido. Si q=g(x) necesita parámetros locales, cada emisor calcula q como estado algebraico.'),
            dict(expression="sum_neighbors('own(\"x\") - x')", meaning='Suma tu valor x menos el x de cada vecino. own conserva los datos del agente que actualiza.'),
            dict(expression='weighted_neighbors("x")', meaning='Suma x de cada vecino multiplicado por el peso de su enlace; no normaliza.'),
            dict(expression='mean_neighbors("x")', meaning='Promedio sin pesos de los vecinos; requiere al menos un vecino.'),
        ]).classes('w-full').props('wrap-cells hide-bottom')
        ui.label('Ejemplo: si recibes x=2 y x=5, la suma es 7 y el promedio es 3.5. Estas son sumas de vecinos, no de toda la red.').classes('text-sm')
        ui.label('Fuera de las comillas, x es tu valor propio. Dentro, x es el valor recibido del vecino. Por ejemplo, x*sum_neighbors("y") multiplica tu x por la suma de sus y. Las variables x e y deben existir en los estados; los parámetros privados del vecino no están disponibles.').classes('text-sm')
        ui.label('Para mezclar ambos, usa own("expresión"): own("q") lee tu q; own("g(x)") calcula g con tu x y tus parámetros. El resto usa datos recibidos y parámetros comunes. Por ejemplo: weighted_neighbors(\'own("q")-q\'). Puedes usar comillas simples por fuera y dobles dentro.').classes('text-sm')
        ui.label('En modo síncrono se usan datos de la misma ronda; en asíncrono, las últimas muestras recibidas.').classes('text-sm text-slate-500')


def open_learning(on_load, on_inspect, on_load_profiles=None, on_inspect_profiles=None):
    with ui.dialog() as dialog, ui.card().style('width:1050px;max-width:96vw;max-height:92vh').classes('gap-3'):
        with ui.row().classes('w-full items-center shrink-0'):
            ui.label('Primera vez · aprende con un ejemplo').classes('section-title')
            ui.space()
            ui.button('Cerrar', on_click=dialog.close).props('flat')
        ui.label('Elige un recorrido. Puedes volver a esta guía en cualquier momento.').classes('muted shrink-0')
        with ui.row().classes('w-full gap-3 shrink-0'):
            def inspect():
                dialog.close()
                on_inspect()
            def load():
                if on_load():
                    dialog.close()
            ui.button('1. Abrir ecuaciones explicadas', icon='menu_book', on_click=inspect).props('unelevated')
            ui.button('2. Cargar ejemplo listo para ejecutar', icon='science', on_click=load).props('outline')
        with ui.column().classes('w-full overflow-auto').style('min-height:0'):
            if on_load_profiles is not None:
                with ui.expansion('Ampliación: funciones distintas por agente', icon='account_tree').classes('w-full border rounded-lg'):
                    ui.label('Dos perfiles, una actualización compartida. Aprende a asignarlos y a pasar de 4 a 6 agentes.')
                    def inspect_profiles():
                        dialog.close()
                        on_inspect_profiles()
                    def load_profiles():
                        if on_load_profiles():
                            dialog.close()
                    with ui.row():
                        ui.button('Abrir ecuaciones con perfiles', on_click=inspect_profiles).props('outline')
                        ui.button('Cargar ejemplo de dos perfiles', on_click=load_profiles).props('unelevated')
                    guide_markdown((ROOT / 'docs' / 'PERFILES_FUNCIONES.md').read_text(encoding='utf-8')).classes('w-full learning-prose')
            guide_markdown(GUIDE.read_text(encoding='utf-8')).classes('w-full learning-prose')
    dialog.open()
