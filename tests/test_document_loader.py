import os
import pytest
from tools.document_loader import load_document


def test_load_document_from_text_file(tmp_path):
    file_path = tmp_path / "test_invoice.txt"
    sample_text = "INVOICE #123\nVendor: Test Corp\nTotal: 500.00"
    file_path.write_text(sample_text, encoding="utf-8")

    loaded_text = load_document(str(file_path))
    assert "INVOICE #123" in loaded_text
    assert "Test Corp" in loaded_text


def test_load_document_from_bytes():
    raw_bytes = b"INVOICE #456\nVendor: Byte Corp\nTotal: 1200.00"
    loaded_text = load_document(raw_bytes, filename="invoice.txt")
    assert "INVOICE #456" in loaded_text
    assert "Byte Corp" in loaded_text


def test_load_document_direct_string():
    raw_text = "INVOICE #789\nVendor: String Corp"
    loaded_text = load_document(raw_text)
    assert "String Corp" in loaded_text
