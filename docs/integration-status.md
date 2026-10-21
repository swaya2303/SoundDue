# SoundDue — Integration Status

> **Last updated:** 2026-10-20  
> Legend: ✅ Implemented · 🟡 Mock / Partial · 📝 Plan only · ❌ Not done

---

## Core Backend

| Feature | Status | Notes |
|---------|--------|-------|
| FastAPI backend | ✅ Implemented | `backend/app/` — full REST API |
| SQLite persistence | ✅ Implemented | `sounddue_cases.db` — append-only schema |
| Case management (`POST/GET /cases`) | ✅ Implemented | |
| File upload + storage | ✅ Implemented | CSV / Excel; stored as Records |
| File validation | ✅ Implemented | `app/file_validator.py` — row-level error codes |
| Column auto-mapper | ✅ Implemented | `app/column_mapper.py` — synonym dict + fuzzy fallback |
| Auto-confirm exact synonym mappings | ✅ Implemented | On first `GET /files/{id}/mapping/suggestions` |
| Normaliser | ✅ Implemented | `app/normaliser.py` — canonical field extraction |

---

## Analysis Engine

| Feature | Status | Notes |
|---------|--------|-------|
| Symbolic rule runner | ✅ Implemented | `app/analyzer.py` — 4 named rules |
| RULE-SD-001 `share_sum_check` | ✅ Implemented | Gap / excess detection with per-group tolerance |
| RULE-SD-002 `missing_claim` | ✅ Implemented | Recordings with no linked ownership claim |
| RULE-SD-003 `conflicting_shares` | ✅ Implemented | Different sources disagree on share % |
| RULE-SD-004 `duplicate_isrc` | ✅ Implemented | Same ISRC in multiple recording records |
| Rule trace (`rule_trace` field) | ✅ Implemented | Ordered list of matched conditions per finding |
| Exact linker | ✅ Implemented | `app/linker.py` — ISRC / work-ID / title exact match |
| Fuzzy candidate proposer | ✅ Implemented | `app/fuzzy_matcher.py` — RapidFuzz; requires corroboration |
| Corroboration requirement | ✅ Implemented | Name ≥ 85 OR duration ≤ ±3 s; title-only blocked |
| Version-token penalty (0.85×) | ✅ Implemented | live/remix/acoustic/demo/etc |
| Rejected-pair suppression | ✅ Implemented | Rejected candidates never re-proposed |
| MeTTa / hyperon integration | 🟡 Mock | Rules are simulated in Python; `reasoning/.venv` has hyperon==0.2.10 but it is **not called** at runtime. See `docs/reasoning-runtime.md` |

---

## Review & Rerun

| Feature | Status | Notes |
|---------|--------|-------|
| `POST /findings/{id}/review` (accept/reject/correct) | ✅ Implemented | Append-only `ReviewDecision` + `AuditEvent` |
| Correct action with patch fields | ✅ Implemented | `corrected_values` JSON stored on ReviewDecision |
| `POST /cases/{id}/rerun` | ✅ Implemented | Re-runs analysis; returns diff (new/changed/resolved) |
| Fuzzy candidate review (`accept`/`reject`) | ✅ Implemented | `POST /cases/{id}/candidates/{id}/review` |
| Review history per finding | ✅ Implemented | `review_decisions` array on `GET /findings/{id}` |

---

## Export

| Feature | Status | Notes |
|---------|--------|-------|
| `GET /cases/{id}/export?format=json` | ✅ Implemented | Full findings with evidence refs and rule traces |
| `GET /cases/{id}/export?format=csv` | ✅ Implemented | One row per finding |
| `GET /cases/{id}/export?format=html` | ✅ Implemented | Readable report; six sections per finding; limitations note |
| Template-based plain-language explanations | ✅ Implemented | `app/exporter.py` — keyed by finding type, filled from structured trace only |
| LLM explanation rewrite | 🟡 Mock | `SOUNDDUE_LLM_REWRITE=1` env flag; guard discards output if it introduces any number/name/ID not in the finding; **disabled by default** |

