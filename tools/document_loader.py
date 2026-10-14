"""
DocAgent Document Loader & Visual Tampering Engine
==================================================
Handles digital PDFs, scanned documents, and image files.
Extracts raw text layer, renders page images, performs concrete visual
tampering inspection (invisible/microscopic text, covered overlays),
and computes document legibility metrics.
"""

import os
import re
import base64
import hashlib
import logging
from typing import Union, Optional, Dict, Any, List, Tuple
import pymupdf as fitz

logger = logging.getLogger(__name__)

# Global lazy-initialized RapidOCR singleton
_ocr_engine = None


def get_ocr_engine():
    """Returns singleton instance of RapidOCR, loading model into memory only once."""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except ImportError:
            try:
                from rapidocr import RapidOCR
                _ocr_engine = RapidOCR()
            except ImportError:
                logger.warning("RapidOCR not installed. Scanned page OCR fallback will be disabled.")
                _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None


def run_rapidocr(img_bytes: bytes) -> str:
    """Run RapidOCR on image bytes and return clean newline-delimited text."""
    engine = get_ocr_engine()
    if not engine:
        return ""
    try:
        result = engine(img_bytes)
        if isinstance(result, tuple):
            result = result[0]
        if not result:
            return ""
        if hasattr(result, "txts") and result.txts:
            return "\n".join(result.txts)
        if isinstance(result, list):
            lines = [item[1] for item in result if len(item) > 1 and item[1]]
            return "\n".join(lines)
    except Exception as e:
        logger.warning(f"RapidOCR execution failed: {e}")
    return ""


def get_document_text(pdf_bytes: bytes, min_chars_per_page: int = 50) -> Dict[str, Any]:
    """
    Extracts text for Reader A and Reader B.
    Returns both raw digital text (for tampering check) and complete text (for Reader B).
    Attempts fast digital text extraction first, and automatically triggers
    RapidOCR on any page that looks like a flat scan.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    raw_digital_text = []
    reader_b_text = []
    used_ocr = False

    try:
        for page in doc:
            # 1. Try extracting the native digital text layer
            digital_page_text = page.get_text("text").strip()
            raw_digital_text.append(digital_page_text)

            # 2. If the page has enough digital text, use it directly
            if len(digital_page_text) >= min_chars_per_page:
                reader_b_text.append(digital_page_text)
            else:
                # 3. OCR FALLBACK: Page is a scan/image! Render at 150 DPI and run RapidOCR
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                ocr_page_text = run_rapidocr(img_bytes)

                if ocr_page_text.strip():
                    used_ocr = True
                    reader_b_text.append(ocr_page_text.strip())
                elif digital_page_text:
                    reader_b_text.append(digital_page_text)
    finally:
        doc.close()

    return {
        "digital_layer_text": "\n".join(t for t in raw_digital_text if t).strip(),
        "verifier_text": "\n".join(t for t in reader_b_text if t).strip(),
        "used_ocr_fallback": used_ocr,
    }


def compute_file_hash(data: bytes) -> str:
    """Calculate deterministic SHA-256 hash of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def check_document_tampering(doc: fitz.Document) -> Tuple[bool, List[str]]:
    """
    Concrete visual mismatch & tampering check on digital PDFs.
    Detects:
      1. Invisible / White Text Injection (font color == #ffffff on white canvas)
      2. Microscopic Font Injection (font size < 3.0 pt hiding numbers or keywords)
      3. Covered Text Layers (text obscured by opaque vector drawings)
      4. Discrepant Annotation Overlays
    """
    reasons = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_dict = page.get_text("dict")
        drawings = page.get_drawings()
        
        # 1. Inspect text spans for hidden/microscopic text
        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    
                    font_size = float(span.get("size", 10.0))
                    color = int(span.get("color", 0))
                    bbox = fitz.Rect(span.get("bbox", (0, 0, 0, 0)))

                    # Check for microscopic text (< 3.0 pt)
                    if font_size < 3.0 and len(text) > 1:
                        reasons.append(
                            f"Microscopic text injection detected on page {page_num + 1}: "
                            f"'{text[:40]}' (size: {font_size:.1f}pt)"
                        )

                    # Check for white / invisible text (#ffffff == 16777215)
                    # Often used to inject invisible prompt injections or false totals
                    if color == 16777215 or color == 0xFFFFFF:
                        if re.search(r"[a-zA-Z0-9]", text):
                            reasons.append(
                                f"Invisible white text layer detected on page {page_num + 1}: "
                                f"'{text[:40]}' (color: #FFFFFF)"
                            )

                    # 2. Check for text hidden behind opaque vector drawings
                    for draw in drawings:
                        draw_rect = draw.get("rect")
                        fill_color = draw.get("fill")
                        # If drawing has solid fill and fully covers text bbox
                        if fill_color is not None and draw_rect and draw_rect.contains(bbox):
                            # If rect is not transparent
                            if draw.get("fill_opacity", 1.0) == 1.0:
                                reasons.append(
                                    f"Text layer covered by opaque vector overlay on page {page_num + 1}: "
                                    f"'{text[:30]}' covered by drawing"
                                )
                                break

        # 3. Inspect Form Annotations / Hidden Overlays
        annots = list(page.annots())
        for annot in annots:
            info = annot.info
            annot_text = (info.get("content") or "").strip()
            # If an annotation has opacity and covers key content
            if annot_text and ("total" in annot_text.lower() or "amount" in annot_text.lower()):
                reasons.append(
                    f"Suspicious annotation overlay modifying financial content on page {page_num + 1}: '{annot_text}'"
                )

    tampering_detected = len(reasons) > 0
    return tampering_detected, reasons


