# Función de este módulo: Gestiona el inventario de placas y comprueba las conexiones para el despliegue remoto.
"""Inventario y diagnóstico; credenciales opcionales gestionadas en lab.credentials."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import uuid

from .storage import write_bytes_atomic

_HOST_KEYS_LOCK = threading.Lock()


def validate_device(raw):
    """Acepta hostnames o IP; el usuario y el puerto no dependen de pi-x.local."""
    name = str(raw.get('name', '')).strip()
    host = str(raw.get('host', '')).strip()
    user = str(raw.get('user', '')).strip()
    if not name or len(name) > 80:
        raise ValueError('Escribe un nombre de dispositivo de hasta 80 caracteres')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?', host):
            raise ValueError('Escribe un hostname o una IP, sin protocolo ni ruta')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+', user):
        raise ValueError('Usuario SSH inválido')
    port = raw.get('port', 22)
    if isinstance(port, bool) or int(port) != port or not 1 <= int(port) <= 65535:
        raise ValueError('Puerto SSH inválido')
    return dict(id=raw.get('id') or uuid.uuid4().hex, name=name, host=host,
                user=user, port=int(port))


def probe(device):
    """Comprueba resolución y servicio SSH sin autenticarse ni ejecutar comandos."""
    try:
        target = resolve_host(device['host'], device['port'])
        with socket.create_connection((target, device['port']), timeout=2) as sock:
            ip = sock.getpeername()[0]
            sock.settimeout(2)
            banner = sock.recv(255).decode('ascii', errors='replace').strip()
            if not banner.startswith('SSH-'):
                return dict(**device, status='Servicio diferente', detail=f'{ip}: no se recibió identificación SSH')
            return dict(**device, status='SSH disponible', detail=f'{ip} · pendiente autenticar')
    except socket.gaierror:
        return dict(**device, status='Nombre no resuelto', detail='Comprueba la red, el hostname o utiliza la IP.')
    except OSError as exc:
        return dict(**device, status='Sin conexión', detail=str(exc))


def resolve_host(host, port=22):
    """Resuelve un hostname o devuelve su IP; en Windows añade soporte mDNS.

    Algunas versiones de Winsock usadas por Python no consultan mDNS aunque
    Resolve-DnsName sí pueda resolver `.local`. La alternativa recibe un host
    ya validado y nunca construye comandos a partir de texto libre.
    """
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return host
    except socket.gaierror as original:
        if os.name != 'nt' or not host.lower().endswith('.local'):
            raise original
        # validate_device restringe host a letras, números, puntos y guiones;
        # repetir la comprobación mantiene segura esta función si se usa sola.
        if not re.fullmatch(r'[a-zA-Z0-9.-]+', host):
            raise original
        script = f"(Resolve-DnsName -Name '{host}' -Type A -ErrorAction Stop).IPAddress"
        try:
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                    capture_output=True, text=True, timeout=5, check=False)
            for line in result.stdout.splitlines():
                candidate = line.strip()
                try:
                    if isinstance(ipaddress.ip_address(candidate), ipaddress.IPv4Address):
                        return candidate
                except ValueError:
                    continue
        except (OSError, subprocess.SubprocessError):
            pass
        raise original


def probe_all(devices):
    """Comprueba varios dispositivos sin esperar secuencialmente a cada timeout."""
    if not devices:
        return []
    with ThreadPoolExecutor(max_workers=min(12, len(devices))) as pool:
        return list(pool.map(probe, devices))


class UnknownHost(Exception):
    """Pide al formulario mostrar la huella que el usuario debe verificar."""
    def __init__(self, fingerprint):
        super().__init__('Verifica la identidad de esta placa antes de guardar su clave de host.')
        self.fingerprint = fingerprint


def key_fingerprint(key):
    """Representa una clave pública SSH sin mostrar su contenido completo."""
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


def open_ssh(device, known_hosts, password=None, key_filename=None, expected_fingerprint=None, *, accept_new=False):
    """Abre SSH con identidad verificada; el llamador debe cerrar la sesión.

    accept_new permite confiar en la primera identidad, nunca en una cambiada.
    Las identidades nuevas se guardan solo después de autenticar correctamente.
    La escritura combina claves bajo un candado y es atómica para los lotes.
    """
    import paramiko

    if key_filename:
        key_path = Path(key_filename).expanduser()
        if not key_path.is_file():
            raise ValueError('No existe el archivo de clave privada indicado. Si usas contraseña, deja ese campo vacío.')
        key_filename = str(key_path)
    # Resolver primero permite explicar claramente un fallo de hostname. Si
    # getaddrinfo falla, Paramiko mostraría únicamente un código de Windows.
    try:
        target = resolve_host(device['host'], device['port'])
    except socket.gaierror as exc:
        raise ValueError(f'Windows no puede resolver {device["host"]}. Edita el dispositivo y usa el hostname real o su IP.') from exc
    transport_socket = socket.create_connection((target, device['port']), timeout=4)

    pending_keys = []

    class VerifyHost(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            fingerprint = key_fingerprint(key)
            if ((expected_fingerprint is not None and fingerprint != expected_fingerprint)
                    or (expected_fingerprint is None and not accept_new)):
                raise UnknownHost(fingerprint)
            client.get_host_keys().add(hostname, key.get_name(), key)
            pending_keys.append((hostname, key))

    client = paramiko.SSHClient()
    try:
        client.load_system_host_keys()
        if Path(known_hosts).exists():
            client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(VerifyHost())
        try:
            client.connect(device['host'], port=device['port'], username=device['user'], sock=transport_socket,
                           password=password or None, key_filename=key_filename or None,
                           allow_agent=False, look_for_keys=False,
                           timeout=4, banner_timeout=4, auth_timeout=4)
        except paramiko.BadHostKeyException as exc:
            raise ValueError('La clave de host cambió. Actual: ' + key_fingerprint(exc.key) +
                             '; guardada: ' + key_fingerprint(exc.expected_key) +
                             '. Verifica en la placa: ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub. '
                             'No se reemplazó la identidad guardada.') from exc
        except paramiko.AuthenticationException as exc:
            raise ValueError('SSH rechazó la autenticación. Comprueba el usuario y la contraseña de esta placa.') from exc
        except paramiko.SSHException as exc:
            if 'No authentication methods available' in str(exc):
                raise ValueError('Introduce la contraseña SSH. Raspberry Pi Connect no proporciona automáticamente esas credenciales a la plataforma.') from exc
            raise
        if pending_keys:
            with _HOST_KEYS_LOCK:
                merged = paramiko.HostKeys()
                if Path(known_hosts).exists():
                    merged.load(str(known_hosts))
                for hostname, key in pending_keys:
                    # Otra conexión del lote pudo registrar este host mientras
                    # autenticábamos. No aceptar identidades contradictorias.
                    previous = merged.lookup(hostname)
                    if previous and (key.get_name() not in previous or previous[key.get_name()] != key):
                        raise ValueError('La identidad SSH cambió durante la comprobación. No se guardó la clave nueva.')
                    merged.add(hostname, key.get_name(), key)
                data = ''.join(f'{host} {kind} {key.get_base64()}\n'
                               for host, keys in merged.items() for kind, key in keys.items())
                write_bytes_atomic(Path(known_hosts), data.encode('utf-8'))
        return client
    except BaseException:
        client.close()
        transport_socket.close()
        raise


def check_ssh(device, known_hosts, password=None, key_filename=None, expected_fingerprint=None, *, accept_new=False):
    """Consulta Python y SFTP, sin instalar software ni conservar credenciales."""
    client = open_ssh(device, known_hosts, password, key_filename, expected_fingerprint, accept_new=accept_new)
    try:
        _, stdout, stderr = client.exec_command('python3 --version', timeout=5)
        version = stdout.read(1024).decode(errors='replace').strip()
        error = stderr.read(1024).decode(errors='replace').strip()
        if stdout.channel.recv_exit_status() != 0:
            raise ValueError(error or 'Python 3 no está disponible en esta placa')
        match = re.fullmatch(r'Python (\d+)\.(\d+)(?:\.\S+)?', version)
        if not match or tuple(map(int, match.groups())) < (3, 10):
            raise ValueError(f'Se necesita Python 3.10 o posterior; la placa informa: {version or "versión desconocida"}.')
        with client.open_sftp() as sftp:
            sftp.get_channel().settimeout(5)
            sftp.stat('.')
        return f'{version} · acceso SSH y SFTP comprobado'
    finally:
        client.close()


def check_access_all(devices, known_hosts, passwords=None, *, use_saved=True):
    """Una sesión por placa: autentica, consulta Python y prueba SFTP.

    Lote acotado a cuatro conexiones simultáneas; cada resultado es independiente.
    Los secretos se leen en el servidor y nunca forman parte del resultado.
    No realiza un sondeo TCP previo ni reintenta contraseñas rechazadas.
    """
    from .credentials import connection_password
    from .storage import now

    passwords = passwords or {}
    unique = {d['id']: dict(d) for d in devices}

    def check(device):
        secret = None
        try:
            secret = connection_password(device, passwords.get(device['id']), use_saved)
            if not secret:
                return dict(**device, status='Falta contraseña',
                            detail='Edita esta placa e introduce su contraseña SSH.', checked_at=now())
            message = check_ssh(device, known_hosts, secret, accept_new=True)
            return dict(**device, status='Acceso comprobado', detail=message, checked_at=now())
        except Exception as exc:
            message = str(exc)
            if secret:
                message = message.replace(secret, '[contraseña oculta]')
            return dict(**device, status='Error de acceso', detail=message, checked_at=now())

    if not unique:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(unique))) as pool:
        return list(pool.map(check, unique.values()))