---

## Frontend

| Feature | Status | Notes |
|---------|--------|-------|
| React + TypeScript + Vite + Tailwind | ✅ Implemented | `frontend/` |
| Cases list + create form (TanStack Table) | ✅ Implemented | |
| File upload with file-kind selector | ✅ Implemented | |
| Column mapping UI with auto-confirm | ✅ Implemented | |
| Validation issues panel | ✅ Implemented | |
| Findings list with filters (rule / status) | ✅ Implemented | TanStack Table |
| Finding detail — six sections | ✅ Implemented | Issue, Evidence, Rule (trace checklist), Uncertainty, Next step, Review history |
| Side-by-side record comparison | ✅ Implemented | Conflicting-values table in Evidence section |
| Accept / Reject / Correct buttons | ✅ Implemented | Note required; Correct has inline form |
| Rerun + diff view (New / Changed / Resolved) | ✅ Implemented | `RerunPanel.tsx` |
| Fuzzy candidates page with score breakdown | ✅ Implemented | `CandidatesSection.tsx` |
| Footer disclaimer note | ✅ Implemented | "findings are leads for human review, not ownership decisions" |

---

## Developer Experience

| Feature | Status | Notes |
|---------|--------|-------|
| `make demo` seed script | ✅ Implemented | `backend/scripts/seed_demo.py` — uses httpx; prints URL + steps |
| `make backend` / `make frontend` / `make test` | ✅ Implemented | `Makefile` at project root |
| README (problem, audience, Mermaid arch, run steps) | ✅ Implemented | |
| Prototype status section in README | ✅ Implemented | Honest shortcuts / limitations list |
| `docs/ai-use-disclosure.md` | ✅ Implemented | |
| `docs/demo-script.md` | ✅ Implemented | 3-minute walkthrough with timing marks |
| Backend test suite | ✅ Implemented | 289 tests passing (`pytest`) |
| Playwright smoke test (steps 1–5) | 🟡 Partial | `frontend/e2e/midnight-train-flow.spec.ts` — steps 1–5 pass; step 6 (FindingDetail sections) has a known selector issue; left as-is per prototype scope |
| Fuzzy precision eval script | ✅ Implemented | `backend/scripts/eval_precision.py` — static analysis of expected_findings.json |

---

## Stretch Goals — SingularityNET

| Feature | Status | Notes |
|---------|--------|-------|
| `.proto` definition (`AnalyzeRoyaltyRecords`) | ✅ Implemented | `grpc/sounddue.proto` |
| gRPC server (Python) | ✅ Implemented | `grpc/server.py` — delegates to HTTP API via httpx; requires generated stubs |
| gRPC client script | ✅ Implemented | `grpc/client.py` — `--case-id N --host localhost:50051` |
| Stub generation (`grpc_tools.protoc`) | 📝 Plan only | Command documented in `grpc/README.md`; not run (requires `grpcio-tools` install) |
| SingularityNET daemon publishing | 📝 Plan only | Documented step; testnet not configured |

---

## Stretch Goals — Omega AGI

| Feature | Status | Notes |
|---------|--------|-------|
| Omega integration plan | 📝 Plan only | `docs/omega-plan.md` |
| Omega SDK integration (code) | ❌ Not done | Setup differs from hyperon package; unverified locally |

---

## Known Limitations (Prototype)

- **No authentication** — single `demo-user` actor everywhere
- **No multi-tenancy** — all cases share one SQLite file
- **SQLite only** — not suitable for concurrent writes at scale
- **MeTTa rules are simulated** — hyperon is not called at runtime
- **LLM rewrite is mocked** — disabled by default; guard is implemented but no real LLM is wired
- **Playwright step 6 known failure** — FindingDetail selector issue; not fixed per scope
- **gRPC stubs not generated** — server.py has a guard for missing stubs and will print a helpful error
- **No deployment config** — no Docker image, no CI/CD pipeline
