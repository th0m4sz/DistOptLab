"""Crea un acceso directo de Windows; no copia ni instala otra aplicación."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

# Las rutas viajan por JSON: espacios, apóstrofes y & no se interpretan como código.
SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$shortcutData = $env:LAB_SHORTCUT_REQUEST | ConvertFrom-Json
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcutDirectory = $shortcutData.directory
if (-not $shortcutDirectory) { $shortcutDirectory = $shortcutShell.SpecialFolders.Item('Desktop') }
if (-not (Test-Path -LiteralPath $shortcutDirectory -PathType Container)) { throw 'No existe la carpeta de destino' }
$shortcutFile = Join-Path $shortcutDirectory 'DistOptLab.lnk'
if (Test-Path -LiteralPath $shortcutFile) {
  $oldShortcut = $shortcutShell.CreateShortcut($shortcutFile)
  if ($oldShortcut.TargetPath -ne $shortcutData.target) {
    $shortcutFile = Join-Path $shortcutDirectory ('DistOptLab (' + $shortcutData.name + ').lnk')
    if (Test-Path -LiteralPath $shortcutFile) {
      $otherShortcut = $shortcutShell.CreateShortcut($shortcutFile)
      if ($otherShortcut.TargetPath -ne $shortcutData.target) { throw 'Ya existe otro acceso con ese nombre; no se reemplaza' }
    }
  }
}
$shortcut = $shortcutShell.CreateShortcut($shortcutFile)
$shortcut.TargetPath = $shortcutData.target
$shortcut.WorkingDirectory = $shortcutData.root
$shortcut.Description = 'Abrir DistOptLab'
$shortcut.WindowStyle = 7
$shortcut.IconLocation = Join-Path $env:SystemRoot 'System32\shell32.dll'
$shortcut.Save()
$checkedShortcut = $shortcutShell.CreateShortcut($shortcutFile)
if ($checkedShortcut.TargetPath -ne $shortcutData.target -or $checkedShortcut.WorkingDirectory -ne $shortcutData.root) { throw 'El acceso no tiene las rutas esperadas' }
@{path=$shortcutFile; target=$checkedShortcut.TargetPath; root=$checkedShortcut.WorkingDirectory} | ConvertTo-Json -Compress
'''


def create_shortcut(root=ROOT, directory=None):
    if sys.platform != 'win32':
        raise ValueError('El acceso .lnk corresponde a Windows')
    root = Path(root).resolve()
    target = root / 'iniciar.cmd'
    if not target.is_file():
        raise ValueError('No se encontró iniciar.cmd en la plataforma')
    request = dict(root=str(root), target=str(target), name=root.name,
                   directory=str(Path(directory).resolve()) if directory else None)
    environment = dict(os.environ, LAB_SHORTCUT_REQUEST=json.dumps(request))
    command = [str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),
               '-NoProfile', '-NonInteractive', '-Command', SCRIPT]
    result = subprocess.run(command, env=environment, capture_output=True, check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(result.stdout.decode('utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path, help='Carpeta; por defecto el escritorio real de Windows')
    args = parser.parse_args()
    try:
        value = create_shortcut(directory=args.destino)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.decode('utf-8', errors='replace').splitlines()[0] if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f'No se pudo crear el acceso directo: {detail}', file=sys.stderr)
        return 1
    print('Acceso creado: ' + value['path'])
    print('Apunta a esta carpeta. Si la mueves, vuelve a crear el acceso directo.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
