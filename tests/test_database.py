"""
Tests for Database Persistence Layer and Repositories
=====================================================
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.session import Base
from db.models import InvoiceRecord, LineItemRecord, ValidationRecord, AnomalyRecord, AuditTrailRecord
from db.repository import (
    save_processed_invoice,
    get_invoice_by_id,
    get_invoice_by_thread_id,
    list_invoices,
    get_pending_reviews,
    record_human_decision,
    get_vendor_spend_history,
    get_analytics_summary,
)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for unit testing."""
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def test_save_and_retrieve_processed_invoice(db_session):
    workflow_result = {
        "extracted_data": {
            "vendor_name": "Infosys Limited",
            "vendor_id": "27AABCI1234F1ZM",
            "invoice_number": "INF-2026-999",
            "invoice_date": "2026-09-25",
            "due_date": "2026-10-25",
            "currency": "INR",
            "subtotal": 40000.0,
            "tax_amount": 7200.0,
            "total_amount": 47200.0,
            "payment_terms": "Net 30",
            "confidence_score": 0.98,
            "line_items": [
                {"description": "Consulting service", "quantity": 10.0, "unit_price": 4000.0, "total": 40000.0}
            ],
        },
        "validation_results": [
            {"rule_name": "max_amount", "passed": True, "severity": "error", "message": "Within budget cap", "field": "total_amount"},
            {"rule_name": "approved_vendor", "passed": True, "severity": "error", "message": "Approved vendor", "field": "vendor_name"},
        ],
        "anomalies": [
            {"type": "round_number", "severity": "info", "score": 0.3, "message": "Round amount detected"}
        ],
        "audit_trail": [
            {"step": "extraction", "timestamp": "2026-09-25T10:00:00Z", "detail": "Extracted 1 line items"},
            {"step": "validation", "timestamp": "2026-09-25T10:00:01Z", "detail": "Evaluated 2 rules"},
        ],
        "decision": "auto_approve",
        "approval_level": "auto",
        "risk_score": 0.0,
        "decision_reasoning": "Clean invoice with zero risk",
        "is_duplicate": False,
    }

    # Save
    record = save_processed_invoice(db_session, workflow_result, thread_id="thread-test-01", filename="test_inv.pdf")
    assert record.id is not None
    assert record.thread_id == "thread-test-01"
    assert record.vendor_name == "Infosys Limited"
    assert record.total_amount == 47200.0

    # Retrieve by thread_id
    retrieved = get_invoice_by_thread_id(db_session, "thread-test-01")
    assert retrieved is not None
    assert len(retrieved.line_items) == 1
    assert retrieved.line_items[0].description == "Consulting service"
    assert len(retrieved.validations) == 2
    assert len(retrieved.anomalies) == 1
    assert len(retrieved.audit_trail) == 2


def test_human_decision_recording_and_review_queue(db_session):
    workflow_result = {
        "extracted_data": {
            "vendor_name": "Tata Consultancy Services",
            "invoice_number": "TCS-600K",
            "total_amount": 600000.0,
            "currency": "INR",
        },
        "validation_results": [{"rule_name": "max_amount", "passed": False, "severity": "error", "message": "Over budget"}],
        "anomalies": [],
        "audit_trail": [{"step": "decision", "timestamp": "2026-09-25T12:00:00Z", "detail": "Flagged for Director"}],
        "decision": "flag_review",
        "approval_level": "director",
        "risk_score": 0.25,
        "decision_reasoning": "Exceeds director budget threshold",
        "is_duplicate": False,
    }

    save_processed_invoice(db_session, workflow_result, thread_id="thread-review-01", filename="tcs.pdf")

    # Verify in pending review queue
    pending = get_pending_reviews(db_session)
    assert len(pending) == 1
    assert pending[0].thread_id == "thread-review-01"
    assert pending[0].status == "pending_review"

    # Human approves the invoice
    updated = record_human_decision(
        db_session,
        thread_id="thread-review-01",
        human_action="approve",
        reasoning="Approved per Q3 budget allocation",
        reviewer_name="Director Sharma",
    )

    assert updated is not None
    assert updated.status == "approved_by_human"
    assert updated.decision == "auto_approve"
    assert updated.reviewed_by == "Director Sharma"

    # Queue should now be empty
    assert len(get_pending_reviews(db_session)) == 0


def test_vendor_spend_history_and_analytics(db_session):
    # Insert multiple invoices for Infosys and Wipro
    for i, amt in enumerate([10000.0, 20000.0, 30000.0]):
        save_processed_invoice(
            db_session,
            {
                "extracted_data": {"vendor_name": "Infosys Limited", "invoice_number": f"INF-{i}", "total_amount": amt},
                "validation_results": [],
                "anomalies": [],
                "audit_trail": [],
                "decision": "auto_approve",
                "approval_level": "auto",
                "risk_score": 0.0,
            },
            thread_id=f"inf-{i}",
        )

    save_processed_invoice(
        db_session,
        {
            "extracted_data": {"vendor_name": "Wipro Technologies", "invoice_number": "WIP-1", "total_amount": 50000.0},
            "validation_results": [],
            "anomalies": [{"type": "round_number", "severity": "info", "score": 0.3, "message": "Round amount"}],
            "audit_trail": [],
            "decision": "flag_review",
            "approval_level": "manager",
            "risk_score": 0.3,
        },
        thread_id="wip-1",
    )

    # Test vendor spend history query
    history = get_vendor_spend_history(db_session, "Infosys Limited")
    assert len(history) == 3
    amounts = [h["total_amount"] for h in history]
    assert sorted(amounts) == [10000.0, 20000.0, 30000.0]

    # Test analytics aggregation
    analytics = get_analytics_summary(db_session)
    assert analytics["total_invoices"] == 4
    assert analytics["total_spend"] == 110000.0
    assert "auto_approve" in analytics["decisions"]
    assert "flag_review" in analytics["decisions"]
    assert len(analytics["top_vendors"]) == 2
    assert analytics["top_vendors"][0]["vendor"] == "Infosys Limited"
