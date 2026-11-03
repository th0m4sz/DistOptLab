# Función de este módulo: Compara duraciones de ensayos archivados sin ejecutar algoritmos.
"""Una fila por ensayo: condiciones visibles, sin mezclar trabajo o precisión distintos."""
import csv
import io
import math
from pathlib import Path

from .storage import read_json


COLUMNS = [('reference','Ensayo'),('duration_s','Duración (s)'),('mode','Comunicación'),('target','Equipo'),('algorithm','Algoritmo'),
           ('nodes','Agentes'),('topology','Topología'),('steps','Iteraciones previstas por agente'),
           ('period_s','Espera mínima (s)'),
           ('observed_s','Confirmación (s)'),('margin_s','Margen estimado (s)'),
           ('status','Estado'),('criterion','Criterio declarado'),('id','Identificador del registro')]


def duration_rows(folders):
    rows = []
    for folder in folders:
        folder = Path(folder)
        config = read_json(folder/'config.json')
        record = read_json(folder/'ejecucion.json')
        timing = read_json(folder/'tiempos.json', {})
        report = read_json(folder/'evaluacion.json', {})
        complete = record['status']=='completed' and timing.get('status')=='completed'
        def measured(key):
            value = timing.get(key)
            return value if complete and type(value) in (int,float) and math.isfinite(value) else None
        rows.append(dict(reference=len(rows)+1, id=record['id'], algorithm=config.get('algorithm_name') or config['algorithm'],
                         target='Raspberry Pi' if record.get('mode')=='remote_tcp' else 'Laptop',
                         mode={'sync':'Síncrono','async':'Asíncrono','coordinator':('Coordinador asíncrono' if config.get('coordinator_exchange')=='async' else 'Coordinador síncrono')}.get(config.get('execution_mode'),config.get('execution_mode','Sin declarar')),
                         nodes=len(config['nodes']),topology=config.get('topology','Personalizada'),
                         steps=config['steps'],period_s=config['period_s'],duration_s=measured('duration_s'),
                         observed_s=measured('observed_duration_s'),margin_s=measured('alignment_margin_s'),
                         status='Terminado' if record['status']=='completed' else record['status'],
                         criterion=('Cumplido' if report.get('converged') else 'No cumplido') if report.get('convergence_evaluated') else 'Sin criterio evaluado'))
    return rows


def duration_csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=[k for k,_ in COLUMNS])
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()
