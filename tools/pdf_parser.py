import fitz  # PyMuPDF
import io

def pdf_to_text(pdf_bytes: bytes) -> str:
    """
    Extract text from a PDF file provided as bytes.
    """
    try:
        # Open the PDF from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        return text.strip()
    except Exception as e:
        raise ValueError(f"Failed to parse PDF document: {e}")
