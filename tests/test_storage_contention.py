"""Contención del registro local durante la recogida de resultados remotos."""
import os
import io
from pathlib import Path, PurePosixPath
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from lab.remote_runner import collect
from lab.storage import write_bytes_atomic


class StorageContentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'nodo_4.jsonl'
        self.target.write_bytes(b'previous\n')

    def test_retries_replacement_without_losing_previous_file(self):
        real_replace = os.replace
        attempts = []
        def replace(source, target):
            attempts.append(target)
            if len(attempts) < 4:
                self.assertEqual(self.target.read_bytes(), b'previous\n')
                raise PermissionError('registro abierto por un lector')
            real_replace(source, target)
        with patch('lab.storage.os.replace', side_effect=replace), patch('lab.storage.time.sleep'):
            write_bytes_atomic(self.target, b'complete\n')
        self.assertEqual(len(attempts), 4)
        self.assertEqual(self.target.read_bytes(), b'complete\n')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_persistent_lock_preserves_previous_file_and_reports_error(self):
        with patch('lab.storage.os.replace', side_effect=PermissionError('locked')), patch('lab.storage.time.sleep'):
            with self.assertRaises(PermissionError):
                write_bytes_atomic(self.target, b'new\n')
        self.assertEqual(self.target.read_bytes(), b'previous\n')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_live_collect_defers_locked_file_and_final_collect_retries(self):
        remote = self.root / 'remote'
        remote.mkdir()
        (remote / 'nodo_4.jsonl').write_bytes(b'complete\npartial')
        class SFTP:
            def open(_, path, mode):
                return (remote / Path(path).name).open(mode)
            def stat(_, path):return (remote / Path(path).name).stat()
        with patch('lab.storage.os.replace', side_effect=PermissionError('locked')), patch('lab.storage.time.sleep'):
            self.assertFalse(collect(SFTP(), PurePosixPath('/run'), self.root, ['nodo_4.jsonl'], defer_locked=True))
            self.assertEqual(self.target.read_bytes(), b'previous\n')
        self.assertTrue(collect(SFTP(), PurePosixPath('/run'), self.root, ['nodo_4.jsonl']))
        self.assertEqual(self.target.read_bytes(), b'complete\n')

    def test_live_collect_defers_source_lock_but_final_collection_requires_access(self):
        class SFTP:
            locked=True
            def stat(self,path):return type('Stat',(),dict(st_size=len(b'complete\n')))()
            def open(self,path,mode):
                if self.locked:
                    raise PermissionError('resumen remoto durante su reemplazo')
                return io.BytesIO(b'complete\n')
        sftp=SFTP()
        self.assertFalse(collect(sftp,PurePosixPath('/run'),self.root,['nodo_4.jsonl'],defer_locked=True))
        self.assertEqual(self.target.read_bytes(),b'previous\n')
        with self.assertRaises(PermissionError):
            collect(sftp,PurePosixPath('/run'),self.root,['nodo_4.jsonl'])
        sftp.locked=False
        self.assertTrue(collect(sftp,PurePosixPath('/run'),self.root,['nodo_4.jsonl']))
        self.assertEqual(self.target.read_bytes(),b'complete\n')

    @unittest.skipUnless(os.name == 'nt', 'Bloqueo de archivo específico de Windows')
    def test_windows_reader_releases_handle_while_writer_retries(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        # Permitir lectura/escritura, pero retener el reemplazo por renombrado.
        handle = create(str(self.target), 0x80000000, 3, None, 3, 0x80, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        def release():
            time.sleep(.08)
            close(handle)
        thread = threading.Thread(target=release)
        thread.start()
        try:
            write_bytes_atomic(self.target, b'new\n')
        finally:
            thread.join()
        self.assertEqual(self.target.read_bytes(), b'new\n')
