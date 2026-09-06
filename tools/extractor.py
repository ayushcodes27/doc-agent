import json
import logging
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from config import settings
from api.models import ExtractedInvoice

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT_TEMPLATE = """You are an expert financial document intelligence system.
Extract all invoice metadata, monetary amounts, and line items from the provided document into a structured JSON object.

DOCUMENT CONTENT:
\"\"\"
{document_text}
\"\"\"

Extraction Instructions & Rules:
1. Extract exact values from the document.
2. Return ONLY a valid, parseable JSON object matching this schema:
{{
    "vendor_name": "string (name of supplier/company issuing invoice)",
    "vendor_id": "string or null (tax ID, GSTIN, VAT, or registration number if present)",
    "invoice_number": "string (unique identifier or invoice ID)",
    "invoice_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD or null",
    "currency": "INR/USD/EUR/GBP (ISO 3-letter currency code)",
    "subtotal": 0.00,
    "tax_amount": 0.00,
    "total_amount": 0.00,
    "line_items": [
        {{
            "description": "string",
            "quantity": 1.0,
            "unit_price": 0.00,
            "total": 0.00
        }}
    ],
    "payment_terms": "string or null (e.g. Net 30, Due on receipt)",
    "confidence_score": 0.95
}}

Important Guidelines:
- If date is in DD/MM/YYYY or text format, convert it to ISO "YYYY-MM-DD".
- Ensure subtotal, tax_amount, and total_amount are numeric floats.
- If a value is missing or unreadable, estimate confidence_score lower (e.g., 0.5 - 0.7).
- Verify: subtotal + tax_amount ≈ total_amount.
- Verify: each line item quantity × unit_price ≈ item total.
- Return ONLY the raw JSON object, without markdown explanations or preamble.
"""


def get_genai_client_and_model(api_key: Optional[str] = None, model_name: Optional[str] = None):
    """Configure and return the Gemini Client and model name."""
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not configured. Please set it in your .env file or environment."
        )
    client = genai.Client(api_key=key)
    model = model_name or settings.GEMINI_MODEL
    return client, model


def extract_invoice_data(
    document_text: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> ExtractedInvoice:
    """
    Extract structured invoice data from raw document text using Gemini.
    Returns a validated ExtractedInvoice Pydantic model.
    """
    if not document_text or not document_text.strip():
        raise ValueError("Document text is empty. Cannot perform extraction.")

    client, model = get_genai_client_and_model(api_key=api_key, model_name=model_name)
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(document_text=document_text)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        )
        
        response_text = response.text.strip()
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()

        data = json.loads(response_text)
        
        # Parse and validate with Pydantic
        extracted = ExtractedInvoice(**data)
        return extracted

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        raise ValueError(f"LLM returned invalid JSON output: {str(e)}")
    except Exception as e:
        logger.error(f"Error during invoice extraction: {e}")
        raise
