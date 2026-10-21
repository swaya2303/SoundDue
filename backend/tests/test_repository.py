"""
test_repository.py — Integration tests for app/repository.py.

Uses an in-memory SQLite database and a temporary storage directory
so tests never touch the real sounddue_cases.db or ./storage/.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Patch the storage root BEFORE importing repository so the module picks it up.
import app.repository as repo_module
from app.models import Base, create_all_tables


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect repository storage to a temp directory."""
    monkeypatch.setattr(repo_module, "_STORAGE_ROOT", tmp_path / "storage")
    return tmp_path / "storage"


@pytest.fixture()
def db_session(tmp_storage):
    """In-memory SQLite session using the new app/models Base."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateCase:
    def test_creates_case_with_correct_fields(self, db_session):
        case = repo_module.create_case(db_session, name="Test Case", description="desc")
        db_session.commit()

        assert case.id is not None
        assert case.name == "Test Case"
        assert case.description == "desc"
        assert case.created_by == repo_module.DEMO_USER

    def test_two_cases_get_different_ids(self, db_session):
        c1 = repo_module.create_case(db_session, name="Case A")
        c2 = repo_module.create_case(db_session, name="Case B")
        db_session.commit()

        assert c1.id != c2.id


class TestAddFile:
    def test_file_is_written_to_disk(self, db_session, tmp_storage):
        case = repo_module.create_case(db_session, name="File Test")
        db_session.commit()

        content = b"recording_id,title\nR001,Hello World"
        uf = repo_module.add_file(
            db_session,
            case_id=case.id,
            original_name="recordings.csv",
            content_bytes=content,
            file_type="recordings",
        )
        db_session.commit()

        stored = Path(uf.storage_path)
        assert stored.exists(), f"File not found at {stored}"
        assert stored.read_bytes() == content

    def test_sha256_is_recorded(self, db_session, tmp_storage):
        import hashlib

        case = repo_module.create_case(db_session, name="SHA Test")
        db_session.commit()

        content = b"hello"
        uf = repo_module.add_file(
            db_session,
            case_id=case.id,
            original_name="test.csv",
            content_bytes=content,
            file_type="recordings",
        )
        db_session.commit()

        expected = hashlib.sha256(content).hexdigest()
        assert uf.sha256 == expected

    def test_file_stored_under_case_subdirectory(self, db_session, tmp_storage):
        case = repo_module.create_case(db_session, name="Dir Test")
        db_session.commit()

        uf = repo_module.add_file(
            db_session,
            case_id=case.id,
            original_name="works.csv",
            content_bytes=b"data",
            file_type="works",
        )
        db_session.commit()

        assert str(case.id) in uf.storage_path


class TestSaveAndSupersede:
    def _make_case_and_file(self, db_session):
        case = repo_module.create_case(db_session, name="Record Test")
        db_session.commit()
        uf = repo_module.add_file(
            db_session,
            case_id=case.id,
            original_name="r.csv",
            content_bytes=b"x",
            file_type="recordings",
        )
        db_session.commit()
        return case, uf

    def test_save_single_record(self, db_session, tmp_storage):
        case, uf = self._make_case_and_file(db_session)

        records = repo_module.save_records(
            db_session,
            case_id=case.id,
            records=[{"normalised": {"title": "Song A"}, "raw": {"Title": "Song A"}, "source_row": 1}],
            record_type="recording",
            source_file_id=uf.id,
        )
        db_session.commit()

        assert len(records) == 1
        assert records[0].version == 1
        assert records[0].supersedes_id is None
        assert records[0].normalised_json["title"] == "Song A"

    def test_supersede_creates_new_version(self, db_session, tmp_storage):
        case, uf = self._make_case_and_file(db_session)

        [original] = repo_module.save_records(
            db_session,
            case_id=case.id,
            records=[{"normalised": {"title": "Old Title"}, "raw": {}, "source_row": 2}],
            record_type="recording",
            source_file_id=uf.id,
        )
        db_session.commit()
        old_id = original.id

        new_rec = repo_module.supersede_record(
            db_session,
            old_record_id=old_id,
            new_normalised={"title": "New Title"},
            new_raw={"Title": "New Title (corrected)"},
        )
        db_session.commit()

        assert new_rec.id != old_id
        assert new_rec.version == 2
        assert new_rec.supersedes_id == old_id
        assert new_rec.normalised_json["title"] == "New Title"

    def test_old_record_is_unchanged_after_supersede(self, db_session, tmp_storage):
        from app.models import Record

        case, uf = self._make_case_and_file(db_session)

        [original] = repo_module.save_records(
            db_session,
            case_id=case.id,
            records=[{"normalised": {"title": "Unchanged"}, "raw": {}, "source_row": 3}],
            record_type="recording",
            source_file_id=uf.id,
        )
        db_session.commit()
        old_id = original.id

        repo_module.supersede_record(
            db_session,
            old_record_id=old_id,
            new_normalised={"title": "Changed"},
            new_raw={},
        )
        db_session.commit()

        # Re-fetch the old record and assert it was NOT modified
        old_row = db_session.get(Record, old_id)
        assert old_row.normalised_json["title"] == "Unchanged"
        assert old_row.version == 1
        assert old_row.supersedes_id is None

    def test_supersede_missing_record_raises(self, db_session, tmp_storage):
        with pytest.raises(ValueError, match="not found"):
            repo_module.supersede_record(
                db_session,
                old_record_id=99999,
                new_normalised={},
                new_raw={},
            )


class TestSaveFindings:
    def test_save_finding_creates_rule_trace_and_evidence(self, db_session, tmp_storage):
        case = repo_module.create_case(db_session, name="Finding Test")
        db_session.commit()

        findings_input = [
            {
                "rule_id": "RULE-001",
                "rule_version": "1.0",
                "severity": "warning",
                "summary": "Shares do not sum to 100%",
                "uncertainty": "May be unclaimed",
                "next_step": "Check share schedules",
                "matched_conditions": ["share_sum < 100"],
                "supporting_record_ids": [1, 2],
                "missing_information": "Missing share holder",
                "conflicting_information": "",
                "evidence": {"file_name": "ownership.csv", "row_number": 3, "total_pct": 80.0},
            }
        ]

        saved = repo_module.save_findings(db_session, case_id=case.id, findings=findings_input)
        db_session.commit()

        assert len(saved) == 1
        f = saved[0]
        # Finding stores rule_id in finding_type field
        assert f.finding_type == "RULE-001"
        assert f.severity == "warning"
        assert f.status == "open"

        # Check RuleTrace was created
        from app.models import RuleTrace

        rt = db_session.query(RuleTrace).filter_by(finding_id=f.id).first()
        assert rt is not None
        assert rt.matched_conditions == ["share_sum < 100"]
        assert rt.supporting_record_ids == [1, 2]
        # rule_id lives on RuleTrace
        assert rt.rule_id == "RULE-001"

        # Check Evidence was created — evidence stored as field_values JSON
        from app.models import Evidence

        ev = db_session.query(Evidence).filter_by(finding_id=f.id).first()
        assert ev is not None
        assert ev.field_values["file_name"] == "ownership.csv"


class TestRecordDecision:
    def test_record_decision_on_finding(self, db_session, tmp_storage):
        case = repo_module.create_case(db_session, name="Decision Test")
        db_session.commit()

        [finding] = repo_module.save_findings(
            db_session,
            case_id=case.id,
            findings=[
                {
                    "rule_id": "RULE-002",
                    "rule_version": "1.0",
                    "severity": "info",
                    "summary": "No link found",
                    "evidence": {},
                }
            ],
        )
        db_session.commit()

        rd = repo_module.record_decision(
            db_session,
            decision="accept",
            finding_id=finding.id,
            note="Confirmed by analyst",
        )
        db_session.commit()

        assert rd.id is not None
        assert rd.decision == "accept"
        assert rd.finding_id == finding.id
        assert rd.note == "Confirmed by analyst"
        assert rd.actor == repo_module.DEMO_USER

    def test_record_decision_requires_target(self, db_session, tmp_storage):
        with pytest.raises(ValueError):
            repo_module.record_decision(db_session, decision="reject")


class TestLogAuditEvent:
    def test_audit_event_is_inserted(self, db_session, tmp_storage):
        case = repo_module.create_case(db_session, name="Audit Test")
        db_session.commit()

        evt = repo_module.log_audit_event(
            db_session,
            case_id=case.id,
            event_type="file_uploaded",
            payload={"filename": "recordings.csv", "rows": 10},
        )
        db_session.commit()

        assert evt.id is not None
        assert evt.event_type == "file_uploaded"
        assert evt.actor == repo_module.DEMO_USER
        assert evt.payload["rows"] == 10

    def test_multiple_audit_events_accumulate(self, db_session, tmp_storage):
        from app.models import AuditEvent

        case = repo_module.create_case(db_session, name="Multi Audit")
        db_session.commit()

        for i in range(3):
            repo_module.log_audit_event(
                db_session, case_id=case.id, event_type=f"event_{i}"
            )
        db_session.commit()

        count = db_session.query(AuditEvent).filter_by(case_id=case.id).count()
        assert count == 3

    def test_full_workflow(self, db_session, tmp_storage):
        """End-to-end: create case → upload file → save record → supersede → log audit."""
        case = repo_module.create_case(db_session, name="Workflow Test")
        db_session.commit()

        uf = repo_module.add_file(
            db_session,
            case_id=case.id,
            original_name="recordings.csv",
            content_bytes=b"id,title\nR1,Track One",
            file_type="recordings",
        )
        db_session.commit()

        [rec] = repo_module.save_records(
            db_session,
            case_id=case.id,
            records=[{"normalised": {"title": "Track One"}, "raw": {}, "source_row": 1}],
            record_type="recording",
            source_file_id=uf.id,
        )
        db_session.commit()

        new_rec = repo_module.supersede_record(
            db_session,
            old_record_id=rec.id,
            new_normalised={"title": "Track One (corrected)"},
            new_raw={"title": "Track One (corrected)"},
        )
        db_session.commit()

        repo_module.log_audit_event(
            db_session,
            case_id=case.id,
            event_type="record_corrected",
            payload={"old_id": rec.id, "new_id": new_rec.id},
        )
        db_session.commit()

        from app.models import AuditEvent, Record

        all_records = db_session.query(Record).filter_by(case_id=case.id).all()
        assert len(all_records) == 2
        assert any(r.supersedes_id == rec.id for r in all_records)

        events = db_session.query(AuditEvent).filter_by(case_id=case.id).all()
        assert len(events) == 1
        assert events[0].event_type == "record_corrected"
