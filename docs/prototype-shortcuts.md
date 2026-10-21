# SoundDue — Prototype Shortcuts

> This is a hackathon prototype. The following shortcuts were taken deliberately
> and are documented here per the project spec.

## 1. Authentication: Hard-coded demo user
- There is no login system. All review actions use the actor string `"demo-user"`.
- **Production path**: Add OAuth2 / JWT with proper role-based access control.

## 2. Database: SQLite
- Uses a local `backend/sounddue.db` SQLite file.
- **Production path**: PostgreSQL with connection pooling.

## 3. MeTTa engine: Simulated in Python
- `metta_engine.py` implements the 4 MeTTa rules as explicit Python logic.
- The `hyperon` package (real MeTTa runtime) is listed as a stretch goal.
- Rule IDs and versions are embedded in code and reported in every finding.
- **Production path**: Port rules to real `.metta` files, load via `hyperon` SDK.

## 4. File storage: Local filesystem
- Uploaded files are parsed directly from the multipart stream; not persisted to disk long-term.
- **Production path**: Object storage (GCS/S3) with file versioning.

## 5. Share arithmetic: Python `float` with tolerance check
- `share_pct` is stored as `Numeric(7,4)` in SQLite but compared with a 0.01% tolerance.
- **Production path**: Use Python `Decimal` throughout, including the rule engine.

## 6. No LLM integration
- All matching and rule evaluation is fully deterministic (RapidFuzz + explicit rules).
- LLM suggestions are listed as optional/stretch only.

## 7. No real-time updates
- The frontend polls on user action (button click). No WebSockets.
- **Production path**: Server-sent events or WebSocket for live finding updates.

## 8. No user management or multi-tenancy
- Single user, single SQLite database, no data isolation.
- **Production path**: Per-tenant schema or row-level security.

## 9. CORS open to all origins
- `allow_origins=["*"]` for local development convenience.
- **Production path**: Restrict to known frontend origins.

## 10. No pagination
- All list endpoints return all rows. Fine for demo data sizes.
- **Production path**: Add `limit`/`offset` or cursor pagination.

## 11. Hyperon in isolated Python 3.12 venv

- The `hyperon` package (MeTTa runtime) has no wheel for Python 3.13.
- The backend runs on Python 3.13; reasoning runs in `reasoning/.venv` (Python 3.12).
- This is an **isolated venv** approach, not a proper polyglot service boundary.
- The MeTTa runtime itself is **experimental** (SingularityNET / Hyperon project).
- Nothing in the backend imports `hyperon` directly — only `reasoning/wrapper.py` does.
- **Production path**: Containerise the reasoning service (`METTA_MODE=http`), pin
  the hyperon version in a Docker image, and expose it as a proper micro-service.
- See [`docs/reasoning-runtime.md`](reasoning-runtime.md) for full details.
