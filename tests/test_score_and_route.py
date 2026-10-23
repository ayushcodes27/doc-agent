import pytest
from tools.score_and_route import (
    normalize_str,
    normalize_whitespace,
    evaluate_pillar_1_trust,
    evaluate_pillar_2_math,
    run_decision_engine,
)


def test_normalize_str_and_whitespace():
    assert normalize_str("INV-2024-99") == "inv202499"
    assert normalize_str("Acme Corp. #123!") == "acmecorp123"
    assert normalize_whitespace("  Total   Due: \n $100.00 \t ") == "total due: $100.00"


def test_pillar_1_clean_agreement():
    obs_a = {
        "visual_discrepancy_detected": False,
        "total_amount": 1000.00,
        "vendor_name": "Acme Industrial Supplies",
        "invoice_number": "INV-2024-001",
    }
    obs_b = {
        "total_amount": 1000.00,
        "vendor_name": "Acme Industrial Supplies",
        "invoice_number": "INV-2024-001",
        "evidence_snippets": {
            "total_amount": "Total: $1000.00",
            "vendor_name": "Acme Industrial Supplies",
            "invoice_number": "INV-2024-001",
        },
    }
    verifier_text = "Acme Industrial Supplies Invoice INV-2024-001 Total: $1000.00 Thank you!"
    score, breaker, reasons = evaluate_pillar_1_trust(obs_a, obs_b, verifier_text)

    assert score == 0.0
    assert breaker is False
    assert len(reasons) == 0


def test_pillar_1_tampering_hard_breaker():
    obs_a = {
        "visual_discrepancy_detected": True,
        "total_amount": 500.00,
        "vendor_name": "Test Vendor",
        "invoice_number": "INV-100",
    }
    obs_b = {
        "total_amount": 500.00,
        "vendor_name": "Test Vendor",
        "invoice_number": "INV-100",
    }
    score, breaker, reasons = evaluate_pillar_1_trust(obs_a, obs_b, "Test Vendor INV-100")
    assert breaker is True
    assert any("tampering" in r.lower() for r in reasons)


def test_pillar_1_total_mismatch_hard_breaker():
    obs_a = {"total_amount": 100.00, "vendor_name": "Alpha", "invoice_number": "INV-1"}
    obs_b = {"total_amount": 150.00, "vendor_name": "Alpha", "invoice_number": "INV-1"}
    score, breaker, reasons = evaluate_pillar_1_trust(obs_a, obs_b, "Alpha INV-1 Total: 100")
    assert breaker is True
    assert any("total mismatch" in r.lower() for r in reasons)


def test_pillar_1_soft_checks():
    # Discrepant vendor, discrepant invoice num, missing snippets
    obs_a = {
        "total_amount": 100.00,
        "vendor_name": "Global Logistics",
        "invoice_number": "INV-101",
    }
    obs_b = {
        "total_amount": 100.00,
        "vendor_name": "Completely Different Services",
        "invoice_number": "INV-999",
        "evidence_snippets": {
            "vendor_name": "Completely Different Services",
            "total_amount": "Not found in text",
        },
    }
    score, breaker, reasons = evaluate_pillar_1_trust(obs_a, obs_b, "Some completely unrelated raw text")
    assert breaker is False
    assert score == 0.50  # Capped at 0.50 (0.20 + 0.15 + 0.15)
    assert len(reasons) == 3


def test_pillar_2_clean_math():
    obs_a = {
        "line_items": [
            {"quantity": 2, "unit_price": 50.0, "total": 100.0},
            {"quantity": 1, "unit_price": 200.0, "total": 200.0},
        ],
        "subtotal": 300.0,
        "tax_amount": 30.0,
        "total_amount": 330.0,
        "invoice_date": "2024-01-15",
        "due_date": "2024-02-15",
    }
    score, breaker, reasons = evaluate_pillar_2_math(obs_a, is_sql_duplicate=False)
    assert score == 0.0
    assert breaker is False
    assert len(reasons) == 0


