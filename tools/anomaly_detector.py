import statistics
from typing import List, Dict, Any, Union, Optional
from api.models import ExtractedInvoice


def _get_field(data: Union[ExtractedInvoice, Dict[str, Any]], field: str, default: Any = None) -> Any:
    if isinstance(data, ExtractedInvoice):
        return getattr(data, field, default)
    return data.get(field, default)


def detect_anomalies(
    invoice: Union[ExtractedInvoice, Dict[str, Any]],
    historical_data: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Flag statistical and heuristic anomalies by evaluating the invoice
    against historical invoice data and known anomaly patterns.
    """
    anomalies: List[Dict[str, Any]] = []
    history = historical_data or []

    vendor_name = str(_get_field(invoice, "vendor_name", "") or "").strip().lower()
    total_amount = float(_get_field(invoice, "total_amount", 0.0) or 0.0)
    subtotal = float(_get_field(invoice, "subtotal", 0.0) or 0.0)
    tax_amount = float(_get_field(invoice, "tax_amount", 0.0) or 0.0)

    # 1. Amount Spike Anomaly vs Historical Vendor Invoices
    if history and vendor_name:
        vendor_invoices = [
            h for h in history
            if str(h.get("vendor_name", "")).strip().lower() == vendor_name
        ]
        if vendor_invoices:
            hist_totals = [float(h.get("total_amount", 0.0) or 0.0) for h in vendor_invoices]
            avg_amount = sum(hist_totals) / len(hist_totals)
            
            if len(hist_totals) >= 3 and statistics.stdev(hist_totals) > 0:
                stdev = statistics.stdev(hist_totals)
                z_score = (total_amount - avg_amount) / stdev
                if z_score > 2.5:
                    anomalies.append({
                        "type": "statistical_outlier",
                        "message": f"Invoice total ({total_amount:,.2f}) is a statistical outlier (z-score: {z_score:.2f}) vs vendor history.",
                        "severity": "warning" if z_score < 4.0 else "error",
                        "score": min(round(z_score / 10.0, 2) + 0.3, 1.0),
                    })
            elif avg_amount > 0 and total_amount > avg_amount * 2.5:
                ratio = total_amount / avg_amount
                score = min(round((ratio - 1.0) / 4.0, 2), 1.0)
                anomalies.append({
                    "type": "amount_spike",
                    "message": (
                        f"Invoice total ({total_amount:,.2f}) is {ratio:.1f}x higher than "
                        f"historical vendor average ({avg_amount:,.2f})."
                    ),
                    "severity": "warning" if ratio < 5.0 else "error",
                    "score": score,
                })
        elif not vendor_invoices and total_amount > 50000.0:
            anomalies.append({
                "type": "new_vendor_high_amount",
                "message": f"First time seeing this vendor, and amount is unusually high ({total_amount:,.2f}).",
                "severity": "warning",
                "score": 0.5,
            })

    # 2. Suspicious Round Number Anomaly
    if total_amount >= 10000.0 and total_amount % 1000.0 == 0.0:
        anomalies.append({
            "type": "round_number",
            "message": f"Suspiciously round invoice total amount: {total_amount:,.2f}",
            "severity": "info",
            "score": 0.3,
        })

    # 3. High Tax Ratio Anomaly (> 30% of subtotal)
    if subtotal > 0:
        tax_ratio = tax_amount / subtotal
        if tax_ratio > 0.30:
            anomalies.append({
                "type": "high_tax_ratio",
                "message": f"High tax amount ({tax_amount:,.2f}) represents {tax_ratio * 100:.1f}% of subtotal ({subtotal:,.2f}).",
                "severity": "warning",
                "score": min(round(tax_ratio, 2), 1.0),
            })

    # 4. Threshold Avoidance (Structuring)
    for cap in [100000.0, 200000.0]:
        if cap * 0.98 <= total_amount < cap:
            anomalies.append({
                "type": "threshold_avoidance",
                "message": f"Amount ({total_amount:,.2f}) is suspiciously close to the {cap:,.2f} approval limit (structuring pattern).",
                "severity": "error",
                "score": 0.8,
            })

    return anomalies
