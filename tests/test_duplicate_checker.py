from datetime import date
from api.models import ExtractedInvoice
from tools.duplicate_checker import (
    generate_fingerprint,
    check_duplicate,
    register_invoice_fingerprint,
    _in_memory_cache,
)


def setup_function():
    _in_memory_cache.clear()


def test_generate_fingerprint_deterministic():
    inv1 = ExtractedInvoice(
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date=date.today(),
        subtotal=1000.0,
        total_amount=1000.0,
    )
    inv2 = ExtractedInvoice(
        vendor_name="  acme corp ",
        invoice_number="inv-001",
        invoice_date=date.today(),
        subtotal=1000.0,
        total_amount=1000.0,
    )
    assert generate_fingerprint(inv1) == generate_fingerprint(inv2)


def test_check_duplicate_new_invoice():
    inv = ExtractedInvoice(
        vendor_name="Logitech",
        invoice_number="LOGI-100",
        invoice_date=date.today(),
        subtotal=250.0,
        total_amount=250.0,
    )
    res = check_duplicate(inv, record_if_new=True)
    assert res["is_duplicate"] is False
    assert "fingerprint" in res

    # Subsequent check should return duplicate=True
    res_second = check_duplicate(inv)
    assert res_second["is_duplicate"] is True
    assert res_second["original_id"] == "LOGI-100"


def test_register_invoice_fingerprint():
    inv = ExtractedInvoice(
        vendor_name="Dell",
        invoice_number="DELL-900",
        invoice_date=date.today(),
        subtotal=3000.0,
        total_amount=3000.0,
    )
    fp = register_invoice_fingerprint(inv)
    assert len(fp) == 64

    res = check_duplicate(inv)
    assert res["is_duplicate"] is True