def compute_text_quality_score(raw_text: str, total_pages: int = 1) -> float:
    """
    Computes document legibility / text quality score (0.0 to 1.0)
    based on character readability, word density, and garbage ratio.
    """
    if not raw_text.strip():
        return 0.0

    total_chars = len(raw_text)
    if total_chars == 0:
        return 0.0

    # Count alphanumeric characters vs control / non-printable / garbage
    alnum_chars = sum(1 for c in raw_text if c.isalnum())
    alnum_ratio = alnum_chars / total_chars

    clean_chars = sum(1 for c in raw_text if c.isalnum() or c.isspace() or c in ",.-/()$€£₹:;")
    clean_ratio = clean_chars / total_chars

    # Word count and vocabulary density (words containing alphanumeric characters)
    words = [w for w in raw_text.split() if any(c.isalnum() for c in w)]
    avg_words_per_page = len(words) / max(total_pages, 1)

    # Plausibility: An enterprise invoice typically has 40 - 1500 words per page
    if avg_words_per_page < 15:
        density_factor = max(avg_words_per_page / 15.0, 0.0)
    elif avg_words_per_page > 1500:
        density_factor = 0.8
    else:
        density_factor = 1.0

    score = round(alnum_ratio * 0.4 + clean_ratio * 0.3 + density_factor * 0.3, 3)
    return min(max(score, 0.0), 1.0)


def extract_text_from_pdf(source: Union[str, bytes]) -> str:
    """Extract raw digital text layer from a PDF file path or raw bytes using PyMuPDF."""
    text_content = []
    
    if isinstance(source, bytes):
        doc = fitz.open(stream=source, filetype="pdf")
    elif isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"PDF file not found at path: {source}")
        doc = fitz.open(source)
    else:
        raise TypeError("Source must be a file path string or bytes.")

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")
            if page_text.strip():
                text_content.append(page_text.strip())
    finally:
        doc.close()
        
    return "\n\n".join(text_content)


def render_pdf_pages_to_base64(
    source: Union[str, bytes],
    max_pages: int = 5,
    dpi: int = 150
) -> List[str]:
    """Render PDF pages into Base64 PNG images for multimodal vision models."""
    base64_images = []
    if isinstance(source, bytes):
        doc = fitz.open(stream=source, filetype="pdf")
    else:
        doc = fitz.open(source)

    try:
        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            b64_str = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            base64_images.append(b64_str)
    finally:
        doc.close()

    return base64_images


