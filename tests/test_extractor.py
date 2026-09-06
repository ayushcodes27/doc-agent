import json
import pytest
from unittest.mock import MagicMock, patch
from tools.extractor import extract_invoice_data, get_genai_client_and_model
from api.models import ExtractedInvoice


SAMPLE_GEMINI_RESPONSE = json.dumps({
    "vendor_name": "Acme Tech Solutions Pvt Ltd",
    "vendor_id": "29AABCU9603R1ZM",
    "invoice_number": "INV-2026-0891",
    "invoice_date": "2026-08-15",
    "due_date": "2026-09-14",
    "currency": "INR",
    "subtotal": 140000.00,
    "tax_amount": 25200.00,
    "total_amount": 165200.00,
    "line_items": [
        {
            "description": "Dell UltraSharp 27\" 4K Monitor",
            "quantity": 2.0,
            "unit_price": 35000.00,
            "total": 70000.00
        },
        {
            "description": "Logitech MX Master 3S Wireless Mouse",
            "quantity": 5.0,
            "unit_price": 8000.00,
            "total": 40000.00
        },
        {
            "description": "Ergonomic Mechanical Keyboard",
            "quantity": 3.0,
            "unit_price": 10000.00,
            "total": 30000.00
        }
    ],
    "payment_terms": "Net 30 Days",
    "confidence_score": 0.98
})


def test_extract_invoice_data_empty_input():
    with pytest.raises(ValueError, match="Document text and bytes are empty"):
        extract_invoice_data("")


def test_extract_invoice_data_missing_api_key():
    with patch("tools.extractor.settings.GEMINI_API_KEY", ""):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
            extract_invoice_data("Sample invoice text", api_key="")


@patch("tools.extractor.get_genai_client_and_model")
def test_extract_invoice_data_success(mock_get_client_model):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = f"```json\n{SAMPLE_GEMINI_RESPONSE}\n```"
    mock_client.models.generate_content.return_value = mock_response
    mock_get_client_model.return_value = (mock_client, "gemini-1.5-pro")

    result = extract_invoice_data(
        "Dummy text content of invoice",
        api_key="fake-test-key"
    )

    assert isinstance(result, ExtractedInvoice)
    assert result.vendor_name == "Acme Tech Solutions Pvt Ltd"
    assert result.invoice_number == "INV-2026-0891"
    assert result.total_amount == 165200.00
    assert len(result.line_items) == 3
    assert result.confidence_score == 0.98
