"""El borrado de diseños es recuperable y se limita a la carpeta de modelos."""
from pathlib import Path
import tempfile
import unittest

from lab.drafts import remove_draft, restore_draft, save_recovery, latest_recovery


class DraftTests(unittest.TestCase):
    def test_recovery_preserves_unfinished_input_and_deleted_draft_stays_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'modelo.json'
            source.write_text('{}')
            raw = {'_form': True, 'fields': [{'default':'[1,'}], 'states':[{'update':'x + ('}]}
            save_recovery(root / 'recuperacion' / 'session.json', raw, source)
            self.assertEqual(latest_recovery(root), (raw, str(source)))
            archived = remove_draft(root, source)
            self.assertEqual(latest_recovery(root), (None, None))
            restore_draft(root, archived)
            self.assertEqual(latest_recovery(root), (raw, str(source)))

    def test_remove_and_restore_preserve_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'modelos'
            root.mkdir()
            source = root / 'mi_borrador.json'
            original = b'{"name":"Mi trabajo","states":[]}'
            source.write_bytes(original)
            archived = remove_draft(root, source)
            self.assertFalse(source.exists())
            self.assertEqual(archived.read_bytes(), original)
            self.assertEqual(restore_draft(root, archived), source)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(archived.exists())

    def test_cannot_remove_or_restore_outside_models(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'modelos'
            root.mkdir()
            unrelated = Path(folder) / 'config.json'
            unrelated.write_text('{}')
            with self.assertRaises(ValueError):
                remove_draft(root, unrelated)
            with self.assertRaises(ValueError):
                restore_draft(root, unrelated)
            self.assertTrue(unrelated.exists())

    def test_restore_never_overwrites_new_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'modelo.json'
            source.write_text('original')
            archived = remove_draft(root, source)
            source.write_text('nuevo')
            with self.assertRaises(ValueError):
                restore_draft(root, archived)
            self.assertEqual(source.read_text(), 'nuevo')
            self.assertEqual(archived.read_text(), 'original')
