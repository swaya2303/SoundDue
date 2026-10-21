"""
backend/scripts/seed_demo.py
=============================
Seeds the Midnight Train demo case via the running HTTP API.

Usage:
    python backend/scripts/seed_demo.py

The SoundDue backend must be running on http://localhost:8000.
"""
from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.normpath(
    os.path.join(_HERE, "..", "..", "data", "synthetic",
                 "scenario_01_midnight_train_unclaimed")
)
_BASE = os.getenv("SOUNDDUE_API_URL", "http://localhost:8000")

_FILES = [
    ("recordings.csv", "recordings"),
    ("ownership.csv",  "ownership"),
    ("works.csv",      "works"),
    ("mappings.csv",   "mappings"),
]


def main() -> None:
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is required.  pip install httpx")
        sys.exit(1)

    client = httpx.Client(base_url=_BASE, timeout=30)

    try:
        client.get("/cases")
    except httpx.ConnectError:
        print(f"ERROR: Cannot reach {_BASE}")
        print("Make sure the backend is running:  make backend")
        sys.exit(1)

    # 1. Create case
    r = client.post("/cases", data={
        "name": "Midnight Train Demo",
        "description": "Scenario 1 — possible missing claim",
    })
    if r.status_code not in (200, 201):
        print(f"ERROR creating case: {r.text}")
        sys.exit(1)
    case = r.json()
    case_id = case["id"]
    print(f"✓ Case created: id={case_id}  name=\"{case['name']}\"")

    # 2. Upload files
    uploaded = 0
    for filename, kind in _FILES:
        path = os.path.join(_DATA, filename)
        if not os.path.exists(path):
            print(f"  ⚠  {filename} not found at {path} — skipping")
            continue
        with open(path, "rb") as fh:
            r = client.post(
                f"/cases/{case_id}/files",
                data={"file_kind": kind},
                files={"file": (filename, fh, "text/csv")},
            )
        if r.status_code not in (200, 201):
            print(f"  ✗  {filename}: {r.text}")
        else:
            meta = r.json()
            print(f"  ✓  {filename}  ({meta.get('row_count', '?')} rows)")
            uploaded += 1
    print(f"✓ {uploaded} files uploaded")

    # 3. Analyze
    r = client.post(f"/cases/{case_id}/analyze", timeout=60)
    if r.status_code not in (200, 201):
        print(f"ERROR during analysis: {r.text}")
        sys.exit(1)
    result = r.json()
    fc = result.get("finding_count", 0)
    print(f"✓ Analysis complete: {fc} finding{'s' if fc != 1 else ''}")

    # 4. Print instructions
    print()
    print("=" * 60)
    print(f"Open the UI at:  http://localhost:5173")
    print()
    print("Steps:")
    print("  1. Click \"Midnight Train Demo\" → Open")
    print("  2. Go to \"4. Findings\" and click \"View →\" on any finding")
    print("  3. Click \"Correct record\", add a note, submit")
    print("  4. Click \"← Back to findings\" then \"↻ Rerun\" → \"↻ Run now\"")
    print("  5. The corrected finding appears under Resolved")
    print()
    print(f"Export (HTML):  GET {_BASE}/cases/{case_id}/export?format=html")
    print(f"Export (CSV):   GET {_BASE}/cases/{case_id}/export?format=csv")
    print(f"Export (JSON):  GET {_BASE}/cases/{case_id}/export?format=json")
    print("=" * 60)


if __name__ == "__main__":
    main()
