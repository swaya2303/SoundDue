# FICTIONAL DEMO DATA — Scenario 06: unmapped_recording

Two recordings of "Ghost Signal" exist: a demo (REC-S6-001) and an album version
(REC-S6-002). Only the album version has a verified mapping to the work WRK-S6-001.
The demo recording has no mapping entry at all. SoundDue must raise an
`unlinked_recording` finding (R4) for the demo; a title-based link must never
be used as a substitute for an explicit mapping.
