# DistOptLab

**Distributed Optimization Laboratory** — a configurable experimental platform for local processes and Raspberry Pi networks.

[Español](README.es.md) · [Python contract](docs/CONTRATO.md) · [First algorithm](docs/PRIMER_ALGORITMO.md)

DistOptLab is an open-source experimental platform for designing and evaluating distributed optimization algorithms. It brings together algorithm definition, execution on a PC or Raspberry Pi network, and visualization of recorded results. Users can compare communication modes and network topologies, and study how algorithms respond to scheduled node withdrawal and return.

The interface and detailed guides are currently in Spanish. This README provides the installation and first-run instructions in English. DistOptLab is distributed under the [MIT license](LICENSE).

## Features

- Define algorithms through a guided equation editor or a commented Python template.
- Run one independent Python process per agent locally, or deploy to Raspberry Pi using SSH/SFTP; algorithm messages use TCP.
- Select synchronous, asynchronous latest-sample, or explicit-coordinator communication.
- Configure ring, star, complete or custom graphs, local data and function profiles.
- Schedule participant withdrawal/return and parameter changes.
- Inspect agent states, received input versions, CSV records and interactive plots; export PNG, PDF and SVG figures.

Execution completion does not certify convergence, feasibility or optimality. Asynchronous messaging does not automatically make an algorithm mathematically asynchronous-safe. Imported Python algorithms execute as local code; use trusted files.

## Installation

The tested host setup is Windows x64 with Python 3.11. A Raspberry Pi is optional for local experiments. Internet access is required to download dependencies. Other Python versions and operating systems require their own validation.

1. Install Python 3.11 x64 with its `py` launcher.
2. Download or clone this repository into a writable folder and extract any ZIP fully.
3. Double-click `instalar.cmd`. This creates an independent `.venv`, installs `requirements-lock.txt`, runs `pip check` and checks the application files.
4. Double-click `iniciar.cmd`, then open **http://127.0.0.1:8778**. Keep the terminal running. Stop active experiments and press Ctrl+C in the terminal to close the server.

From PowerShell, the equivalent commands are:

```powershell
py -3.11 instalar.py
.venv\Scripts\python.exe abrir.py
```

For another port, run `.venv\Scripts\python.exe app.py --port 8780` and open that port manually. This is useful if another copy is already running. Do not reuse a virtual environment copied from another machine.

On Linux/macOS, use `python3 instalar.py` and `.venv/bin/python abrir.py`. Those complete installation paths have not been validated for this release. Saved SSH passwords use Windows Credential Manager; on other systems enter passwords temporarily.

`requirements.txt` lists direct dependencies. `requirements-lock.txt` fixes their transitive dependencies for installation; both files are intentional.

## First experiment

1. Open **Ver ejemplo guiado** (guided example), then **Cargar ejemplo listo para ejecutar** (load ready-to-run example).
2. Select **Laptop (procesos locales)** (local processes) and start the experiment.
3. Open **Ejecución** (execution), select `x`, and choose the agents and horizontal axis.
4. Use **Guardar disposición de gráficas** to remember the plot layout. Results are stored locally in `datos/experimentos/`.

No SSH connection or credentials are needed for this example. The five ready-to-use presets are in [ejemplos/predeterminados/](ejemplos/predeterminados/), and their algorithm code is in [algoritmos/](algoritmos/). They include RDCF, coordinated RCCRD, reference consensus and two tutorials. Saved parameter values are preserved; all supplied endpoints are loopback-only.

To use a preset, select its method in the **Algoritmo** (algorithm) menu: the default configuration loads automatically. To reload it after editing fields, expand **Ejemplo predeterminado** and click **Cargar ejemplo predeterminado**. A default you have saved yourself takes priority over the bundled preset.

The algorithm shown as **RDCF — dinámica de replicadores con factores de capacidad** corresponds to *Replicator Dynamics with Capacity Factors* in the paper. Its stable internal ID is `distribuido_ccrd`. This display-name change does not alter its equations.

## Reproduce the paper settings

[Article configurations](ejemplos/articulo/README.md) provide 18 six-agent configurations separately from the original default examples. They are in `ejemplos/articulo/`, organized by scenario, algorithm, topology and communication mode. Each case contains a `configuracion.json`: expand **Abrir una configuración guardada** (open a saved configuration), then click **Seleccionar JSON** to load it. They are prepared for local execution. To run on boards, first register and verify your own devices, then assign agents through the SSH/TCP execution dialog.

The article configurations are inputs, not the historical experimental records. This minimal software release does not contain the paper draft, private deployment information, raw campaign logs or result images. Do not describe this repository as containing those records until a separately sanitized research dataset is published.

## Documentation and structure

- `app.py`, `abrir.py`, `*.cmd`: application and launch/install entry points.
- `lab/`: algorithm runtime, communication, deployment, storage and UI helpers.
- `algoritmos/`, `ejemplos/`, `plantillas/`: algorithm code, public configurations and Python template.
- `docs/`: essential Spanish guides: [editor](docs/ASISTENTE.md), [contract](docs/CONTRATO.md), [profiles](docs/PERFILES_FUNCIONES.md), [boards](docs/EJECUCION_PLACAS.md), [withdrawal](docs/FALLAS.md) and [parameter changes](docs/DEMANDA_VARIABLE.md).
- `herramientas/`: installation checks, public example preparation, portable ZIP and Windows shortcut.
- `tests/`: automated checks. Run `.venv\Scripts\python.exe -m unittest discover -s tests`.

`datos/`, `.venv/`, caches, logs and personal device inventories are generated locally and excluded from Git. Loopback addresses such as `127.0.0.1` are required local endpoints, not saved board addresses. TCP/SSH ports and protocol identifiers in the source are functional settings, not credentials.

Optional Windows desktop shortcut: run `crear_acceso_directo.cmd` after installation. A portable source ZIP can be created with `.venv\Scripts\python.exe -m herramientas.compartir`; its recipient must install their own environment.

See [third-party notices](THIRD_PARTY_NOTICES.md). No external credentials or SSH keys are distributed.
