"""Perfiles: fórmulas heterogéneas, persistencia, aislamiento y transporte real."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lab import plugins
from lab.algorithms import agent_config, build, example, refresh_registry
from lab.drafts import latest_recovery, save_recovery
from lab.equations import blank_model, generate_source, model_from_source, preview_model, validate_model
from lab.plugins import PluginSpec, install
from lab.results import catalog, global_catalog, read_records
from lab.runner import LocalRunner
from lab.storage import Store, read_json, write_json


def model():
    m = blank_model()
    m.update(id='test_profiles', name='Perfiles temporales', default_profile='square',
             fields=[['inicio', 'Inicio', 2], ['factor', 'Factor', 1]],
             function_profiles=[
                 dict(id='square', name='Cuadrado', functions=[dict(name='cost', args=['z'], expression='factor*z**2')]),
                 dict(id='fourth', name='Cuarto', functions=[dict(name='cost', args=['z'], expression='factor*z**4')])],
             states=[dict(name='x', initial='inicio', update='x', kind='next'),
                     dict(name='f', update='cost(x)', kind='derived')],
             observations=[dict(name='cost', expression='cost(x)')],
             global_metrics=[dict(name='total', expression='sum_all("cost(x)")')])
    return m


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        directory = self.root / 'algorithms'
        directory.mkdir()
        self.patch = patch.object(plugins, 'DIRECTORY', directory)
        self.patch.start()
        refresh_registry()

    def tearDown(self):
        self.doCleanups()
        self.patch.stop()
        refresh_registry()
        self.temp.cleanup()

    def configure(self, m=None, n=2):
        m = m or model()
        source = generate_source(m)
        self.assertEqual(model_from_source(source), validate_model(m))
        config = example(install(source), n, 'completa')
        config['nodes'][1]['function_profile'] = 'fourth'
        config.update(steps=4, period_s=.005)
        return config

    def test_local_dispatch_observations_global_cost_and_private_assignment(self):
        config = self.configure()
        config['nodes'][1]['params']['factor'] = 3
        rt = build(config)
        states = {i: rt.initial_state(i) for i in rt.ids}
        self.assertEqual(states[1]['f'], 4)
        self.assertEqual(states[2]['f'], 48)
        self.assertEqual(rt.observe(2, states[2], 0)['obs/cost'], 48)
        _, series = rt.module.evaluar(rt, {i: [s] * 5 for i, s in states.items()})
        self.assertEqual(series[0]['total'], 52)
        for i in rt.ids:
            local_config = agent_config(rt, i)
            local = build(local_config)
            self.assertEqual(local.initial_state(i), states[i])
            self.assertEqual(local.nodes[i]['function_profile'], rt.nodes[i]['function_profile'])
            for other in local_config['nodes']:
                if other['id'] != i:
                    self.assertNotIn('params', other)
                    self.assertNotIn('function_profile', other)

    def test_own_function_uses_own_profile_and_remote_state(self):
        m = model()
        m['states'][0]['update'] = 'x + sum_neighbors(\'own("cost(x)") - f\')'
        config = self.configure(m)
        rt = build(config)
        states = {i: rt.initial_state(i) for i in rt.ids}
        self.assertEqual(build(agent_config(rt, 1)).update(1, states[1], {2: states[2]})['x'], -10)
        self.assertEqual(build(agent_config(rt, 2)).update(2, states[2], {1: states[1]})['x'], 14)

    def test_validate_every_profile_and_reject_remote_functions(self):
        mutations = [
            lambda m: m.update(default_profile='unknown'),
            lambda m: m.update(default_profile=[]),
            lambda m: m['function_profiles'][1].update(functions=[]),
            lambda m: m['function_profiles'][1]['functions'][0].update(args=['z', 'extra']),
            lambda m: m['function_profiles'][1].update(id='square'),
            lambda m: m['states'][0].update(update='sum_neighbors("cost(x)")'),
            lambda m: m['states'][0].update(update='sum_neighbors(\'derivative("cost", x)\')'),
        ]
        for index, change in enumerate(mutations):
            m = model()
            change(m)
            with self.subTest(index=index), self.assertRaises(ValueError):
                generate_source(m)
        m = model()
        m['function_profiles'][1]['functions'] = [dict(name='helper', args=['z'], expression='z*z'),
                                                   dict(name='cost', args=['z'], expression='factor*helper(z)**2')]
        validate_model(m)  # Los auxiliares privados no tienen que repetirse.

    def test_defaults_old_config_and_saved_profile_assignments(self):
        config = self.configure(n=4)
        spec = PluginSpec(plugins.DIRECTORY / 'test_profiles.py')
        self.assertEqual([n['function_profile'] for n in spec.make_example(6, 'completa')['nodes']], ['square']*6)
        write_json(self.root / 'experiment.json', config)
        restored = build(read_json(self.root / 'experiment.json'))
        self.assertEqual(restored.nodes[2]['function_profile'], 'fourth')
        missing = copy.deepcopy(config)
        missing['nodes'][0].pop('function_profile')
        self.assertEqual(build(missing).nodes[1]['function_profile'], 'square')
        for invalid in ['deleted', []]:
            missing['nodes'][0]['function_profile'] = invalid
            with self.assertRaises(ValueError):
                build(missing)
        unfinished = model()
        unfinished['_form'] = True
        unfinished['function_profiles'][1]['functions'][0]['expression'] = 'factor*('
        folder = self.root / 'drafts'
        save_recovery(folder / 'recuperacion' / 'draft.json', unfinished)
        self.assertEqual(latest_recovery(folder)[0], unfinished)

    def test_preview_exercises_every_profile(self):
        m = model()
        for i in range(3):
            profile = copy.deepcopy(m['function_profiles'][0])
            profile.update(id=f'extra{i}', name=f'Extra {i}')
            m['function_profiles'].append(profile)
        result = preview_model(m)
        self.assertEqual(len(result['rows'][0]['states']), 5)
        self.assertEqual(set(result['profiles'].values()), {p['id'] for p in m['function_profiles']})
        self.assertEqual(result['rows'][0]['states'][2]['f'], 16)
        self.assertEqual(result['global_series'][0]['total'], 32)

    def test_profiles_transport_sync_async_and_coordinator(self):
        for mode in ('sync', 'async', 'coordinator'):
            with self.subTest(mode=mode):
                m = model()
                m.update(id='profiles_' + mode, mode=mode)
                if mode == 'coordinator':
                    m['coordinator'] = [dict(name='total', expression='sum_all("cost(x)")')]
                    m['states'][0]['update'] = 'x + 0*global_data["total"]'
                else:
                    m['states'][0]['update'] = 'x + 0*sum_neighbors("f")'
                config = self.configure(m)
                runner = LocalRunner(Store(self.root / mode))
                self.addCleanup(runner.shutdown)
                run_id = runner.start(config)
                runner.thread.join(40)
                self.assertFalse(runner.thread.is_alive())
                folder = runner.store.folder(run_id)
                self.assertEqual(read_json(folder / 'ejecucion.json')['status'], 'completed')
                self.assertTrue(read_json(folder / 'evaluacion.json')['records_valid'])
                self.assertIn('obs/cost', catalog(folder))
                self.assertIn('total', global_catalog(folder))
                self.assertEqual(read_records(folder, 1)[-1]['state']['f'], 4)
                self.assertEqual(read_records(folder, 2)[-1]['state']['f'], 16)
                local = read_json(folder / 'config_agente_1.json')
                self.assertEqual(local['nodes'][0]['function_profile'], 'square')
                self.assertNotIn('function_profile', local['nodes'][1])

    def test_tutorial_and_existing_installed_models_remain_valid(self):
        base = Path(__file__).resolve().parents[1]
        for path in (base / 'algoritmos').glob('*.py'):
            source = path.read_text(encoding='utf-8-sig')
            if 'ASISTENTE =' in source:
                with self.subTest(file=path.name):
                    preview_model(model_from_source(source), steps=2)
        path = base / 'ejemplos/perfiles'
        supplied = PluginSpec(path / 'tutorial_perfiles.py')
        config = read_json(path / 'configuracion.json')
        self.assertEqual(supplied.sha256, config['plugin_sha256'])
        install(supplied.path.read_text(encoding='utf-8'))
        rt = build(config)
        states = {i: rt.initial_state(i) for i in rt.ids}
        for k in range(rt.steps):
            states = {i: rt.update(i, states[i], {j: states[j] for j in rt.neighbors[i]}, k) for i in rt.ids}
        # Solo controla que el ejemplo no se desborde y conserve sus mediciones.
        for i, state in states.items():
            self.assertIsInstance(rt.observe(i, state, rt.steps)['obs/costo_local'], (int, float))


if __name__ == '__main__':
    unittest.main()
