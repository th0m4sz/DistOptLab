"""SSH/SFTP simulados con procesos Python y TCP reales, sin credenciales."""
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from lab import plugins
from lab.algorithms import REGISTRY, example, refresh_registry
from lab.plugins import install
from lab.remote_runner import deployment_files
from lab.runner import LocalRunner, allocate_ports
from lab.storage import Store, read_json
from test_flexible import SOURCE


class SFTP:
    def __init__(self, root):
        self.root = root

    def path(self, remote):
        return self.root / remote.lstrip('/')

    def stat(self, remote):
        return self.path(remote).stat()

    def mkdir(self, remote):
        self.path(remote).mkdir()

    def open(self, remote, mode):
        return self.path(remote).open(mode)

    def get_channel(self):
        return self

    def settimeout(self, timeout):
        pass

    def close(self):
        pass


class Channel:
    def __init__(self, root):
        self.root = root
        self.position = 0

    def set_combine_stderr(self, value):
        pass

    def exec_command(self, command):
        prefix, invocation = command.split(' && exec ', 1)
        cwd = self.root / shlex.split(prefix)[1].lstrip('/')
        args = shlex.split(invocation)
        args[0] = sys.executable
        for flag in ('--folder', '--config'):
            if flag in args:
                index = args.index(flag) + 1
                args[index] = str(self.root / args[index].lstrip('/'))
        self.output = cwd / 'ssh_output.txt'
        self.stream = self.output.open('wb')
        self.process = subprocess.Popen(args, cwd=cwd, stdout=self.stream, stderr=subprocess.STDOUT)

    def recv_ready(self):
        return self.output.stat().st_size > self.position

    def recv(self, size):
        with self.output.open('rb') as stream:
            stream.seek(self.position)
            value = stream.read(size)
            self.position += len(value)
            return value

    def exit_status_ready(self):
        return self.process.poll() is not None

    def recv_exit_status(self):
        return self.process.wait(timeout=5)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        self.stream.close()


class Session:
    def __init__(self, root, name):
        self.root, self.name, self.closed = root, name, False
        root.mkdir()

    def open_sftp(self):
        return SFTP(self.root)

    def get_transport(self):
        return self

    def open_session(self, timeout):
        return Channel(self.root)

    def exec_command(self, command, timeout):
        # Preflight usa un script fijo: capturar solo la cantidad de puertos.
        self.assert_preflight = 'sys.version_info' in command
        ports = allocate_ports(2)
        out = io.BytesIO(json.dumps(dict(home='/home/pi', hostname=self.name,
            python='3.11', machine='aarch64', ports=ports)).encode())
        out.channel = type('Exit', (), {'recv_exit_status': lambda _: 0})()
        return None, out, io.BytesIO()

    def close(self):
        self.closed = True


class CollectionProgressTests(unittest.TestCase):
    def test_large_download_keeps_control_alive(self):
        from pathlib import PurePosixPath
        from lab.remote_runner import collect
        data=b'example record\n'*40000
        clock=[0.0];last_control=[0.0];released=[]
        class SlowFile(io.BytesIO):
            def read(self,size=-1):
                block=super().read(size)
                clock[0]+=len(block)/65536*10
                if clock[0]-last_control[0]>30:
                    raise TimeoutError('Remote worker lease expired during transfer')
                return block
        class SlowSFTP:
            def open(self,*args):return SlowFile(data)
            def stat(self,*args):return type('Stat',(),dict(st_size=len(data)))()
        def control():
            last_control[0]=clock[0]
            if clock[0]>=10 and not released:released.append(clock[0])
        with tempfile.TemporaryDirectory() as directory:
            collect(SlowSFTP(),PurePosixPath('/run'),Path(directory),['records.jsonl'],service=control)
            self.assertEqual((Path(directory)/'records.jsonl').read_bytes(),data)
        self.assertGreater(clock[0],30)
        self.assertLessEqual(released[0],30)


class RemoteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.algorithms = self.root / 'algorithms'
        self.algorithms.mkdir()
        self.patch = patch.object(plugins, 'DIRECTORY', self.algorithms)
        self.patch.start()
        refresh_registry()
        self.resolve = patch('lab.devices.resolve_host', return_value='127.0.0.1')
        self.resolve.start()

    def tearDown(self):
        self.doCleanups()
        self.resolve.stop()
        self.patch.stop()
        refresh_registry()
        self.temp.cleanup()

    def setup_run(self, mode):
        install(SOURCE.replace('MODE', repr(mode)))
        config = example('prueba_temporal', 2)
        config['nodes'][1]['params']['vector'] = [9, 43]
        sessions = {i: Session(self.root / f'pi{i}', f'pi-{i}') for i in (1, 2)}
        devices = {i: dict(id=str(i),name=f'Pi {i}',host=f'pi-{i}.local',port=22,user='admin') for i in (1, 2)}
        runner = LocalRunner(Store(self.root / 'data'))
        self.addCleanup(runner.shutdown)
        return runner, config, devices, sessions

    def assert_remote(self, mode):
        runner, config, devices, sessions = self.setup_run(mode)
        run_id = runner.start_remote(config, devices, sessions)
        runner.thread.join(timeout=40)
        self.assertFalse(runner.thread.is_alive())
        folder = runner.store.folder(run_id)
        record = read_json(folder / 'ejecucion.json')
        self.assertEqual(record['status'], 'completed', str(record) + str([p.read_text() for p in folder.glob('consola*')]))
        self.assertEqual(record['mode'], 'remote_tcp')
        self.assertTrue(read_json(folder / 'evaluacion.json')['records_valid'], read_json(folder / 'evaluacion.json'))
        saved = read_json(folder / 'config.json')
        self.assertEqual(saved['clock_scope'], 'per_agent')
        self.assertNotIn('clock_origin', saved)
        timing = read_json(folder/'tiempos.json')
        self.assertEqual(timing['status'], 'completed')
        self.assertGreater(timing['duration_s'], 0)
        self.assertEqual(timing['duration_s'], max(n['last_sample_s'] for n in timing['nodes'].values()))
        self.assertGreaterEqual(timing['observed_duration_s']+timing['alignment_margin_s'], timing['duration_s'])
        for entry in timing['nodes'].values():
            self.assertEqual(len(entry['calibration_start']['samples']),5)
            self.assertEqual(len(entry['calibration_end']['samples']),3)
            sample = entry['calibration_start']['best']
            self.assertAlmostEqual(sample['offset_s'],(sample['send_s']+sample['receive_s'])/2-sample['remote_s'])
        self.assertTrue((folder/'tiempos_agentes.csv').exists())
        for i in (1, 2):
            files = deployment_files(folder, i)
            self.assertNotIn('config.json', files)
            view = json.loads(files[f'config_agente_{i}.json'])
            self.assertEqual([n['id'] for n in view['nodes'] if 'params' in n], [i])
            self.assertEqual(view['execution_target'], 'remote')
            self.assertTrue(sessions[i].closed)

    def test_failed_authentication_closes_session_without_exposing_password(self):
        import paramiko
        from lab.devices import open_ssh
        for error in (paramiko.SSHException('No authentication methods available'),
                      paramiko.AuthenticationException('Authentication failed')):
            with patch('paramiko.SSHClient') as factory, patch('lab.devices.socket.create_connection') as sock:
                factory.return_value.connect.side_effect = error
                with self.assertRaises(ValueError) as caught:
                    open_ssh(dict(host='127.0.0.1',port=22,user='admin'), self.root/'known_hosts', password='synthetic_secret')
                self.assertNotIn('synthetic_secret', str(caught.exception))
                factory.return_value.close.assert_called_once()
                sock.return_value.close.assert_called_once()

    def test_sync(self):
        self.assert_remote('sync')

    def test_locked_local_log_does_not_stop_remote_agents(self):
        real_replace = __import__('os').replace
        blocked = []
        def replace(source, target):
            if Path(target).name == 'nodo_2.jsonl' and len(blocked) < 20:
                blocked.append(target)
                raise PermissionError('Windows reader holds log')
            real_replace(source, target)
        # Agotar los reintentos de una consulta y recuperar en la siguiente.
        with patch('lab.storage.os.replace', side_effect=replace):
            self.assert_remote('sync')
        self.assertEqual(len(blocked), 20)

    def test_async(self):
        self.assert_remote('async')

    def test_coordinator(self):
        self.assert_remote('coordinator')

    def test_duplicate_assignment_rejected_before_deployment(self):
        runner, config, devices, sessions = self.setup_run('sync')
        devices[2] = devices[1]
        with self.assertRaisesRegex(ValueError, 'diferente'):
            runner.start_remote(config, devices, sessions)
        self.assertEqual(runner.store.list_runs(), [])

    def test_stop_remote_preserves_partial_records(self):
        runner, config, devices, sessions = self.setup_run('sync')
        config.update(steps=500, period_s=.02)
        run_id = runner.start_remote(config, devices, sessions)
        until = time.monotonic() + 15
        while not all(s['round'] >= 3 for s in runner.states(run_id)) and time.monotonic() < until:
            time.sleep(.1)
        runner.stop()
        runner.thread.join(timeout=25)
        self.assertFalse(runner.thread.is_alive())
        self.assertEqual(read_json(runner.store.folder(run_id) / 'ejecucion.json')['status'], 'stopped')
        self.assertTrue((runner.store.folder(run_id) / 'nodo_1.jsonl').is_file())
