"""
reasoning/wrapper.py
====================
Low-level helpers that turn Python data into MeTTa programs and run them.

This module is the ONLY place in SoundDue that imports ``hyperon`` directly.
All other code (including the FastAPI backend on Python 3.13) must go through
``reasoning.engine.MettaEngine`` which chooses the appropriate implementation.

EXPERIMENTAL RUNTIME
--------------------
Hyperon / MeTTa is an experimental runtime. The Python API may change between
patch versions. This file is pinned to ``hyperon==0.2.10``.  Review the
hyperon CHANGELOG before upgrading.

INJECTION SAFETY
----------------
Every user-supplied string (IDs, titles, contributor names, territory codes,
etc.) MUST be passed through ``quote(text)`` before being embedded in a MeTTa
expression.  ``quote()`` produces a MeTTa *string literal*  -- double-quoted
with backslash-escaped internal backslashes and double-quotes -- so that
arbitrary user text cannot be interpreted as a MeTTa symbol, expression, or
directive.

>>> quote('normal')
'"normal"'
>>> quote('inject") (! rm -rf /)  ; "')
'"inject\\") (! rm -rf /)  ; \\""'

Never concatenate raw user data into MeTTa source text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Injection-safe quoting
# ---------------------------------------------------------------------------

def quote(text: str) -> str:
    """
    Return a MeTTa string literal that safely encodes *text*.

    Steps
    -----
    1. Cast to ``str`` (tolerates None / numbers).
    2. Escape backslashes (``\\`` -> ``\\\\``).
    3. Escape double-quotes (``"`` -> ``\\"``).
    4. Wrap in double-quotes.

    The result is a MeTTa *string atom*, not a symbol.  String atoms are
    inert data; they cannot be mistaken for predicates, directives, or
    sub-expressions by the MeTTa parser.
    """
    s = str(text) if text is not None else ""
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    return f'"{s}"'


def _validate_no_injection(metta_src: str) -> None:
    """
    Sanity-check that *metta_src* does not contain unquoted exclamation marks
    that could execute arbitrary expressions.  This is a belt-and-suspenders
    guard; the primary protection is ``quote()`` on every user string.

    Only call this on the assembled fact block, not on rule files loaded
    from disk (which are trusted).
    """
    # Every "!" should be inside a string literal
    in_string = False
    escape = False
    for ch in metta_src:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if ch == "!" and not in_string:
            raise ValueError(
                f"Unquoted '!' found in fact block -- possible injection. "
                f"Ensure all user text is passed through quote(). "
                f"Offending source (first 200 chars): {metta_src[:200]!r}"
            )


# ---------------------------------------------------------------------------
# Rule / fact assembly
# ---------------------------------------------------------------------------

def load_rules(path: str | Path) -> str:
    """
    Load a ``.metta`` rules file from disk and return its text.

    Rules files are trusted (they come from the repository, not from user
    input) so they are NOT sanitised.
    """
    return Path(path).read_text(encoding="utf-8")


def load_facts(facts: list[str]) -> str:
    """
    Join a list of MeTTa fact strings into a single program block.

    Each element should be a complete MeTTa expression, e.g.::

        '(verified-mapping "REC-001" "WRK-001" "LabelX")'

    Blank / whitespace-only entries are silently skipped.
    """
    joined = "\n".join(f for f in facts if f and f.strip())
    _validate_no_injection(joined)
    return joined


# ---------------------------------------------------------------------------
# Query runner  (fresh space per call)
# ---------------------------------------------------------------------------

def query(program: str, expr: str) -> list[str]:
    """
    Run *expr* against *program* in a **fresh** MeTTa space.

    A new ``MeTTa()`` instance is created on every call so that no state
    leaks between invocations.

    Parameters
    ----------
    program:
        Complete MeTTa source (rules + facts).  Typically produced by
        concatenating ``load_rules(...)`` and ``load_facts(...)``.
    expr:
        A MeTTa expression to evaluate, e.g.
        ``"(match &self (verified-mapping $r $w $s) $r)"``.
        Do NOT include the leading ``!``; this function adds it.

    Returns
    -------
    list[str]
        String representations of the result atoms.  Empty list if nothing
        matched.

    Notes
    -----
    * Hyperon is **experimental**; the ``MeTTa`` class API may change.
    * This function is only importable when ``hyperon`` is installed (Python
      3.12 venv).  The ``MettaEngine`` abstraction in ``engine.py`` wraps
      this and provides a safe fallback.
    """
    from hyperon import MeTTa  # import here so the module is importable even without hyperon

    metta = MeTTa()

    if program.strip():
        metta.run(program)

    results = metta.run(f"!({expr})")

    flat: list[str] = []
    for group in (results or []):
        for atom in group:
            flat.append(str(atom))
    return flat
