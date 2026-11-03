"""Coordinador por últimas muestras: protocolo, TCP real, despliegue y fallas."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab import plugins
from lab.algorithms import agent_config, build, build_saved, example, refresh_registry
from lab.plugins import install
from lab.results import read_records, global_rows
from lab.runner import LocalRunner
from lab.storage import Store, read_json
from lab.transport import Coordinator
import test_remote as remote_fixture


SOURCE = '''ALGORITMO={'id':'prueba_coor_async','name':'Prueba genérica','mode':'coordinator',
'parameters':[],'fields':[],'metrics':[['x','x']]}
def inicial(rt,i): return {'x':float(i)}
def paso(rt,i,propio,vecinos,k,global_data):
    assert not vecinos
    return {'x':propio['x']+.001*(global_data['sum']-propio['x'])}
def coordinar(rt,k,estados):
    assert set(estados)==set(rt.active_ids)
    return {'sum':sum(s['x'] for s in estados.values())}
'''


class CoordinatorAsyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.models = self.root/'algorithms'
        self.models.mkdir()
        self.patch = patch.object(plugins,'DIRECTORY',self.models)
        self.patch.start()
        refresh_registry()
        install(SOURCE)

    def tearDown(self):
        self.doCleanups()
        self.patch.stop()
        refresh_registry()
        self.temp.cleanup()

    def config(self):
        c = example('prueba_coor_async',3)
        c.update(steps=60,period_s=.001,coordinator_exchange='async')
        c['nodes'][1]['timing']={'period_factor':5}
        return c

    def runner(self):
        runner = LocalRunner(Store(self.root/'data'))
        self.addCleanup(runner.shutdown)
        return runner

    def complete(self,runner,run):
        runner.thread.join(65)
        self.assertFalse(runner.thread.is_alive())
        folder = runner.store.folder(run)
        record = read_json(folder/'ejecucion.json')
        report = read_json(folder/'evaluacion.json')
        consoles = '\n'.join(p.read_text(encoding='utf-8') for p in folder.glob('consola*'))
        self.assertEqual(record['status'],'completed',str(record)+consoles)
        self.assertTrue(report['records_valid'],report)
        return folder,report

    def verify_inputs(self,folder):
        c = read_json(folder/'config.json')
        rt = build_saved(c,folder)
        logs = {i:read_records(folder,i) for i in rt.ids}
        unequal = False
        for i in rt.ids:
            view = read_json(folder/f'config_agente_{i}.json')
            self.assertEqual(view['coordinator_exchange'],'async')
            self.assertEqual([n['id'] for n in view['nodes'] if 'params' in n],[i])
            for line in (folder/f'entradas_{i}.jsonl').read_text().splitlines():
                entry = json.loads(line)
                k = entry['k']
                samples = entry['coordinator']['sources']
                unequal |= len({v['version'] for v in samples.values()})>1
                states = {int(j):logs[int(j)][v['version']]['state'] for j,v in samples.items()}
                rt.active_ids = sorted(states)
                # En este algoritmo puro, el agregado realmente usado coincide
                # con las muestras archivadas (no con rondas fabricadas).
                self.assertEqual(rt.aggregate(k,states),entry['global_data'])
                self.assertEqual(samples[str(i)]['version'],k)
        return unequal

    def test_latest_does_not_wait_for_slow_agent_and_retries_are_idempotent(self):
        rt = build(self.config())
        endpoint = Coordinator(rt,'test')
        def request(i,k,x):
            return endpoint.respond(dict(protocol=2,run='test',config=rt.fingerprint,
                                         **{'from':i},round=k,state={'x':float(x)}))
        self.assertEqual(request(1,0,1)['status'],'wait')
        self.assertEqual(request(2,0,2)['status'],'wait')
        self.assertEqual(request(3,0,3)['status'],'ok')
        first = request(1,0,1)
        fast = request(1,40,10)
        self.assertEqual(fast['status'],'ok')
        self.assertEqual(fast['aggregate']['sum'],15)
        self.assertEqual(fast['coordinator']['sources']['2']['version'],0)
        self.assertEqual(request(1,40,10),fast)
        with self.assertRaisesRegex(ValueError,'retrocedida'):
            request(1,0,1)
        self.assertEqual(first['coordinator']['sources']['1']['version'],0)
        sequence = endpoint.sequence
        published = endpoint.respond(dict(protocol=2,run='test',config=rt.fingerprint,
            **{'from':1},round=rt.steps,state={'x':20.0},publish_only=True))
        self.assertTrue(published['published'])
        self.assertEqual(endpoint.sequence,sequence)  # Publicar no ejecuta otro agregado.
        self.assertEqual(request(2,1,2)['aggregate']['sum'],25)

    def test_sync_still_requires_same_round(self):
        c = self.config()
        c['coordinator_exchange']='sync'
        rt = build(c)
        endpoint = Coordinator(rt,'test')
        def request(i,k):
            return endpoint.respond(dict(protocol=2,run='test',config=rt.fingerprint,
                                         **{'from':i},round=k,state={'x':float(i)}))
        self.assertEqual(request(1,0)['status'],'wait')
        self.assertEqual(request(2,0)['status'],'wait')
        self.assertEqual(request(3,0)['status'],'ok')
        self.assertEqual(request(1,1)['status'],'wait')

    def test_local_generic_coordinator_has_mixed_versions(self):
        runner=self.runner()
        folder,_=self.complete(runner,runner.start(self.config()))
        self.assertTrue(self.verify_inputs(folder))

    def test_remote_generic_preserves_policy_and_private_views(self):
        runner=self.runner()
        c=self.config()
        sessions={i:remote_fixture.Session(self.root/f'pi{i}',f'pi-{i}') for i in (1,2,3)}
        devices={i:dict(id=str(i),name=f'Pi {i}',host=f'pi-{i}.local',port=22,user='admin') for i in sessions}
        with patch('lab.devices.resolve_host',return_value='127.0.0.1'):
            folder,_=self.complete(runner,runner.start_remote(c,devices,sessions))
        self.assertTrue(self.verify_inputs(folder))
        self.assertTrue(all(s.closed for s in sessions.values()))

    def test_failure_and_return_require_fresh_phase_samples(self):
        for state_policy in ('keep','reset_returning'):
            with self.subTest(state_policy=state_policy):
                runner=LocalRunner(Store(self.root/state_policy))
                self.addCleanup(runner.shutdown)
                c=self.config()
                c['faults']=dict(version=2,state_policy=state_policy,events=[dict(target='agent',nodes=[3],start=15,end=30)])
                folder,_=self.complete(runner,runner.start(c))
                self.verify_inputs(folder)
                for i in (1,2):
                    entries=[json.loads(x) for x in (folder/f'entradas_{i}.jsonl').read_text().splitlines()]
                    for e in entries:
                        sources=e['coordinator']['sources']
                        if 15<=e['k']<30:
                            self.assertNotIn('3',sources)
                        if e['k']>=30:
                            self.assertGreaterEqual(sources['3']['version'],30)
                if state_policy=='reset_returning':
                    self.assertEqual(read_records(folder,3)[30]['state']['x'],3)

    def test_coordinator_failure_interrupts_without_deadlock(self):
        runner=self.runner()
        c=self.config()
        c['faults']=dict(version=2,state_policy='keep',events=[dict(target='coordinator',start=15,end=None)])
        folder,report=self.complete(runner,runner.start(c))
        self.assertEqual(report['scenario_outcome'],'interrupted')

    def test_actual_rccrd_keeps_its_equations_and_evaluator_is_terminal(self):
        source=(Path(__file__).resolve().parents[1]/'algoritmos/rccrd_coordinado.py').read_text(encoding='utf-8')
        identifier=install(source.replace("'rccrd_coordinado'","'prueba_rccrd_async'"))
        c=example(identifier,4)
        c.update(steps=80,period_s=.001,coordinator_exchange='async')
        c['parameters']['h']=1e-8
        c['nodes'][1]['timing']={'period_factor':4}
        runner=self.runner()
        folder,report=self.complete(runner,runner.start(c))
        self.assertTrue(self.verify_inputs(folder))
        self.assertEqual(len(global_rows(folder)),1)
        self.assertIn('terminales',report['conclusion'])

    def test_invalid_policy_is_rejected_and_default_is_sync(self):
        c=self.config()
        c['coordinator_exchange']='unknown'
        with self.assertRaisesRegex(ValueError,'Intercambio'):
            build(c)
        c.pop('coordinator_exchange')
        self.assertEqual(build(c).coordinator_exchange,'sync')

    def test_stop_during_initial_wait(self):
        # Espera del cliente cancelable, sin necesitar al resto de agentes.
        from lab.transport import CoordinatorClient, serve
        from lab.runner import allocate_ports
        rt=build(self.config())
        endpoint=Coordinator(rt,'test')
        port=allocate_ports(1)[0]
        server=serve(('127.0.0.1',port),endpoint.respond)
        client=CoordinatorClient(('127.0.0.1',port),rt,'test',1)
        calls=0
        def stop():
            nonlocal calls
            calls+=1
            if calls>2:
                raise InterruptedError('Parada solicitada')
        try:
            with self.assertRaises(InterruptedError):
                client.fetch(0,{'x':1.0},2,check_stop=stop)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
