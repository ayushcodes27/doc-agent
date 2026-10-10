import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.session import Base
from db.models import InvoiceRecord, AuditTrailRecord, PendingReviewRecord
from db.repository import (
    record_human_decision,
    submit_human_correction,
    reopen_rejected_case,
    save_processed_invoice,
)
from agent.nodes import _log_audit


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_hash_chained_audit_trail_generation():
    audit_trail = []
    _log_audit(audit_trail, "step_1", "Initial node execution")
    _log_audit(audit_trail, "step_2", "Second node execution")
    _log_audit(audit_trail, "step_3", "Final node execution")

    assert len(audit_trail) == 3
    # Step 1 links from genesis 0*64
    assert audit_trail[0]["previous_hash"] == "0" * 64
    assert len(audit_trail[0]["entry_hash"]) == 64

    # Step 2 links from Step 1's entry_hash
    assert audit_trail[1]["previous_hash"] == audit_trail[0]["entry_hash"]
    assert len(audit_trail[1]["entry_hash"]) == 64

    # Step 3 links from Step 2's entry_hash
    assert audit_trail[2]["previous_hash"] == audit_trail[1]["entry_hash"]
    assert len(audit_trail[2]["entry_hash"]) == 64


def test_human_correction_loop_safeguards(test_db):
    # Setup initial flagged invoice
    workflow_result = {
        "extracted_data": {
            "vendor_name": "Blurry Vendor Inc",
            "invoice_number": "BLUR-001",
            "total_amount": 12000.0,
            "currency": "INR",
        },
        "validation_results": [],
        "anomalies": [],
        "audit_trail": [{"step": "initial", "detail": "Flagged blurry scan"}],
        "decision": "flag_review",
        "approval_level": "manager",
        "risk_score": 0.35,
    }
    save_processed_invoice(test_db, workflow_result, thread_id="thread-corr-01")

    # 1st Correction: Valid
    corr_1 = {"vendor_name": "Crystal Clear Vendor Ltd", "total_amount": 12500.0}
    inv1, msg1 = submit_human_correction(test_db, "thread-corr-01", corr_1, reviewer_name="Specialist1")
    assert inv1 is not None
    assert inv1.vendor_name == "Crystal Clear Vendor Ltd"
    assert inv1.total_amount == 12500.0

    # 2nd Correction: Valid
    corr_2 = {"invoice_number": "CLEAR-001"}
    inv2, msg2 = submit_human_correction(test_db, "thread-corr-01", corr_2, reviewer_name="Specialist2")
    assert inv2 is not None
    assert inv2.invoice_number == "CLEAR-001"

    # 3rd Correction: Blocked by max 2 re-entries limit!
    corr_3 = {"total_amount": 13000.0}
    inv3, msg3 = submit_human_correction(test_db, "thread-corr-01", corr_3, reviewer_name="Specialist3")
    assert inv3 is None
    assert "limit (2) exceeded" in msg3


def test_case_reopening(test_db):
    # Create rejected invoice
    workflow_result = {
        "extracted_data": {"vendor_name": "Rejected Co", "total_amount": 5000.0},
        "validation_results": [],
        "anomalies": [],
        "audit_trail": [],
        "decision": "reject",
        "approval_level": "auto",
        "risk_score": 0.85,
    }
    save_processed_invoice(test_db, workflow_result, thread_id="thread-reopen-01")

    # Reopen for review
    reopened = reopen_rejected_case(test_db, "thread-reopen-01", reviewer_name="AuditorJane", appeal_reason="Supplier provided proof of GST")
    assert reopened is not None
    assert reopened.status == "pending_review"
    assert reopened.decision == "flag_review"
    assert any(a.step == "case_reopened" for a in reopened.audit_trail)
