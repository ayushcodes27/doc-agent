import json
import logging
import time
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from config import settings
from api.models import ExtractedInvoice

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT_TEMPLATE = """You are an expert financial document intelligence system.
Extract all invoice metadata, monetary amounts, and line items from the provided document into a structured JSON object.

Extraction Instructions & Rules:
1. Extract exact values from the document.
2. Return ONLY a valid, parseable JSON object matching this schema:
{
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
        {
            "description": "string",
            "quantity": 1.0,
            "unit_price": 0.00,
            "total": 0.00
        }
    ],
    "payment_terms": "string or null (e.g. Net 30, Due on receipt)",
    "confidence_score": 0.95
}

Important Guidelines:
- If date is in DD/MM/YYYY or text format, convert it to ISO "YYYY-MM-DD".
- Ensure subtotal, tax_amount, and total_amount are numeric floats.
- If a value is missing or unreadable, estimate confidence_score lower (e.g., 0.5 - 0.7).
- Verify: subtotal + tax_amount ≈ total_amount.
- Verify: each line item quantity × unit_price ≈ item total.
- Return ONLY the raw JSON object, without markdown explanations or preamble.
"""


def _clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Helper to parse JSON from LLM output, stripping markdown formatting if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def extract_with_gemini(
    document_text: str = "",
    document_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> ExtractedInvoice:
    """Extract invoice data using Google Gemini API."""
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=key)
    model = model_name or settings.GEMINI_MODEL

    contents_to_send = []
    if document_bytes and mime_type:
        contents_to_send.append(types.Part.from_bytes(data=document_bytes, mime_type=mime_type))
    elif document_text:
        contents_to_send.append(f"DOCUMENT CONTENT:\n{document_text}")
    contents_to_send.append(EXTRACTION_PROMPT_TEMPLATE)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents_to_send,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )
            data = _clean_json_response(response.text)
            return ExtractedInvoice(**data)
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise


def extract_with_github_models(
    document_text: str = "",
    token: Optional[str] = None,
    model_name: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> ExtractedInvoice:
    """Extract invoice data using GitHub Models (Azure AI inference endpoint) via OpenAI SDK."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("The 'openai' package is required for GitHub Models. Please run: pip install openai")

    gh_token = token or settings.GITHUB_TOKEN
    if not gh_token:
        raise ValueError("GITHUB_TOKEN is not configured. Please add it to your .env file.")

    gh_endpoint = endpoint or settings.GITHUB_ENDPOINT
    gh_model = model_name or settings.GITHUB_MODEL

    client = OpenAI(
        base_url=gh_endpoint,
        api_key=gh_token,
        timeout=30.0,
    )

    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT_TEMPLATE},
        {"role": "user", "content": f"Please extract structured invoice data from the following document:\n\n{document_text}"}
    ]

    response = client.chat.completions.create(
        model=gh_model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content or "{}"
    data = _clean_json_response(content)
    return ExtractedInvoice(**data)


def extract_invoice_data(
    document_text: str = "",
    document_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> ExtractedInvoice:
    """
    Extract structured invoice data from raw document text or bytes.
    Supports provider selection ('gemini', 'github_models', 'auto') with automatic fallback.
    """
    if not document_text.strip() and not document_bytes:
        raise ValueError("Document text and bytes are empty. Cannot perform extraction.")

    selected_provider = (provider or settings.LLM_PROVIDER or "auto").lower()

    # If provider is explicitly GitHub Models
    if selected_provider in ["github_models", "github", "azure"]:
        return extract_with_github_models(
            document_text=document_text,
            token=api_key or settings.GITHUB_TOKEN,
            model_name=model_name or settings.GITHUB_MODEL
        )

    # If provider is explicitly Gemini
    if selected_provider == "gemini":
        return extract_with_gemini(
            document_text=document_text,
            document_bytes=document_bytes,
            mime_type=mime_type,
            api_key=api_key,
            model_name=model_name
        )

    # AUTO Mode: Try primary provider (Gemini if key set, else GitHub Models) with failover
    errors = []
    
    # 1. Try Gemini first if key exists
    if settings.GEMINI_API_KEY:
        try:
            return extract_with_gemini(
                document_text=document_text,
                document_bytes=document_bytes,
                mime_type=mime_type,
                api_key=api_key,
                model_name=model_name
            )
        except Exception as e:
            logger.warning(f"Gemini extraction failed ({e}), attempting fallback to GitHub Models...")
            errors.append(f"Gemini error: {e}")

    # 2. Try GitHub Models fallback
    if settings.GITHUB_TOKEN and document_text.strip():
        try:
            return extract_with_github_models(
                document_text=document_text,
                token=settings.GITHUB_TOKEN,
                model_name=settings.GITHUB_MODEL
            )
        except Exception as e:
            logger.warning(f"GitHub Models extraction failed: {e}")
            errors.append(f"GitHub Models error: {e}")

    # If both failed or none configured
    if errors:
        raise RuntimeError(f"All configured LLM providers failed: {'; '.join(errors)}")
    else:
        raise ValueError("No valid LLM credentials configured. Please set GEMINI_API_KEY or GITHUB_TOKEN in .env.")

