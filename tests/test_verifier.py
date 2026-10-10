import pytest
from tools.verifier import compare_and_verify, check_snippet_grounding


def test_compare_and_verify_full_agreement():
    reader_a = {
        "vendor_name": "Acme Technologies Pvt Ltd",
        "invoice_number": "INV-2026-001",
        "total_amount": 15000.0,
        "subtotal": 12500.0,
        "tax_amount": 2500.0,
        "evidence_snippets": {
            "total_amount": "Total: ₹15,000.00",
            "vendor_name": "Acme Technologies",
        }
    }
    reader_b = {
        "vendor_name": "Acme Technologies",
        "invoice_number": "INV-2026-001",
        "total_amount": 15000.0,
        "evidence_snippets": {
            "total_amount": "15000.00",
            "vendor_name": "Acme Technologies Pvt Ltd",
        }
    }
    raw_text = "Tax Invoice\nAcme Technologies Pvt Ltd\nInvoice No: INV-2026-001\nTotal: ₹15,000.00"

    result = compare_and_verify(reader_a, reader_b, raw_text=raw_text)

    assert result["verification_level"] == "full"
    assert result["total_match"] is True
    assert result["vendor_match"] is True
    assert result["invoice_num_match"] is True
    assert result["agreement_score"] == 1.0
    assert len(result["discrepancies"]) == 0


def test_compare_and_verify_total_mismatch():
    reader_a = {
        "vendor_name": "Dell Technologies",
        "invoice_number": "DELL-991",
        "total_amount": 85000.0,
    }
    reader_b = {
        "vendor_name": "Dell Technologies",
        "invoice_number": "DELL-991",
        "total_amount": 75000.0,
    }
    raw_text = "Dell Technologies DELL-991 Total 85000"

    result = compare_and_verify(reader_a, reader_b, raw_text=raw_text)

    assert result["verification_level"] == "none"
    assert result["total_match"] is False
    assert any("Total amount mismatch" in d for d in result["discrepancies"])


def test_compare_and_verify_single_reader_partial():
    reader_a = {
        "vendor_name": "Infosys Limited",
        "invoice_number": "INF-555",
        "total_amount": 42000.0,
    }
    raw_text = "Infosys Limited INF-555 42,000.00"

    result = compare_and_verify(reader_a, reader_b=None, raw_text=raw_text)

    assert result["verification_level"] == "partial"
    assert result["total_match"] is False
    assert any("Reader B (verifier) not available" in d for d in result["discrepancies"])


def test_snippet_grounding():
    raw_text = "Contract payment to Flipkart India Private Limited. Total amount due: 24,500.00 INR."

    # Grounded amount
    assert check_snippet_grounding(24500.0, "24,500.00 INR", raw_text) is True
    # Grounded string
    assert check_snippet_grounding("Flipkart India", "Flipkart India Private Limited", raw_text) is True
    # Ungrounded hallucinated amount
    assert check_snippet_grounding(999999.0, "999,999.00", raw_text) is False
