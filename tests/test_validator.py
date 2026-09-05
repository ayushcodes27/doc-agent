from datetime import date, timedelta
from api.models import ExtractedInvoice, LineItem
from tools.validator import validate_invoice, ValidationResult


def test_validate_invoice_all_passed():
    invoice = ExtractedInvoice(
        vendor_name="Acme Tech Solutions Pvt Ltd",
        invoice_number="INV-2026-001",
        invoice_date=date.today(),
        subtotal=1000.0,
        tax_amount=180.0,
        total_amount=1180.0,
        line_items=[
            LineItem(description="Item 1", quantity=1.0, unit_price=1000.0, total=1000.0)
        ],
    )
    results = validate_invoice(invoice)
    assert len(results) == 5
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
        vendor_name="Acme Corp",
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
        vendor_name="Dell",
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
        "subtotal": 100.0,
        "tax_amount": 18.0,
        "total_amount": 118.0,
        "line_items": [
            {"description": "Mouse", "quantity": 1, "unit_price": 100.0, "total": 100.0}
        ]
    }
    results = validate_invoice(invoice_dict)
    assert len(results) == 5
    assert all(r.passed for r in results)
