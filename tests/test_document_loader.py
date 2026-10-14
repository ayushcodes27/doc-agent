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


def test_get_document_text_digital_pdf():
    import pymupdf as fitz
    from tools.document_loader import get_document_text

    doc = fitz.open()
    page = doc.new_page()
    text = "Enterprise Digital Invoice #INV-2024-999\nVendor: Cloud Hosting Services LLC\nTotal: $1,250.00"
    page.insert_text((50, 50), text)
    pdf_bytes = doc.tobytes()
    doc.close()

    result = get_document_text(pdf_bytes, min_chars_per_page=50)
    assert "Cloud Hosting Services" in result["digital_layer_text"]
    assert "Cloud Hosting Services" in result["verifier_text"]
    assert result["used_ocr_fallback"] is False


def test_get_document_text_scanned_pdf_triggers_rapidocr():
    import pymupdf as fitz
    from tools.document_loader import get_document_text

    # Create a PDF where text is drawn into a pixmap/image, simulating a flat scan
    temp_doc = fitz.open()
    temp_page = temp_doc.new_page()
    temp_page.insert_text((50, 50), "ACME SCANNED INVOICE 9988\nTotal: 450.00", fontsize=14)
    pix = temp_page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    temp_doc.close()

    # Now create the actual scanned PDF containing ONLY the image, no digital text
    scan_doc = fitz.open()
    scan_page = scan_doc.new_page()
    scan_page.insert_image(scan_page.rect, stream=img_bytes)
    scan_bytes = scan_doc.tobytes()
    scan_doc.close()

    result = get_document_text(scan_bytes, min_chars_per_page=50)
    # Digital text layer is empty because it's a flat image scan
    assert len(result["digital_layer_text"]) < 50
    # OCR fallback was used
    assert result["used_ocr_fallback"] is True
    # RapidOCR extracted the text from the image
    assert "ACME" in result["verifier_text"].upper() or "9988" in result["verifier_text"]
