import os
from typing import Union, Optional
import fitz  # PyMuPDF


def extract_text_from_pdf(source: Union[str, bytes]) -> str:
    """Extract all text from a PDF file path or raw bytes using PyMuPDF."""
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


def load_document(source: Union[str, bytes], filename: Optional[str] = None) -> str:
    """Load and extract text from supported document types (PDF, TXT)."""
    if isinstance(source, bytes):
        if filename and filename.lower().endswith(".pdf"):
            return extract_text_from_pdf(source)
        try:
            return source.decode("utf-8")
        except UnicodeDecodeError:
            # Fallback to pdf stream reader if decode fails
            return extract_text_from_pdf(source)
            
    elif isinstance(source, str):
        if source.lower().endswith(".pdf"):
            return extract_text_from_pdf(source)
        if os.path.exists(source):
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        # If source is already raw text string
        return source

    raise ValueError("Unsupported document format or invalid source provided.")
