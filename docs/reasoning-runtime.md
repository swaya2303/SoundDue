# SoundDue — Reasoning Runtime

> [!WARNING]
> The MeTTa / Hyperon runtime is **experimental**. The Python API may change
> between patch versions. This project is pinned to `hyperon==0.2.10`.
> Review the Hyperon CHANGELOG before upgrading.

---

## Verified hyperon version

| Version | Verified? |
|---------|-----------|
| `0.2.10` | ✅ Verified — downloaded and tested |

**Wheel availability** (as of 2026-10-20):

| Python | Platform | Wheel available? |
|--------|----------|-----------------|
| 3.8 | win_amd64 | ✅ yes |
| 3.9 | win_amd64 | ✅ yes |
| 3.10 | win_amd64 | ✅ yes |
| 3.11 | win_amd64 | ✅ yes |
| **3.12** | **win_amd64** | ✅ **yes — used by SoundDue** |
| 3.13 | win_amd64 | ❌ **no wheel** |

Python 3.13 is **not supported** by any published hyperon wheel. The backend
stays on 3.13; only the `reasoning/` layer uses Python 3.12.

---

## Architecture

```
backend/  (Python 3.13 — FastAPI, SQLAlchemy, etc.)
    │
    └── does NOT import hyperon directly
        └── may call reasoning.engine.MettaEngine via METTA_MODE=http

reasoning/  (Python 3.12 venv — hyperon==0.2.10)
    ├── .venv/         ← isolated Python 3.12 environment
    ├── wrapper.py     ← ONLY file that imports hyperon
    ├── engine.py      ← MettaEngine abstraction (InProcess / Http)
    ├── facts.py       ← DB records → MeTTa facts
    └── rules/
        └── base.metta ← MeTTa rules (trusted, not sanitised)
```

---

## Installation

### Prerequisites

Install `uv` (fast Python package manager):

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Add to PATH for the session:
$env:Path = "C:\Users\$env:USERNAME\.local\bin;$env:Path"
```

### Create the reasoning venv (Python 3.12)

```powershell
# From the repo root:
uv python install 3.12
uv venv reasoning\.venv --python 3.12
uv pip install -r reasoning\requirements.txt --python reasoning\.venv\Scripts\python.exe
```

### Verify the installation

```powershell
reasoning\.venv\Scripts\python.exe -c "
from hyperon import MeTTa
m = MeTTa()
r = m.run('!(+ 1 2)')
print('hyperon OK — result:', r)
"
# Expected: hyperon OK — result: [[3]]
```

---

## Running tests

```powershell
reasoning\.venv\Scripts\python.exe -m pytest reasoning\tests\ -v
```

> [!IMPORTANT]
> Run tests with `reasoning\.venv\Scripts\python.exe`, **not** the system
> Python 3.13. The tests will skip automatically with a clear message if
> hyperon is not found.

---

## Quick-check target

```powershell
make check-metta
```

This loads a one-line MeTTa fact, runs a `match` query, and prints the result.

---

## METTA_MODE

| Value | Description |
|-------|-------------|
| `inprocess` (default) | Runs hyperon in-process. Requires the `reasoning/.venv` (Python 3.12). |
| `http` | Delegates to the `metta` micro-service. Requires `docker compose up metta`. |

Set with an environment variable:

```powershell
$env:METTA_MODE = "inprocess"   # default
$env:METTA_MODE = "http"        # use micro-service
```

### When to use the fallback (`METTA_MODE=http`)

Use the HTTP fallback when:

- The main backend **must** stay on a Python version that has no hyperon wheel
  (e.g. Python 3.13).
- You want to isolate the MeTTa runtime in a Docker container for deployment.
- You need to scale the reasoning service independently.

The `reasoning/service/` directory contains a small FastAPI app (Dockerfile
based on `python:3.12-slim`) exposing `POST /reason`, `GET /health`, and
`GET /runtime`.

```powershell
# Start the metta service:
docker compose up metta
# Then in your shell:
$env:METTA_MODE = "http"
make check-metta
```

---

## Injection safety

All user-supplied strings (IDs, titles, contributor names, territory codes,
etc.) are passed through `reasoning.wrapper.quote()` before being embedded
in MeTTa source. `quote()` produces a MeTTa **string literal** (double-quoted,
with internal backslashes and double-quotes escaped) so that arbitrary user text
cannot be interpreted as a MeTTa symbol, directive, or sub-expression.

**Never concatenate raw user data into MeTTa source text.**

---

## Experimental status

Hyperon / MeTTa is an **experimental** runtime by SingularityNET. In this
prototype it is used as a lightweight logic layer for fact loading and pattern
matching. Known limitations:

- The Python API (`hyperon.MeTTa`, `metta.run()`) may change between releases.
- Performance is not benchmarked; not suitable for large-scale reasoning.
- No persistent space — every `query()` call creates a fresh `MeTTa()` instance.

This is documented as a prototype shortcut in [`docs/prototype-shortcuts.md`](prototype-shortcuts.md).
