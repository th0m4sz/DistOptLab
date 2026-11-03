"""Procesos/TCP reales; nunca se apagan placas ni se modifica el catálogo del usuario."""
import copy
import json
import tempfile
import time
import threading
from unittest.mock import Mock
import unittest
from pathlib import Path
from unittest.mock import patch

from lab import plugins
from lab.algorithms import REGISTRY,agent_config,build,example,refresh_registry,topology_edges
from lab.algorithm_library import default_path,load_default
from lab.faults import upgrade_scenario_config
from lab.plugins import install
from lab.runner import LocalRunner
from lab.storage import Store,read_json,write_json
from lab.results import chart_series,read_records

SOURCE = '''ALGORITMO = {'id':'prueba_fallas','name':'Prueba de fallas','mode':'sync',
'parameters':[], 'fields':[['inicio','Inicial',1]], 'metrics':[['x','Estado']]}
INITIALIZATIONS={}
def inicial(rt,i):
    INITIALIZATIONS[i]=INITIALIZATIONS.get(i,0)+1
    return {'x':float(i), 'n':len(rt.active_ids), 'changes':0, 'initializations':INITIALIZATIONS[i]}
def paso(rt,i,propio,vecinos,k,global_data):
    if rt.mode == 'coordinator':
        x = global_data['average']
    else:
        x = (propio['x']+sum(v['x'] for v in vecinos.values()))/(1+len(vecinos))
    return dict(x=x,n=len(rt.active_ids),changes=propio['changes'],initializations=propio['initializations'])
def coordinar(rt,k,estados):
    assert set(estados)==set(rt.active_ids)
    return {'average':sum(v['x'] for v in estados.values())/len(estados)}
def al_cambiar_red(rt,i,propio,evento):
    assert all('params' not in v for j,v in rt.nodes.items() if j!=i)
    propio['changes']+=1
    return propio
'''


class FaultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.algorithms=self.root/'algorithms'
        self.algorithms.mkdir()
        self.patch=patch.object(plugins,'DIRECTORY',self.algorithms)
        self.patch.start()
        refresh_registry()

    def tearDown(self):
        self.doCleanups()
        self.patch.stop()
        refresh_registry()
        self.temp.cleanup()

    def config(self,mode='sync',events=None):
        source=SOURCE.replace("'mode':'sync'", "'mode':'coordinator'") if mode=='coordinator' else SOURCE
        path=self.algorithms/'prueba_fallas.py'
        if path.exists():
            path.write_text(source,encoding='utf-8')
            refresh_registry()
            identifier='prueba_fallas'
        else:
            identifier=install(source)
        config=example(identifier,4,'completa')
        config.update(steps=24,period_s=.002,execution_mode=mode)
        config['faults']=dict(version=2,state_policy='keep',events=events or
                             [dict(target='agent',nodes=[2,4],start=6,end=14)])
        return config

    def run_config(self,config):
        runner=LocalRunner(Store(self.root/'data'))
        try:
            run=runner.start(config)
            runner.thread.join(55)
            self.assertFalse(runner.thread.is_alive())
            folder=runner.store.folder(run)
            execution=read_json(folder/'ejecucion.json')
            self.assertEqual(execution['status'],'completed',execution)
            report=read_json(folder/'evaluacion.json')
            self.assertTrue(report['records_valid'],report)
            return folder,report
        finally:
            runner.shutdown()

    def test_sync_multiple_and_rejoin(self):
        folder,report=self.run_config(self.config())
        self.assertEqual(report['scenario_outcome'],'continued')
        a=read_records(folder,1)
        b=read_records(folder,2)
        self.assertEqual(a[8]['state']['n'],2)
        self.assertEqual(a[16]['state']['n'],4)
        self.assertTrue(all(not r['active'] and not r['values'] for r in b[6:14]))
        self.assertTrue(b[14]['active'])
        self.assertIsNone(chart_series(folder,'x',agents=[2])[0]['y'][7])

    def test_async_multiple_and_rejoin(self):
        folder,report=self.run_config(self.config('async'))
        self.assertEqual(report['scenario_outcome'],'continued')
        self.assertEqual(read_records(folder,1)[8]['state']['n'],2)

    def test_coordinator_reconfigures_expected_agents(self):
        folder,report=self.run_config(self.config('coordinator'))
        self.assertEqual(report['scenario_outcome'],'continued')
        self.assertEqual(read_records(folder,1)[8]['state']['n'],2)

    def dispatch_config(self, state_policy='keep', end=None, mode='sync'):
        """El archivo real y los cuatro generadores del ejemplo del usuario."""
        source=(Path(__file__).resolve().parents[1]/'algoritmos/distribuido_ccrd.py').read_text(encoding='utf-8')
        if not (self.algorithms/'distribuido_ccrd.py').exists():
            install(source)
        c=example('distribuido_ccrd',4,'anillo')
        data=[(100,500,150,64.67,795.5,1.15), (82,362,300,64.46,1448.6,.82),
              (65,315,100,190.92,838.1,1.53), (50,271,250,39.19,696.1,2.46)]
        for node,values in zip(c['nodes'],data):
            node['params'].update(dict(zip(('pmin','pmax','x0','a','b','c'),values)))
        c.update(steps=160,period_s=.001,execution_mode=mode)
        c['faults']=dict(version=2,state_policy=state_policy,
                         events=[dict(target='agent',nodes=[4],start=40,end=end)])
        return c

    def test_dispatch_withdraw_keeps_remaining_power_without_inventing_compensation(self):
        folder,report=self.run_config(self.dispatch_config())
        rows={i:read_records(folder,i) for i in (1,2,3,4)}
        before=sum(rows[i][39]['state']['x'] for i in rows)
        at_failure=sum(rows[i][40]['state']['x'] for i in (1,2,3))
        final=sum(rows[i][-1]['state']['x'] for i in (1,2,3))
        self.assertAlmostEqual(before,800,places=7)
        self.assertAlmostEqual(at_failure,800-rows[4][40]['state']['x'],places=7)
        self.assertAlmostEqual(final,at_failure,places=7)
        self.assertFalse(report['convergence_evaluated'])

    def test_dispatch_withdraw_reset_and_rejoin(self):
        for state_policy in ('keep','reset_returning'):
            with self.subTest(state_policy=state_policy):
                folder,_=self.run_config(self.dispatch_config(state_policy=state_policy,end=110))
                rows={i:read_records(folder,i) for i in (1,2,3,4)}
                self.assertTrue(rows[4][110]['active'])
                at_failure=sum(rows[i][40]['state']['x'] for i in (1,2,3))
                self.assertAlmostEqual(at_failure,800-rows[4][40]['state']['x'],places=7)
                expected=800 if state_policy=='keep' else at_failure+250
                self.assertAlmostEqual(sum(rows[i][-1]['state']['x'] for i in rows),expected,places=7)
                if state_policy=='reset_returning':
                    returned=rows[4][110]['state']
                    self.assertEqual(returned,dict(x=250,hat=(250-50)*(271-250),f=3000-(696.1+2*2.46*250)))

    def test_sync_and_async_ring_exclude_failed_node_without_new_links(self):
        for mode in ('sync','async'):
            with self.subTest(mode=mode):
                c=self.config(mode,events=[dict(target='agent',nodes=[4],start=6,end=14)])
                c.update(topology='anillo',edges=topology_edges([1,2,3,4],'anillo'))
                folder,_=self.run_config(c)
                for i,expected in {1:[2],2:[1,3],3:[2]}.items():
                    rows=[json.loads(s) for s in (folder/f'entradas_{i}.jsonl').read_text().splitlines()]
                    self.assertTrue(all(r['neighbor_ids']==expected for r in rows if 6<=r['k']<14))

    def test_dispatch_async_keep_and_reset_returning_finish(self):
        for state_policy in ('keep','reset_returning'):
            with self.subTest(state_policy=state_policy):
                _,report=self.run_config(self.dispatch_config(state_policy=state_policy,mode='async',end=110))
                self.assertEqual(report['scenario_outcome'],'continued')

    def test_coordinator_failure_stops_algorithm_without_failover(self):
        _,report=self.run_config(self.config('coordinator',events=[dict(target='coordinator',nodes=[],start=6,end=None)]))
        self.assertEqual(report['scenario_outcome'],'interrupted')

    def test_all_agents_can_be_retired_and_rejoin(self):
        folder,_=self.run_config(self.config(events=[dict(target='agent',nodes=[1,2,3,4],start=6,end=14)]))
        self.assertEqual(read_records(folder,1)[20]['state']['n'],4)

    def test_invalid_events_and_private_config(self):
        c=self.config()
        rt=build(c)
        local=agent_config(rt,1)
        self.assertEqual(local['faults'],c['faults'])
        self.assertNotIn('params',local['nodes'][1])
        for bad in [dict(target='agent',nodes=[99],start=4,end=None),
                    dict(target='agent',nodes=[2],start=0,end=None),
                    dict(target='agent',nodes=[2],start=4,end=3)]:
            c['faults']['events']=[bad]
            with self.assertRaises(ValueError):build(c)
        c['faults']['events']=[dict(target='agent',nodes=[2],start=4,end=10),dict(target='agent',nodes=[2],start=8,end=None)]
        with self.assertRaises(ValueError):build(c)

    def test_single_permanent_failure(self):
        c=self.config(events=[dict(target='agent',nodes=[4],start=6,end=None)])
        c['faults']['state_policy']='reset_returning'
        folder,_=self.run_config(c)
        self.assertFalse(read_records(folder,4)[-1]['active'])
        self.assertEqual(read_records(folder,1)[-1]['state']['n'],3)
        for i in (1,2,3,4):
            self.assertTrue(all(r['state']['initializations']==1 for r in read_records(folder,i)))

    def test_reset_only_returning_agents_in_all_three_modes(self):
        for mode in ('sync','async','coordinator'):
            with self.subTest(mode=mode):
                c=self.config(mode)
                c['faults']['state_policy']='reset_returning'
                folder,_=self.run_config(c)
                for i in (1,3):
                    rows=read_records(folder,i)
                    self.assertTrue(all(r['state']['initializations']==1 for r in rows))
                    self.assertEqual(rows[14]['state']['changes'],2)
                for i in (2,4):
                    rows=read_records(folder,i)
                    self.assertEqual(rows[13]['state']['initializations'],1)
                    self.assertEqual(rows[14]['state']['initializations'],2)
                    self.assertEqual(rows[14]['state']['x'],float(i))

    def test_multiple_failures_reset_only_those_returning_at_each_boundary(self):
        c=self.config(events=[dict(target='agent',nodes=[2],start=4,end=8),
                              dict(target='agent',nodes=[4],start=6,end=10),
                              dict(target='agent',nodes=[2],start=12,end=16)])
        c['faults']['state_policy']='reset_returning'
        folder,_=self.run_config(c)
        for i,expected in {1:[],2:[8,16],3:[],4:[10]}.items():
            changes=[json.loads(s) for s in (folder/f'eventos_{i}.jsonl').read_text().splitlines()]
            self.assertEqual([r['k'] for r in changes if r['reinitialized']],expected)
            rows=read_records(folder,i)
            for row in rows:
                self.assertEqual(row['state']['initializations'],1+sum(k<=row['round'] for k in expected))

    def test_retired_configurations_migrate_without_mutating_the_original(self):
        c=self.config()
        old=copy.deepcopy(c)
        old['faults'].update(version=1,policy='observe',state_policy='reset')
        frozen=copy.deepcopy(old)
        with self.assertRaisesRegex(ValueError,'antigua'):build(old)
        upgraded=upgrade_scenario_config(old)
        self.assertEqual(old,frozen)
        self.assertNotIn('policy',upgraded['faults'])
        self.assertEqual(upgraded['faults']['version'],2)
        self.assertEqual(upgraded['faults']['state_policy'],'reset_returning')
        build(upgraded)
        for bad in (dict(policy='observe'),dict(state_policy='reset')):
            invalid=copy.deepcopy(c)
            invalid['faults'].update(bad)
            with self.assertRaises(ValueError):build(invalid)

    def test_legacy_configuration_cannot_reactivate_removed_behavior_on_new_run(self):
        c=self.config()
        c['faults'].update(version=1,policy='observe',state_policy='reset')
        frozen=copy.deepcopy(c)
        folder,_=self.run_config(c)
        archived=read_json(folder/'config.json')
        self.assertEqual(archived['faults']['version'],2)
        self.assertNotIn('policy',archived['faults'])
        self.assertEqual(c,frozen)
        for i in (1,2,3,4):
            self.assertEqual(read_records(folder,i)[-1]['state']['initializations'],2 if i in (2,4) else 1)

    def test_saved_default_is_upgraded_before_validation(self):
        c=self.config()
        c['faults'].update(version=1,policy='observe',state_policy='reset')
        path=default_path(self.root,'prueba_fallas')
        write_json(path,c)
        loaded=load_default(self.root,REGISTRY['prueba_fallas'])
        self.assertEqual(loaded['faults']['version'],2)
        self.assertEqual(loaded['faults']['state_policy'],'reset_returning')
        self.assertNotIn('policy',loaded['faults'])

    def test_multiple_events_are_reproducible_in_sync(self):
        c=self.config(events=[dict(target='agent',nodes=[2],start=4,end=8),
                              dict(target='agent',nodes=[4],start=10,end=None)])
        first,_=self.run_config(c)
        second,_=self.run_config(c)
        for i in (1,2,3,4):
            self.assertEqual([r['state'] for r in read_records(first,i)],
                             [r['state'] for r in read_records(second,i)])

    def test_unexpected_math_timeout_remains_failure(self):
        c=self.config()
        path=self.algorithms/'prueba_fallas.py'
        path.write_text(path.read_text().replace("    if rt.mode == 'coordinator':", "    if k == 7: raise TimeoutError('Error del algoritmo')\n    if rt.mode == 'coordinator':"))
        c['execution_mode']='async'
        c.pop('plugin_sha256',None)
        refresh_registry()
        runner=LocalRunner(Store(self.root/'data'))
        try:
            run=runner.start(c)
            runner.thread.join(40)
            self.assertFalse(runner.thread.is_alive())
            self.assertEqual(read_json(runner.store.folder(run)/'ejecucion.json')['status'],'failed')
        finally:runner.shutdown()

    def test_stop_while_waiting_for_phase(self):
        c=self.config()
        runner=LocalRunner(Store(self.root/'data'))
        try:
            with patch('lab.faults.release_phase'):
                run=runner.start(c)
                deadline=time.monotonic()+8
                while time.monotonic()<deadline and not any(s['status']=='waiting_phase' for s in runner.states(run)):
                    time.sleep(.02)
                runner.stop()
                runner.thread.join(15)
                self.assertFalse(runner.thread.is_alive())
                self.assertEqual(read_json(runner.store.folder(run)/'ejecucion.json')['status'],'stopped')
        finally:runner.shutdown()

    def test_sync_transient_pause_longer_than_old_timeout(self):
        c=self.config(events=[dict(target='agent',nodes=[4],start=12,end=None)])
        path=self.algorithms/'prueba_fallas.py'
        # Una pausa del proceso (carga del equipo o escritura en OneDrive)
        # no debe confundirse con una retirada ni con una falla matemática.
        path.write_text(path.read_text().replace('    if rt.mode ==',
                        "    if i == 1 and k == 4:\n        import time\n        time.sleep(3.3)\n    if rt.mode =="))
        c.pop('plugin_sha256',None)
        refresh_registry()
        _,report=self.run_config(c)
        self.assertEqual(report['scenario_outcome'],'continued')

    def test_offline_agent_does_not_query_neighbors(self):
        from lab.transport import Inbox
        rt=build(self.config('async'))
        inbox=Inbox.__new__(Inbox)
        inbox.runtime,inbox.i,inbox.phase=rt,4,6
        inbox.lock=threading.Lock()
        class OneWait:
            stopped=False
            def is_set(self):return self.stopped
            def wait(self,_):self.stopped=True;return False
        inbox.stop=OneWait()
        connection=Mock()
        inbox.receive(1,connection)
        connection.request.assert_not_called()
        connection.close.assert_called_once()


if __name__=='__main__':unittest.main()
