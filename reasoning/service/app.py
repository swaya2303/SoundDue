"""
reasoning/service/app.py
========================
Tiny FastAPI micro-service that exposes MeTTa query execution over HTTP.

Used when METTA_MODE=http.  The backend (Python 3.13) sends facts+rules to
this service; this service runs them in hyperon (Python 3.12) and returns
structured results.

Endpoints
---------
POST /reason
    Request:  {program: str, expr: str}
    Response: {results: list[str], expr: str}

GET /health
    Response: {status: "ok"}

GET /runtime
    Response: {python_version: str, hyperon_version: str}

EXPERIMENTAL
------------
Hyperon / MeTTa is experimental. See docs/reasoning-runtime.md.

INJECTION SAFETY
----------------
The ``program`` field is assembled by reasoning/facts.py which calls
``quote()`` on all user text.  The service itself does not need to sanitise
further, but it rejects requests where the ``program`` field contains an
unquoted ``!`` outside string literals (belt-and-suspenders check via
_validate_no_injection).

Run
---
    uvicorn reasoning.service.app:app --port 8001

Or with Docker:
    docker compose up metta
"""
from __future__ import annotations

import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import reasoning helpers — this service runs inside reasoning/.venv (Python 3.12)
# where hyperon is installed.
from reasoning.wrapper import _validate_no_injection, query as _wrapper_query

app = FastAPI(
    title="SoundDue MeTTa Service",
    description="Exposes MeTTa (Hyperon) query execution over HTTP.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Prototype — restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ReasonRequest(BaseModel):
    """
    A MeTTa program (facts + rules) and an expression to evaluate.

    ``program`` is the assembled MeTTa source string produced by
    ``reasoning.facts.dicts_to_facts`` / ``reasoning.wrapper.load_facts``.
    All user text inside it must already be quoted via ``reasoning.wrapper.quote()``.

    ``expr`` is a MeTTa expression (without the leading ``!``), e.g.:
        ``"match &self (verified-mapping $r $w $s) $r"``
    """
    program: str
    expr: str


class ReasonResponse(BaseModel):
    results: list[str]
    expr: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/runtime")
def runtime() -> dict:
    """Return the Python and hyperon versions running in this service."""
    python_ver = sys.version
    try:
        import hyperon  # noqa: F401
        # hyperon 0.2.10 does not expose __version__ reliably; pin is the source of truth
        hyperon_ver = getattr(hyperon, "__version__", "0.2.10 (pinned)")
    except ImportError:
        hyperon_ver = "NOT INSTALLED"
    return {"python_version": python_ver, "hyperon_version": hyperon_ver}


@app.post("/reason", response_model=ReasonResponse)
def reason(body: ReasonRequest) -> ReasonResponse:
    """
    Run a MeTTa query against the provided program.

    The program string is validated for unquoted ``!`` before execution
    (belt-and-suspenders; the caller is expected to have already quoted all
    user text via ``reasoning.wrapper.quote()``).
    """
    try:
        _validate_no_injection(body.program)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        results = _wrapper_query(body.program, body.expr)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"MeTTa query failed: {exc}",
        ) from exc

    return ReasonResponse(results=results, expr=body.expr)
