import pytest
from tools.risk_calculator import calculate_composite_risk


def test_hard_gate_duplicate():
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 500.0},
        is_duplicate=True,
    )
    assert res["risk_score"] == 1.0
    assert res["decision"] == "reject"
    assert res["is_hard_gate"] is True


def test_hard_gate_tampering():
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 500.0},
        tampering_detected=True,
    )
    assert res["risk_score"] == 1.0
    assert res["decision"] == "reject"
    assert res["is_hard_gate"] is True


def test_hard_gate_dual_reader_mismatch():
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 500.0},
        verification_level="none",
    )
    assert res["risk_score"] == 1.0
    assert res["decision"] == "reject"
    assert res["is_hard_gate"] is True


def test_clean_invoice_auto_approve():
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 500.0},
        verification_level="full",
        validation_results=[{"passed": True, "severity": "error"}],
        anomalies=[],
        confidence=0.98,
    )
    assert res["risk_score"] == 0.0
    assert res["decision"] == "auto_approve"
    assert res["breakdown"]["pillar_1_verification"] == 0.0
    assert res["breakdown"]["pillar_2_compliance"] == 0.0
    assert res["breakdown"]["pillar_3_behavioral"] == 0.0


def test_warning_saturation_cap_pillar_2():
    # 6 minor warnings * 0.05 = 0.30, but warning cap is 0.15
    many_warnings = [{"passed": False, "severity": "warning", "rule_name": f"rule_{i}"} for i in range(6)]
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 1000.0},
        verification_level="full",
        validation_results=many_warnings,
        anomalies=[],
        confidence=0.95,
    )
    assert res["breakdown"]["pillar_2_compliance"] == 0.15
    assert res["risk_score"] == 0.15
    assert res["decision"] == "auto_approve"  # < 0.25, full verification, low amount


def test_pillar_2_max_ceiling():
    # 2 errors (0.40) + 4 warnings (0.20) -> strictly capped at 0.35 ceiling
    rules = [
        {"passed": False, "severity": "error", "rule_name": "approved_vendor"},
        {"passed": False, "severity": "error", "rule_name": "max_amount"},
        {"passed": False, "severity": "warning", "rule_name": "line_item_math"},
    ]
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Unknown", "total_amount": 1000.0},
        verification_level="full",
        validation_results=rules,
        anomalies=[],
    )
    assert res["breakdown"]["pillar_2_compliance"] == 0.35


def test_pillar_3_max_ceiling():
    # Near duplicate (0.30) + extreme outlier (0.40) -> strictly capped at 0.40 ceiling
    anomalies = [
        {"type": "statistical_outlier", "severity": "error", "score": 0.90, "message": "z-score 4.5"},
    ]
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 50000.0},
        verification_level="full",
        validation_results=[],
        anomalies=anomalies,
        is_near_duplicate=True,
    )
    assert res["breakdown"]["pillar_3_behavioral"] == 0.40


def test_auto_approve_invariant_blocked_on_partial_verification():
    # Clean invoice, but verification is partial:
    # pillar_1 = 0.15. Score = 0.15 (< 0.25).
    # But Auto-Approve Invariant MUST flag for human review because level != full!
    res = calculate_composite_risk(
        extraction_data={"vendor_name": "Acme", "total_amount": 500.0},
        verification_level="partial",
        validation_results=[],
        anomalies=[],
        confidence=0.95,
    )
    assert res["risk_score"] == 0.15
    assert res["decision"] == "flag_review"
    assert "auto-approval blocked" in res["reason"].lower()
