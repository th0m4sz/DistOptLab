"""Rutas de distribución, ejemplos públicos, finales de línea y accesos de Windows."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

import abrir
from herramientas.acceso_directo import create_shortcut
from herramientas.compartir import create_archive
from herramientas.publicar_ejemplos import public_config
from lab.algorithms import build, REGISTRY, refresh_registry
from lab import algorithm_library
from lab.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        refresh_registry()

    def test_public_examples_keep_math_and_private_defaults_have_priority(self):
        self.assertEqual(len(list(algorithm_library.PUBLIC_DEFAULTS.glob('*.json'))),5)
        for spec in REGISTRY.values():
            with self.subTest(algorithm=spec.id):
                public = read_json(algorithm_library.PUBLIC_DEFAULTS/f'{spec.id}.json')
                before = copy.deepcopy(public)
                loaded = algorithm_library.load_default(self.root/'private',spec)
                self.assertEqual(loaded,public)
                build(loaded)
                private = read_json(ROOT/'datos/ejemplos_predeterminados'/f'{spec.id}.json')
                if private:
                    self.assertEqual(public['parameters'],private['parameters'])
                    self.assertEqual(public['edges'],private['edges'])
                    self.assertEqual([n['params'] for n in public['nodes']],[n['params'] for n in private['nodes']])
                local = copy.deepcopy(public); local['name'] = 'Mi ejemplo local'
                write_json(algorithm_library.default_path(self.root/'private',spec.id),local)
                self.assertEqual(algorithm_library.load_default(self.root/'private',spec)['name'],'Mi ejemplo local')
                self.assertEqual(read_json(algorithm_library.PUBLIC_DEFAULTS/f'{spec.id}.json'),before)

    def test_sanitizer_drops_unknown_metadata_and_does_not_mutate_source(self):
        spec=REGISTRY['rccrd_coordinado'];config=spec.make_example(4,'anillo')
        config.update(execution_target='remote',private_note='PRIVATE_SENTINEL',clock_origin=123,
                      coordinator={'host':'PRIVATE_SENTINEL','port':9000})
        config['nodes'][1].update(host='PRIVATE_SENTINEL',device_id='PRIVATE_SENTINEL',private_note='PRIVATE_SENTINEL')
        before=copy.deepcopy(config)
        result=public_config(config,spec)
        self.assertEqual(config,before)
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))
        self.assertEqual(result['execution_target'],'local')
        self.assertEqual(result['nodes'][1]['host'],'127.0.0.1')

    def extracted(self):
        archive=create_archive(self.root/'entregas')
        with zipfile.ZipFile(archive) as bundle:
            names=bundle.namelist()
            self.assertFalse(any('/datos/' in n or '/tmp/' in n or '/.venv/' in n or '/__pycache__/' in n for n in names))
            self.assertIn(ROOT.name+'/herramientas/medir_resultados.py',names)
            self.assertNotIn(ROOT.name+'/medir_resultados.py',names)
            self.assertIn(ROOT.name+'/crear_acceso_directo.cmd',names)
            bundle.extractall(self.root/'copia con espacios y acentos á')
        return self.root/'copia con espacios y acentos á'/ROOT.name

    def test_extracted_copy_verifies_and_tools_work_from_other_directory(self):
        project=self.extracted()
        environment=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        commands=[['herramientas/verificar_instalacion.py'],['herramientas/medir_resultados.py','--help'],
                  ['herramientas/compartir.py','--help'],['herramientas/publicar_ejemplos.py','--help'],
                  ['herramientas/acceso_directo.py','--help']]
        for script,*args in commands:
            result=subprocess.run([sys.executable,str(project/script),*args],cwd=self.root,env=environment,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout.decode('utf-8',errors='replace')+result.stderr.decode('utf-8',errors='replace'))
        result=subprocess.run([sys.executable,'-m','herramientas.verificar_instalacion'],cwd=project,env=environment,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_extracted_app_starts_with_no_original_folder_or_private_data(self):
        project=self.extracted()
        with socket.socket() as holder:
            holder.bind(('127.0.0.1',0));port=holder.getsockname()[1]
        log=(self.root/'app.log').open('wb');self.addCleanup(log.close)
        process=subprocess.Popen([sys.executable,str(project/'app.py'),'--port',str(port),'--no-browser'],cwd=self.root,stdout=log,stderr=log)
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            result=None
            for _ in range(100):
                if process.poll() is not None:break
                try:
                    with opener.open(f'http://127.0.0.1:{port}/health',timeout=.3) as response:result=json.load(response)
                    break
                except OSError:time.sleep(.1)
            self.assertIsNotNone(result,(self.root/'app.log').read_text(errors='replace'))
            self.assertEqual(Path(result['data']),project/'datos')
            self.assertFalse((project/'datos/dispositivos.json').exists())
        finally:
            # En Windows el python.exe del venv puede ser un lanzador: cerrar
            # solo ese PID deja al intérprete hijo con el servidor y log abiertos.
            if process.poll() is None:
                if sys.platform == 'win32':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=True)
                else:
                    process.terminate()
            process.wait(timeout=15)
            log.close()

    @unittest.skipUnless(shutil.which('git'),'Se necesita Git para comprobar los atributos')
    def test_git_ignores_private_files_and_keeps_algorithm_bytes(self):
        repository=self.root/'git-check';repository.mkdir()
        for name in ('.gitignore','.gitattributes'):shutil.copy2(ROOT/name,repository/name)
        (repository/'algoritmos').mkdir();algorithm=repository/'algoritmos/prueba.py'
        original=b'print("ejemplo")\r\n';algorithm.write_bytes(original)
        (repository/'ejemplos/predeterminados').mkdir(parents=True)
        (repository/'ejemplos/predeterminados/prueba.json').write_text('{}')
        for name in ('tmp/privado.json','datos/dispositivos.json','.venv/archivo','servidor.log','local.lnk'):
            path=repository/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('PRIVATE_SENTINEL')
        def git(*args):return subprocess.run(['git',*args],cwd=repository,capture_output=True,check=True).stdout
        git('init','-q');git('config','core.autocrlf','true');git('add','.')
        names=git('ls-files').decode()
        self.assertIn('ejemplos/predeterminados/prueba.json',names)
        self.assertNotIn('privado',names);self.assertNotIn('dispositivos',names);self.assertNotIn('local.lnk',names)
        self.assertEqual(git('show',':algoritmos/prueba.py'),original)
        git('checkout-index','-a','-f')
        self.assertEqual(algorithm.read_bytes(),original)

    @unittest.skipUnless(sys.platform=='win32','Acceso de Windows')
    def test_shortcut_real_paths_idempotency_and_conflicts(self):
        desktop=self.root/'Escritorio';desktop.mkdir()
        first=self.root/"José & equipo's"/'proyecto';first.mkdir(parents=True);(first/'iniciar.cmd').write_text('@echo off')
        link=create_shortcut(first,desktop)
        self.assertEqual(Path(link['target']),first/'iniciar.cmd');self.assertEqual(Path(link['root']),first)
        self.assertTrue(Path(link['path']).is_file())
        self.assertEqual(create_shortcut(first,desktop)['path'],link['path'])
        second=self.root/'otro'/'proyecto';second.mkdir(parents=True);(second/'iniciar.cmd').write_text('@echo off')
        second_link=create_shortcut(second,desktop)
        self.assertNotEqual(second_link['path'],link['path'])
        third=self.root/'tercero'/'proyecto';third.mkdir(parents=True);(third/'iniciar.cmd').write_text('@echo off')
        with self.assertRaises(subprocess.CalledProcessError):create_shortcut(third,desktop)

    def test_launcher_reuses_matching_server_instead_of_spawning(self):
        stream=io.BytesIO(json.dumps(dict(service='distoptlab',data=str(abrir.ROOT/'datos'))).encode())
        with patch('abrir.urllib.request.build_opener') as factory,patch('abrir.webbrowser.open') as browser,patch('abrir.subprocess.call') as spawn:
            factory.return_value.open.return_value=stream
            self.assertEqual(abrir.main(),0)
            browser.assert_called_once_with(abrir.URL);spawn.assert_not_called()


if __name__=='__main__':unittest.main()
