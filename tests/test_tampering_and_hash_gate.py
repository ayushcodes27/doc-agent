import pytest
from tools.duplicate_checker import check_file_hash_gate, check_near_duplicate
from tools.document_loader import compute_file_hash, compute_text_quality_score


def test_compute_file_hash():
    data = b"Invoice content 2026 test bytes"
    h1 = compute_file_hash(data)
    h2 = compute_file_hash(data)
    assert len(h1) == 64
    assert h1 == h2


def test_compute_text_quality_score():
    clean_text = "Tax Invoice\nVendor: Amazon Web Services\nInvoice Date: 2026-08-15\nTotal: $1,250.00\nPayment Terms: Net 30"
    score_clean = compute_text_quality_score(clean_text)
    assert score_clean > 0.80

    garbage_text = "%%%%\x00\x01\x02??###@@"
    score_garbage = compute_text_quality_score(garbage_text)
    assert score_garbage < 0.30


def test_file_hash_gate_empty_bytes():
    res = check_file_hash_gate(b"")
    assert res["is_blocked"] is False
    assert res["file_hash"] == ""


def test_near_duplicate_detection():
    # Near duplicate check with dict
    inv = {
        "vendor_name": "Infosys Limited",
        "invoice_number": "INV-1001",
        "total_amount": 50000.0,
    }
    # No DB records -> False
    res = check_near_duplicate(inv)
    assert res["is_near_duplicate"] is False
