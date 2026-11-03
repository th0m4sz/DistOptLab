# Función de este módulo: Valida los perfiles de funciones y su asignación a cada agente.
"""Perfiles opcionales del contrato: asignación local, independiente del dominio."""
import re


def profile_options(spec):
    rows = spec.get('function_profiles', [])
    if not isinstance(rows, list) or len(rows) > 30:
        raise ValueError('Declara hasta 30 perfiles de funciones')
    options = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Cada perfil necesita id y name')
        key, name = row.get('id'), row.get('name')
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,63}', key):
            raise ValueError('Identificador de perfil inválido')
        if key in options:
            raise ValueError('Hay identificadores de perfil repetidos')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Escribe un nombre para cada perfil')
        options[key] = name
    default = spec.get('default_profile')
    if options and (not isinstance(default, str) or default not in options):
        raise ValueError('Selecciona un perfil predeterminado válido')
    if not options and default:
        raise ValueError('El perfil predeterminado no existe')
    return options


def assigned_profile(spec, node):
    options = profile_options(spec)
    selected = node.get('function_profile', spec.get('default_profile'))
    if selected is not None and (not isinstance(selected, str) or selected not in options):
        raise ValueError(f'Agente {node["id"]}: perfil desconocido {selected!r}')
    return selected
