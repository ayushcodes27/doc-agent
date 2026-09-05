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
    "Acme Tech Solutions Pvt Ltd",
    "Acme Corp",
    "Global Tech Supplies",
    "Cloud Services Inc",
    "Office Depot",
    "Logitech",
    "Dell",
    "Amazon Web Services",
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

    return results
