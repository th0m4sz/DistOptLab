"""Casos matemáticos temporales: nunca se incorporan al catálogo de la aplicación."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab import plugins
from lab.algorithms import agent_config, build, example, refresh_registry
from lab.equations import blank_model, generate_source, model_from_source, preview_model, validate_model
from lab.plugins import PluginSpec, install
from lab.results import catalog, global_catalog, read_records
from lab.runner import LocalRunner
from lab.storage import Store, read_json


def state(name, initial, update, kind='next', **extra):
    return dict(name=name, label=name, initial=initial, update=update, kind=kind, **extra)


def metric(name, expression):
    return dict(name=name, label=name, expression=expression)


def economic_model():
    """Equivalente a CCRD/RCCRD: las ecuaciones pertenecen solo a esta prueba."""
    m = blank_model()
    m.update(id='prueba_economica', name='Prueba económica temporal', mode='coordinator', integration_step='h')
    m['parameters'] = [['robust', 'Robusto', 1], ['h', 'Paso', .002], ['demand_kw', 'Demanda', 12], ['B', 'B', 30]]
    m['fields'] = [['pmin', 'Mínimo', 0], ['pmax', 'Máximo', 10], ['x0', 'Inicial', 2],
                   ['a', 'a', 0], ['b', 'b', 1], ['c', 'c', .5]]
    m['functions'] = [dict(name='coste', args=['z'], expression='a+b*z+c*z**2'),
                      dict(name='marginal', args=['z'], expression='b+2*c*z')]
    m['states'] = [state('x', 'x0', 'hat*(fitness-global_data["media"])', 'euler'),
                   state('fitness', '', 'B-marginal(x)', 'derived'),
                   state('hat', '', '(x-pmin)*(pmax-x)', 'derived')]
    m['coordinator'] = [metric('media_base', 'sum_all("hat*fitness")/sum_all("hat")'),
                         metric('media', 'media_base*sum_all("x-pmin")/(demand_kw-sum_all("pmin")) if robust else media_base')]
    m['checks'] = [dict(expression='pmin <= x <= pmax', message='Potencia fuera de límites')]
    m['observations'] = [metric('coste_local', 'coste(x)')]
    m['global_metrics'] = [metric('total', 'sum_all("x")'), metric('balance', 'total-demand_kw'),
                            metric('coste_total', 'sum_all("coste(x)")')]
    m['criterion'] = 'abs(balance)<0.01'
    return m


def tracking_model():
    m = blank_model()
    m.update(id='prueba_tracking', name='Seguimiento temporal')
    m['parameters'] = [['alpha', 'Paso', .1]]
    m['fields'] = [['centro', 'Centro', 1], ['inicio', 'Inicial', 0], ['self_w', 'Peso propio', .5]]
    m['functions'] = [dict(name='gradiente', args=['z'], expression='z-centro')]
    m['states'] = [state('x', 'inicio', 'self_w*x+weighted_neighbors("x")-alpha*y'),
                   state('y', 'gradiente(x)', 'self_w*y+weighted_neighbors("y")+gradiente(next_x)-gradiente(x)')]
    m['global_metrics'] = [metric('dispersion', 'max_all("x")-min_all("x")')]
    return m


class EquationTests(unittest.TestCase):
    def test_received_fitness_does_not_require_neighbor_coefficients(self):
        m = blank_model()
        m.update(id='received_values', name='Mensajes locales')
        m['fields'] = [['factor','Factor',2], ['inicio','Inicial',3]]
        m['functions'] = [dict(name='cost', args=['z'], expression='factor*z')]
        m['states'] = [state('x','inicio', 'x+weighted_neighbors(\'own("f")-f\')'),
                       state('f','', 'cost(x)', kind='derived')]
        config = self.configure(m, 2)
        config['edges'] = [[1,2,.5]]
        config['nodes'][1]['params'].update(factor=4, inicio=5)
        rt = build(config)
        a,b = rt.initial_state(1),rt.initial_state(2)
        local = build(agent_config(rt, 1))
        self.assertNotIn('params', local.nodes[2])
        result = local.update(1,a,{2:b})
        self.assertEqual(result, {'x':-4, 'f':-8})
    def test_own_inside_neighbor_sum_keeps_local_function_parameters(self):
        m = blank_model()
        m.update(id='own_test', name='Intercambio')
        m['fields'] = [['factor', 'Factor', 2], ['inicio', 'Inicial', 3]]
        m['functions'] = [dict(name='f', args=['z'], expression='factor*z')]
        m['states'] = [state('x', 'inicio', 'x + weighted_neighbors(\'own("f(x)") - recibido\')'),
                       state('recibido', '', 'f(x)', kind='derived')]
        config = self.configure(m, 2)
        config['edges'] = [[1, 2, .5]]
        config['nodes'][1]['params'].update(factor=4, inicio=5)
        rt = build(config)
        a, b = rt.initial_state(1), rt.initial_state(2)
        self.assertEqual(rt.update(1, a, {2:b})['x'], -4)
        self.assertEqual(rt.update(2, b, {1:a})['x'], 12)
        self.assertEqual(a['x'], 3)
        m['states'][0]['update'] = 'mean_neighbors(\'own("[x, factor]") - [x, 2]\')'
        result = preview_model(m)
        self.assertEqual(result['rows'][1]['states'][1]['x'], [0, 0])

    def test_neighbor_private_parameters_rejected_even_in_preview(self):
        m = blank_model()
        m.update(id='private_values', name='Datos privados')
        m['fields'] = [['factor', 'Factor', 2]]
        m['functions'] = [dict(name='f', args=['z'], expression='factor*z')]
        for expression in ('sum_neighbors("factor*x")', 'sum_neighbors("f(x)")'):
            m['states'] = [state('x', '1', expression)]
            with self.subTest(expression=expression), self.assertRaisesRegex(ValueError, 'parámetros privados'):
                preview_model(m)

    def test_own_rejects_invalid_context_and_unknown_local_names(self):
        for expression in ('own("x")', 'sum_all(\'own("x")\')',
                           'sum_neighbors(\'own("no_existe")\')',
                           'sum_neighbors(\'own("next_x")\')',
                           'sum_neighbors(\'own("own(1)")\')'):
            m = tracking_model()
            m['states'][0]['update'] = expression
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                generate_source(m)

    def test_local_functions_keep_parameter_scope(self):
        model = blank_model()
        model.update(id='scope_test', name='Scope test')
        model['parameters'] = [['a', 'Coefficient', 2]]
        model['functions'] = [dict(name='cost', args=['z'], expression='a*z'),
                              dict(name='outer', args=['a'], expression='cost(a)')]
        model['states'] = [state('x', 'outer(3)', 'outer(x)')]
        rows = preview_model(model)['rows']
        self.assertEqual(rows[0]['states'][1]['x'], 6)
        self.assertEqual(rows[1]['states'][1]['x'], 12)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.algorithms = self.root / 'algorithms'
        self.algorithms.mkdir()
        self.patch = patch.object(plugins, 'DIRECTORY', self.algorithms)
        self.patch.start()
        refresh_registry()

    def tearDown(self):
        self.doCleanups()
        self.patch.stop()
        refresh_registry()
        self.temp.cleanup()

    def configure(self, model, n=4):
        source = generate_source(model)
        self.assertEqual(model_from_source(source), validate_model(model))
        return example(install(source), n)

    def test_existing_dispatch_equations_match_without_core_adapter(self):
        reference = Path(__file__).resolve().parents[2] / 'plataforma/algoritmos/ccrd_coordinado.py'
        if not reference.is_file():
            self.skipTest('Comparación opcional: la plataforma original no forma parte de la distribución.')
        config = self.configure(economic_model())
        engine = build(config)
        old = PluginSpec(reference)
        old_config = old.make_example(4, 'anillo')
        old_engine = old(old_config)
        ours = {i: engine.initial_state(i) for i in engine.ids}
        theirs = {i: old_engine.initial_state(i) for i in old_engine.ids}
        for k in range(20):
            aggr = engine.aggregate(k, ours)
            old_aggr = old_engine.aggregate(k, theirs)
            ours = {i: engine.update(i, ours[i], {}, k, aggr) for i in engine.ids}
            theirs = {i: old_engine.update(i, theirs[i], {}, k, old_aggr) for i in engine.ids}
            for i in ours:
                for key in ('x', 'fitness', 'hat'):
                    self.assertAlmostEqual(ours[i][key], theirs[i][key], places=11)

    def test_tracking_uses_new_local_state_and_old_neighbor_state(self):
        config = self.configure(tracking_model(), 2)
        config['edges'] = [[1, 2, .5]]
        config['nodes'][1]['params']['centro'] = 3
        rt = build(config)
        a, b = rt.initial_state(1), rt.initial_state(2)
        out_a = rt.update(1, a, {2: b})
        out_b = rt.update(2, b, {1: a})
        self.assertAlmostEqual(out_a['x'], .1)
        self.assertAlmostEqual(out_b['x'], .3)
        self.assertAlmostEqual(out_a['y'], -1.9)
        self.assertAlmostEqual(out_b['y'], -1.7)
        self.assertEqual(a, {'x': 0, 'y': -1})

    def test_vectors_numerical_gradient_and_projection(self):
        m = blank_model()
        m.update(id='vectores', name='Vectores')
        m['functions'] = [dict(name='objetivo', args=['z'], expression='dot(z,z)')]
        m['states'] = [state('x', '[1, 2]', 'x-0.1*gradient("objetivo",x)', lower='[0, 0]', upper='[0.7, 1.5]')]
        result = preview_model(m)
        vector = result['rows'][1]['states'][1]['x']
        self.assertEqual(vector, [.7, 1.5])
        m['states'][0]['upper'] = '[-1, 1]'
        with self.assertRaisesRegex(ValueError, 'inferior'):
            preview_model(m)

    def test_invalid_expressions_and_order(self):
        for expression in ('__import__("os")', 'x.__class__', '(lambda: 1)()', 'open("archivo")',
                           'x^2', 'next_y', 'sum_all("x")', 'weighted_neighbors("no_existe")'):
            with self.subTest(expression=expression):
                m = tracking_model()
                m['states'][0]['update'] = expression
                with self.assertRaises(ValueError):
                    generate_source(m)
        m = tracking_model()
        m['states'][0]['update'] = 'x/0'
        with self.assertRaisesRegex(ValueError, 'agente 1'):
            preview_model(m)

    def test_optional_cost_and_state_memory(self):
        m = blank_model()
        m.update(id='sin_coste', name='Sin costo')
        m['states'] = [state('x', 'i', 'x+prev'), state('prev', '0', 'x')]
        values = preview_model(m)['rows']
        self.assertEqual(values[2]['states'][1], {'x': 2, 'prev': 1})

    def test_standalone_python_dispatch_can_include_its_own_evaluator(self):
        # Adaptar únicamente el archivo del algoritmo; ningún módulo económico va al núcleo.
        root = Path(__file__).resolve().parents[2] / 'plataforma'
        if not (root / 'algoritmos/ccrd_coordinado.py').is_file() or not (root / 'lab/allocation.py').is_file():
            self.skipTest('Comparación opcional: requiere los archivos históricos de la plataforma original.')
        source = (root / 'algoritmos/ccrd_coordinado.py').read_text(encoding='utf-8')
        evaluator = (root / 'lab/allocation.py').read_text(encoding='utf-8')
        source = source.replace('    from lab.allocation import evaluate_allocation\n', '') + '\n' + evaluator
        source = source.replace('reference_dispatch=reference,', "reference_dispatch={str(i): x for i, x in reference.items()} if reference else None,")
        # La preparación global antigua solo pertenece al gestor/coordinador.
        # Las comprobaciones locales siguen ejecutándose en validar().
        source = source.replace('def preparar(ctx):',
                                'def preparar(ctx):\n    if ctx.local_id is not None:\n        return')
        config = example(install(source), 4)
        config.update(steps=10)
        self.assertEqual(self.run_tcp(config)['status'], 'completed')

    def run_tcp(self, config):
        runner = LocalRunner(Store(self.root / 'data'))
        self.addCleanup(runner.shutdown)
        run_id = runner.start(config)
        runner.thread.join(40)
        self.assertFalse(runner.thread.is_alive())
        folder = runner.store.folder(run_id)
        record = read_json(folder / 'ejecucion.json')
        report = read_json(folder / 'evaluacion.json')
        self.assertEqual(record['status'], 'completed', record)
        self.assertTrue(report['records_valid'], report)
        self.folder, self.report = folder, report
        return record

    def test_generated_dispatch_real_tcp_and_all_requested_charts(self):
        config = self.configure(economic_model())
        config.update(steps=20, period_s=0)
        self.run_tcp(config)
        self.assertTrue({'x', 'hat', 'fitness', 'obs/coste_local'} <= set(catalog(self.folder)))
        self.assertTrue({'total', 'balance', 'coste_total'} <= set(global_catalog(self.folder)))
        self.assertEqual(len(read_records(self.folder, 1)), 21)

    def test_generated_tracking_real_tcp(self):
        config = self.configure(tracking_model(), 2)
        config.update(steps=15, period_s=0)
        config['edges'] = [[1, 2, .5]]
        self.run_tcp(config)

    def test_async_global_results_only_terminal(self):
        m = tracking_model()
        m['mode'] = 'async'
        config = self.configure(m, 2)
        config.update(steps=8, period_s=.01)
        config['edges'] = [[1, 2, .5]]
        self.run_tcp(config)
        self.assertIn('terminales', self.report['conclusion'])
        self.assertEqual(len((self.folder / 'serie_global.csv').read_text().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
