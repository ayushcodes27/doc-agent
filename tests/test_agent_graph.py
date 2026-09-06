import pytest
from unittest.mock import patch
from api.models import ExtractedInvoice
from agent.graph import build_workflow, run_docagent
from tools.duplicate_checker import _in_memory_cache


def setup_function():
    _in_memory_cache.clear()


@patch("agent.nodes.extract_invoice_data")
def test_full_graph_auto_approve_scenario(mock_extract):
    mock_invoice = ExtractedInvoice(
        vendor_name="Acme Tech Solutions Pvt Ltd",
        invoice_number="INV-AUTO-001",
        invoice_date="2026-08-15",
        subtotal=40000.0,
        tax_amount=7200.0,
        total_amount=47200.0,
        line_items=[{"description": "Laptops", "quantity": 1.0, "unit_price": 40000.0, "total": 40000.0}],
        confidence_score=0.96,
    )
    mock_extract.return_value = mock_invoice

    result = run_docagent("Document text content", "sample.pdf")

    assert result["decision"] == "auto_approve"
    assert result["approval_level"] == "auto"
    assert result["risk_score"] == 0.0
    assert result["is_duplicate"] is False
    assert len(result["audit_trail"]) == 7
    assert len(result["messages"]) == 1


@patch("agent.nodes.extract_invoice_data")
def test_full_graph_high_amount_director_review_scenario(mock_extract):
    mock_invoice = ExtractedInvoice(
        vendor_name="Acme Tech Solutions Pvt Ltd",
        invoice_number="INV-HIGH-888",
        invoice_date="2026-08-15",
        subtotal=250000.0,
        tax_amount=45000.0,
        total_amount=295000.0,
        line_items=[{"description": "Server hardware", "quantity": 1.0, "unit_price": 250000.0, "total": 250000.0}],
        confidence_score=0.95,
    )
    mock_extract.return_value = mock_invoice

    result = run_docagent("High amount invoice document", "high.pdf")

    assert result["decision"] == "flag_review"
    assert result["approval_level"] == "director"
    assert len(result["audit_trail"]) == 7


@patch("agent.nodes.extract_invoice_data")
def test_full_graph_unapproved_vendor_scenario(mock_extract):
    mock_invoice = ExtractedInvoice(
        vendor_name="Unknown Unregistered Supplier Ltd",
        invoice_number="INV-UNKNOWN-99",
        invoice_date="2026-08-15",
        subtotal=20000.0,
        tax_amount=3600.0,
        total_amount=23600.0,
        line_items=[],
        confidence_score=0.90,
    )
    mock_extract.return_value = mock_invoice

    result = run_docagent("Unknown vendor invoice text", "unknown.pdf")

    assert result["risk_score"] >= 0.25
    failed_rules = [v for v in result["validation_results"] if not v["passed"]]
    assert any(r["rule_name"] == "approved_vendor" for r in failed_rules)


@patch("agent.nodes.extract_invoice_data")
def test_full_graph_duplicate_rejection_scenario(mock_extract):
    mock_invoice = ExtractedInvoice(
        vendor_name="Dell",
        invoice_number="DELL-DUP-100",
        invoice_date="2026-08-15",
        subtotal=10000.0,
        tax_amount=0.0,
        total_amount=10000.0,
        line_items=[{"description": "Dell Monitor", "quantity": 1.0, "unit_price": 10000.0, "total": 10000.0}],
        confidence_score=0.98,
    )
    mock_extract.return_value = mock_invoice

    # First run registers fingerprint
    res1 = run_docagent("Dell invoice", "dell1.pdf")
    assert res1["decision"] == "auto_approve"

    # Second run with same invoice should trigger duplicate rejection
    res2 = run_docagent("Dell invoice identical", "dell2.pdf")
    assert res2["is_duplicate"] is True
    assert res2["decision"] == "reject"
    assert res2["risk_score"] == 1.0
