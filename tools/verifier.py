"""
DocAgent Hybrid Dual-Reader Verifier
===================================
Independent text-only verifier comparison and snippet grounding logic.
Compares Primary Reader A (multimodal) against Verifier Reader B (text-only)
and verifies evidence snippets exist in the raw document text.
"""

import re
import difflib
from typing import Dict, Any, Optional, List, Tuple


def _normalize_string(val: Optional[str]) -> str:
    """Normalize string for robust entity comparison."""
    if not val:
        return ""
    # Strip whitespace, lower case, remove punctuation
    clean = re.sub(r"[^\w\s]", "", str(val).lower()).strip()
    # Normalize common business suffixes
    clean = re.sub(r"\b(inc|corp|corporation|ltd|limited|pvt|llc|gmbh|co)\b", "", clean).strip()
    return re.sub(r"\s+", " ", clean)


def _normalize_identifier(val: Optional[str]) -> str:
    """Normalize invoice numbers or tax IDs (alphanumeric only, uppercase)."""
    if not val:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(val).upper())


def check_snippet_grounding(
    target_value: Any,
    snippet: Optional[str],
    raw_text: str,
) -> bool:
    """
    Verifies that the extracted snippet or numeric value actually exists
    verbatim in the raw OCR/digital text layer of the document.
    """
    if not raw_text:
        return False

    raw_lower = raw_text.lower()

    # 1. Check snippet string if provided
    if snippet and snippet.strip():
        snippet_clean = snippet.strip().lower()
        if snippet_clean in raw_lower:
            return True
        # Check normalized whitespace
        snip_norm = re.sub(r"\s+", " ", snippet_clean)
        raw_norm = re.sub(r"\s+", " ", raw_lower)
        if snip_norm in raw_norm:
            return True

    # 2. Check numeric value presence in raw text
    if isinstance(target_value, (int, float)):
        val_float = float(target_value)
        if val_float <= 0:
            return True
        patterns = [
            f"{val_float:,.2f}".lower(),
            f"{val_float:,.0f}".lower(),
            f"{val_float:.2f}".lower(),
            str(int(val_float)),
        ]
        # European format e.g. 1.234,56
        patterns.append(f"{val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        for pat in patterns:
            if pat in raw_lower or pat.replace(",", "") in raw_lower:
                return True

    # 3. Check string target
    if isinstance(target_value, str) and target_value.strip():
        target_norm = _normalize_string(target_value)
        if target_norm and target_norm in _normalize_string(raw_text):
            return True

    return False


def compare_and_verify(
    reader_a: Dict[str, Any],
    reader_b: Optional[Dict[str, Any]] = None,
    raw_text: str = "",
) -> Dict[str, Any]:
    """
    Core verification algorithm comparing Reader A and Reader B.
    Computes field agreement, checks evidence snippets in raw text,
    and assigns verification_level: 'full', 'partial', or 'none'.
    """
    if not reader_a:
        return {
            "verification_level": "none",
            "agreement_score": 0.0,
            "total_match": False,
            "vendor_match": False,
            "invoice_num_match": False,
            "snippets_grounded": False,
            "discrepancies": ["Reader A extracted no data."],
            "details": "Extraction failed: no primary reader data available.",
        }

    # Extract Reader A values
    total_a = float(reader_a.get("total_amount", 0.0) or 0.0)
    vendor_a = str(reader_a.get("vendor_name", "") or "").strip()
    inv_num_a = str(reader_a.get("invoice_number", "") or "").strip()
    snippets_a = reader_a.get("evidence_snippets", {}) or {}

    # Verify Reader A evidence in raw text
    total_grounded_a = check_snippet_grounding(total_a, snippets_a.get("total_amount"), raw_text)
    vendor_grounded_a = check_snippet_grounding(vendor_a, snippets_a.get("vendor_name"), raw_text)

    # When Reader B is not provided or unavailable
    if not reader_b:
        # In single-reader mode: cannot achieve 'full' without dual verification
        discrepancies = ["Reader B (verifier) not available for dual-reader confirmation."]
        # Grounding check
        snippets_grounded = total_grounded_a or vendor_grounded_a or bool(raw_text.strip() and total_a > 0)
        level = "partial" if (total_a > 0 and vendor_a) else "none"

        return {
            "verification_level": level,
            "agreement_score": 0.5 if level == "partial" else 0.0,
            "total_match": False,
            "vendor_match": False,
            "invoice_num_match": False,
            "snippets_grounded": snippets_grounded,
            "discrepancies": discrepancies,
            "details": f"Single reader only ({level}). Auto-approval requires full dual-reader verification.",
        }

    # Extract Reader B values
    total_b = float(reader_b.get("total_amount", 0.0) or 0.0)
    vendor_b = str(reader_b.get("vendor_name", "") or "").strip()
    inv_num_b = str(reader_b.get("invoice_number", "") or "").strip()
    snippets_b = reader_b.get("evidence_snippets", {}) or {}

    discrepancies: List[str] = []

    # 1. Total Amount Agreement (strict $0.05 tolerance)
    diff_total = abs(total_a - total_b)
    total_match = diff_total <= 0.05
    if not total_match:
        discrepancies.append(
            f"Total amount mismatch: Reader A extracted {total_a:.2f}, Reader B extracted {total_b:.2f} (diff: {diff_total:.2f})."
        )

    # 2. Vendor Name Agreement (Normalized & fuzzy similarity >= 0.80)
    v_a_norm = _normalize_string(vendor_a)
    v_b_norm = _normalize_string(vendor_b)
    if v_a_norm == v_b_norm:
        vendor_match = True
    elif v_a_norm in v_b_norm or v_b_norm in v_a_norm:
        vendor_match = True
    else:
        sim = difflib.SequenceMatcher(None, v_a_norm, v_b_norm).ratio()
        vendor_match = sim >= 0.80
        if not vendor_match:
            discrepancies.append(
                f"Vendor name disagreement: Reader A='{vendor_a}', Reader B='{vendor_b}' (similarity: {sim:.2f})."
            )

    # 3. Invoice Number Agreement
    id_a = _normalize_identifier(inv_num_a)
    id_b = _normalize_identifier(inv_num_b)
    if id_a == id_b:
        inv_match = True
    elif len(id_a) >= 3 and len(id_b) >= 3 and (id_a in id_b or id_b in id_a):
        inv_match = True
    else:
        dist = sum(1 for a, b in zip(id_a, id_b) if a != b) + abs(len(id_a) - len(id_b))
        inv_match = dist <= 1
        if not inv_match:
            discrepancies.append(
                f"Invoice number discrepancy: Reader A='{inv_num_a}', Reader B='{inv_num_b}'."
            )

    # 4. Snippet Grounding in Raw Text
    total_grounded_b = check_snippet_grounding(total_b, snippets_b.get("total_amount"), raw_text)
    vendor_grounded_b = check_snippet_grounding(vendor_b, snippets_b.get("vendor_name"), raw_text)
    
    snippets_grounded = (total_grounded_a or total_grounded_b) and (vendor_grounded_a or vendor_grounded_b)
    if not snippets_grounded and raw_text.strip():
        discrepancies.append("Evidence snippets could not be fully grounded in document raw text.")

    # 5. Compute Agreement Score
    matches = sum([total_match, vendor_match, inv_match, snippets_grounded])
    agreement_score = round(matches / 4.0, 2)

    # 6. Assign Verification Level
    if total_match and vendor_match and (snippets_grounded or not raw_text.strip()):
        verification_level = "full"
        details = f"Full verification passed: Readers agree on total ({total_a:.2f}), vendor, and snippets grounded."
    elif total_match:
        verification_level = "partial"
        details = f"Partial verification: Total amounts agree ({total_a:.2f}), but minor field or grounding discrepancies."
    else:
        verification_level = "none"
        details = f"Verification failed: Major disagreement on total amount ({total_a:.2f} vs {total_b:.2f})."

    return {
        "verification_level": verification_level,
        "agreement_score": agreement_score,
        "total_match": total_match,
        "vendor_match": vendor_match,
        "invoice_num_match": inv_match,
        "snippets_grounded": snippets_grounded,
        "discrepancies": discrepancies,
        "details": details,
    }
