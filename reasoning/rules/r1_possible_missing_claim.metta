; reasoning/rules/r1_possible_missing_claim.metta
; ================================================
; Rule R1 — possible_missing_claim
; ID:      R1
; Version: 1.0
;
; EXPERIMENTAL: Hyperon / MeTTa runtime. See docs/reasoning-runtime.md.
;
; Purpose
; -------
; An ownership row is EXPLICITLY labelled "unclaimed" (or equivalent synonym)
; by the source.  A named claimant may exist but was not included in the
; supplied data.  This is distinct from R2 (incomplete_ownership_info) which
; fires when the gap is SILENT — no row acknowledges it.
;
; Condition
; ---------
; The fact (unclaimed <work_id> <share> <rc> <territory> <eff_from> <eff_to>)
; exists in the space.  These facts are emitted by reasoning/facts.py only
; when the source row's Claim Status / Status field is in the unclaimed labels
; set {"unclaimed", "unregistered", "unknown", "pool"}.
;
; Python NEVER pre-filters which rows trigger this rule.  It loads ALL
; ownership rows as either (claim ...) or (unclaimed ...) facts.  The
; decision to fire is made purely by whether this match returns any results.
;
; Worked example (fictional)
; --------------------------
; Facts loaded:
;   (claim "WRK-S1-001" "Writer A" "60.0000" "mechanical" "WW"
;          "2020-01-01" "2030-12-31" "publisher-share")
;   (unclaimed "WRK-S1-001" "40.0000" "mechanical" "WW"
;              "2020-01-01" "2030-12-31")
;
; Query:
;   !(match &self (unclaimed $w $share $rc $t $ef $et)
;       (r1-fires $w $share $rc $t $ef $et))
;
; Result:
;   [(r1-fires "WRK-S1-001" "40.0000" "mechanical" "WW"
;              "2020-01-01" "2030-12-31")]
;
; Python receives this atom, reads its arguments, and formats a Finding with:
;   finding_type: possible_missing_claim
;   severity:     warning
;   matched_conditions: ["status in unclaimed labels", "share = 40.0000 %"]
;   next_step: verify ownership agreement and registration status
;              before requesting a correction.
;
; Next step (required wording)
; ----------------------------
; "Verify the ownership agreement and registration status before requesting
;  a correction."
;
; ---------------------------------------------------------------------------
; Rule definition (used by rule_runner.py as the query expression)
; ---------------------------------------------------------------------------
;
; The helper relation r1-fires is defined here for documentation.
; rule_runner.py executes the query directly via metta.run("!(<expr>)").

(= (r1-fires $w $share $rc $t $ef $et)
   (match &self (unclaimed $w $share $rc $t $ef $et)
     (r1-fires $w $share $rc $t $ef $et)))
