from datetime import date, timedelta
from api.models import ExtractedInvoice, LineItem
from tools.validator import validate_invoice, ValidationResult


def test_validate_invoice_all_passed():
    invoice = ExtractedInvoice(
        vendor_name="Acme Tech Solutions Pvt Ltd",
        vendor_id="27AABCU9603R1ZM",
        invoice_number="INV-2026-001",
        invoice_date=date.today(),
        subtotal=1000.0,
        tax_amount=180.0,
        total_amount=1180.0,
        payment_terms="Net 30",
        line_items=[
            LineItem(description="Item 1", quantity=1.0, unit_price=1000.0, total=1000.0)
        ],
    )
    results = validate_invoice(invoice)
    assert len(results) == 9
    assert all(r.passed for r in results)


def test_validate_invoice_exceeds_max_amount():
    invoice = ExtractedInvoice(
        vendor_name="Acme Tech Solutions Pvt Ltd",
        invoice_number="INV-2026-002",
        invoice_date=date.today(),
        subtotal=600000.0,
        tax_amount=0.0,
        total_amount=600000.0,
        line_items=[
            LineItem(description="Big Enterprise Purchase", quantity=1.0, unit_price=600000.0, total=600000.0)
        ],
    )
    results = validate_invoice(invoice)
    max_amount_result = next(r for r in results if r.rule_name == "max_amount")
    assert not max_amount_result.passed
    assert "exceeds limit" in max_amount_result.message


def test_validate_invoice_unapproved_vendor():
    invoice = ExtractedInvoice(
        vendor_name="Unapproved Shell Company LLC",
        invoice_number="INV-999",
        invoice_date=date.today(),
        subtotal=500.0,
        tax_amount=0.0,
        total_amount=500.0,
    )
    results = validate_invoice(invoice)
    vendor_result = next(r for r in results if r.rule_name == "approved_vendor")
    assert not vendor_result.passed
    assert "NOT in the approved vendor list" in vendor_result.message


def test_validate_invoice_future_date():
    future_date = date.today() + timedelta(days=10)
    invoice = ExtractedInvoice(
        vendor_name="Infosys Limited",
        invoice_number="INV-2026-003",
        invoice_date=future_date,
        subtotal=500.0,
        total_amount=500.0,
    )
    results = validate_invoice(invoice)
    date_result = next(r for r in results if r.rule_name == "date_validity")
    assert not date_result.passed
    assert "is in the future" in date_result.message


def test_validate_invoice_line_item_math_mismatch():
    invoice = ExtractedInvoice(
        vendor_name="Dell Technologies",
        invoice_number="INV-2026-004",
        invoice_date=date.today(),
        subtotal=5000.0,
        total_amount=5000.0,
        line_items=[
            LineItem(description="Monitor", quantity=1.0, unit_price=2000.0, total=2000.0)
        ],
    )
    results = validate_invoice(invoice)
    math_result = next(r for r in results if r.rule_name == "line_item_math")
    assert not math_result.passed


def test_validate_invoice_dict_input():
    invoice_dict = {
        "vendor_name": "Logitech",
        "invoice_number": "LOGI-881",
        "invoice_date": str(date.today()),
        "currency": "INR",
        "subtotal": 100.0,
        "tax_amount": 18.0,
        "total_amount": 118.0,
        "line_items": [
            {"description": "Mouse", "quantity": 1, "unit_price": 100.0, "total": 100.0}
        ]
    }
    invoice_dict["vendor_id"] = "LOGI-TAX-991"
    invoice_dict["payment_terms"] = "Due on receipt"
    results = validate_invoice(invoice_dict)
    assert len(results) == 9
    assert all(r.passed for r in results)


def test_validate_invoice_visual_discrepancy():
    invoice = ExtractedInvoice(
        vendor_name="Acme Tech Solutions Pvt Ltd",
        invoice_number="INV-2026-DISC",
        invoice_date=date.today(),
        subtotal=38400.0,
        tax_amount=6912.0,
        total_amount=45312.0,
        visual_amount=42480.0,  # Deliberate conflict from scanned image
        visual_discrepancy_detected=True,
        visual_notes="Scanned copy shows 42,480.00 while line items calculate to 45,312.00",
    )
    results = validate_invoice(invoice)
    disc_result = next(r for r in results if r.rule_name == "visual_text_consistency")
    assert not disc_result.passed
    assert disc_result.severity == "error"
    assert "42,480.00" in disc_result.message
    assert "45,312.00" in disc_result.message
