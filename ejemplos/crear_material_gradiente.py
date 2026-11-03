"""Regenera los archivos didácticos; nunca instala ni ejecuta el algoritmo."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.equations import blank_model, generate_source
from lab.plugins import PluginSpec


def material():
    model = blank_model()
    model.update(id='tutorial_gradiente', name='Ejemplo guiado · seguimiento de gradiente',
                 description='Tres agentes minimizan la suma de sus costos cuadráticos. Tutorial con red completa y promedios uniformes. Consulta la guía antes de cambiar la topología.')
    model['parameters'] = [dict(key='alpha', label='Paso del gradiente (alpha)', type='number', default=0.1, min=0.000001)]
    model['fields'] = [dict(key='centro', label='Centro del costo local', type='number', default=2),
                       dict(key='inicio', label='Valor inicial de x', type='number', default=0)]
    model['functions'] = [dict(name='costo', args=['z'], expression='0.5*(z-centro)**2'),
                          dict(name='gradiente', args=['z'], expression='z-centro')]
    model['states'] = [dict(name='x', label='Decisión local x', kind='next', initial='inicio',
                            update='(x + sum_neighbors("x"))/n - alpha*y', lower='', upper=''),
                        dict(name='y', label='Seguimiento del gradiente y', kind='next', initial='gradiente(x)',
                            update='(y + sum_neighbors("y"))/n + gradiente(next_x) - gradiente(x)', lower='', upper='')]
    model['observations'] = [dict(name='costo_local', label='Costo local', expression='costo(x)'),
                             dict(name='gradiente_local', label='Gradiente local', expression='gradiente(x)')]
    model['global_metrics'] = [dict(name='separacion', label='Separación entre decisiones', expression='max_all("x") - min_all("x")'),
                               dict(name='suma_costos', label='Suma de costos locales', expression='sum_all("costo(x)")')]
    # Sin criterio de óptimo ni comparación teórica automática, por petición del usuario.
    return model


if __name__ == '__main__':
    directory = Path(__file__).resolve().parent / 'gradiente'
    directory.mkdir(exist_ok=True)
    model = material()
    (directory / 'modelo.json').write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding='utf-8')
    plugin = directory / 'tutorial_gradiente.py'
    plugin.write_text(generate_source(model), encoding='utf-8')
    spec = PluginSpec(plugin)
    config = spec.make_example(3, 'completa')
    config.update(name='Tutorial · tres agentes con centros 1, 3 y 5', steps=100, period_s=0.01)
    for node, center in zip(config['nodes'], [1, 3, 5]):
        node['params'].update(centro=center, inicio=0)
    (directory / 'configuracion.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
