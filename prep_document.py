"""
DocAgent Ingestion & Document Preparation Engine (prep_document.py)
==================================================================
Handles PDF / Image ingestion, SHA-256 hash generation, and hybrid OCR fallback:
- Renders page images at 150 DPI for Observer A (Gemini Vision)
- Extracts raw digital text layer (passed to Observer A for digital-vs-visual tampering detection)
- Extracts verifier text with RapidOCR fallback when digital text < 50 chars (passed to Observer B so scanned PDFs never fail)
"""

import hashlib
from typing import Dict, Any, Optional
from tools.document_loader import (
    get_document_text,
    prepare_document_source,
    compute_file_hash,
    render_pdf_to_images,
    check_document_tampering,
    run_rapidocr,
)


def prep_document(
    source: Any,
    filename: str = "document.pdf",
    min_chars_per_page: int = 50,
) -> Dict[str, Any]:
    """
    Ingest document and prepare:
      1. file_hash: SHA-256 hash of raw file bytes for pre-LLM SQL Gate
      2. raw_digital_text / digital_layer_text: Native digital text for Observer A
      3. verifier_text: Text with RapidOCR fallback (< 50 chars) for Observer B
      4. page_images: 150 DPI rendered images for multimodal inspection
      5. tampering_detected: Concrete hidden/microscopic text tampering flag
    """
    return prepare_document_source(source=source, filename=filename)


def extract_raw_and_verifier_text(
    pdf_bytes: bytes,
    min_chars_per_page: int = 50,
) -> Dict[str, Any]:
    """
    Extract both raw digital text and verifier text (with RapidOCR fallback).
    """
    return get_document_text(pdf_bytes, min_chars_per_page=min_chars_per_page)


__all__ = [
    "prep_document",
    "extract_raw_and_verifier_text",
    "get_document_text",
    "prepare_document_source",
    "compute_file_hash",
    "render_pdf_to_images",
    "check_document_tampering",
    "run_rapidocr",
]