def test_pillar_2_sql_duplicate_breaker():
    obs_a = {
        "line_items": [{"quantity": 1, "unit_price": 100.0}],
        "subtotal": 100.0,
        "tax_amount": 0.0,
        "total_amount": 100.0,
    }
    score, breaker, reasons = evaluate_pillar_2_math(obs_a, is_sql_duplicate=True)
    assert breaker is True
    assert any("Duplicate Invoice #" in r for r in reasons)


def test_pillar_2_arithmetic_mismatches():
    obs_a = {
        "line_items": [{"quantity": 1, "unit_price": 100.0}],
        "subtotal": 150.0,  # mismatch (+0.25)
        "tax_amount": 10.0,
        "total_amount": 200.0,  # 150 + 10 != 200 (+0.25)
        "invoice_date": "2024-02-01",
        "due_date": "2024-01-01",  # due < invoice (+0.15)
    }
    score, breaker, reasons = evaluate_pillar_2_math(obs_a, is_sql_duplicate=False)
    assert breaker is False
    assert score == 0.50  # Capped at 0.50
    assert len(reasons) == 3


def test_pillar_2_high_value_cap():
    obs_a = {
        "line_items": [{"quantity": 10, "unit_price": 2000.0}],
        "subtotal": 20000.0,
        "tax_amount": 0.0,
        "total_amount": 20000.0,  # > $10,000 cap
    }
    score, breaker, reasons = evaluate_pillar_2_math(obs_a, is_sql_duplicate=False, payout_cap=10000.0)
    assert score == 0.25
    assert any("exceeds auto-approval cap" in r for r in reasons)


def test_decision_engine_routing_auto_approve():
    obs_a = {
        "vendor_name": "Stripe Payments",
        "invoice_number": "INV-500",
        "line_items": [{"quantity": 1, "unit_price": 500.0}],
        "subtotal": 500.0,
        "tax_amount": 0.0,
        "total_amount": 500.0,
        "invoice_date": "2024-01-01",
        "due_date": "2024-01-15",
    }
    obs_b = {
        "vendor_name": "Stripe Payments",
        "invoice_number": "INV-500",
        "total_amount": 500.0,
        "evidence_snippets": {
            "total_amount": "Total: 500.00",
        },
    }
    verifier_text = "Stripe Payments INV-500 Total: 500.00"
    decision = run_decision_engine(obs_a, obs_b, verifier_text, is_sql_duplicate=False)
    assert decision["status"] == "AUTO_APPROVE"
    assert decision["composite_risk_score"] < 0.20
    assert decision["hard_breaker_triggered"] is False


def test_decision_engine_routing_human_review():
    # Valid extraction but exceeds payout cap (0.25 risk score)
    obs_a = {
        "vendor_name": "Cloud Infra Inc",
        "invoice_number": "INV-9999",
        "line_items": [{"quantity": 1, "unit_price": 15000.0}],
        "subtotal": 15000.0,
        "tax_amount": 0.0,
        "total_amount": 15000.0,
    }
    obs_b = {
        "vendor_name": "Cloud Infra Inc",
        "invoice_number": "INV-9999",
        "total_amount": 15000.0,
        "evidence_snippets": {"total_amount": "Total: 15000.00"},
    }
    verifier_text = "Cloud Infra Inc INV-9999 Total: 15000.00"
    decision = run_decision_engine(obs_a, obs_b, verifier_text, is_sql_duplicate=False, payout_cap=10000.0)
    assert decision["status"] == "HUMAN_REVIEW"
    assert 0.20 <= decision["composite_risk_score"] < 0.60


def test_decision_engine_routing_auto_reject():
    # Breaker triggered: SQL duplicate
    obs_a = {"total_amount": 50.0}
    decision = run_decision_engine(obs_a, None, "", is_sql_duplicate=True)
    assert decision["status"] == "AUTO_REJECT"
    assert decision["hard_breaker_triggered"] is True
