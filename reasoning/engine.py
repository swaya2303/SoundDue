"""
reasoning/engine.py
====================
``MettaEngine`` -- one interface, two implementations.

Usage
-----
Select the implementation via the environment variable ``METTA_MODE``::

    METTA_MODE=inprocess   (default) -- runs hyperon in-process.
                                        Requires the reasoning/.venv (Python 3.12).
    METTA_MODE=http        -- delegates to the metta micro-service.
                              Requires the service to be running (see
                              reasoning/service/ and docker-compose.yml).

Import and use::

    from reasoning.engine import get_engine

    engine = get_engine()
    engine.load_rules("reasoning/rules/base.metta")
    engine.load_facts([...])
    results = engine.query("(match &self (verified-mapping $r $w $s) $r)")
    engine.reset()

Nothing outside this module (and reasoning/wrapper.py) may import ``hyperon``
directly.

EXPERIMENTAL
------------
The MeTTa / Hyperon runtime is experimental.  See docs/reasoning-runtime.md.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class MettaEngine(ABC):
    """
    Abstract MeTTa reasoning engine.

    State model
    -----------
    Each engine instance has an internal *current program* buffer that
    accumulates rules and facts.  Call ``reset()`` to clear it between
    independent queries.
    """

    def __init__(self) -> None:
        self._program_parts: list[str] = []

    def load_rules(self, path: str | Path) -> "MettaEngine":
        """Append the contents of a ``.metta`` rules file to the program buffer."""
        from reasoning.wrapper import load_rules
        self._program_parts.append(load_rules(path))
        return self

    def load_facts(self, facts: list[str]) -> "MettaEngine":
        """Append a list of MeTTa fact strings to the program buffer."""
        from reasoning.wrapper import load_facts
        self._program_parts.append(load_facts(facts))
        return self

    @abstractmethod
    def query(self, expr: str) -> list[str]:
        """
        Evaluate *expr* against the accumulated program and return results.

        Each call uses a **fresh** MeTTa space loaded with the current buffer.
        The buffer is NOT cleared after a query; call ``reset()`` explicitly.
        """

    def reset(self) -> "MettaEngine":
        """Clear the program buffer so the next query starts from a clean state."""
        self._program_parts.clear()
        return self

    @property
    def _program(self) -> str:
        return "\n".join(self._program_parts)


# ---------------------------------------------------------------------------
# In-process implementation  (requires Python 3.12 + hyperon==0.2.10)
# ---------------------------------------------------------------------------

class InProcessEngine(MettaEngine):
    """
    Runs MeTTa queries in-process via the ``hyperon`` Python package.

    Only usable from the Python 3.12 reasoning venv.  Instantiating this
    class from Python 3.13 (where hyperon is not installed) will raise
    ``ImportError`` with a clear message.
    """

    def query(self, expr: str) -> list[str]:
        try:
            from reasoning.wrapper import query as _query
        except ImportError as exc:
            raise ImportError(
                "METTA_MODE=inprocess requires 'hyperon' to be installed.\n"
                "Run: uv pip install hyperon==0.2.10 --python reasoning/.venv/Scripts/python.exe\n"
                "Or switch to: METTA_MODE=http  (see docs/reasoning-runtime.md)"
            ) from exc
        return _query(self._program, expr)


# ---------------------------------------------------------------------------
# HTTP implementation  (delegates to reasoning/service/)
# ---------------------------------------------------------------------------

class HttpEngine(MettaEngine):
    """
    Delegates MeTTa queries to the ``metta`` micro-service.

    Requires the service to be running (``docker compose up metta`` or
    ``uvicorn reasoning.service.app:app``).

    The service URL is configured via ``METTA_SERVICE_URL``
    (default: ``http://localhost:8001``).
    """

    def __init__(self) -> None:
        super().__init__()
        self._base = os.environ.get("METTA_SERVICE_URL", "http://localhost:8001")

    def query(self, expr: str) -> list[str]:
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx is required for METTA_MODE=http") from exc

        payload = {
            "program": self._program,
            "expr": expr,
        }
        resp = httpx.post(f"{self._base}/reason", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["results"]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_engine(mode: str | None = None) -> MettaEngine:
    """
    Return a ``MettaEngine`` for the configured mode.

    Parameters
    ----------
    mode:
        ``"inprocess"`` | ``"http"``.  If *None*, reads ``METTA_MODE`` env var
        (default: ``"inprocess"``).

    Raises
    ------
    ValueError
        If an unknown mode is specified.
    ImportError
        If the selected mode's runtime dependency is unavailable.
    """
    resolved = (mode or os.environ.get("METTA_MODE", "inprocess")).lower()
    if resolved == "inprocess":
        return InProcessEngine()
    if resolved == "http":
        return HttpEngine()
    raise ValueError(
        f"Unknown METTA_MODE={resolved!r}. "
        "Valid values: 'inprocess' (requires Python 3.12 + hyperon) or "
        "'http' (requires metta micro-service)."
    )
