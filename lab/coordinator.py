# Función de este módulo: Ejecuta el proceso separado que reúne estados y calcula los agregados declarados por el algoritmo.
"""Proceso separado para algoritmos que declaran un coordinador matemático."""
import argparse
import os
from pathlib import Path
import time

from .algorithms import build_saved
from .storage import now,read_json,write_json
from .transport import Coordinator,serve


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    runtime=build_saved(read_json(args.folder/'config.json'),args.folder)
    endpoint=runtime.config['coordinator']
    status_path=args.folder/'coordinador.json'
    server=serve((endpoint['host'],endpoint['port']),Coordinator(runtime,args.run_id).respond)
    write_json(status_path,dict(role='coordinador matemático',pid=os.getpid(),status='running',
               connection=f'servidor TCP {endpoint["host"]}:{endpoint["port"]}',updated_at=now()))
    try:
        while not any((args.folder/name).exists() for name in ('DETENER','FINALIZAR')):
            if runtime.config.get('execution_target') == 'remote':
                try:
                    if time.time() - (args.folder/'GESTOR_ACTIVO').stat().st_mtime > 30:
                        break
                except FileNotFoundError:
                    break
            if runtime.fault_plan.enabled:
                current=max([b for b in runtime.fault_plan.boundaries if (args.folder/f'FASE_{b}.LISTA').exists()] or [0])
                offline=runtime.fault_plan.offline('coordinator',max(0,current))
                write_json(status_path,dict(role='coordinador matemático',pid=os.getpid(),
                    status='faulted' if offline else 'running', simulated_failure=offline,
                    connection=f'servidor TCP {endpoint["host"]}:{endpoint["port"]}',updated_at=now()))
            time.sleep(.05)
    finally:
        server.shutdown()
        server.server_close()
        write_json(status_path,dict(role='coordinador matemático',pid=os.getpid(),status='completed',
                   connection=f'servidor TCP {endpoint["host"]}:{endpoint["port"]}',updated_at=now()))


if __name__=='__main__':
    main()
