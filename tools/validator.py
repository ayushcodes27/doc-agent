from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import List, Dict, Any, Union, Optional
from api.models import ExtractedInvoice


@dataclass
class ValidationResult:
    passed: bool
    rule_name: str
    message: str
    severity: str  # "error" | "warning" | "info"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT_APPROVED_VENDORS = [
    # Indian IT & Consulting
    "Acme Tech Solutions Pvt Ltd",
    "Infosys Limited",
    "Tata Consultancy Services",
    "Wipro Technologies",
    "HCL Technologies",
    "Tech Mahindra",
    # Cloud & SaaS Providers
    "Amazon Web Services",
    "Google Cloud Platform",
    "Microsoft Azure",
    "Salesforce Inc",
    "Atlassian Pty Ltd",
    # Hardware & Office Supplies
    "Dell Technologies",
    "Lenovo India Pvt Ltd",
    "HP Inc",
    "Logitech",
    "Office Depot",
    # Professional Services
    "Deloitte Touche Tohmatsu",
    "Ernst & Young LLP",
    "KPMG Advisory Services",
    # Logistics & Facilities
    "Blue Dart Express Ltd",
    "FedEx India",
    "Sodexo India Services",
]

DEFAULT_COMPLIANCE_RULES = [
    {
        "name": "max_amount",
        "description": "Invoice amount must not exceed department budget limit",
        "threshold": 500000.0,
        "severity": "error",
    },
    {
        "name": "approved_vendor",
        "description": "Vendor must be in the approved vendor list",
        "severity": "error",
    },
    {
        "name": "date_validity",
        "description": "Invoice date must be valid and not in the future",
        "severity": "error",
    },
    {
        "name": "line_item_math",
        "description": "Line item totals must sum to subtotal (±1% tolerance)",
        "severity": "warning",
    },
    {
        "name": "total_math",
        "description": "Subtotal + Tax Amount must equal Total Amount (±1% tolerance)",
        "severity": "warning",
    },
    {
        "name": "visual_text_consistency",
        "description": "Embedded scanned image amount must match digital line-item total",
        "severity": "error",
    },
    {
        "name": "vendor_id_present",
        "description": "Vendor must provide a valid tax/registration ID (GSTIN, VAT, etc.)",
        "severity": "warning",
    },
    {
        "name": "payment_terms_check",
        "description": "Invoice must specify payment terms",
        "severity": "info",
    },
    {
        "name": "currency_consistency",
        "description": "Currency must be a recognized ISO 4217 code",
        "severity": "warning",
    },
]


def _get_field(data: Union[ExtractedInvoice, Dict[str, Any]], field: str, default: Any = None) -> Any:
    if isinstance(data, ExtractedInvoice):
        return getattr(data, field, default)
    return data.get(field, default)


