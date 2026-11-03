"""Pruebas de contrato y TCP real con un algoritmo sintético temporal."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from lab import plugins
from lab.algorithms import REGISTRY, LOAD_ERRORS, agent_config, build, example, refresh_registry
from lab.plugins import inspect_source, install, flatten
from lab.results import catalog, chart_series, read_records, evaluate, global_catalog
from lab.runner import LocalRunner
from lab.storage import Store, read_json


SOURCE = '''ALGORITMO = {
 'id': 'prueba_temporal', 'name': 'Prueba temporal', 'mode': MODE,
 'fields': [{'key': 'vector', 'label': 'Vector', 'default': [1, 2], 'type': 'json'}],
 'parameters': [
   {'key': 'activo', 'label': 'Activo', 'default': True, 'type': 'boolean'},
   {'key': 'texto', 'label': 'Texto', 'default': 'prueba', 'type': 'string'},
   {'key': 'orden', 'label': 'Orden', 'default': 2, 'type': 'integer'},
   {'key': 'regla', 'label': 'Regla', 'default': 'A', 'type': 'select', 'choices': ['A', 'B']}
 ], 'metrics': [], 'steps': 5, 'period_s': 0.01
}
def preparar(rt):
    if rt.local_id is not None:
        assert [n['id'] for n in rt.config['nodes'] if 'params' in n] == [rt.local_id]
        assert [i for i,n in rt.nodes.items() if 'params' in n] == [rt.local_id]
def inicial(rt, i):
    return {'vector': rt.nodes[i]['params']['vector'], 'memoria': {'veces': 0}, 'texto': 'inicio', 'round': 7}
def paso(rt, i, propio, vecinos, k, global_data):
    if rt.mode != 'coordinator' and len(rt.ids) > 1:
        assert vecinos and all('vector' in v and 'memoria' in v for v in vecinos.values())
    if rt.mode == 'coordinator':
        assert global_data['ids'] == rt.ids
    propio['vector'][0] += i
    propio['memoria']['veces'] += 1
    propio['texto'] = 'paso'
    if k >= 2:
        propio['nueva'] = [[k, i]]
    return propio
def observar(rt, i, estado, k):
    return {'suma': sum(estado['vector'])}
def validar(rt, i, estado):
    if rt.local_id is not None:
        assert i == rt.local_id  # No validar al vecino con coeficientes ajenos.
    assert estado['vector'][1] == rt.nodes[i]['params']['vector'][1]
def coordinar(rt, k, estados):
    return {'ids': sorted(estados), 'ronda': k}
def evaluar(rt, logs):
    return {'conclusion': 'Prueba temporal completa', 'converged': True}, [{'round': k, 'total': sum(v[k]['vector'][0] for v in logs.values())} for k in range(rt.steps+1)]
'''


class FlexibleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.algorithms = self.root / 'plugins'
        self.algorithms.mkdir()
        self.patch = patch.object(plugins, 'DIRECTORY', self.algorithms)
        self.patch.start()
        refresh_registry()

    def tearDown(self):
        self.doCleanups()
        self.patch.stop()
        refresh_registry()
        self.temp.cleanup()

    def configure(self, mode='sync', n=2):
        install(SOURCE.replace('MODE', repr(mode)))
        config = example('prueba_temporal', n)
        return config

    def run_config(self, config):
        store = Store(self.root / 'data')
        runner = LocalRunner(store)
        self.addCleanup(runner.shutdown)
        run_id = runner.start(config)
        runner.thread.join(timeout=35)
        self.assertFalse(runner.thread.is_alive(), 'La ejecución no finalizó')
        record = read_json(store.folder(run_id) / 'ejecucion.json')
        if record['status'] != 'completed':
            details = [p.read_text(encoding='utf-8') for p in store.folder(run_id).glob('consola*')]
            self.fail(str(record) + str(details))
        return runner, store.folder(run_id), run_id

    def test_library_defaults_remove_restore_and_snapshot(self):
        from lab.algorithm_library import save_default, load_default, remove_algorithm, restore_algorithm
        config = self.configure()
        config['nodes'][1]['params']['vector'] = [3, 43]
        config['execution_mode'] = 'async'
        saved = save_default(self.root, config)
        spec = REGISTRY['prueba_temporal']
        self.assertEqual(load_default(self.root, spec)['nodes'][1]['params']['vector'], [3, 43])
        self.assertEqual(saved['execution_mode'], 'async')
        _, folder, _ = self.run_config(saved)
        removed = remove_algorithm(self.root, spec)
        refresh_registry()
        self.assertNotIn(spec.id, REGISTRY)
        from lab.algorithms import build_saved
        self.assertEqual(build_saved(read_json(folder / 'config.json'), folder).mode, 'async')
        self.assertTrue(evaluate(folder)['records_valid'])
        self.assertEqual(restore_algorithm(self.root, removed), spec.id)
        refresh_registry()
        self.assertEqual(load_default(self.root, REGISTRY[spec.id]), saved)
        with self.assertRaises(ValueError):
            restore_algorithm(self.root, self.root)

    def test_execution_mode_override_runs_same_file_both_ways(self):
        config = self.configure('sync')
        for mode in ('async', 'sync'):
            config['execution_mode'] = mode
            rt = build(config)
            self.assertEqual(rt.mode, mode)
            self.assertEqual(build(agent_config(rt, 1)).mode, mode)
            runner, folder, _ = self.run_config(config)
            self.assertEqual(read_json(folder / 'config.json')['execution_mode'], mode)
            runner.shutdown()
        config['execution_mode'] = 'coordinator'
        with self.assertRaises(ValueError):
            build(config)
        (self.algorithms / 'prueba_temporal.py').unlink()
        refresh_registry()
        coordinated = self.configure('coordinator')
        coordinated['execution_mode'] = 'async'
        with self.assertRaises(ValueError):
            build(coordinated)

    def test_async_terminal_global_is_visible_with_time_axis(self):
        import csv
        config = self.configure('async')
        _, folder, _ = self.run_config(config)
        with (folder / 'serie_global.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['round', 'total'])
            writer.writeheader()
            writer.writerow({'round': 5, 'total': 17})
        trace = chart_series(folder, 'total', scope='global', x_axis='@wall_s')[0]
        end = max(read_records(folder, i)[-1]['wall_s'] for i in (1, 2))
        self.assertEqual(trace['x'], [end])
        self.assertEqual(trace['y'], [17])
        self.assertEqual(trace['mode'], 'markers+text')
        self.assertEqual(trace['text'], ['17'])

    def test_empty_and_descriptor_does_not_execute(self):
        self.assertEqual(REGISTRY, {})
        source = SOURCE.replace('MODE', repr('sync')) + '\nraise RuntimeError("No importar al descubrir")\n'
        install(source)
        refresh_registry()
        self.assertIn('prueba_temporal', REGISTRY)
        self.assertEqual(example('prueba_temporal')['parameters']['texto'], 'prueba')
        (self.algorithms / 'roto.py').write_text('esto no es Python', encoding='utf-8')
        refresh_registry()
        self.assertIn('roto.py', LOAD_ERRORS)
        self.assertIn('prueba_temporal', REGISTRY)

    def test_state_copies_types_and_version(self):
        config = self.configure()
        rt = build(config)
        original = rt.initial_state(1)
        peers = {2: rt.initial_state(2)}
        after = rt.update(1, original, peers)
        self.assertEqual(original['vector'], [1, 2])
        self.assertEqual(after['vector'], [2, 2])
        self.assertEqual(peers[2]['memoria'], {'veces': 0})
        self.assertEqual(flatten({'a/b': [2], 'a': {'b': 3}}), {'a~1b/0': 2., 'a/b': 3.})
        with self.assertRaises(ValueError):
            rt.check_state(1, {'x': float('nan')})
        config['parameters']['activo'] = 1
        with self.assertRaises(ValueError):
            build(config)
        config['parameters']['activo'] = True
        (self.algorithms / 'prueba_temporal.py').write_text(SOURCE.replace('MODE', repr('sync')) + '\n# nueva versión\n', encoding='utf-8')
        refresh_registry()
        with self.assertRaises(ValueError):
            build(config)

    def test_agent_config_contains_only_own_fields_and_public_data(self):
        config = self.configure()
        config['nodes'][0]['private_note'] = 'dato privado fuera de params'
        config['nodes'][1]['params']['vector'] = [98765, 43]
        config['private_metadata'] = {'secreto': 123456}
        config['nodes'][1]['timing'] = {'period_factor': 2, 'send_delay_ms': 5, 'private_note': 'no copiar'}
        full = build(config)
        local_config = agent_config(full, 1)
        local = build(local_config)
        self.assertEqual(local.local_id, 1)
        self.assertEqual(local.fingerprint, full.fingerprint)
        self.assertEqual(local.parameters_values, full.parameters_values)
        self.assertNotIn('private_metadata', local.config)
        self.assertNotIn('private_note', local.nodes[1])
        self.assertNotIn('params', local.nodes[2])
        self.assertEqual(local.nodes[2]['timing'], {'period_factor': 2, 'send_delay_ms': 5})
        self.assertEqual(local.check_received_state(2, {'vector': [3, 43]}), {'vector': [3, 43]})
        with self.assertRaises(ValueError):
            local.check_received_state(2, {'vector': [float('nan')]})
        with self.assertRaisesRegex(ValueError, 'propio agente'):
            local.check_state(2, {'vector': [3, 43]})
        local.config['nodes'][0]['params']['vector'][0] = -1
        self.assertEqual(full.nodes[1]['params']['vector'][0], 1)
        local_config['nodes'][1]['params'] = {'vector': [1, 2]}
        with self.assertRaisesRegex(ValueError, 'parámetros ajenos'):
            build(local_config)

    def assert_run(self, mode):
        config = self.configure(mode)
        config['nodes'][1]['params']['vector'][1] = 43
        runner, folder, run_id = self.run_config(config)
        for i in (1, 2):
            view = read_json(folder / f'config_agente_{i}.json')
            self.assertEqual([n['id'] for n in view['nodes'] if 'params' in n], [i])
            meta = read_json(folder / f'nodo_{i}.json')
            self.assertEqual(meta['config_scope'], 'local')
            self.assertEqual(meta['config_sha256'], view['agent_view']['experiment_sha256'])
        self.assertTrue(all('params' in n for n in read_json(folder / 'config.json')['nodes']))
        report = read_json(folder / 'evaluacion.json')
        self.assertTrue(report['records_valid'], report)
        self.assertTrue(report['converged'])
        self.assertFalse(report['equations_verified'])
        rows = read_records(folder, 1)
        self.assertEqual(rows[-1]['state']['vector'], [6, 2])
        self.assertEqual(rows[-1]['state']['texto'], 'paso')
        keys = catalog(folder)
        self.assertIn('nueva/0/0', keys)
        self.assertIn('obs/suma', keys)
        self.assertIn('total', global_catalog(folder))
        traces = chart_series(folder, 'nueva/0/0', x_axis='vector/0', agents=[1], kind='markers')
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]['y'][:3], [None, None, None])
        self.assertEqual(traces[0]['x'][-1], 6)
        self.assertEqual(chart_series(folder, 'total', scope='global')[0]['y'][-1], 17)
        self.assertIn('value/round', (folder / 'nodo_1.csv').read_text())
        # Visualizar y exportar no depende del archivo instalado.
        (self.algorithms / 'prueba_temporal.py').unlink()
        refresh_registry()
        self.assertIn('vector/0', catalog(folder))
        with zipfile.ZipFile(runner.export(run_id)) as archive:
            self.assertIn('algoritmo.py', archive.namelist())
            self.assertIn('nodo_1.jsonl', archive.namelist())
            self.assertIn('nodo_1.csv', archive.namelist())
        meta = read_json(folder / 'nodo_1.json')
        meta['state']['vector'][0] = -99
        (folder / 'nodo_1.json').write_text(json.dumps(meta), encoding='utf-8')
        with self.assertRaises(ValueError):
            evaluate(folder)

    def test_tcp_sync(self):
        self.assert_run('sync')

    def test_tcp_async(self):
        self.assert_run('async')

    def test_tcp_coordinator(self):
        self.assert_run('coordinator')

    def test_single_agent(self):
        self.run_config(self.configure(n=1))

    def test_legacy_numeric_contract_keeps_extra_state(self):
        source = """ALGORITMO = {'id': 'anterior', 'name': 'Contrato anterior',
            'fields': [['inicio', 'Inicial', 3]], 'parameters': [['h', 'Paso', 0.1]],
            'metrics': [['x', 'Variable X']]}
