import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from api.models import ExtractedInvoice
from tools.extractor import extract_invoice_data
from tools.validator import validate_invoice, ValidationResult
from tools.duplicate_checker import check_duplicate
from tools.anomaly_detector import detect_anomalies as run_anomaly_detection
from config import settings

logger = logging.getLogger(__name__)


def _log_audit(audit_trail: List[Dict[str, Any]], step_name: str, detail: str) -> None:
    """Helper to append structured log entry to the audit trail list."""
    audit_trail.append({
        "step": step_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detail": detail,
    })


def extract_data(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Extract structured data from document text using LLM extractor tool."""
    audit_trail = list(state.get("audit_trail", []))
    doc_text = state.get("document_text", "")
    doc_bytes = state.get("document_bytes")
    mime_type = state.get("mime_type")

    if not doc_text.strip() and not doc_bytes:
        _log_audit(audit_trail, "extraction", "Failed: Empty document text and no bytes provided.")
        return {
            "extracted_data": None,
            "extraction_confidence": 0.0,
            "audit_trail": audit_trail,
        }

    try:
        extracted: ExtractedInvoice = extract_invoice_data(
            document_text=doc_text,
            document_bytes=doc_bytes,
            mime_type=mime_type
        )
        # Convert ExtractedInvoice Pydantic model to dict safely serializable to JSON
        extracted_dict = json.loads(extracted.model_dump_json())
        confidence = float(extracted.confidence_score)

        _log_audit(
            audit_trail,
            "extraction",
            f"Successfully extracted invoice #{extracted.invoice_number} from '{extracted.vendor_name}' "
            f"({len(extracted.line_items)} line items, confidence={confidence:.2f})"
        )
        return {
            "extracted_data": extracted_dict,
            "extraction_confidence": confidence,
            "audit_trail": audit_trail,
        }
    except Exception as exc:
        logger.warning(f"LLM extraction node exception: {exc}")
        _log_audit(audit_trail, "extraction", f"Extraction error/fallback: {str(exc)}")
        return {
            "extracted_data": state.get("extracted_data"),
            "extraction_confidence": state.get("extraction_confidence", 0.0),
            "audit_trail": audit_trail,
        }


def validate_compliance(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Run business compliance rules against extracted invoice data."""
    audit_trail = list(state.get("audit_trail", []))
    extracted_data = state.get("extracted_data")

    if not extracted_data:
        _log_audit(audit_trail, "validation", "Skipped: Missing extracted invoice data.")
        return {
            "validation_results": [],
            "audit_trail": audit_trail,
        }

    results: List[ValidationResult] = validate_invoice(extracted_data)
    results_serialized = [r.to_dict() for r in results]
    failed_count = sum(1 for r in results if not r.passed)

    _log_audit(
        audit_trail,
        "validation",
        f"Evaluated {len(results)} compliance rules ({failed_count} failed)."
    )

    return {
        "validation_results": results_serialized,
        "audit_trail": audit_trail,
    }


def check_duplicates(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Perform duplicate invoice detection via fingerprinting."""
    audit_trail = list(state.get("audit_trail", []))
    extracted_data = state.get("extracted_data")

    if not extracted_data:
        _log_audit(audit_trail, "dedup", "Skipped: Missing extracted invoice data.")
        return {
            "is_duplicate": False,
            "audit_trail": audit_trail,
        }

    dup_res = check_duplicate(extracted_data, record_if_new=True)
    is_dup = bool(dup_res.get("is_duplicate", False))
    original_id = dup_res.get("original_id")

    detail_msg = f"Duplicate detected! Original ID: {original_id}" if is_dup else "No duplicate found. Registered fingerprint."
    _log_audit(audit_trail, "dedup", detail_msg)

    return {
        "is_duplicate": is_dup,
        "audit_trail": audit_trail,
    }


def detect_anomalies(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Run anomaly detection checks against historical patterns and rules."""
    audit_trail = list(state.get("audit_trail", []))
    extracted_data = state.get("extracted_data")

    if not extracted_data:
        _log_audit(audit_trail, "anomaly_detection", "Skipped: Missing extracted invoice data.")
        return {
            "anomalies": [],
            "audit_trail": audit_trail,
        }

    anomalies = run_anomaly_detection(extracted_data)
    _log_audit(
        audit_trail,
        "anomaly_detection",
        f"Detected {len(anomalies)} statistical/pattern anomalies."
    )

    return {
        "anomalies": anomalies,
        "audit_trail": audit_trail,
    }


def calculate_risk(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Calculate aggregate risk score (0.0 to 1.0) based on all findings."""
    audit_trail = list(state.get("audit_trail", []))
    validation_results = state.get("validation_results", [])
    anomalies = state.get("anomalies", [])
    is_duplicate = state.get("is_duplicate", False)
    confidence = float(state.get("extraction_confidence", 1.0))

    score = 0.0

    if is_duplicate:
        score = 1.0
    else:
        # Failed validations impact
        for val in validation_results:
            if not val.get("passed", True):
                sev = val.get("severity", "error")
                if sev == "error":
                    score += 0.25
                elif sev == "warning":
                    score += 0.10

        # Anomalies impact
        if anomalies:
            max_anomaly = max((float(a.get("score", 0.3)) for a in anomalies), default=0.0)
            score += max_anomaly

        # Extraction confidence penalty
        if confidence < 0.70:
            score += 0.30

    final_score = min(max(round(score, 2), 0.0), 1.0)

    _log_audit(audit_trail, "risk_scoring", f"Calculated aggregate risk score: {final_score:.2f}")

    return {
        "risk_score": final_score,
        "audit_trail": audit_trail,
    }


def make_decision(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Determine automated decision (auto_approve, flag_review, reject) and level."""
    audit_trail = list(state.get("audit_trail", []))
    risk_score = float(state.get("risk_score", 0.0))
    is_duplicate = state.get("is_duplicate", False)
    extracted_data = state.get("extracted_data") or {}
    total_amount = float(extracted_data.get("total_amount", 0.0) or 0.0)

    if not extracted_data:
        decision = "reject"
        level = "auto"
        reason = "Rejection: No data was extracted from the document."
    elif is_duplicate:
        decision = "reject"
        level = "auto"
        reason = "Duplicate invoice detected with matching vendor, invoice number, and total amount."
    elif risk_score >= 0.70:
        decision = "reject"
        level = "auto"
        reason = f"High risk score ({risk_score:.2f}) exceeds rejection threshold (0.70)."
    elif risk_score >= 0.40:
        decision = "flag_review"
        level = "director" if (total_amount > 200000.0 or risk_score >= 0.60) else "manager"
        reason = f"Moderate risk score ({risk_score:.2f}) requires human review by {level.title()}."
    elif total_amount > 200000.0:
        decision = "flag_review"
        level = "director"
        reason = f"Invoice total amount ({total_amount:,.2f}) exceeds director review threshold (200,000)."
    elif total_amount > 100000.0:
        decision = "flag_review"
        level = "manager"
        reason = f"Invoice total amount ({total_amount:,.2f}) exceeds manager auto-approve threshold (100,000)."
    else:
        decision = "auto_approve"
        level = "auto"
        reason = f"Low risk score ({risk_score:.2f}) and total amount within limits."

    _log_audit(
        audit_trail,
        "decision",
        f"Decision: {decision.upper()} | Level: {level.upper()} | {reason}"
    )

    return {
        "decision": decision,
        "approval_level": level,
        "decision_reasoning": reason,
        "audit_trail": audit_trail,
    }


def generate_report(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node: Generate a structured Markdown report summarizing the invoice outcome."""
    audit_trail = list(state.get("audit_trail", []))
    extracted = state.get("extracted_data") or {}
    validations = state.get("validation_results", [])
    anomalies = state.get("anomalies", [])
    decision = state.get("decision", "unknown")
    risk_score = state.get("risk_score", 0.0)
    reasoning = state.get("decision_reasoning", "")
    level = state.get("approval_level", "auto")

    # Format structured report markdown
    vendor = extracted.get("vendor_name", "N/A")
    inv_num = extracted.get("invoice_number", "N/A")
    inv_date = extracted.get("invoice_date", "N/A")
    amount = extracted.get("total_amount", 0.0)
    currency = extracted.get("currency", "INR")

    decision_banner = {
        "auto_approve": "✅ **AUTO-APPROVED**",
        "flag_review": "⚠️ **FLAGGED FOR HUMAN REVIEW**",
        "reject": "❌ **REJECTED**",
    }.get(decision, "ℹ️ **PROCESSING COMPLETE**")

    validation_summary = "\n".join([
        f"- {'✓' if v.get('passed') else '✗'} **{v.get('rule_name')}**: {v.get('message')}"
        for v in validations
    ]) if validations else "- No compliance checks recorded."

    anomaly_summary = "\n".join([
        f"- ⚠️ **[{a.get('type')}]**: {a.get('message')} (Severity: {a.get('severity', 'warning')})"
        for a in anomalies
    ]) if anomalies else "- No anomalies detected."

    report_content = f"""### 🧾 DocAgent Invoice Processing Report

#### Status Overview
{decision_banner}
- **Assigned Approval Level:** `{level.upper()}`
- **Aggregate Risk Score:** `{risk_score:.0%}`
- **Decision Reasoning:** {reasoning}

---

#### 📄 Invoice Details
- **Vendor:** {vendor}
- **Invoice Number:** `{inv_num}`
- **Issue Date:** `{inv_date}`
- **Total Amount:** `{currency} {amount:,.2f}`

---

#### 🛡️ Compliance & Validation Results
{validation_summary}

---

#### 🔍 Fraud & Anomaly Audit
{anomaly_summary}

---
*Report automatically generated by DocAgent Orchestrator.*
"""

    _log_audit(audit_trail, "report_generated", "Executive processing report created.")

    return {
        "messages": [{"role": "assistant", "content": report_content}],
        "audit_trail": audit_trail,
    }
