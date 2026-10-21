# SoundDue — Omega AGI Integration Plan

> **Status:** Plan only — not implemented.  
> This document describes the intended integration; no Omega SDK code has been written.

---

## What is Omega?

[Omega](https://wiki.opencog.org/w/Omega) is a goal-directed reasoning and planning framework developed within the OpenCog / SingularityNET ecosystem. It combines:

- **Goal trees** — hierarchical decompositions of high-level objectives into subgoals
- **Procedural knowledge** — action schemas that can achieve subgoals under conditions
- **Probabilistic planning** — selecting action sequences with expected utility maximisation
- **Integration with AtomSpace** — goals and plans are represented as hypergraph atoms, making them queryable and extensible by MeTTa rules

Unlike MeTTa (which is a declarative, rewriting-based language for symbolic reasoning), Omega provides a *planning layer* that can decide *what to do next* based on the current state of the knowledge graph.

---

## Why Omega for SoundDue?

SoundDue currently runs a fixed, sequential set of four symbolic rules. An Omega integration would allow the system to:

1. **Express reconciliation as a goal** — e.g. `(GoalState (AllClaimsReconciled case-42))` — and let the planner determine which rules or data requests to invoke.
2. **Prioritise findings dynamically** — high-uncertainty findings or high-value works could be escalated first.
3. **Richer proof trees** — Omega's plan traces would replace the current `rule_trace` with a full goal–subgoal–action tree, auditable at every step.
4. **Active data requests** — the planner could determine that a gap cannot be resolved without additional ownership data, and generate a structured request to a rights holder.

---

## Planned Architecture

```
User uploads CSVs
       │
       ▼
FastAPI backend (existing)
  → Normaliser → Linker → Fuzzy matcher
       │
       ▼
AtomSpace (hyperon / MeTTa)
  ← Records, claims, links loaded as atoms
       │
       ▼
Omega Planner
  ← Goal: AllClaimsReconciled(case_id)
  → Selects and executes rule-actions (RULE-SD-001 … 004)
  → Generates subgoals: ResolveGap(work_id), VerifyISRC(recording_id)
  → Returns plan trace as atom tree
       │
       ▼
Finding generator
  ← Reads plan trace atoms
  → Emits structured findings with Omega goal-tree as rule_trace
       │
       ▼
REST API / Frontend (existing)
```

---

## Mapping Existing Rules to Omega Actions

| Existing Rule | Omega Action Schema | Goal it Serves |
|--------------|--------------------|-|
| `RULE-SD-001 share_sum_check` | `(ActionSchema CheckShareSum ?work ?territory ?period)` | `(SharesSumTo100 ?work ?territory ?period)` |
| `RULE-SD-002 missing_claim` | `(ActionSchema FindMissingClaim ?recording)` | `(AllRecordingsHaveClaim case)` |
| `RULE-SD-003 conflicting_shares` | `(ActionSchema DetectConflict ?work ?source_a ?source_b)` | `(NoConflictingShares ?work)` |
| `RULE-SD-004 duplicate_isrc` | `(ActionSchema CheckISRCUniqueness)` | `(ISRCsAreUnique case)` |

---

## Implementation Steps (Future Work)

1. **Install Omega SDK** — the Omega package is separate from `hyperon` and is currently not available as a standard pip package. Contact the SingularityNET team for the current distribution channel.

2. **Load records into AtomSpace** — extend `app/analyzer.py` to write normalised records as `(EvaluationLink (PredicateNode "recording") (ListLink ...))` atoms before running analysis.

3. **Define goal atoms** — create a MeTTa file `reasoning/goals.metta` with top-level goal expressions.

4. **Instantiate Omega planner** — call `omega.Planner(atomspace).plan(top_goal)` and capture the returned plan tree.

5. **Translate plan steps to findings** — walk the plan tree; each failed precondition becomes a Finding; each successful action step becomes a matched condition in `rule_trace`.

6. **Replace existing rule runner** — `run_analysis` in `analyzer.py` currently calls Python functions directly; replace with Omega plan execution.

---

## Risks and Unknowns

| Risk | Severity | Notes |
|------|----------|-------|
| Omega SDK not pip-installable | High | As of Oct 2026, no stable public release found |
| AtomSpace performance on large files | Medium | Not benchmarked; may be slow for 10k+ rows |
| Omega planning may be non-deterministic | Medium | Seed or deterministic mode needed for reproducibility |
| MeTTa ↔ Omega atom format compatibility | Medium | Unclear without experimentation; documentation is sparse |
| Prototype timeline | High | Full integration would require 2–3 additional weeks |

---

## Recommended Next Step

Contact the SingularityNET developer relations team to:
- Obtain the current Omega Python SDK distribution
- Request a minimal working example of Omega planning with a Python AtomSpace
- Clarify whether the `hyperon` package (already installed in `reasoning/.venv`) exposes any Omega planning APIs

Until then, the existing Python-simulated symbolic rules in `app/analyzer.py` are the production path.

---

*This plan is speculative. No Omega code has been tested or run. Mark as **Plan only** in `docs/integration-status.md`.*
