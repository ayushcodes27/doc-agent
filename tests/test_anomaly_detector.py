from datetime import date
from api.models import ExtractedInvoice
from tools.anomaly_detector import detect_anomalies


def test_detect_anomalies_none_detected():
    invoice = ExtractedInvoice(
        vendor_name="Office Depot",
        invoice_number="INV-101",
        invoice_date=date.today(),
        subtotal=1250.0,
        tax_amount=150.0,
        total_amount=1400.0,
    )
    historical_data = [
        {"vendor_name": "Office Depot", "total_amount": 1300.0},
        {"vendor_name": "Office Depot", "total_amount": 1500.0},
    ]
    anomalies = detect_anomalies(invoice, historical_data)
    assert len(anomalies) == 0


def test_detect_anomalies_amount_spike():
    invoice = ExtractedInvoice(
        vendor_name="Cloud Services Inc",
        invoice_number="INV-500",
        invoice_date=date.today(),
        subtotal=40000.0,
        tax_amount=0.0,
        total_amount=40000.0,
    )
    historical_data = [
        {"vendor_name": "Cloud Services Inc", "total_amount": 5000.0},
        {"vendor_name": "Cloud Services Inc", "total_amount": 7000.0},
    ]
    anomalies = detect_anomalies(invoice, historical_data)
    spike_anomaly = next((a for a in anomalies if a["type"] == "amount_spike"), None)
    assert spike_anomaly is not None
    assert spike_anomaly["severity"] in ["warning", "error"]
    assert "historical vendor average" in spike_anomaly["message"]


def test_detect_anomalies_suspicious_round_number():
    invoice = ExtractedInvoice(
        vendor_name="Acme Corp",
        invoice_number="INV-777",
        invoice_date=date.today(),
        subtotal=50000.0,
        tax_amount=0.0,
        total_amount=50000.0,
    )
    anomalies = detect_anomalies(invoice)
    round_anomaly = next((a for a in anomalies if a["type"] == "round_number"), None)
    assert round_anomaly is not None
    assert round_anomaly["score"] == 0.3


def test_detect_anomalies_high_tax_ratio():
    invoice = ExtractedInvoice(
        vendor_name="Acme Corp",
        invoice_number="INV-888",
        invoice_date=date.today(),
        subtotal=1000.0,
        tax_amount=400.0,  # 40% tax ratio
        total_amount=1400.0,
    )
    anomalies = detect_anomalies(invoice)
    tax_anomaly = next((a for a in anomalies if a["type"] == "high_tax_ratio"), None)
    assert tax_anomaly is not None
    assert tax_anomaly["severity"] == "warning"