def inicial(rt, i):
    return {'x': rt.nodes[i]['params']['inicio'], 'memoria': [1, 2]}
def paso(rt, i, propio, vecinos, k, global_data):
    return propio
"""
        install(source)
        runtime = build(example('anterior'))
        self.assertEqual(runtime.initial_state(1)['memoria'], [1, 2])
        self.assertIn('memoria/1', runtime.observe(1, runtime.initial_state(1), 0))

    def test_disconnected_topology_is_an_algorithm_choice(self):
        config = self.configure()
        config['edges'] = []
        self.assertEqual(build(config).neighbors, {1: {}, 2: {}})
        config['require_connected'] = True
        with self.assertRaises(ValueError):
            build(config)

    def test_evaluation_error_does_not_change_execution_status(self):
        install(SOURCE.replace('MODE', repr('sync')).replace("return {'conclusion': 'Prueba temporal completa', 'converged': True},", "raise RuntimeError('Fallo voluntario de evaluación')\n    return {},"))
        config = example('prueba_temporal')
        _, folder, _ = self.run_config(config)
        report = read_json(folder / 'evaluacion.json')
        self.assertFalse(report['records_valid'])
        self.assertFalse(report['convergence_evaluated'])
        self.assertIn('Fallo voluntario', report['conclusion'])

    def test_stop_keeps_partial_results(self):
        config = self.configure()
        config.update(steps=10000, period_s=.03)
        store = Store(self.root / 'stop')
        runner = LocalRunner(store)
        try:
            run_id = runner.start(config)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not (store.folder(run_id) / 'nodo_1.jsonl').exists():
                time.sleep(.05)
            runner.stop()
            runner.thread.join(15)
            self.assertFalse(runner.thread.is_alive())
            self.assertEqual(read_json(store.folder(run_id) / 'ejecucion.json')['status'], 'stopped')
            self.assertTrue(runner.export(run_id).exists())
            self.assertFalse((store.folder(run_id) / 'evaluacion.json').exists())
        finally:
            runner.shutdown()


if __name__ == '__main__':
    unittest.main()
