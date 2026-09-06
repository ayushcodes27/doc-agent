import pytest
from unittest.mock import patch, MagicMock
from api.models import ExtractedInvoice
from agent.nodes import (
    extract_data,
    validate_compliance,
    check_duplicates,
    detect_anomalies,
    calculate_risk,
    make_decision,
    generate_report,
)


@pytest.fixture
def sample_extracted_dict():
    return {
        "vendor_name": "Acme Tech Solutions Pvt Ltd",
        "vendor_id": "29AABCU9603R1ZM",
        "invoice_number": "INV-2026-001",
        "invoice_date": "2026-08-15",
        "due_date": "2026-09-14",
        "currency": "INR",
        "subtotal": 50000.0,
        "tax_amount": 9000.0,
        "total_amount": 59000.0,
        "line_items": [
            {"description": "Monitor", "quantity": 1.0, "unit_price": 50000.0, "total": 50000.0}
        ],
        "payment_terms": "Net 30",
        "confidence_score": 0.95,
    }


def test_extract_data_empty_text():
    state = {"document_text": "", "audit_trail": []}
    res = extract_data(state)
    assert res["extracted_data"] is None
    assert res["extraction_confidence"] == 0.0
    assert len(res["audit_trail"]) == 1
    assert "Failed" in res["audit_trail"][0]["detail"]


@patch("agent.nodes.extract_invoice_data")
def test_extract_data_success(mock_extract):
    mock_extracted = ExtractedInvoice(
        vendor_name="Acme Corp",
        invoice_number="INV-123",
        invoice_date="2026-08-01",
        subtotal=100.0,
        total_amount=100.0,
        confidence_score=0.98,
    )
    mock_extract.return_value = mock_extracted

    state = {"document_text": "Sample text", "audit_trail": []}
    res = extract_data(state)

    assert res["extracted_data"]["vendor_name"] == "Acme Corp"
    assert res["extraction_confidence"] == 0.98
    assert len(res["audit_trail"]) == 1


def test_validate_compliance_node(sample_extracted_dict):
    state = {"extracted_data": sample_extracted_dict, "audit_trail": []}
    res = validate_compliance(state)
    assert "validation_results" in res
    assert len(res["validation_results"]) > 0
    assert len(res["audit_trail"]) == 1


def test_check_duplicates_node(sample_extracted_dict):
    state = {"extracted_data": sample_extracted_dict, "audit_trail": []}
    res = check_duplicates(state)
    assert "is_duplicate" in res
    assert res["is_duplicate"] is False
    assert len(res["audit_trail"]) == 1


def test_detect_anomalies_node(sample_extracted_dict):
    state = {"extracted_data": sample_extracted_dict, "audit_trail": []}
    res = detect_anomalies(state)
    assert "anomalies" in res
    assert len(res["audit_trail"]) == 1


def test_calculate_risk_low_risk(sample_extracted_dict):
    state = {
        "extracted_data": sample_extracted_dict,
        "validation_results": [{"passed": True, "severity": "error"}],
        "anomalies": [],
        "is_duplicate": False,
        "extraction_confidence": 0.95,
        "audit_trail": [],
    }
    res = calculate_risk(state)
    assert res["risk_score"] == 0.0


def test_calculate_risk_high_risk_duplicate():
    state = {
        "validation_results": [],
        "anomalies": [],
        "is_duplicate": True,
        "extraction_confidence": 0.95,
        "audit_trail": [],
    }
    res = calculate_risk(state)
    assert res["risk_score"] == 1.0


def test_make_decision_auto_approve(sample_extracted_dict):
    state = {
        "extracted_data": sample_extracted_dict,
        "risk_score": 0.1,
        "is_duplicate": False,
        "audit_trail": [],
    }
    res = make_decision(state)
    assert res["decision"] == "auto_approve"
    assert res["approval_level"] == "auto"


def test_make_decision_high_amount_flagged():
    high_amt_dict = {
        "vendor_name": "Acme Tech",
        "total_amount": 150000.0,
    }
    state = {
        "extracted_data": high_amt_dict,
        "risk_score": 0.1,
        "is_duplicate": False,
        "audit_trail": [],
    }
    res = make_decision(state)
    assert res["decision"] == "flag_review"
    assert res["approval_level"] == "manager"


def test_make_decision_rejected():
    state = {
        "extracted_data": {"vendor_name": "Test"},
        "risk_score": 0.85,
        "is_duplicate": False,
        "audit_trail": [],
    }
    res = make_decision(state)
    assert res["decision"] == "reject"


def test_generate_report_node(sample_extracted_dict):
    state = {
        "extracted_data": sample_extracted_dict,
        "validation_results": [{"rule_name": "max_amount", "passed": True, "message": "OK"}],
        "anomalies": [],
        "decision": "auto_approve",
        "risk_score": 0.0,
        "decision_reasoning": "All checks passed",
        "approval_level": "auto",
        "audit_trail": [],
    }
    res = generate_report(state)
    assert "messages" in res
    assert len(res["messages"]) == 1
    assert "DocAgent Invoice Processing Report" in res["messages"][0]["content"]