def prepare_document_source(
    source: Union[str, bytes],
    filename: Optional[str] = "document.pdf",
    max_pages: int = 5,
) -> Dict[str, Any]:
    """
    Comprehensive document source preparation.
    Extracts digital text layer, renders page images, computes SHA-256 hash,
    performs concrete visual mismatch inspection, and measures text quality.
    """
    if isinstance(source, str) and os.path.exists(source):
        with open(source, "rb") as f:
            file_bytes = f.read()
        target_filename = os.path.basename(source)
    elif isinstance(source, bytes):
        file_bytes = source
        target_filename = filename or "document.pdf"
    else:
        # Raw text string passed directly
        text_bytes = source.encode("utf-8")
        return {
            "raw_text": source,
            "pages_count": 1,
            "page_images_base64": [],
            "file_bytes": text_bytes,
            "file_hash": compute_file_hash(text_bytes),
            "tampering_detected": False,
            "tampering_reasons": [],
            "text_quality_score": compute_text_quality_score(source, 1),
            "is_digital_pdf": False,
            "is_scanned": False,
        }

    file_hash = compute_file_hash(file_bytes)
    is_pdf = target_filename.lower().endswith(".pdf") or file_bytes.startswith(b"%PDF")

    if not is_pdf:
        # Non-PDF text or image handling
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = ""
        
        b64_img = [base64.b64encode(file_bytes).decode("utf-8")] if not raw_text else []
        verifier_text = raw_text
        used_ocr = False

        if not raw_text and b64_img:
            # Flattened image file (PNG/JPG/etc): run RapidOCR
            ocr_text = run_rapidocr(file_bytes)
            if ocr_text.strip():
                verifier_text = ocr_text.strip()
                used_ocr = True

        effective_text = verifier_text if verifier_text else raw_text
        return {
            "raw_text": raw_text,
            "digital_layer_text": raw_text,
            "verifier_text": verifier_text,
            "used_ocr_fallback": used_ocr,
            "pages_count": 1,
            "page_images_base64": b64_img,
            "file_bytes": file_bytes,
            "file_hash": file_hash,
            "tampering_detected": False,
            "tampering_reasons": [],
            "text_quality_score": compute_text_quality_score(effective_text, 1),
            "is_digital_pdf": False,
            "is_scanned": bool(b64_img),
        }

    # Process PDF document
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_count = len(doc)
    
    # 1. Inspect concrete tampering & visual mismatches on native digital layer
    tampering_detected, tampering_reasons = check_document_tampering(doc)

    # 2. Render page images for vision models
    page_images = []
    has_images = False
    for page_num in range(min(pages_count, max_pages)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        page_images.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
        if len(page.get_images()) > 0:
            has_images = True

    doc.close()

    # 3. Hybrid text extraction (digital layer first, RapidOCR on flat scanned pages)
    extracted_text_data = get_document_text(file_bytes)
    digital_text = extracted_text_data["digital_layer_text"]
    verifier_text = extracted_text_data["verifier_text"]
    used_ocr = extracted_text_data["used_ocr_fallback"]

    # Determine if primarily scanned or digital
    is_scanned = (len(digital_text.split()) < 30) and (has_images or used_ocr)
    is_digital_pdf = len(digital_text.split()) >= 30

    effective_text = verifier_text if verifier_text else digital_text
    text_quality = compute_text_quality_score(effective_text, pages_count)

    return {
        "raw_text": digital_text,
        "digital_layer_text": digital_text,
        "verifier_text": verifier_text,
        "used_ocr_fallback": used_ocr,
        "pages_count": pages_count,
        "page_images_base64": page_images,
        "file_bytes": file_bytes,
        "file_hash": file_hash,
        "tampering_detected": tampering_detected,
        "tampering_reasons": tampering_reasons,
        "text_quality_score": text_quality,
        "is_digital_pdf": is_digital_pdf,
        "is_scanned": is_scanned,
    }


def load_document(source: Union[str, bytes], filename: Optional[str] = None) -> str:
    """Convenience backwards-compatible loader returning document text (with OCR fallback for scans)."""
    prep = prepare_document_source(source, filename)
    return prep.get("verifier_text") or prep.get("raw_text", "")
