# FICTIONAL DEMO DATA — Scenario 01: midnight_train_unclaimed

Writers A (60 %) and B (40 %) co-wrote "Midnight Train".
The rights registration supplies Writer A's 60 % claim and **explicitly** marks
the remaining 40 % as "unclaimed", indicating a known gap with a named pool entry.
SoundDue must raise a `possible_missing_claim` finding (R1) for the unclaimed
portion and must **not** treat this as a silent omission.
