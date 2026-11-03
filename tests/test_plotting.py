import tempfile
import unittest
from pathlib import Path

from lab.plotting import readable_yaxis
from lab.results import global_catalog, chart_series


class PlottingTests(unittest.TestCase):
    def test_constant_total_has_context_without_modifying_values(self):
        traces = [dict(y=[800, 800.0000000000038])]
        axis = readable_yaxis(traces)
        self.assertLess(axis['range'][0], 800)
        self.assertGreater(axis['range'][1], 801)
        self.assertEqual(traces[0]['y'][1], 800.0000000000038)

    def test_small_error_uses_explicit_exponents(self):
        self.assertEqual(readable_yaxis([dict(y=[0, 3.6e-12])])['tickformat'], '.3e')

    def test_round_remains_x_axis_but_not_a_metric(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'serie_global.csv').write_text('round,total\n0,800\n1,800\n')
            (folder/'config.json').write_text('{"nodes": []}')
            self.assertEqual(global_catalog(folder), {'total':'total'})
            self.assertEqual(chart_series(folder, 'total', scope='global')[0]['x'], [0, 1])