def validate_invoice(
    invoice: Union[ExtractedInvoice, Dict[str, Any]],
    rules: Optional[List[Dict[str, Any]]] = None,
    approved_vendors: Optional[List[str]] = None,
) -> List[ValidationResult]:
    """Run compliance rules against an extracted invoice."""
    rules_to_run = rules if rules is not None else DEFAULT_COMPLIANCE_RULES
    vendor_list = approved_vendors if approved_vendors is not None else DEFAULT_APPROVED_VENDORS
    
    results: List[ValidationResult] = []

    vendor_name = _get_field(invoice, "vendor_name", "")
    total_amount = float(_get_field(invoice, "total_amount", 0.0) or 0.0)
    subtotal = float(_get_field(invoice, "subtotal", 0.0) or 0.0)
    tax_amount = float(_get_field(invoice, "tax_amount", 0.0) or 0.0)
    invoice_date_val = _get_field(invoice, "invoice_date")
    line_items = _get_field(invoice, "line_items", [])

    for rule in rules_to_run:
        rule_name = rule["name"]
        severity = rule.get("severity", "error")

        if rule_name == "max_amount":
            threshold = float(rule.get("threshold", 500000.0))
            passed = total_amount <= threshold
            results.append(
                ValidationResult(
                    passed=passed,
                    rule_name=rule_name,
                    message=(
                        f"Invoice amount ({total_amount:,.2f}) is within limit ({threshold:,.2f})"
                        if passed
                        else f"Invoice amount ({total_amount:,.2f}) exceeds limit ({threshold:,.2f})"
                    ),
                    severity=severity,
                )
            )

        elif rule_name == "approved_vendor":
            # Match case-insensitively or exact match
            v_name_clean = str(vendor_name).strip().lower()
            approved_clean = [v.strip().lower() for v in vendor_list]
            passed = any(v in v_name_clean or v_name_clean in v for v in approved_clean)
            results.append(
                ValidationResult(
                    passed=passed,
                    rule_name=rule_name,
                    message=(
                        f"Vendor '{vendor_name}' is in approved list."
                        if passed
                        else f"Vendor '{vendor_name}' is NOT in the approved vendor list."
                    ),
                    severity=severity,
                )
            )

        elif rule_name == "date_validity":
            today = date.today()
            parsed_date = None
            if isinstance(invoice_date_val, date):
                parsed_date = invoice_date_val
            elif isinstance(invoice_date_val, str) and invoice_date_val:
                try:
                    parsed_date = datetime.strptime(invoice_date_val, "%Y-%m-%d").date()
                except ValueError:
                    parsed_date = None

            if parsed_date is None:
                results.append(
                    ValidationResult(
                        passed=False,
                        rule_name=rule_name,
                        message=f"Invalid or unparseable invoice date: '{invoice_date_val}'.",
                        severity=severity,
                    )
                )
            else:
                passed = parsed_date <= today
                results.append(
                    ValidationResult(
                        passed=passed,
                        rule_name=rule_name,
                        message=(
                            f"Invoice date {parsed_date} is valid."
                            if passed
                            else f"Invoice date {parsed_date} is in the future (today is {today})."
                        ),
                        severity=severity,
                    )
                )

        elif rule_name == "line_item_math":
            line_sum = 0.0
            for item in line_items:
                if isinstance(item, dict):
                    line_sum += float(item.get("total", 0.0) or 0.0)
                else:
                    line_sum += float(getattr(item, "total", 0.0) or 0.0)

            tolerance = max(abs(subtotal) * 0.01, 1.0)
            passed = abs(line_sum - subtotal) <= tolerance
            results.append(
                ValidationResult(
                    passed=passed,
                    rule_name=rule_name,
                    message=(
                        f"Line items sum ({line_sum:,.2f}) matches subtotal ({subtotal:,.2f})."
                        if passed
                        else f"Line items sum ({line_sum:,.2f}) does not match subtotal ({subtotal:,.2f})."
                    ),
                    severity=severity,
                )
            )

        elif rule_name == "total_math":
            expected_total = subtotal + tax_amount
            tolerance = max(abs(total_amount) * 0.01, 1.0)
            passed = abs(expected_total - total_amount) <= tolerance
            results.append(
                ValidationResult(
                    passed=passed,
                    rule_name=rule_name,
                    message=(
                        f"Subtotal ({subtotal:,.2f}) + Tax ({tax_amount:,.2f}) matches Total ({total_amount:,.2f})."
                        if passed
                        else f"Subtotal ({subtotal:,.2f}) + Tax ({tax_amount:,.2f}) = {expected_total:,.2f}, which does not match Total ({total_amount:,.2f})."
                    ),
                    severity=severity,
                )
            )

        elif rule_name == "visual_text_consistency":
            visual_amount = _get_field(invoice, "visual_amount")
            discrepancy_detected = bool(_get_field(invoice, "visual_discrepancy_detected", False))
            visual_notes = _get_field(invoice, "visual_notes", "")

            has_conflict = False
            diff = 0.0
            if visual_amount is not None:
                try:
                    v_val = float(visual_amount)
                    diff = abs(v_val - total_amount)
                    tolerance = max(abs(total_amount) * 0.01, 1.0)
                    if diff > tolerance:
                        has_conflict = True
                except (ValueError, TypeError):
                    pass

            if has_conflict:
                v_formatted = f"{float(visual_amount):,.2f}"
                note_suffix = f" Details: {visual_notes}" if visual_notes else ""
                results.append(
                    ValidationResult(
                        passed=False,
                        rule_name=rule_name,
                        message=(
                            f"CRITICAL DISCREPANCY: Scanned copy amount ({v_formatted}) conflicts with "
                            f"digital line-item total ({total_amount:,.2f}) — difference of {diff:,.2f}.{note_suffix}"
                        ),
                        severity=severity,
                    )
                )
            elif discrepancy_detected:
                results.append(
                    ValidationResult(
                        passed=False,
                        rule_name=rule_name,
                        message=f"CRITICAL DISCREPANCY: Discrepancy detected between embedded scanned copy and digital text. {visual_notes or ''}".strip(),
                        severity=severity,
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        passed=True,
                        rule_name=rule_name,
                        message="Visual scan amount is consistent with digital text line items.",
                        severity=severity,
                    )
                )

        elif rule_name == "vendor_id_present":
            vendor_id = _get_field(invoice, "vendor_id")
            has_id = bool(vendor_id and str(vendor_id).strip())
            results.append(
                ValidationResult(
                    passed=has_id,
                    rule_name=rule_name,
                    message=(
                        f"Vendor ID/GSTIN present: '{vendor_id}'."
                        if has_id
                        else "Vendor did not provide a tax/registration ID (GSTIN, VAT, etc.)."
                    ),
                    severity=severity,
                )
            )

        elif rule_name == "payment_terms_check":
            payment_terms = _get_field(invoice, "payment_terms")
            has_terms = bool(payment_terms and str(payment_terms).strip())
            results.append(
                ValidationResult(
                    passed=has_terms,
                    rule_name=rule_name,
                    message=(
                        f"Payment terms specified: '{payment_terms}'."
                        if has_terms
                        else "No payment terms specified on this invoice."
                    ),
                    severity=severity,
                )
            )

        elif rule_name == "currency_consistency":
            currency = str(_get_field(invoice, "currency", "") or "").strip().upper()
            valid_currencies = {
                "INR", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "SGD", "AED", "CHF",
            }
            is_valid = currency in valid_currencies
            results.append(
                ValidationResult(
                    passed=is_valid,
                    rule_name=rule_name,
                    message=(
                        f"Currency '{currency}' is a recognized ISO 4217 code."
                        if is_valid
                        else f"Currency '{currency}' is not in the recognized currency list."
                    ),
                    severity=severity,
                )
            )

    return results
