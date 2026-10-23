"""
DocAgent Deterministic 2-Pillar Scoring & Routing Engine
========================================================
Combines:
  - Pillar 1: Extraction & Observer Trust (Max 0.50)
  - Pillar 2: Hard Math & SQL Deduplication (Max 0.50)
Produces bounded composite risk score in [0.00, 1.00] and deterministic routing:
  - Hard Breaker or R >= 0.60 -> AUTO_REJECT
  - 0.20 <= R < 0.60         -> HUMAN_REVIEW
  - R < 0.20                 -> AUTO_APPROVE
"""

import re
from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple, Optional


def normalize_str(s: str) -> str:
    """Lowercases and strips non-alphanumeric chars for clean comparison."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def normalize_whitespace(s: str) -> str:
    """Collapses multiple spaces/newlines into single spaces for snippet matching."""
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def evaluate_pillar_1_trust(
    obs_a: Dict[str, Any], 
    obs_b: Optional[Dict[str, Any]], 
    verifier_text: str
) -> Tuple[float, bool, List[str]]:
    """
    Pillar 1: Cross-examines Observer A (Gemini) and Observer B (GPT-4o-mini).
    Returns: (p1_score [max 0.50], hard_breaker_triggered, list_of_reasons)
    """
    score = 0.0
    reasons = []
    hard_breaker = False

    obs_a = obs_a or {}
    obs_b = obs_b or {}

    # 1. HARD BREAKER: Visual Tampering flagged by Observer A
    if obs_a.get("visual_discrepancy_detected") is True:
        hard_breaker = True
        reasons.append("CRITICAL: Visual vs. Digital layer tampering detected by Observer A.")

    # 2. HARD BREAKER: Total Amount Mismatch (> $0.05)
    total_a = float(obs_a.get("total_amount") or 0.0)
    total_b = float(obs_b.get("total_amount") or -999.0)
    if abs(total_a - total_b) > 0.05:
        hard_breaker = True
        reasons.append(f"CRITICAL: Observer total mismatch (A: {total_a:.2f} vs B: {total_b:.2f}).")

    # 3. SOFT CHECK: Vendor Name Similarity (< 80% -> +0.20)
    vendor_a = normalize_str(obs_a.get("vendor_name", ""))
    vendor_b = normalize_str(obs_b.get("vendor_name", ""))
    similarity = SequenceMatcher(None, vendor_a, vendor_b).ratio()
    if similarity < 0.80:
        score += 0.20
        reasons.append(f"P1 (+0.20): Vendor name low similarity ({similarity:.0%}).")

    # 4. SOFT CHECK: Invoice Number Match (Normalized mismatch -> +0.15)
    inv_a = normalize_str(obs_a.get("invoice_number", ""))
    inv_b = normalize_str(obs_b.get("invoice_number", ""))
    if inv_a != inv_b:
        score += 0.15
        reasons.append(f"P1 (+0.15): Invoice number discrepancy ('{inv_a}' vs '{inv_b}').")

    # 5. SOFT CHECK: Evidence Snippet Grounding (+0.15 if any snippet is hallucinated)
    norm_source_text = normalize_whitespace(verifier_text)
    snippets = obs_b.get("evidence_snippets") or {}
    missing_snippets = []
    for field, quote in snippets.items():
        if not quote or normalize_whitespace(quote) not in norm_source_text:
            missing_snippets.append(field)

    if missing_snippets or not snippets:
        score += 0.15
        reasons.append(f"P1 (+0.15): Unverified grounding snippets for {missing_snippets or ['all']}.")

    return min(round(score, 2), 0.50), hard_breaker, reasons


def evaluate_pillar_2_math(
    obs_a: Dict[str, Any], 
    is_sql_duplicate: bool,
    payout_cap: float = 10000.0
) -> Tuple[float, bool, List[str]]:
    """
    Pillar 2: Validates internal invoice arithmetic, SQL deduplication, dates, and caps.
    Returns: (p2_score [max 0.50], hard_breaker_triggered, list_of_reasons)
    """
    score = 0.0
    reasons = []
    hard_breaker = False

    obs_a = obs_a or {}

    # 1. HARD BREAKER: Semantic Duplicate in SQL DB (Same Vendor + Invoice #)
    if is_sql_duplicate:
        hard_breaker = True
        reasons.append("CRITICAL: Duplicate Invoice # for this vendor already exists in SQL DB.")

    # 2. MATH CHECK A: Sum of Line Items == Subtotal (+0.25)
    line_items = obs_a.get("line_items") or []
    subtotal = float(obs_a.get("subtotal") or 0.0)
    tax = float(obs_a.get("tax_amount") or 0.0)
    total = float(obs_a.get("total_amount") or 0.0)

    if line_items:
        calculated_subtotal = sum(
            float(item.get("quantity", 1)) * float(item.get("unit_price", 0.0))
            for item in line_items
        )
        if abs(calculated_subtotal - subtotal) > 0.05:
            score += 0.25
            reasons.append(
                f"P2 (+0.25): Line-item sum ({calculated_subtotal:.2f}) != Subtotal ({subtotal:.2f})."
            )
    else:
        score += 0.25
        reasons.append("P2 (+0.25): No line items extracted to verify math.")

    # 3. MATH CHECK B: Subtotal + Tax == Total (+0.25)
    if abs((subtotal + tax) - total) > 0.05:
        score += 0.25
        reasons.append(
            f"P2 (+0.25): Subtotal ({subtotal:.2f}) + Tax ({tax:.2f}) != Total ({total:.2f})."
        )

    # 4. COMPLIANCE CHECK A: Due Date >= Invoice Date (+0.15)
    inv_date = obs_a.get("invoice_date")  # Expected ISO format YYYY-MM-DD
    due_date = obs_a.get("due_date")
    if inv_date and due_date and str(due_date) < str(inv_date):
        score += 0.15
        reasons.append(f"P2 (+0.15): Due date ({due_date}) is earlier than invoice date ({inv_date}).")

    # 5. COMPLIANCE CHECK B: High-Value Payout Cap (+0.25 forces Human Review)
    currency = str(obs_a.get("currency") or "USD").upper()
    effective_cap = payout_cap * 10 if currency == "INR" else payout_cap
    if total > effective_cap:
        score += 0.25
        reasons.append(f"P2 (+0.25): Total ({total:.2f}) exceeds auto-approval cap ({effective_cap:.2f}).")

    return min(round(score, 2), 0.50), hard_breaker, reasons


def run_decision_engine(
    obs_a: Dict[str, Any], 
    obs_b: Optional[Dict[str, Any]], 
    verifier_text: str, 
    is_sql_duplicate: bool,
    payout_cap: float = 10000.0
) -> Dict[str, Any]:
    """Combines Pillar 1 & Pillar 2 into a final deterministic routing decision."""
    p1_score, p1_breaker, p1_reasons = evaluate_pillar_1_trust(obs_a, obs_b, verifier_text)
    p2_score, p2_breaker, p2_reasons = evaluate_pillar_2_math(obs_a, is_sql_duplicate, payout_cap=payout_cap)

    composite_score = round(p1_score + p2_score, 2)  # Naturally bounded in [0.00, 1.00]
    all_reasons = p1_reasons + p2_reasons

    if p1_breaker or p2_breaker or composite_score >= 0.60:
        status = "AUTO_REJECT"
    elif composite_score >= 0.20:
        status = "HUMAN_REVIEW"
    else:
        status = "AUTO_APPROVE"

    return {
        "status": status,
        "composite_risk_score": composite_score,
        "pillar_1_trust_score": p1_score,
        "pillar_2_math_score": p2_score,
        "hard_breaker_triggered": p1_breaker or p2_breaker,
        "audit_reasons": all_reasons
    }
