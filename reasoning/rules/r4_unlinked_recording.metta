; reasoning/rules/r4_unlinked_recording.metta
; ============================================
; Rule R4 — unlinked_recording
; ID:      R4
; Version: 1.0
;
; EXPERIMENTAL: Hyperon / MeTTa runtime. See docs/reasoning-runtime.md.
;
; Purpose
; -------
; A recording in the recordings file has no verified mapping row pointing
; to it.  A mapping is considered verified ONLY when its "verified" field is
; an explicit truthy string ("true", "1", "yes", "y").
;
; Title similarity is NEVER used as a substitute for a verified mapping.
; Even 100 % title match does not constitute a link.
;
; Condition
; ---------
; The fact (unlinked-recording <recording_id> <title>) exists in the space.
; These facts are emitted by rule_runner.py ONLY when:
;   1. A recording row has a non-empty recording_id.
;   2. No verified mapping row points to that recording_id.
;
; Python identifies which recordings are unlinked; Python does NOT decide
; whether R4 fires — MeTTa decides by returning results (or not).
;
; Worked example (fictional)
; --------------------------
; Scenario: REC-S6-001 ("Ghost Signal" Demo) — no verified mapping.
;           REC-S6-002 ("Ghost Signal" Album) — IS mapped (verified = true).
;
; Facts loaded:
;   (recording "REC-S6-001" "Ghost Signal")
;   (recording "REC-S6-002" "Ghost Signal")
;   (verified-mapping "REC-S6-002" "WRK-S6-001" "LabelZeta")
;   ; Python: REC-S6-001 not in verified mapping set → unlinked
;   (unlinked-recording "REC-S6-001" "Ghost Signal")
;   ; REC-S6-002 IS verified → no unlinked-recording fact for it
;
; Query:
;   !(match &self (unlinked-recording $rec $title)
;       (r4-fires $rec $title))
;
; Result:
;   [(r4-fires "REC-S6-001" "Ghost Signal")]
;
; Python receives this atom and formats a Finding with:
;   finding_type:       unlinked_recording
;   severity:           warning
;   matched_conditions: ["recording_id = REC-S6-001 not in verified mapping rows"]
;   missing_information: ["A verified mapping row for REC-S6-001"]
;   next_step: "Supply a mappings file containing a verified link between
;               recording REC-S6-001 and its corresponding work, or confirm
;               that no such link should exist."
;
; No-fire case (title match MUST NOT create a link)
; --------------------------------------------------
; Both REC-S6-001 and WRK-S6-001 have the title "Ghost Signal".
; Despite the match, no (verified-mapping "REC-S6-001" ...) fact exists.
; Rule R4 fires for REC-S6-001 correctly.
; No "title_match_link" fact is ever produced — the schema has no such fact.
;
; For REC-S6-002 (album version, IS mapped with verified = true):
;   verified-mapping fact exists → no unlinked-recording fact → R4 does NOT fire. ✓
;
; ---------------------------------------------------------------------------
; Rule definition (used by rule_runner.py as the query expression)
; ---------------------------------------------------------------------------

(= (r4-fires $rec $title)
   (match &self (unlinked-recording $rec $title)
     (r4-fires $rec $title)))
