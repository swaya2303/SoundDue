"""
metta_engine.py — Symbolic rule evaluation for SoundDue.

# Prototype shortcut: MeTTa rules are simulated in Python (hyperon integration is a stretch goal)

Rules are explicit, symbolic, and traceable — not statistical.
Each rule returns a list of finding dicts that are persisted to the findings table.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from database import Finding, Mapping, MatchCandidate, OwnershipClaim, Recording, Work


class MeTTaEngine:
    """
    Symbolic rule engine that evaluates data-quality rules against the DB.

    Rules implemented:
      RULE-001 v1.0  share_sum_check
      RULE-002 v1.0  missing_isrc_on_mapping
      RULE-003 v1.0  recording_work_no_link
      RULE-004 v1.0  incompatible_share_comparison
    """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run_all(self, db_session: Session) -> list[dict]:
        """Run every rule and persist findings. Returns list of finding dicts."""
        findings: list[dict] = []
        findings.extend(self._rule_001_share_sum_check(db_session))
        findings.extend(self._rule_002_missing_isrc_on_mapping(db_session))
        findings.extend(self._rule_003_recording_work_no_link(db_session))
        findings.extend(self._rule_004_incompatible_share_comparison(db_session))
        db_session.commit()
        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _store_finding(self, db_session: Session, fd: dict) -> Finding:
        finding = Finding(
            rule_id=fd["rule_id"],
            rule_version=fd["rule_version"],
            severity=fd["severity"],
            summary=fd["summary"],
            evidence_json=fd["evidence"],
            uncertainty=fd["uncertainty"],
            next_step=fd["next_step"],
            status="open",
            created_at=datetime.utcnow(),
        )
        db_session.add(finding)
        db_session.flush()
        fd["id"] = finding.id
        return finding

    # ------------------------------------------------------------------
    # RULE-001 v1.0  share_sum_check
    # ------------------------------------------------------------------
    def _rule_001_share_sum_check(self, db_session: Session) -> list[dict]:
        """
        Group ownership_claims by (work_iswc, rights_category, territory,
        period_start, period_end).  Sum shares per group.
        Flag if sum != 100.0 (tolerance 0.01).
        """
        claims = db_session.query(OwnershipClaim).all()

        # Group
        groups: dict[tuple, list[OwnershipClaim]] = {}
        for c in claims:
            key = (c.work_iswc, c.rights_category, c.territory, c.period_start, c.period_end)
            groups.setdefault(key, []).append(c)

        findings: list[dict] = []
        for key, group_claims in groups.items():
            iswc, cat, territory, p_start, p_end = key
            total = sum(float(c.share_pct) for c in group_claims)

            if abs(total - 100.0) <= 0.01:
                continue  # Shares are OK

            if total < 99.99:
                severity = "warning"
                summary = "Shares do not sum to 100% — gap present"
            else:
                severity = "error"
                summary = "Shares exceed 100%"

            evidence = {
                "work_iswc": iswc,
                "rights_category": cat,
                "territory": territory,
                "period_start": p_start,
                "period_end": p_end,
                "total_pct": round(total, 4),
                "claim_ids": [c.id for c in group_claims],
                "claim_rows": [
                    {
                        "id": c.id,
                        "rights_holder": c.rights_holder,
                        "share_pct": float(c.share_pct),
                    }
                    for c in group_claims
                ],
            }

            fd = {
                "rule_id": "RULE-001",
                "rule_version": "1.0",
                "severity": severity,
                "summary": summary,
                "evidence": evidence,
                "uncertainty": (
                    "Gap may reflect unclaimed shares not marked as such in source data"
                ),
                "next_step": (
                    "Obtain share schedules from all rights holders for this "
                    "work/territory/period"
                ),
            }
            self._store_finding(db_session, fd)
            findings.append(fd)

        return findings

    # ------------------------------------------------------------------
    # RULE-002 v1.0  missing_isrc_on_mapping
    # ------------------------------------------------------------------
    def _rule_002_missing_isrc_on_mapping(self, db_session: Session) -> list[dict]:
        """
        For each mapping row, check if recording_isrc exists in recordings table.
        Flag if missing.
        """
        mappings = db_session.query(Mapping).all()
        known_isrcs: set[str] = {
            r.isrc for r in db_session.query(Recording).all() if r.isrc
        }

        findings: list[dict] = []
        for mapping in mappings:
            if mapping.recording_isrc and mapping.recording_isrc not in known_isrcs:
                evidence = {
                    "mapping_id": mapping.id,
                    "recording_isrc": mapping.recording_isrc,
                    "work_iswc": mapping.work_iswc,
                }
                fd = {
                    "rule_id": "RULE-002",
                    "rule_version": "1.0",
                    "severity": "warning",
                    "summary": (
                        f"Mapping references ISRC {mapping.recording_isrc!r} "
                        "which is not present in recordings table"
                    ),
                    "evidence": evidence,
                    "uncertainty": (
                        "Recording may exist under a different ISRC or may not "
                        "have been supplied"
                    ),
                    "next_step": "Verify ISRC with rights holder or CMO database",
                }
                self._store_finding(db_session, fd)
                findings.append(fd)

        return findings

    # ------------------------------------------------------------------
    # RULE-003 v1.0  recording_work_no_link
    # ------------------------------------------------------------------
    def _rule_003_recording_work_no_link(self, db_session: Session) -> list[dict]:
        """
        For recordings with no accepted mapping to any work (neither in the
        mappings table nor via an accepted match_candidate), emit an info finding.
        """
        recordings = db_session.query(Recording).all()
        mappings = db_session.query(Mapping).all()

        # ISRCs that appear in the mappings table
        mapped_isrcs: set[str] = {
            m.recording_isrc for m in mappings if m.recording_isrc
        }

        # Recording IDs that have an accepted match_candidate
        accepted_recording_ids: set[int] = {
            mc.recording_id
            for mc in db_session.query(MatchCandidate).filter(
                MatchCandidate.status == "accepted"
            ).all()
        }

        findings: list[dict] = []
        for rec in recordings:
            has_mapping = rec.isrc and rec.isrc in mapped_isrcs
            has_accepted_candidate = rec.id in accepted_recording_ids
            if not has_mapping and not has_accepted_candidate:
                evidence = {
                    "recording_id": rec.id,
                    "isrc": rec.isrc,
                    "title": rec.title,
                }
                fd = {
                    "rule_id": "RULE-003",
                    "rule_version": "1.0",
                    "severity": "info",
                    "summary": (
                        f"Recording {rec.isrc!r} ({rec.title!r}) has no linked work"
                    ),
                    "evidence": evidence,
                    "uncertainty": (
                        "Work may exist but was not supplied in this upload batch"
                    ),
                    "next_step": "Supply works data or mapping file",
                }
                self._store_finding(db_session, fd)
                findings.append(fd)

        return findings

    # ------------------------------------------------------------------
    # RULE-004 v1.0  incompatible_share_comparison
    # ------------------------------------------------------------------
    def _rule_004_incompatible_share_comparison(self, db_session: Session) -> list[dict]:
        """
        If two ownership_claims for the same work_iswc have DIFFERENT
        rights_category or territory values, flag incompatible comparison.
        Only fires when >= 2 distinct (rights_category, territory) combos
        exist for the same ISWC.
        """
        claims = db_session.query(OwnershipClaim).all()

        # Build map: iswc → set of (rights_category, territory) combos
        iswc_combos: dict[str, set[tuple]] = {}
        for c in claims:
            key = c.work_iswc
            combo = (c.rights_category, c.territory)
            iswc_combos.setdefault(key, set()).add(combo)

        findings: list[dict] = []
        for iswc, combos in iswc_combos.items():
            if len(combos) >= 2:
                evidence = {
                    "work_iswc": iswc,
                    "distinct_combos": [
                        {"rights_category": cat, "territory": ter}
                        for cat, ter in sorted(combos)
                    ],
                }
                fd = {
                    "rule_id": "RULE-004",
                    "rule_version": "1.0",
                    "severity": "info",
                    "summary": (
                        "Multiple rights categories/territories present — "
                        "shares are not directly comparable"
                    ),
                    "evidence": evidence,
                    "uncertainty": (
                        "Different rights categories (e.g. mechanical vs performance) "
                        "are administered separately"
                    ),
                    "next_step": (
                        "Separate analysis per rights category and territory required"
                    ),
                }
                self._store_finding(db_session, fd)
                findings.append(fd)

        return findings
