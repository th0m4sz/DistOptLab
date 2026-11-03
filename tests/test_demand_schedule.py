import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab import plugins
from lab.algorithms import example, build, agent_config, refresh_registry
from lab.equations import blank_model, generate_source, Interpreter
from lab.parameter_schedule import ParameterSchedule
from lab.plugins import install, fields
from lab.results import read_records, global_rows, reconstructed_rows, chart_series
from lab.runner import LocalRunner
from lab.storage import Store, read_json, write_json
from lab.temporal_results import temporal_rows
import test_remote as remote_fixture


def plan(key='demand'):
    return dict(version=1, parameter=key, events=[dict(at=3,value=6),dict(at=5,value=2)])


class DemandScheduleTests(unittest.TestCase):
    def test_validation_and_values_do_not_mutate_config(self):
        config = dict(parameters={'demand':10},steps=8,demand_schedule=plan())
        declarations = fields([dict(key='demand',label='Demanda',default=10,min=0,max=100)])
        before = copy.deepcopy(config)
        schedule = ParameterSchedule(config, declarations)
        self.assertEqual([schedule.at(k)['demand'] for k in range(8)], [10,10,10,6,6,2,2,2])
        self.assertIsNone(schedule.across([2,3])['demand'])
        self.assertEqual(schedule.across([3,4])['demand'],6)
        self.assertEqual(before,config)
        for event in [dict(at=True,value=20),dict(at=0,value=20),dict(at=8,value=20),
                      dict(at=2.5,value=20),dict(at=3,value=float('nan')),dict(at=3,value=-1)]:
            invalid = copy.deepcopy(config)
            invalid['demand_schedule']['events']=[event]
            with self.subTest(event=event), self.assertRaises(ValueError):
                ParameterSchedule(invalid,declarations)
        for key,events in [('missing',[dict(at=3,value=20)]),('demand',[]),
                           ('demand',[dict(at=3,value=20),dict(at=3,value=30)])]:
            invalid = copy.deepcopy(config)
            invalid['demand_schedule'].update(parameter=key,events=events)
            with self.assertRaises(ValueError): ParameterSchedule(invalid,declarations)

    def test_installed_dispatch_changes_reference_without_inventing_correction(self):
        refresh_registry()
        config = example('distribuido_ccrd',4)
        config.update(steps=8,demand_schedule=plan('demanda'))
        config['demand_schedule']['events']=[dict(at=3,value=900)]
        rt = build(config)
        states = {i:rt.initial_state(i) for i in rt.ids}
        own = states[1]; peers={i:states[i] for i in rt.neighbors[1]}
        self.assertEqual(rt.update(1,own,peers,2),rt.update(1,own,peers,3))
        self.assertEqual(rt.observe(1,own,2)['reference/demanda'],800)
        self.assertEqual(rt.observe(1,own,3)['reference/demanda'],900)
        view = agent_config(rt,1)
        self.assertEqual(view['demand_schedule'],config['demand_schedule'])
        self.assertEqual([n['id'] for n in view['nodes'] if 'params' in n],[1])

    def test_rccrd_coordinator_really_uses_new_demand(self):
        refresh_registry()
        config=example('rccrd_coordinado',4)
        config.update(steps=8,demand_schedule=dict(version=1,parameter='demand_kw',events=[dict(at=3,value=900)]))
        rt=build(config); states={i:rt.initial_state(i) for i in rt.ids}
        old,new=rt.aggregate(2,states),rt.aggregate(3,states)
        minimum=sum(n['params']['pmin'] for n in rt.nodes.values())
        self.assertAlmostEqual(new['fitness_mean']/old['fitness_mean'],(800-minimum)/(900-minimum))
        self.assertNotEqual(rt.update(1,states[1],{},2,old)['x'],rt.update(1,states[1],{},3,new)['x'])


class ScheduledExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        directory=self.root/'algorithms';directory.mkdir()
        self.registry_patch=patch.object(plugins,'DIRECTORY',directory);self.registry_patch.start();refresh_registry()

    def tearDown(self):
        self.doCleanups();self.registry_patch.stop();refresh_registry();self.temp.cleanup()

    def config(self,mode='sync',exchange='sync'):
        model=blank_model();model.update(id=f'scheduled_{mode}_{exchange}',name='Referencia programada',mode=mode)
        model['parameters']=[dict(key='demand',label='Demanda',type='number',default=10)]
        model['states']=[dict(name='x',label='x',initial='0',kind='next',
                             update='global_data["target"]' if mode=='coordinator' else 'demand')]
        model['functions']=[dict(name='reference',args=['z'],expression='z+demand')]
        model['global_metrics']=[dict(name='total',label='Total',expression='sum_all("x")'),
                                 dict(name='balance',label='Balance',expression='total-n*demand')]
        if mode=='coordinator': model['coordinator']=[dict(name='target',expression='demand')]
        install(generate_source(model));config=example(model['id'],2)
        config.update(steps=8,period_s=.002,demand_schedule=plan(),coordinator_exchange=exchange)
        return config,model

    def complete(self,runner,run_id):
        runner.thread.join(40);self.assertFalse(runner.thread.is_alive())
        folder=runner.store.folder(run_id);record=read_json(folder/'ejecucion.json')
        self.assertEqual(record['status'],'completed',str(record)+str([p.read_text() for p in folder.glob('consola*')]))
        report=read_json(folder/'evaluacion.json');self.assertTrue(report['records_valid'],report)
        return folder

    def test_local_sync_async_and_both_coordinator_exchanges(self):
        for mode,exchange in [('sync','sync'),('async','sync'),('coordinator','sync'),('coordinator','async')]:
            with self.subTest(mode=mode,exchange=exchange):
                config,model=self.config(mode,exchange)
                rt=build(config)
                self.assertEqual(Interpreter(model,rt,1,k=3).evaluate('reference(1)'),7)
                runner=LocalRunner(Store(self.root/f'data_{mode}_{exchange}'));self.addCleanup(runner.shutdown)
                folder=self.complete(runner,runner.start(config))
                for i in (1,2):
                    rows=read_records(folder,i)
                    self.assertEqual([r['state']['x'] for r in rows],[0,10,10,10,6,6,2,2,2])
                    self.assertEqual([r['values']['reference/demand'] for r in rows],[10,10,10,6,6,2,2,2,2])
                self.assertEqual(global_rows(folder)[-1]['balance'],'0')
                self.assertEqual(reconstructed_rows(folder)[3]['balance'],8)
                trace=chart_series(folder,'reference/demand',scope='agents',max_points=2)[0]
                self.assertIn(3,trace['x']);self.assertIn(5,trace['x'])
                self.assertEqual(trace['line']['shape'],'hv')
                runner.shutdown()

    def test_scheduled_changes_with_failure_and_return(self):
        config,_=self.config('coordinator','async')
        config['faults']=dict(version=2,state_policy='keep',events=[dict(target='agent',nodes=[2],start=4,end=6)])
        runner=LocalRunner(Store(self.root/'faults'));self.addCleanup(runner.shutdown)
        folder=self.complete(runner,runner.start(config))
        self.assertEqual(read_records(folder,2)[-1]['state']['x'],2)
        self.assertEqual(read_json(folder/'evaluacion.json')['scenario_outcome'],'continued')

    def test_remote_deploys_schedule_and_keeps_private_views(self):
        config,_=self.config('coordinator','async')
        sessions={i:remote_fixture.Session(self.root/f'pi{i}',f'pi-{i}') for i in (1,2)}
        devices={i:dict(id=str(i),name=f'Pi {i}',host=f'pi-{i}.local',port=22,user='admin') for i in (1,2)}
        runner=LocalRunner(Store(self.root/'remote'));self.addCleanup(runner.shutdown)
        with patch('lab.devices.resolve_host',return_value='127.0.0.1'):
            folder=self.complete(runner,runner.start_remote(config,devices,sessions))
        for i in (1,2):
            self.assertEqual(read_records(folder,i)[-1]['state']['x'],2)
            self.assertEqual(read_json(folder/f'config_agente_{i}.json')['demand_schedule'],config['demand_schedule'])
            self.assertTrue(sessions[i].closed)

    def test_temporal_reference_is_missing_only_while_active_agents_disagree(self):
        config,_=self.config('async');rt=build(config)
        folder=self.root/'time';folder.mkdir();(folder/'algoritmo.py').write_bytes(rt.descriptor.path.read_bytes())
        config.update(clock_scope='shared_laptop',clock_origin=1)
        write_json(folder/'config.json',config)
        for i,times in [(1,[0,1,2,3,4,5,6,7,8]),(2,[0,1,2,3.5,4.5,5.5,6.5,7.5,8.5])]:
            rows=[dict(round=k,wall_s=t,node=i,state={'x':1},values={'x':1}) for k,t in enumerate(times)]
            (folder/f'nodo_{i}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            write_json(folder/f'nodo_{i}.json',dict(status='completed'))
        rows={r['time/experiment_s']:r for r in temporal_rows(folder,1)}
        self.assertEqual(rows[2]['reference/demand'],10)
        self.assertIsNone(rows[3]['reference/demand']);self.assertIsNone(rows[3]['balance'])
        self.assertEqual(rows[3]['total'],2)
        self.assertEqual(rows[3.5]['reference/demand'],6)
        self.assertEqual(rows[3.5]['balance'],-10)
        # La reducción visual de ensayos largos conserva el índice exacto del salto.
        config.update(steps=2000,demand_schedule=dict(version=1,parameter='demand',events=[dict(at=1001,value=20)]))
        write_json(folder/'config.json',config)
        for i in (1,2):
            records=[dict(round=k,wall_s=k,node=i,state={'x':1},values={'x':1}) for k in range(2001)]
            (folder/f'nodo_{i}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        indexed={r['round']:r for r in reconstructed_rows(folder)}
        self.assertEqual(indexed[1000]['reference/demand'],10)
        self.assertEqual(indexed[1001]['reference/demand'],20)


if __name__=='__main__':unittest.main()
