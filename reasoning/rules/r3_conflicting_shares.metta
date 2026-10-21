; reasoning/rules/r3_conflicting_shares.metta
; ============================================
; Rule R3 — conflicting_shares
; ID:      R3
; Version: 1.0
;
; EXPERIMENTAL: Hyperon / MeTTa runtime. See docs/reasoning-runtime.md.
;
; Purpose
; -------
; Two or more ownership records for the same contributor (by contributor_id)
; in the same compatible scope (work_id, rights_category, territory, period)
; report DIFFERENT share values.  This arises when two ownership files are
; uploaded for the same case and they disagree on the figures.
;
; Scope compatibility
; -------------------
; Two rows are in the same scope when ALL of the following match:
;   work_id, contributor_id, rights_category, territory,
;   effective_from, effective_to.
; If any of these differ, the rows are NOT in the same scope and R3 must
; NOT fire (see scenario 5: incompatible_scopes).
;
; Condition
; ---------
; The fact (share-conflict <work_id> <contributor_id> <rc> <territory>
;                          <eff_from> <eff_to> <share_a> <share_b>)
; exists in the space.  These facts are emitted by rule_runner.py ONLY when:
;   1. At least two rows share the same (work_id, contributor_id, rc,
;      territory, effective_from, effective_to) key.
;   2. Those rows have DIFFERENT Decimal share values.
;
; Python groups and compares; Python does NOT decide whether R3 fires —
; MeTTa decides by returning results from the match below (or not).
;
; Worked example (fictional)
; --------------------------
; Scenario: WRK-S4-001, mechanical / WW, 2019-2029.
;   Source A: Writer A = 60 %, Writer B = 40 %.
;   Source B: Writer A = 50 %, Writer B = 50 %.
;
; Facts loaded (claim rows from both files):
;   (claim "WRK-S4-001" "Writer A" "60.0000" "mechanical" "WW"
;          "2019-01-01" "2029-12-31" "publisher-share")   ; source A
;   (claim "WRK-S4-001" "Writer A" "50.0000" "mechanical" "WW"
;          "2019-01-01" "2029-12-31" "publisher-share")   ; source B
;   ; Python detects same contributor_id "WRT-A-S4", different shares
;   (share-conflict "WRK-S4-001" "WRT-A-S4" "mechanical" "WW"
;                  "2019-01-01" "2029-12-31" "50.0000" "60.0000")
;
; Query:
;   !(match &self
;       (share-conflict $w $cid $rc $t $ef $et $s1 $s2)
;       (r3-fires $w $cid $rc $t $ef $et $s1 $s2))
;
; Result:
;   [(r3-fires "WRK-S4-001" "WRT-A-S4" "mechanical" "WW"
;              "2019-01-01" "2029-12-31" "50.0000" "60.0000")]
;
; Python receives this atom and formats a Finding with:
;   finding_type:         conflicting_shares
;   severity:             error
;   matched_conditions:   ["contributor_id = WRT-A-S4",
;                          "scope = (WRK-S4-001 / mechanical / WW / 2019–2029)",
;                          "distinct share values: 50.0000 %, 60.0000 %"]
;   conflicting_information: ["Share 50.0000 % in source B",
;                             "Share 60.0000 % in source A"]
;   next_step: "Obtain the authoritative share schedule from the relevant CMO
;               or publisher and confirm which figure is correct."
;
; No-fire case (scenario 5)
; -------------------------
; Source A (WW / all-rights / 2020-2025) and Source B (US / mechanical / 2019-2023)
; have different territory AND rights_category → they do NOT form the same scope key →
; no share-conflict fact is emitted → MeTTa returns empty → R3 does NOT fire. ✓
;
; ---------------------------------------------------------------------------
; Rule definition (used by rule_runner.py as the query expression)
; ---------------------------------------------------------------------------

(= (r3-fires $w $cid $rc $t $ef $et $s1 $s2)
   (match &self (share-conflict $w $cid $rc $t $ef $et $s1 $s2)
     (r3-fires $w $cid $rc $t $ef $et $s1 $s2)))
