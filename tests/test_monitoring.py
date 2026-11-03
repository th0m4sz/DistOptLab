import tempfile
import unittest
from pathlib import Path

from lab.monitoring import folder_revision, RefreshGate


class MonitoringTests(unittest.TestCase):
    def test_unchanged_run_is_not_rendered_again_and_controls_invalidate(self):
        gate = RefreshGate()
        views = [dict(scope='agents', metrics=['x'], x_axis='@round')]
        self.assertTrue(gate.needed('a', (1,), views))
        gate.commit('a', (1,), views)
        self.assertFalse(gate.needed('a', (1,), views))
        self.assertTrue(gate.needed('a', (2,), views))
        self.assertTrue(gate.needed('b', (1,), views))
        self.assertTrue(gate.needed('a', (1,), [dict(scope='global')]))
        self.assertTrue(gate.needed('a', (1,), views + [dict(scope='agents')]))
        # No confirmar una lectura fallida deja pendiente el mismo refresco.
        self.assertTrue(gate.needed('b', (1,), views))

    def test_revision_tracks_writes_additions_and_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = folder_revision(root)
            path = root/'nodo_1.jsonl'
            path.write_text('{}\n')
            second = folder_revision(root)
            self.assertNotEqual(first, second)
            self.assertEqual(second, folder_revision(root))
            path.write_text('{"round": 1}\n')
            self.assertNotEqual(second, folder_revision(root))
            path.unlink()
            self.assertEqual(first, folder_revision(root))
            (root/'descarga.zip').write_bytes(b'exportacion')
            self.assertEqual(first, folder_revision(root))


if __name__ == '__main__':
    unittest.main()
