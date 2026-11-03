# Función de este módulo: Convierte y valida los enlaces y la matriz de adyacencia utilizados en el formulario.
"""Conversión entre enlaces y matriz de adyacencia para el formulario.

La configuración guardada siempre usa ``edges``; la matriz es otra forma de
editar esos mismos enlaces, no un segundo formato de experimento.
"""
import math
import re


def parse_edges(text):
    """Lee una pareja por línea, con peso opcional: origen,destino[,peso]."""
    edges = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = [value.strip() for value in line.split(',')]
        if len(values) not in (2, 3):
            raise ValueError('Enlaces: escribe origen,destino o bien origen,destino,peso')
        try:
            i, j = int(values[0]), int(values[1])
            weight = float(values[2]) if len(values) == 3 else 1.0
        except ValueError as exc:
            raise ValueError('Enlaces: los agentes deben ser enteros y el peso numérico') from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError('Enlaces: el peso debe ser positivo y finito')
        edges.append([i, j] if len(values) == 2 else [i, j, weight])
    return edges


def format_edges(edges):
    return '\n'.join(','.join(str(value) for value in edge) for edge in edges)


def format_matrix(ids, edges):
    """La fila y columna k corresponden al agente mostrado en la posición k."""
    positions = {node_id: index for index, node_id in enumerate(ids)}
    matrix = [[0.0 for _ in ids] for _ in ids]
    for edge in edges:
        i, j = positions[edge[0]], positions[edge[1]]
        weight = edge[2] if len(edge) == 3 else 1
        matrix[i][j] = matrix[j][i] = weight
    # El punto y coma separa filas como en MATLAB; el salto mantiene legible
    # una matriz grande en el editor de texto.
    return ';\n'.join(' '.join(f'{value:g}' for value in row) for row in matrix)


def parse_matrix(text, ids):
    """Acepta filas separadas por salto o ';', como en una matriz de MATLAB."""
    source = text.strip()
    if source.startswith('[') and source.endswith(']'):
        source = source[1:-1]
    lines = [line.strip() for line in re.split(r'[;\n]+', source) if line.strip()]
    count = len(ids)
    if len(lines) != count:
        raise ValueError(f'Matriz: se necesitan {count} filas, una por agente')
    matrix = []
    for line in lines:
        cells = line.replace(',', ' ').split()
        if len(cells) != count:
            raise ValueError(f'Matriz: cada fila debe contener {count} valores')
        try:
            row = [float(cell) for cell in cells]
        except ValueError as exc:
            raise ValueError('Matriz: escribe solamente números') from exc
        if any(not math.isfinite(value) or value < 0 for value in row):
            raise ValueError('Matriz: los pesos deben ser finitos y no negativos')
        matrix.append(row)
    if any(matrix[i][i] != 0 for i in range(count)):
        raise ValueError('Matriz: la diagonal debe ser cero; no hay enlaces de un agente consigo mismo')
    edges = []
    for i in range(count):
        for j in range(i + 1, count):
            weight = matrix[i][j]
            if not math.isclose(weight, matrix[j][i], rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError('Matriz: debe ser simétrica porque los enlaces son bidireccionales')
            if weight:
                edges.append([ids[i], ids[j]] if weight == 1 else [ids[i], ids[j], weight])
    return edges
