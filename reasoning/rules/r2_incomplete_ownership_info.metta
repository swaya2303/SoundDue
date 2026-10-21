; reasoning/rules/r2_incomplete_ownership_info.metta
; ====================================================
; Rule R2 — incomplete_ownership_info
; ID:      R2
; Version: 1.0
;
; EXPERIMENTAL: Hyperon / MeTTa runtime. See docs/reasoning-runtime.md.
;
; Purpose
; -------
; Ownership records for a (work_id, rights_category, territory, period) scope
; sum to less than 100 % AND no row in that scope explicitly flags any share
; as "unclaimed".  The gap is SILENT — the source simply omitted data with no
; explanation.  This is distinct from R1 which fires only when the source
; EXPLICITLY labels a share unclaimed.
;
; Required wording (exact)
; ------------------------
; "Incomplete or inconsistent ownership information. Additional evidence is
;  required."
;
; The description must mention "missing from the supplied records".
;
; Condition
; ---------
; The fact (scope-gap <work_id> <rc> <territory> <eff_from> <eff_to> <sum>)
; exists in the space.  These facts are emitted by rule_runner.py ONLY when:
;   1. All rows in the scope are non-unclaimed (i.e. R1 would not fire).
;   2. The Decimal sum of shares < 99.99.
;
; Python computes the sum (MeTTa 0.2.10 has no GROUP BY / aggregation).
; Python does NOT decide whether R2 fires; it emits scope-gap facts and lets
; MeTTa decide by returning results (or not).
;
; Worked example (fictional)
; --------------------------
; Scenario: WRK-S2-001, mechanical / WW, 2020-2030.
;   Source A supplies only Writer A at 60 %.
;   Writer B's 40 % is entirely absent — no "unclaimed" row.
;
; Facts loaded:
;   (claim "WRK-S2-001" "Writer A" "60.0000" "mechanical" "WW"
;          "2020-01-01" "2030-12-31" "publisher-share")
;   ; Python computed: sum = 60.0000, no unclaimed row → emits scope-gap
;   (scope-gap "WRK-S2-001" "mechanical" "WW" "2020-01-01" "2030-12-31" "60.0000")
;
; Query:
;   !(match &self (scope-gap $w $rc $t $ef $et $sum)
;       (r2-fires $w $rc $t $ef $et $sum))
;
; Result:
;   [(r2-fires "WRK-S2-001" "mechanical" "WW" "2020-01-01" "2030-12-31" "60.0000")]
;
; Python receives this atom and formats a Finding with:
;   finding_type:      incomplete_ownership_info
;   severity:          warning
;   summary:           "Incomplete or inconsistent ownership information.
;                       Additional evidence is required. Shares for
;                       WRK-S2-001 / mechanical / WW sum to 60.0000 %,
;                       leaving 40 % missing from the supplied records."
;   matched_conditions: ["sum(share) = 60.0000 < 100", "no unclaimed row in scope"]
;   missing_information: ["40.0000 % of shares missing from the supplied records"]
;   next_step: "Supply complete ownership schedules for this work, territory,
;               and rights category covering the relevant period."
;
; ---------------------------------------------------------------------------
; Rule definition (used by rule_runner.py as the query expression)
; ---------------------------------------------------------------------------

(= (r2-fires $w $rc $t $ef $et $sum)
   (match &self (scope-gap $w $rc $t $ef $et $sum)
     (r2-fires $w $rc $t $ef $et $sum)))
