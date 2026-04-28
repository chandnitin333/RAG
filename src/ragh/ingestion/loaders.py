"""Document loaders. Returns extracted plain text for any supported file type.

Heavy parser libs (pdfplumber, PyMuPDF, pytesseract, python-docx, Pillow) are
lazy-imported inside the loader functions so `is_supported()` and module
imports stay cheap.

PDF strategy: pdfplumber → PyMuPDF → OCR (per-page rasterize + tesseract).
"""
from pathlib import Path
import io
import tempfile
from loguru import logger

from ragh.config import settings


SUPPORTED_TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log"}
SUPPORTED_PDF_EXT = {".pdf"}
SUPPORTED_DOCX_EXT = {".docx", ".doc"}
SUPPORTED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


def is_supported(path: Path) -> bool:
    ext = path.suffix.lower()
    return (
        ext in SUPPORTED_TEXT_EXT
        or ext in SUPPORTED_PDF_EXT
        or ext in SUPPORTED_DOCX_EXT
        or ext in SUPPORTED_IMAGE_EXT
    )


# --------------------------- file-path loaders ---------------------------

def load_pdf(path: Path) -> str:
    import pdfplumber
    text_pages = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_pages.append(page_text)
    except Exception as e:
        logger.warning("pdfplumber failed on {}: {}", path, e)

    joined = "\n\n".join(text_pages).strip()
    if joined:
        return joined

    # fallback 1: PyMuPDF
    try:
        import fitz
        text_pages = []
        with fitz.open(str(path)) as doc:
            for page in doc:
                text_pages.append(page.get_text("text") or "")
        joined = "\n\n".join(text_pages).strip()
        if joined:
            return joined
    except Exception as e:
        logger.warning("PyMuPDF failed on {}: {}", path, e)

    # fallback 2: OCR (scanned PDF)
    if settings.OCR_FALLBACK:
        try:
            return _ocr_pdf(path)
        except Exception as e:
            logger.warning("OCR failed on {}: {}", path, e)

    return ""


def _ocr_pdf(path: Path) -> str:
    import fitz
    from PIL import Image
    import pytesseract
    pages_text = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages_text.append(pytesseract.image_to_string(img))
    return "\n\n".join(pages_text).strip()


def load_docx(path: Path) -> str:
    import docx
    doc = docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_image(path: Path) -> str:
    from PIL import Image
    import pytesseract
    img = Image.open(str(path))
    return pytesseract.image_to_string(img)


def load_any(path: Path) -> str:
    """Dispatch by extension. Returns "" if unsupported or empty."""
    ext = path.suffix.lower()
    try:
        if ext in SUPPORTED_PDF_EXT:
            return load_pdf(path)
        if ext in SUPPORTED_DOCX_EXT:
            return load_docx(path)
        if ext in SUPPORTED_TEXT_EXT:
            return load_text(path)
        if ext in SUPPORTED_IMAGE_EXT:
            return load_image(path)
    except Exception as e:
        logger.exception("load_any failed for {}: {}", path, e)
    return ""


# --------------------------- bytes loaders (for /upload) ---------------------------

def extract_text_from_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in SUPPORTED_PDF_EXT:
        return _extract_pdf_bytes(data)
    if ext in SUPPORTED_DOCX_EXT:
        return _extract_docx_bytes(data)
    if ext in SUPPORTED_TEXT_EXT:
        return data.decode("utf-8", errors="ignore")
    if ext in SUPPORTED_IMAGE_EXT:
        return _extract_image_bytes(data)
    return data.decode("utf-8", errors="ignore")


def _extract_pdf_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return load_pdf(Path(tmp.name))


def _extract_docx_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return load_docx(Path(tmp.name))


def _extract_image_bytes(data: bytes) -> str:
    from PIL import Image
    import pytesseract
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img)
