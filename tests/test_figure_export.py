import copy
import csv
import io
import json
import math
import unittest
from unittest.mock import patch
import zipfile

from lab.figure_export import default_options, package, render


class FigureExportTests(unittest.TestCase):
    def fixture(self):
        return dict(data=[dict(type='scatter', name='Agent 1', mode='lines',
                              x=list(range(2001)), y=[None if k==20 else k*.01 for k in range(2001)],
                              line=dict(shape='hv'))],
                    layout=dict(xaxis=dict(title=dict(text='Time (s)')), yaxis=dict(title=dict(text='Power (MW)'))))

    def test_package_all_samples_gaps_and_original_unchanged(self):
        figure = self.fixture()
        original = copy.deepcopy(figure)
        options = default_options(figure)
        bundle = package(figure, options, dict(run_id='test'))
        self.assertTrue(bundle['pdf'].startswith(b'%PDF'))
        self.assertTrue(bundle['png'].startswith(b'\x89PNG'))
        self.assertIn(b'<svg',bundle['svg'])
        with zipfile.ZipFile(io.BytesIO(bundle['zip'])) as z:
            rows = list(csv.DictReader(io.StringIO(z.read('data.csv').decode('utf-8-sig'))))
            self.assertEqual(len(rows), 2001)
            self.assertEqual(rows[20]['y'], '')
            saved = json.loads(z.read('figure.json'))
            self.assertEqual(saved['figure'],original)
            self.assertIn('reproduce.py',z.namelist())
        self.assertEqual(figure,original)

    def test_renderer_preserves_step_and_gap_and_requested_size(self):
        figure = self.fixture()
        captured = []
        def save(fig, stream, **kwargs):
            line = fig.axes[0].lines[0]
            captured.append((line.get_drawstyle(), list(line.get_ydata()), list(fig.get_size_inches())))
        with patch('matplotlib.figure.Figure.savefig',save):
            render(figure,default_options(figure),formats=('pdf',))
        self.assertEqual(captured[0][0],'steps-post')
        self.assertTrue(math.isnan(captured[0][1][20]))
        self.assertEqual(len(captured[0][1]),2001)
        self.assertAlmostEqual(captured[0][2][0],180/25.4)

    def test_duration_error_bars_and_labels(self):
        f = dict(data=[dict(type='bar',orientation='h',name='Duration',x=[2,3],y=['Run 1','Run 2'],
                           error_x=dict(array=[.1,.2]))],layout=dict(xaxis=dict(title='Time (s)'),yaxis=dict(title='Run')))
        options = default_options(f)
        options['categories']['0'] = ['Sync - Laptop', 'Async - Laptop']
        output = package(f,options,{})
        with zipfile.ZipFile(io.BytesIO(output['zip'])) as z:
            rows = list(csv.DictReader(io.StringIO(z.read('data.csv').decode('utf-8-sig'))))
            self.assertEqual(rows[1]['x_error'],'0.2')
            self.assertEqual(rows[1]['y'],'Async - Laptop')

    def test_blank_axis_and_invalid_dimensions_rejected(self):
        f = self.fixture()
        options = default_options(f)
        options['width_mm'] = 0
        with self.assertRaises(ValueError):
            render(f,options)
        options = default_options(f)
        options['xlabel'] = ''
        with self.assertRaises(ValueError):
            render(f,options)
