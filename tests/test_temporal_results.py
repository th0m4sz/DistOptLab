import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from lab.algorithms import example, refresh_registry
from lab.equations import blank_model, generate_source
from lab.results import chart_series, export_csv, evaluator_rows, global_rows, global_catalog
from lab.storage import write_json, read_json
from lab.temporal_results import temporal_rows, time_basis
from herramientas.medir_resultados import verify_timing


class TemporalResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        refresh_registry()
        config = example('tutorial_gradiente',2,'completa')
        config.update(algorithm='prueba_tiempo',execution_mode='async',clock_scope='per_agent',steps=2)
        for node in config['nodes']:
            node['params'] = {}
        model = blank_model()
        model.update(id='prueba_tiempo',name='Prueba tiempo',mode='async')
        model['states'] = [dict(name='x',label='x',initial='0',update='x',kind='next')]
        model['global_metrics'] = [dict(name=n,label=n,expression=e) for n,e in [
            ('total','sum_all("x")'),('doble','2*total'),('indices','sum_all("k")'),('indice_comun','k')]]
        source = generate_source(model)
        (self.root/'algoritmo.py').write_text(source,encoding='utf-8')
        config['plugin_sha256'] = hashlib.sha256((self.root/'algoritmo.py').read_bytes()).hexdigest()
        write_json(self.root/'config.json',config)
        self.rows = {}
        nodes = {}
        for i, times, values in [(1,[-1,1,3],[1,2,4]),(2,[-.5,2,4],[10,20,40])]:
            self.rows[i] = [dict(node=i,round=k,monotonic_s=i*100+t,wall_s=t+2,
                                state={'x':x},values={'x':x}) for k,(t,x) in enumerate(zip(times,values))]
            self.save_rows(i)
            write_json(self.root/f'nodo_{i}.json',dict(status='completed'))
            nodes[str(i)] = dict(offset_s=1000-i*100, alignment_margin_s=.01,
                                last_sample_s=times[-1],start_s=.02,
                                final=dict(last_sample_monotonic_s=i*100+times[-1]))
        write_json(self.root/'tiempos.json',dict(version=1,status='completed',remote=True,
                   origin_monotonic_s=1000,nodes=nodes,duration_s=4,observed_duration_s=4.5,alignment_margin_s=.01,start_spread_s=0))

    def save_rows(self,i):
        (self.root/f'nodo_{i}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in self.rows[i]))

    def test_latest_past_state_not_same_index_or_interpolation(self):
        rows = temporal_rows(self.root,1)
        self.assertEqual([r['time/experiment_s'] for r in rows],[0,1,2,3,4])
        self.assertEqual([r['total'] for r in rows],[11,12,22,24,44])
        self.assertEqual([r['doble'] for r in rows],[22,24,44,48,88])
        self.assertEqual([r['indices'] for r in rows],[0,1,2,3,4])
        self.assertEqual([r['indice_comun'] for r in rows],[0,None,1,None,2])
        trace = chart_series(self.root,'total',scope='global_time',interval=1)[0]
        self.assertEqual(trace['line']['shape'],'hv')
        self.assertEqual(trace['x'],[0,1,2,3,4])
        agents = chart_series(self.root,'x',x_axis='@experiment_s')
        self.assertEqual(agents[0]['x'],[0,1,3])
        self.assertEqual(agents[1]['x'],[0,2,4])

    def test_failures_excluded_at_observed_times_and_restored(self):
        self.rows[2][1]['active'] = False
        self.rows[2][1]['values'] = {}
        self.save_rows(2)
        rows = temporal_rows(self.root,1)
        self.assertEqual([r['total'] for r in rows],[11,12,2,4,44])
        # La transición queda incluida incluso fuera de la cuadrícula.
        self.assertIn(2,[r['time/experiment_s'] for r in temporal_rows(self.root,3)])

    def test_partial_logs_do_not_invent_future_or_extrapolate_running_agent(self):
        self.rows[2] = self.rows[2][:2]
        self.save_rows(2)
        write_json(self.root/'nodo_2.json',dict(status='running'))
        rows = temporal_rows(self.root,1)
        self.assertEqual(rows[-1]['time/experiment_s'],2)
        self.assertEqual(rows[-1]['total'],22)

    def test_legacy_remote_is_not_aligned_by_guessing(self):
        (self.root/'tiempos.json').unlink()
        self.assertIsNone(time_basis(self.root))
        self.assertEqual(temporal_rows(self.root),[])

    def test_legacy_local_origin_is_explicit_and_supported(self):
        (self.root/'tiempos.json').unlink()
        config = read_json(self.root/'config.json')
        config.update(clock_scope='shared_laptop',clock_origin=123)
        write_json(self.root/'config.json',config)
        self.assertEqual(time_basis(self.root)['kind'],'legacy_local')
        self.assertTrue(temporal_rows(self.root))

    def test_export_and_independent_duration_recalculation(self):
        self.assertEqual(verify_timing(self.root),4)
        export_csv(self.root)
        self.assertTrue((self.root/'serie_global_por_tiempo.csv').is_file())
        self.assertIn('experiment_s',(self.root/'nodo_1.csv').read_text())
        self.assertTrue((self.root/'tiempos_agentes.csv').is_file())
        timing = read_json(self.root/'tiempos.json')
        timing['duration_s']=3.9
        write_json(self.root/'tiempos.json',timing)
        with self.assertRaisesRegex(ValueError,'global inconsistente'):
            verify_timing(self.root)

    def test_no_active_agents_yields_gap_not_zero(self):
        for i in (1,2):
            self.rows[i][1]['active']=False
            self.save_rows(i)
        rows = temporal_rows(self.root,1)
        self.assertIsNone(rows[2]['total'])

    def test_evaluator_evolution_uses_recorded_events_and_keeps_terminal_csv(self):
        path = self.root/'serie_global.csv'
        path.write_text('round,total,doble\n2,44,88\n')
        original = path.read_bytes()
        self.rows[1][1]['monotonic_s'] += .25
        self.save_rows(1)
        rows = evaluator_rows(self.root)
        self.assertEqual([r['time/experiment_s'] for r in rows], [0,1.25,2,3,4])
        self.assertEqual([r['total'] for r in rows], [11,12,22,24,44])
        self.assertEqual(set(global_catalog(self.root)), {'total','doble'})
        trace = chart_series(self.root, 'total', scope='global', x_axis='@experiment_s')[0]
        self.assertEqual(trace['x'], [0,1.25,2,3,4])
        self.assertEqual(trace['line']['shape'], 'hv')
        self.assertEqual(len(global_rows(self.root)), 1)
        self.assertEqual(path.read_bytes(), original)
        export_csv(self.root)
        self.assertTrue((self.root/'serie_global_evolucion.csv').exists())

    def test_terminal_custom_metrics_or_missing_clock_are_not_invented(self):
        path = self.root/'serie_global.csv'
        path.write_text('round,manual\n2,99\n')
        self.assertEqual(evaluator_rows(self.root), [{'round':'2','manual':'99'}])
        path.write_text('round,total\n2,44\n')
        (self.root/'tiempos.json').unlink()
        self.assertEqual(evaluator_rows(self.root), [{'round':'2','total':'44'}])


if __name__=='__main__':
    unittest.main()
