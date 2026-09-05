from datetime import date
from api.models import ExtractedInvoice, LineItem, InvoiceStatus, ApprovalLevel


def test_line_item_creation():
    item = LineItem(
        description="Cloud Computing Server",
        quantity=2.0,
        unit_price=5000.0,
        total=10000.0
    )
    assert item.description == "Cloud Computing Server"
    assert item.quantity == 2.0
    assert item.unit_price == 5000.0
    assert item.total == 10000.0


def test_extracted_invoice_validation():
    invoice = ExtractedInvoice(
        vendor_name="Acme Tech",
        invoice_number="INV-001",
        invoice_date=date(2026, 8, 15),
        subtotal=1000.0,
        tax_amount=180.0,
        total_amount=1180.0,
        currency="INR",
        line_items=[
            LineItem(description="Item A", quantity=1.0, unit_price=1000.0, total=1000.0)
        ],
        confidence_score=0.98
    )
    assert invoice.vendor_name == "Acme Tech"
    assert invoice.currency == "INR"
    assert invoice.total_amount == 1180.0
    assert len(invoice.line_items) == 1
    assert invoice.confidence_score == 0.98


def test_currency_symbol_normalization():
    invoice = ExtractedInvoice(
        vendor_name="Global Vendor",
        invoice_number="INV-002",
        invoice_date=date(2026, 8, 15),
        subtotal=500.0,
        total_amount=500.0,
        currency="$",
    )
    assert invoice.currency == "USD"
