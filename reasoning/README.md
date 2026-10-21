# reasoning/

This directory will contain MeTTa rule definitions (`.metta` files) for SoundDue.

## Current status

The reconciliation rules (RULE-001 through RULE-004) are currently implemented as
explicit Python in `backend/metta_engine.py` — a documented prototype shortcut.

Porting them to real MeTTa (via the `hyperon` SDK) is a stretch goal.

## Planned structure

```
reasoning/
  rules/
    share_sum_check.metta          # RULE-001
    missing_isrc_on_mapping.metta  # RULE-002
    recording_work_no_link.metta   # RULE-003
    incompatible_comparison.metta  # RULE-004
  tests/
    test_rules.py                  # Load .metta files, run against synthetic data
  README.md
```

## References

- [Hyperon / OpenCog Hyperon](https://github.com/trueagi-io/hyperon-experimental)
- [MeTTa language spec](https://wiki.opencog.org/w/MeTTa)
