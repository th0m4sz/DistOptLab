import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from lab.algorithms import example, refresh_registry
from lab.equations import blank_model, generate_source
from lab.results import reconstructed_rows, chart_series, global_rows, export_csv


class ReconstructedGlobalsTests(unittest.TestCase):
    def test_curve_uses_actual_local_indices_without_changing_evaluator(self):
        refresh_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = example('tutorial_gradiente', 2, 'completa')
            config['execution_mode'] = 'async'
            config['clock_scope'] = 'per_agent'
            model = blank_model()
            model.update(id='prueba_curva', name='Prueba curva', mode='async')
            model['states'] = [dict(name='x',label='x',initial='0',update='x',kind='next')]
            model['global_metrics'] = [dict(name='total',label='total',expression='sum_all("x")'),
                                       dict(name='doble',label='doble',expression='2*total')]
            config['algorithm'] = 'prueba_curva'
            config['params'] = {}
            for node in config['nodes']:
                node['params'] = {}
            (root/'algoritmo.py').write_text(generate_source(model),encoding='utf-8')
            config['plugin_sha256'] = hashlib.sha256((root/'algoritmo.py').read_bytes()).hexdigest()
            (root/'config.json').write_text(json.dumps(config))
            for i in (1,2):
                rows = [dict(round=k,wall_s=k*(.1 if i==1 else 3),node=i,state={'x':i+k},values={'x':i+k},active=not(i==2 and k==1)) for k in range(3)]
                (root/f'nodo_{i}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            (root/'serie_global.csv').write_text('round,total\n2,7\n')
            before = (root/'serie_global.csv').read_bytes()
            self.assertEqual(reconstructed_rows(root),[{'round':0,'total':3,'doble':6},{'round':1,'total':2,'doble':4},{'round':2,'total':7,'doble':14}])
            trace = chart_series(root,'total',scope='global_index')[0]
            self.assertEqual(trace['x'],[0,1,2])
            self.assertEqual(trace['y'],[3,2,7])
            self.assertEqual(len(global_rows(root)),1)
            self.assertEqual((root/'serie_global.csv').read_bytes(),before)
            export_csv(root)
            self.assertTrue((root/'serie_global_por_indice.csv').exists())
            # Actualizar un registro invalida el caché de visualización.
            rows[-1]['state']['x']=20
            (root/'nodo_2.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(reconstructed_rows(root)[-1]['total'],23)
            first = [json.loads(line) for line in (root/'nodo_1.jsonl').read_text().splitlines()]
            first[1]['active'] = False
            (root/'nodo_1.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in first))
            self.assertIsNone(reconstructed_rows(root)[1]['total'])
            # Mientras llega el último registro de un agente, no inventar su estado.
            (root/'nodo_2.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows[:2]))
            self.assertEqual([r['round'] for r in reconstructed_rows(root)],[0,1])


if __name__=='__main__':
    unittest.main()
