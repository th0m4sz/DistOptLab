# Función de este módulo: Guarda y consulta contraseñas SSH opcionales en el almacén de credenciales de Windows.
"""Contraseñas SSH opcionales en Windows Credential Manager, fuera de los ensayos."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os


def supported():
    return os.name == 'nt'


def target(device):
    identity = [device['id'], device['host'].lower(), device['port'], device['user']]
    digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    # Esta variante no modifica ni elimina las contraseñas de la plataforma original.
    return 'DistOptLab/SSH/' + digest


class Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
                ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
                ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)), ('Persist', wintypes.DWORD),
                ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


def api():
    if not supported():
        raise ValueError('Guardar contraseñas está disponible en Windows; puedes introducirla al conectar.')
    lib = ctypes.WinDLL('advapi32', use_last_error=True)
    lib.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.POINTER(ctypes.POINTER(Credential))]
    lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    for name in ('CredWriteW', 'CredReadW', 'CredDeleteW'):
        getattr(lib, name).restype = wintypes.BOOL
    lib.CredFree.argtypes = [ctypes.c_void_p]
    lib.CredFree.restype = None
    return lib


def failure(action):
    # Nunca incluir la contraseña, ni una estructura que la contenga, en errores.
    code = ctypes.get_last_error()
    raise OSError(f'No se pudo {action} la contraseña en Windows (código {code}).')


def save_password(device, password):
    data = password.encode('utf-8')
    if not data or len(data) > 2560:
        raise ValueError('Introduce una contraseña de hasta 2560 bytes para guardarla.')
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    cred = Credential(Type=1, TargetName=target(device),
                      Comment='Contraseña SSH de la plataforma flexible',
                      CredentialBlobSize=len(data), CredentialBlob=buffer,
                      Persist=2, UserName=device['user'])  # Persiste en este equipo/usuario.
    try:
        if not api().CredWriteW(ctypes.byref(cred), 0):
            failure('guardar')
    finally:
        ctypes.memset(buffer, 0, len(data))


def read_password(device):
    if not supported():
        return None
    lib = api()
    pointer = ctypes.POINTER(Credential)()
    if not lib.CredReadW(target(device), 1, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == 1168:
            return None
        failure('leer')
    try:
        cred = pointer.contents
        return ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode('utf-8')
    finally:
        if pointer.contents.CredentialBlobSize:
            ctypes.memset(pointer.contents.CredentialBlob, 0, pointer.contents.CredentialBlobSize)
        lib.CredFree(pointer)


def has_password(device):
    return read_password(device) is not None


def forget_password(device):
    if not supported():
        return
    if not api().CredDeleteW(target(device), 1, 0) and ctypes.get_last_error() != 1168:
        failure('eliminar')


def connection_password(device, entered, use_saved=True):
    """La entrada puntual tiene prioridad; el secreto guardado nunca va al navegador."""
    return entered or (read_password(device) if use_saved else None)
