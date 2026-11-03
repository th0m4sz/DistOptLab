"""Despliegue aislado con SSH/SFTP simulados y procesos TCP reales."""
import unittest
import test_remote as remote_fixtures
from test_faults import SOURCE
from lab.algorithms import example
from lab.plugins import install
from lab.runner import LocalRunner
from lab.storage import Store,read_json


class FaultRemoteTests(unittest.TestCase):
    setUp=remote_fixtures.RemoteTest.setUp
    tearDown=remote_fixtures.RemoteTest.tearDown

    def check_remote(self,mode,coordinator_failure=False,topology='completa',permanent=False,state_policy='keep'):
        source=SOURCE.replace("'mode':'sync'","'mode':'coordinator'") if mode=='coordinator' else SOURCE
        c=example(install(source),4,topology)
        c.update(steps=18,period_s=.002,execution_mode=mode)
        event=dict(target='coordinator',nodes=[],start=5,end=None) if coordinator_failure else dict(target='agent',nodes=[4] if permanent else [2,4],start=5,end=None if permanent else 11)
        c['faults']=dict(version=2,state_policy=state_policy,events=[event])
        sessions={i:remote_fixtures.Session(self.root/f'pi{i}',f'pi-{i}') for i in (1,2,3,4)}
        devices={i:dict(id=str(i),name=f'Pi {i}',host=f'pi-{i}.local',port=22,user='admin') for i in (1,2,3,4)}
        runner=LocalRunner(Store(self.root/'data'))
        self.addCleanup(runner.shutdown)
        run=runner.start_remote(c,devices,sessions)
        runner.thread.join(55)
        self.assertFalse(runner.thread.is_alive())
        folder=runner.store.folder(run)
        result=read_json(folder/'ejecucion.json')
        self.assertEqual(result['status'],'completed',str(result)+str([p.read_text() for p in folder.glob('consola*')]))
        report=read_json(folder/'evaluacion.json')
        self.assertTrue(report['records_valid'],report)
        expected='interrupted' if coordinator_failure else 'continued'
        self.assertEqual(report['scenario_outcome'],expected)
        self.assertTrue((folder/'eventos.json').is_file())
        for i in (1,2,3,4):
            self.assertTrue((folder/f'eventos_{i}.jsonl').is_file())
            self.assertTrue(sessions[i].closed)
            if state_policy=='reset_returning':
                from lab.results import read_records
                self.assertEqual(read_records(folder,i)[-1]['state']['initializations'],2 if i in (2,4) else 1)

    def test_remote_sync(self):self.check_remote('sync')
    def test_remote_async(self):self.check_remote('async')
    def test_remote_coordinator(self):self.check_remote('coordinator')
    def test_remote_sync_ring(self):self.check_remote('sync',topology='anillo',permanent=True)
    def test_remote_reset_returning_async(self):self.check_remote('async',state_policy='reset_returning')
    def test_remote_reset_returning_coordinator(self):self.check_remote('coordinator',state_policy='reset_returning')
    def test_remote_coordinator_failure(self):self.check_remote('coordinator',coordinator_failure=True)


if __name__=='__main__':unittest.main()
