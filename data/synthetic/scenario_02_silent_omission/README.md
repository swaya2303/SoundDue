# FICTIONAL DEMO DATA — Scenario 02: silent_omission

Writers A and B co-wrote "Midnight Train". Only Writer A's 60 % claim appears
in the supplied ownership file; Writer B's share is simply absent with no label.
SoundDue must raise `incomplete_ownership_info` (R2) because the gap is a silent
omission, not an explicit declaration, and must **not** raise a missing-claim
finding (R1) since no source marks the share as "unclaimed".
