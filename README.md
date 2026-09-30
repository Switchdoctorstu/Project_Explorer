# MPP Programme Explorer

Desktop viewer for Microsoft Project plans using Python, Tkinter, JPype, and MPXJ (via the bundled ProjectLibre JAR).

## Features

- Load `.mpp`, `.mpt`, and `.xml` project files
- Explore programme structure, tasks, dependencies, resources, assignments, calendars, and project properties
- Export CSV registers
- Export offline 3D visualisation HTML
- Open dynamic 3D preview via local server

## Prerequisites

- Python 3.14+
- Java runtime compatible with the bundled MPXJ classes
- `projectlibre-1.9.8.jar` in the repository root

## Quick start (Windows PowerShell)

```powershell
cd .\Project_Explorer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python explorer.py
```

## Exports

Generated outputs default to the `REPORTS/` folder unless you choose another path.

## 3D visualisation modes

- **Open 3D preview**: serves from `http://127.0.0.1:<port>/...` and opens in browser
- **Export 3D visualisation...**: writes standalone offline HTML that works from `file://`

## Packaging

Package data is configured in `pyproject.toml` to include vendored JS assets under `mpp_explorer/reporting/assets/*.js`.
