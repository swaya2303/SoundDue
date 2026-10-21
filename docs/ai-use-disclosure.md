# AI Use Disclosure

## Summary

This project was built with significant AI coding-tool assistance as part of a rapid prototyping exercise.

## Where AI tools were used

| Area | Tool | Role |
|------|------|------|
| Backend boilerplate | Antigravity (Google DeepMind) | Generated FastAPI structure, SQLAlchemy models, test scaffolding |
| Rule engine | Antigravity | Drafted the four symbolic rules and MeTTa simulation layer |
| Fuzzy matcher | Antigravity | Wrote RapidFuzz candidate-proposal logic, corroboration requirement, tests |
| Column mapper | Antigravity | Generated synonym dictionary, auto-confirm logic, API endpoints |
| Frontend components | Antigravity | Generated React/TypeScript/Tailwind components, TanStack Table v9 usage |
| Export module | Antigravity | Generated JSON/CSV/HTML rendering and template-based plain-language explanations |
| gRPC stub | Antigravity | Generated `.proto` definition and server/client stubs |
| Documentation | Antigravity | Drafted README, demo script, this disclosure, integration status |

## LLM rewriting (optional feature)

The export module includes an optional LLM-rewrite path (`SOUNDDUE_LLM_REWRITE=1`) that can call OpenAI GPT-4o-mini to improve plain-language explanations. This feature is **disabled by default**. When enabled, any rewrite that introduces identifiers or numbers not present in the original is silently discarded.

## What was not AI-generated

- Domain decisions about which rules to implement and their semantics
- Choice of synthetic test scenarios and expected findings
- Architecture decisions (append-only findings, fingerprint-based rerun diff, corroboration requirement for fuzzy matching, never-overwrite record policy)
- Review of all generated code for correctness

## Limitations

AI-generated code was reviewed but not exhaustively audited. The prototype should not be used in production without independent security and correctness review.
