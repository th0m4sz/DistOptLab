"""Recalcula los tiempos y exporta la curva temporal desde registros archivados.

Uso desde la raíz: python -m herramientas.medir_resultados datos/experimentos/ID --intervalo 0.1
No ejecuta actualizaciones ni cambia el criterio de convergencia del algoritmo.
"""
import argparse
import csv
import math
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab.storage import read_json
from lab.temporal_results import temporal_rows, timing_text, export_timing


def verify_timing(folder):
    data = read_json(Path(folder)/'tiempos.json', {})
    if data.get('status') != 'completed':
        raise ValueError('No hay una medición completa con el protocolo temporal')
    durations = []
    for node, entry in data['nodes'].items():
        initial = entry.get('calibration_start')
        if initial:
            samples = initial['samples']
            for sample in samples+entry.get('calibration_end', {}).get('samples', []):
                expected = (sample['send_s']+sample['receive_s'])/2-sample['remote_s']
                half = (sample['receive_s']-sample['send_s'])/2
                if half < 0 or not math.isclose(expected,sample['offset_s'],abs_tol=1e-9) or not math.isclose(half,sample['half_round_trip_s'],abs_tol=1e-9):
                    raise ValueError(f'Calibración inconsistente: agente {node}')
            if initial['best'] != min(samples,key=lambda s:s['half_round_trip_s']):
                raise ValueError(f'Selección de calibración inconsistente: agente {node}')
            if entry['offset_s'] != initial['best']['offset_s']:
                raise ValueError(f'Offset inconsistente: agente {node}')
        from lab.results import read_records
        rows = read_records(folder,int(node),strict=True)
        if not rows or rows[-1].get('monotonic_s') != entry['final']['last_sample_monotonic_s']:
            raise ValueError(f'La última marca no coincide con el JSONL: agente {node}')
        duration = max(0.0, rows[-1]['monotonic_s']+entry['offset_s']-data['origin_monotonic_s'])
        if not math.isclose(duration,entry['last_sample_s'],abs_tol=1e-9):
            raise ValueError(f'Duración inconsistente: agente {node}')
        durations.append(duration)
    if not math.isclose(max(durations),data['duration_s'],abs_tol=1e-9):
        raise ValueError('Duración global inconsistente')
    return data['duration_s']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experimento', type=Path)
    parser.add_argument('--intervalo',type=float,default=.1)
    args = parser.parse_args()
    print(timing_text(args.experimento))
    timing = read_json(args.experimento/'tiempos.json', {})
    if timing.get('status') == 'completed':
        print(f'Duración recalculada y consistente: {verify_timing(args.experimento):.9f} s')
    rows = temporal_rows(args.experimento,args.intervalo)
    if rows:
        path = args.experimento/'serie_global_por_tiempo.csv'
        with path.open('w',newline='',encoding='utf-8') as stream:
            writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f'{len(rows)} muestras; intervalo base {args.intervalo} s; {path}')
    else:
        print('Sin curva global temporal: requiere referencia común y métricas del asistente.')
    export_timing(args.experimento)


if __name__=='__main__':
    main()
