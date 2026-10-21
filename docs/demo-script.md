# SoundDue Demo Script (3 minutes)

## Before you start

```bash
make backend    # terminal 1 → http://localhost:8000
make frontend   # terminal 2 → http://localhost:5173
make demo       # seeds the Midnight Train case, prints the URL
```

Open **http://localhost:5173** in Chrome.

---

## [0:00] Open the case (~20 s)

> *"SoundDue is a prototype tool for detecting ownership discrepancies in music rights records. Let's walk through a real scenario — the Midnight Train case, where an internal source and a registration snapshot disagree about a contributor's share."*

1. On the Cases screen, click **Open →** next to **"Midnight Train Demo"**.
2. You land in the Case Workspace with five tabs.

---

## [0:20] Upload and mapping (~30 s)

> *"We uploaded four files: recordings, works, ownership, and mapping data. The system detected column mappings automatically — 'Track Code' → recording_id, 'Songwriter %' → share. For exact synonym matches it confirms without asking."*

3. Click **2. Map columns** — show the green ✓ Mappings confirmed badges.
4. The **Analyze** button in the top-right is already enabled.

---

## [0:50] Run analysis and inspect a finding (~60 s)

> *"Let's run the rule engine."*

5. Click **Analyze**. The app switches to **4. Findings**.

> *"One finding: possible_missing_claim. The rule detected that an internal source credits a contributor with a share, but the registration snapshot marks that share as missing from the supplied records."*

6. Click **View →** on the finding.

> *"Each finding has six sections. The Issue says what was detected. Evidence shows the two conflicting records side-by-side. Rule shows exactly which conditions fired and the rule version. Uncertainty tells us what we don't know. Next Step guides the reviewer."*

7. Scroll through all six sections.

---

## [1:50] Reject a wrong fuzzy match (~20 s)

8. Click **← Back to findings**, then **5. Match candidates**.
9. Show a fuzzy candidate's score breakdown (title %, name %, duration).
10. Click **Reject** on a low-score candidate.

> *"Rejected pairs are never re-proposed on reruns — that's the corroboration requirement: title similarity alone isn't enough."*

---

## [2:10] Correct the record and rerun (~40 s)

11. Go back to **4. Findings**, click **View →**.
12. Click **Correct record**. Add field `share_status = claimed`. Write a note: *"Registration confirmed — share is now claimed."*
13. Click **Confirm**.

> *"The system creates a new record version — it never overwrites. The original is preserved."*

14. Click **← Back to findings**, then **↻ Rerun** → **↻ Run now**.
15. Point to **✓ Resolved: 1** in the diff.

> *"The corrected finding is now resolved. The full history — who corrected it, when, and what they wrote — is preserved in the Review History section."*

---

## [2:50] Export (~10 s)

> *"Finally, every finding can be exported."*

Open in browser:
```
http://localhost:8000/cases/1/export?format=html
```

> *"The HTML report includes the plain-language explanation, full rule trace, evidence rows, and a limitations note on every page."*

---

## Limitations to mention

- *"This is a prototype. Rules are simulated in Python — the MeTTa/hyperon integration is a planned next step, not yet done."*
- *"No authentication, no multi-tenancy, SQLite only."*
- *"Findings are leads for human review, not ownership decisions."*
