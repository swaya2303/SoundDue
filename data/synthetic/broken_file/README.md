# FICTIONAL DEMO DATA — Broken File: validation demo

This file is intentionally malformed to demonstrate SoundDue input validation.
The following errors are present (all data is fictional):

| Row | Error |
|-----|-------|
| 1   | `share` = 150.0000 — exceeds 100 % |
| 2–3 | Exact duplicate rows for WRT-B (same contributor, scope, and values) |
| 4   | `share` = -5.0000 — below 0 % |
| 5   | `effective_to` (2020-12-31) is before `effective_from` (2025-01-01) |
| 6   | `status` = "approved" — not in allowed vocabulary |

None of these rows should be accepted by the `OwnershipClaim` Pydantic model.
