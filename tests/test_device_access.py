"""Autenticación por lotes y confianza SSH con servidores locales desechables."""
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import paramiko

from lab.devices import check_access_all, check_ssh, key_fingerprint, open_ssh, UnknownHost


class SSHFixture:
    """Solo autenticación SSH real; no ejecuta comandos ni utiliza placas reales."""
    def __init__(self, key):
        self.key = key
        self.attempts = []
        self.stop = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(16)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.transports = []
        self.workers = []
        self.thread = threading.Thread(target=self.accept, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def device(self, identifier='one'):
        return dict(id=identifier, name=identifier, host='127.0.0.1', port=self.port, user='test')

    def accept(self):
        while not self.stop.is_set():
            try:
                sock, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            worker = threading.Thread(target=self.serve, args=(sock,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def serve(self, sock):
        fixture = self
        class Auth(paramiko.ServerInterface):
            def get_allowed_auths(self, username):
                return 'password'

            def check_auth_password(self, username, password):
                fixture.attempts.append(username)
                return paramiko.AUTH_SUCCESSFUL if (username, password)==('test', 'synthetic') else paramiko.AUTH_FAILED

        transport = paramiko.Transport(sock)
        self.transports.append(transport)
        try:
            transport.add_server_key(self.key)
            transport.start_server(server=Auth())
            while transport.is_active() and not self.stop.wait(.01):
                pass
        except (paramiko.SSHException, EOFError, OSError):
            pass
        finally:
            transport.close()

    def __exit__(self, *_):
        self.stop.set()
        self.listener.close()
        self.thread.join(2)
        for transport in self.transports:
            transport.close()
        for worker in self.workers:
            worker.join(2)


class DeviceAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = paramiko.RSAKey.generate(1024)  # Claves exclusivamente sintéticas.
        cls.other_key = paramiko.RSAKey.generate(1024)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.known = Path(self.temp.name)/'known_hosts'

    def test_first_identity_saved_only_after_successful_authentication(self):
        with SSHFixture(self.key) as server:
            with self.assertRaisesRegex(ValueError, 'autenticación'):
                open_ssh(server.device(), self.known, 'incorrect', accept_new=True)
            self.assertFalse(self.known.exists())
            client = open_ssh(server.device(), self.known, 'synthetic', accept_new=True)
            client.close()
            keys = paramiko.HostKeys(str(self.known))
            self.assertEqual(keys[f'[127.0.0.1]:{server.port}']['ssh-rsa'], self.key)
            # La segunda conexión verifica la identidad conocida sin intervención.
            client = open_ssh(server.device(), self.known, 'synthetic', accept_new=True)
            client.close()
            self.assertEqual(len(server.attempts), 3)

    def test_changed_key_rejected_before_password_authentication(self):
        with SSHFixture(self.key) as server:
            keys = paramiko.HostKeys()
            keys.add(f'[127.0.0.1]:{server.port}', 'ssh-rsa', self.other_key)
            keys.save(str(self.known))
            before = self.known.read_bytes()
            with self.assertRaisesRegex(ValueError, 'clave de host cambió'):
                open_ssh(server.device(), self.known, 'synthetic', accept_new=True)
            self.assertEqual(server.attempts, [])
            self.assertEqual(self.known.read_bytes(), before)

    def test_strict_api_and_explicit_fingerprint_still_work(self):
        with SSHFixture(self.key) as server:
            with self.assertRaises(UnknownHost):
                open_ssh(server.device(), self.known, 'synthetic')
            with self.assertRaises(UnknownHost):
                open_ssh(server.device(), self.known, 'synthetic',
                         expected_fingerprint=key_fingerprint(self.other_key), accept_new=True)
            self.assertFalse(self.known.exists())
            self.assertEqual(server.attempts, [])
            client = open_ssh(server.device(), self.known, 'synthetic',
                              expected_fingerprint=key_fingerprint(self.key))
            client.close()
            self.assertTrue(self.known.exists())

    def test_concurrent_connections_preserve_all_host_keys(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            servers = [stack.enter_context(SSHFixture(self.key)) for _ in range(8)]
            def connect(server):
                client = open_ssh(server.device(str(server.port)), self.known, 'synthetic', accept_new=True)
                client.close()
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(connect, servers))
            keys = paramiko.HostKeys(str(self.known))
            self.assertEqual(len(keys), 8)
            for server in servers:
                self.assertEqual(keys[f'[127.0.0.1]:{server.port}']['ssh-rsa'], self.key)

    def test_corrupt_known_hosts_closes_client_and_socket(self):
        self.known.write_text('bad entry', encoding='utf-8')
        with patch('lab.devices.socket.create_connection') as sock, patch('paramiko.SSHClient') as factory:
            factory.return_value.load_host_keys.side_effect = ValueError('Archivo inválido')
            with self.assertRaisesRegex(ValueError, 'Archivo inválido'):
                open_ssh(dict(host='127.0.0.1',port=22,user='test'), self.known, 'synthetic', accept_new=True)
            factory.return_value.close.assert_called_once()
            sock.return_value.close.assert_called_once()

    def test_batch_uses_saved_passwords_and_keeps_individual_results(self):
        devices = [dict(id=str(i), name=str(i), host=f'pi-{i}.local', port=22, user='test') for i in range(4)]
        def saved(device):
            return None if device['id']=='1' else 'synthetic'
        def access(device, path, password, **options):
            self.assertEqual(password, 'synthetic')
            self.assertTrue(options['accept_new'])
            if device['id']=='2':
                raise ValueError('Rejected synthetic')
            return 'Python 3.11 · acceso SSH y SFTP comprobado'
        with patch('lab.credentials.read_password', side_effect=saved), patch('lab.devices.check_ssh', side_effect=access) as check:
            results = check_access_all(devices+[devices[0]], self.known)
        self.assertEqual([r['status'] for r in results], ['Acceso comprobado','Falta contraseña','Error de acceso','Acceso comprobado'])
        self.assertEqual(check.call_count, 3)
        self.assertNotIn('synthetic', str(results))
        self.assertNotIn('password', str(results))

    def test_batch_is_bounded_and_does_not_require_preliminary_probe(self):
        devices = [dict(id=str(i), name=str(i), host=f'pi-{i}.local', port=22, user='test') for i in range(10)]
        lock = threading.Lock()
        gate = threading.Event()
        active = peak = 0
        def access(*_, **__):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                if active==4:
                    gate.set()
            gate.wait(2)
            with lock:
                active -= 1
            return 'Comprobado'
        with patch('lab.credentials.read_password', return_value='synthetic'), patch('lab.devices.check_ssh', side_effect=access) as check, patch('lab.devices.probe') as probe:
            results = check_access_all(devices, self.known)
        self.assertEqual(peak, 4)
        self.assertEqual(check.call_count, 10)
        self.assertEqual(len(results), 10)
        probe.assert_not_called()

    def test_temporary_password_does_not_read_saved_secret(self):
        device = dict(id='one',name='one',host='pi.local',port=22,user='test')
        with patch('lab.credentials.read_password') as read, patch('lab.devices.check_ssh', return_value='Comprobado') as check:
            result = check_access_all([device], self.known, {'one':'synthetic'}, use_saved=False)
        read.assert_not_called()
        self.assertEqual(result[0]['status'], 'Acceso comprobado')
        self.assertEqual(check.call_args.args[2], 'synthetic')

    def test_access_checks_python_version_sftp_and_always_closes(self):
        for version, fail_sftp in [('Python 3.11.9',False),('Python 3.9.2',False),('Python 3.11.9',True)]:
            client = MagicMock()
            stdout = io.BytesIO(version.encode())
            stdout.channel = MagicMock()
            stdout.channel.recv_exit_status.return_value = 0
            client.exec_command.return_value = (None, stdout, io.BytesIO())
            client.open_sftp.return_value.__enter__.return_value.stat.side_effect = OSError('SFTP no disponible') if fail_sftp else None
            with patch('lab.devices.open_ssh', return_value=client):
                if version=='Python 3.9.2' or fail_sftp:
                    with self.assertRaises((ValueError,OSError)):
                        check_ssh({}, self.known, 'synthetic', accept_new=True)
                else:
                    self.assertIn('SFTP comprobado', check_ssh({}, self.known, 'synthetic', accept_new=True))
            client.close.assert_called_once()


if __name__=='__main__':
    unittest.main()
