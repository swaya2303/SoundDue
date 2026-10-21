"""
seed_demo.py — Upload all four demo CSV files to a running SoundDue backend.

Usage:
    python seed_demo.py [--base-url http://localhost:8000]

Prototype shortcut: uses hard-coded demo data files from demo_data/.
"""

import argparse
import sys
from pathlib import Path

import urllib.request
import urllib.error

DEMO_DIR = Path(__file__).parent / "demo_data"
FILES = [
    ("recordings.csv", "recordings"),
    ("works.csv", "works"),
    ("ownership.csv", "ownership"),
    ("mappings.csv", "mappings"),
]


def upload_file(base_url: str, csv_path: Path, file_type: str) -> dict:
    import mimetypes, email.generator, io, uuid

    boundary = uuid.uuid4().hex
    body_parts = []

    # file_type field
    body_parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file_type"\r\n\r\n{file_type}\r\n'
    )

    # file field
    data = csv_path.read_bytes()
    body_parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{csv_path.name}"\r\nContent-Type: text/csv\r\n\r\n'
    )

    raw_body = "".join(body_parts).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{base_url}/upload",
        data=raw_body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        import json
        return json.loads(resp.read())


def run_matching(base_url: str) -> dict:
    import json
    req = urllib.request.Request(
        f"{base_url}/run-matching",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"Seeding demo data to {base} ...\n")
    for filename, file_type in FILES:
        path = DEMO_DIR / filename
        if not path.exists():
            print(f"  MISSING: {path}", file=sys.stderr)
            sys.exit(1)
        try:
            result = upload_file(base, path, file_type)
            print(f"  OK {filename} -> batch_id={result['batch_id']}, rows={result['row_count']}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  FAIL {filename}: HTTP {e.code} -- {body}", file=sys.stderr)
            sys.exit(1)

    print("\nRunning matching + rules ...")
    try:
        result = run_matching(base)
        print(f"  new_candidates : {result['new_candidates']}")
        print(f"  findings_generated: {result['findings_generated']}")
        print()
        for f in result.get("findings", []):
            sev = f.get("severity", "?").upper()
            rule = f"{f.get('rule_id')} v{f.get('rule_version')}"
            print(f"  [{sev}] {rule}: {f.get('summary')}")
    except urllib.error.HTTPError as e:
        print(f"  FAIL run-matching: HTTP {e.code}", file=sys.stderr)
        sys.exit(1)

    print("\nDone. Open http://localhost:5173 for the UI.")


if __name__ == "__main__":
    main()
