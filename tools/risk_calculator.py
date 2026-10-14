"""
DocAgent Bounded Composite Risk Scoring Engine
=============================================
Combines Hard Gates (Circuit Breakers), Warning Saturation Caps,
and 3 Independent Mathematically Bounded Risk Dimensions (Pillars):
  - Hard Gates: Evaluated first. If triggered, calculation stops instantly and routes to Auto-Reject.
  - Pillar 1: Data Trust & Verification Risk (Max Ceiling: 0.25)
  - Pillar 2: Policy & Compliance Risk (Max Ceiling: 0.35, with a 0.15 Warning Saturation Cap)
  - Pillar 3: Behavioral & Spend Anomaly Risk (Max Ceiling: 0.40)
"""

from typing import Dict, Any, List, Optional, Tuple


def calculate_composite_risk(
    extraction_data: Optional[Dict[str, Any]] = None,
    verification_level: str = "full",
    validation_results: Optional[List[Dict[str, Any]]] = None,
    anomalies: Optional[List[Dict[str, Any]]] = None,
    is_duplicate: bool = False,
    is_near_duplicate: bool = False,
    tampering_detected: bool = False,
    confidence: float = 1.0,
    human_verified: bool = False,
) -> Dict[str, Any]:
    """
    Computes a mathematically bounded composite risk score [0.00, 1.00]
    with Hard Gate circuit breakers, warning saturation caps, and 3 independent pillars.
    """
    extraction_data = extraction_data or {}
    validation_results = validation_results or []
    anomalies = anomalies or []

    v_level = (verification_level or "full").lower()
    total_amount = float(extraction_data.get("total_amount", 0.0) or 0.0)
    visual_tampering = any(
        a.get("type") == "visual_text_mismatch" for a in anomalies
    ) or tampering_detected

    # ==========================================
    # STEP 1: HARD GATES (Instant Circuit Breakers)
    # ==========================================
    if not extraction_data:
        return {
            "risk_score": 1.00,
            "decision": "reject",
            "approval_level": "auto",
            "reason": "Rejection: No data was extracted from the document.",
            "is_hard_gate": True,
            "breakdown": {
                "pillar_1_verification": 0.25,
                "pillar_2_compliance": 0.35,
                "pillar_3_behavioral": 0.40,
            },
        }

    if is_duplicate:
        return {
            "risk_score": 1.00,
            "decision": "reject",
            "approval_level": "auto",
            "reason": "Duplicate invoice detected with matching vendor, invoice number, and total amount.",
            "is_hard_gate": True,
            "breakdown": {
                "pillar_1_verification": 0.25,
                "pillar_2_compliance": 0.35,
                "pillar_3_behavioral": 0.40,
            },
        }

    if visual_tampering:
        return {
            "risk_score": 1.00,
            "decision": "reject",
            "approval_level": "auto",
            "reason": "Rejection: Critical document tampering alert detected.",
            "is_hard_gate": True,
            "breakdown": {
                "pillar_1_verification": 0.25,
                "pillar_2_compliance": 0.35,
                "pillar_3_behavioral": 0.40,
            },
        }

    if v_level == "none":
        return {
            "risk_score": 1.00,
            "decision": "reject",
            "approval_level": "auto",
            "reason": "Rejection: Dual-reader total amount mismatch (Verification Level: NONE).",
            "is_hard_gate": True,
            "breakdown": {
                "pillar_1_verification": 0.25,
                "pillar_2_compliance": 0.35,
                "pillar_3_behavioral": 0.40,
            },
        }

    error_rules = [
        r for r in validation_results
        if not r.get("passed", True) and (r.get("severity") or "").lower() == "error"
    ]

    # Multiple critical compliance errors (e.g. unapproved vendor + budget breach + future date)
    if len(error_rules) >= 3:
        return {
            "risk_score": 1.00,
            "decision": "reject",
            "approval_level": "auto",
            "reason": f"Rejection: Multiple critical compliance policy violations ({len(error_rules)} errors).",
            "is_hard_gate": True,
            "breakdown": {
                "pillar_1_verification": 0.25,
                "pillar_2_compliance": 0.35,
                "pillar_3_behavioral": 0.40,
            },
        }

    # ==========================================
    # STEP 2: PILLAR 1 - DATA TRUST & VERIFICATION (Max: 0.25)
    # ==========================================
    pillar_1 = 0.00

    # Reader agreement penalty
    if v_level == "partial":
        pillar_1 += 0.15

    # Extraction confidence penalty
    if confidence < 0.70:
        pillar_1 += 0.10

    pillar_1 = min(0.25, round(pillar_1, 2))

    # ==========================================
    # STEP 3: PILLAR 2 - POLICY & COMPLIANCE (Max: 0.35)
    # ==========================================
    pillar_2 = 0.00
    warning_penalty_sum = 0.00

    for rule in validation_results:
        if not rule.get("passed", True):
            sev = (rule.get("severity") or "error").lower()
            if sev == "error":
                pillar_2 += 0.25  # Hard policy violation (e.g. unapproved vendor, future date)
            elif sev == "warning":
                warning_penalty_sum += 0.05  # Minor math or format warning

    # Apply Warning Saturation Cap: Warnings can never add more than 0.15 total
    capped_warnings = min(0.15, round(warning_penalty_sum, 2))
    pillar_2 += capped_warnings
    pillar_2 = min(0.35, round(pillar_2, 2))

    # ==========================================
    # STEP 4: PILLAR 3 - BEHAVIORAL & SPEND ANOMALIES (Max: 0.40)
    # ==========================================
    pillar_3 = 0.00

    if is_near_duplicate:
        pillar_3 += 0.30

    # Inspect all anomaly flags
    for anomaly in anomalies:
        a_type = anomaly.get("type", "")
        msg = anomaly.get("message", "").lower()
        score = float(anomaly.get("score", 0.25))

        if a_type == "near_duplicate" and not is_near_duplicate:
            pillar_3 = max(pillar_3, 0.30)
        elif a_type == "statistical_outlier" or "z-score" in msg:
            if anomaly.get("severity") == "error" or score >= 0.70:
                pillar_3 = max(pillar_3, 0.40)  # Extreme statistical outlier (> 4.0 sigma)
            else:
                pillar_3 = max(pillar_3, 0.25)  # Moderate statistical outlier (> 2.5 sigma)
        elif a_type == "amount_spike":
            pillar_3 = max(pillar_3, 0.25)
        elif a_type == "round_number":
            pillar_3 = max(pillar_3, 0.25)
        elif a_type == "threshold_avoidance":
            pillar_3 = max(pillar_3, 0.25)
        elif a_type == "new_vendor_high_amount":
            pillar_3 = max(pillar_3, 0.25)
        elif a_type == "high_tax_ratio":
            pillar_3 = max(pillar_3, 0.25)
        else:
            pillar_3 = max(pillar_3, min(max(score, 0.25), 0.40))

    pillar_3 = min(0.40, round(pillar_3, 2))

    # ==========================================
    # STEP 5: FINAL COMPOSITE SCORE & ROUTING
    # ==========================================
    final_risk_score = round(pillar_1 + pillar_2 + pillar_3, 2)
    final_risk_score = min(1.00, max(0.00, final_risk_score))

    # Decision & Approval Level Determination
    if final_risk_score >= 0.70:
        decision = "reject"
        level = "auto"
        reason = f"High risk score ({final_risk_score:.2f}) exceeds rejection threshold (0.70)."
    elif is_near_duplicate:
        decision = "flag_review"
        level = "manager"
        reason = "Near-duplicate invoice detected; requires human verification before payment."
    elif total_amount > 200000.0 or final_risk_score >= 0.60:
        decision = "flag_review"
        level = "director"
        reason = f"Elevated risk score ({final_risk_score:.2f}) or high total amount (${total_amount:,.2f}) requires Director review."
    elif total_amount > 100000.0 or final_risk_score >= 0.25:
        decision = "flag_review"
        level = "manager"
        reason = f"Moderate risk score ({final_risk_score:.2f}) or total amount (${total_amount:,.2f}) exceeds auto-approve threshold."
    elif v_level != "full" and not human_verified:
        # Enforce Auto-Approve Invariant: Can never auto-approve without full verification
        decision = "flag_review"
        level = "manager"
        reason = f"Low risk score ({final_risk_score:.2f}), but auto-approval blocked because verification level is '{v_level}'. Requires human confirmation."
    else:
        decision = "auto_approve"
        level = "auto"
        reason = f"Low risk score ({final_risk_score:.2f}), full verification confirmed, and total amount within limits."

    return {
        "risk_score": final_risk_score,
        "decision": decision,
        "approval_level": level,
        "reason": reason,
        "is_hard_gate": False,
        "breakdown": {
            "pillar_1_verification": pillar_1,
            "pillar_2_compliance": pillar_2,
            "pillar_3_behavioral": pillar_3,
        },
    }
