"""
Text extraction pipeline.

Flow for a PDF:
1. Try direct text extraction with pdfplumber (fast, works for "born-digital" PDFs).
2. If the average extracted characters-per-page is below a threshold, treat the PDF
   as scanned/image-based and fall back to OCR: render each page to an image with
   PyMuPDF, then run Tesseract OCR on each image.
3. Clean the combined text and split it into paragraphs.

Flow for a DOCX:
1. Read paragraphs directly with python-docx (DOCX text is never "scanned", so no
   OCR path is needed).
2. Clean and split as above.

`extract_text` is the single entry point routes/services should call; it returns an
ExtractionResult with everything the Submission model needs to persist.
"""
import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
import numpy as np
from docx import Document
from PIL import Image, ImageFilter, ImageOps

# If a PDF page has fewer than this many extracted characters, we assume it's a
# scanned image and OCR it instead of trusting the (near-empty) text layer.
MIN_CHARS_PER_PAGE_BEFORE_OCR = 40

# Render scale for OCR: 2.5 ≈ 180 DPI provides crisp edges for handwritten text.
OCR_RENDER_ZOOM = 2.5


@dataclass
class ExtractionResult:
    text: str
    paragraphs: list[str] = field(default_factory=list)
    page_count: int | None = None
    word_count: int = 0
    was_ocr_used: bool = False
    error: str | None = None


def clean_text(raw_text: str) -> str:
    """Normalize whitespace and collapse repeated blank lines."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_repeated_lines(pages_text: list[str]) -> list[str]:
    """
    Detect lines that appear on almost every page (running headers/footers) and
    strip them, since they add noise to paragraph-level similarity comparisons.
    """
    if len(pages_text) < 3:
        return pages_text

    line_counts: dict[str, int] = {}
    for page in pages_text:
        seen_this_page = set(line.strip() for line in page.split("\n") if line.strip())
        for line in seen_this_page:
            line_counts[line] = line_counts.get(line, 0) + 1

    threshold = max(3, int(len(pages_text) * 0.8))
    repeated = {line for line, count in line_counts.items() if count >= threshold and len(line) < 120}

    cleaned_pages = []
    for page in pages_text:
        kept_lines = [line for line in page.split("\n") if line.strip() not in repeated]
        cleaned_pages.append("\n".join(kept_lines))
    return cleaned_pages


def split_into_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs on blank lines. For OCR output (e.g. handwritten
    assignments) where blank lines are rare, group consecutive lines into paragraphs
    so semantic embeddings can be generated.
    """
    raw_paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in raw_paragraphs if len(p.strip()) > 1]

    # If the text has no double-newline paragraphs but contains multiple lines of text:
    if len(paragraphs) <= 1 and text.strip():
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 1]
        if len(lines) > 3:
            chunk_size = 3
            grouped = [" ".join(lines[i : i + chunk_size]) for i in range(0, len(lines), chunk_size)]
            paragraphs = [g for g in grouped if len(g.strip()) > 1]
        elif lines:
            paragraphs = [" ".join(lines)]

    return paragraphs


def _clean_and_count_words(text: str) -> tuple[str, int]:
    cleaned = clean_text(text)
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", cleaned)
    return cleaned, len(words)


def _ocr_single_image(image: Image.Image) -> str:
    """
    Multi-pass OCR strategy:
    1. Standard OCR (PSM 3). Fast and accurate for clean typed pages.
    2. If sparse (< 20 words), try Grayscale + Autocontrast with PSM 6 and PSM 11.
    3. If still sparse, apply adaptive thresholding / background subtraction (which
       suppresses notebook ruling lines and cancels out uneven phone camera lighting)
       with PSM 6 and PSM 11.
    4. Select whichever candidate extracted the most alphanumeric words.
    """
    candidates: list[tuple[int, str]] = []

    # Pass 1: Standard OCR
    try:
        t1 = pytesseract.image_to_string(image, config="--oem 1 --psm 3")
        c1, w1 = _clean_and_count_words(t1)
        candidates.append((w1, c1))
        if w1 >= 30:
            return c1
    except Exception:
        pass

    # Pass 2: Grayscale + Autocontrast
    try:
        gray = ImageOps.grayscale(image)
        auto = ImageOps.autocontrast(gray, cutoff=2)
        for psm in (6, 11):
            t2 = pytesseract.image_to_string(auto, config=f"--oem 1 --psm {psm}")
            c2, w2 = _clean_and_count_words(t2)
            candidates.append((w2, c2))
            if w2 >= 40:
                return c2
    except Exception:
        pass

    # Pass 3: Adaptive local thresholding (removes lined paper rules and phone shadows)
    try:
        gray = ImageOps.grayscale(image)
        blur = gray.filter(ImageFilter.BoxBlur(15))
        arr_gray = np.array(gray, dtype=np.int16)
        arr_blur = np.array(blur, dtype=np.int16)
        diff = arr_blur - arr_gray
        thresholded = (diff > 10).astype(np.uint8) * 255
        clean_bin = Image.fromarray(255 - thresholded)

        for psm in (6, 11):
            t3 = pytesseract.image_to_string(clean_bin, config=f"--oem 1 --psm {psm}")
            c3, w3 = _clean_and_count_words(t3)
            candidates.append((w3, c3))
    except Exception:
        pass

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _ocr_pdf_page(pdf_doc: "fitz.Document", page_index: int) -> str:
    page = pdf_doc[page_index]
    matrix = fitz.Matrix(OCR_RENDER_ZOOM, OCR_RENDER_ZOOM)
    pix = page.get_pixmap(matrix=matrix)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return _ocr_single_image(image)


def extract_from_pdf(file_path: str) -> ExtractionResult:
    try:
        pages_text: list[str] = []
        was_ocr_used = False
        pdf_doc = fitz.open(file_path)
        page_count = len(pdf_doc)

        for i in range(page_count):
            p = pdf_doc[i]
            direct_text = p.get_text() or ""
            # Page-by-page OCR decision for mixed digital and scanned PDFs
            if len(direct_text.strip()) < MIN_CHARS_PER_PAGE_BEFORE_OCR:
                was_ocr_used = True
                ocr_text = _ocr_pdf_page(pdf_doc, i)
                pages_text.append(ocr_text)
            else:
                pages_text.append(direct_text)

        pdf_doc.close()
        pages_text = remove_repeated_lines(pages_text)
        combined = clean_text("\n\n".join(pages_text))
        paragraphs = split_into_paragraphs(combined)
        words = combined.split()

        if len(words) == 0 or len(paragraphs) == 0:
            return ExtractionResult(
                text="",
                paragraphs=[],
                page_count=page_count,
                word_count=0,
                was_ocr_used=was_ocr_used,
                error=(
                    "No readable text could be extracted from this document (0 words found). "
                    "If this is a handwritten or scanned assignment, please ensure the photo is clear, "
                    "well-lit, and legible."
                ),
            )

        return ExtractionResult(
            text=combined,
            paragraphs=paragraphs,
            page_count=page_count,
            word_count=len(words),
            was_ocr_used=was_ocr_used,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller via .error
        return ExtractionResult(text="", error=f"PDF extraction failed: {exc}")


def extract_from_docx(file_path: str) -> ExtractionResult:
    try:
        doc = Document(file_path)
        paragraphs_raw = []
        for p in doc.paragraphs:
            if p.text.strip():
                paragraphs_raw.append(p.text.strip())

        # Extract text from tables as well as paragraphs
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    paragraphs_raw.append(" | ".join(cells))

        combined = clean_text("\n\n".join(paragraphs_raw))
        paragraphs = split_into_paragraphs(combined)
        words = combined.split()

        if len(words) == 0 or len(paragraphs) == 0:
            return ExtractionResult(
                text="",
                paragraphs=[],
                page_count=None,
                word_count=0,
                was_ocr_used=False,
                error="The uploaded DOCX file appears to be empty or contains no readable text paragraphs.",
            )

        return ExtractionResult(
            text=combined,
            paragraphs=paragraphs,
            page_count=None,
            word_count=len(words),
            was_ocr_used=False,
        )
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(text="", error=f"DOCX extraction failed: {exc}")


def extract_text(file_path: str, file_type: str) -> ExtractionResult:
    if file_type == "pdf":
        return extract_from_pdf(file_path)
    elif file_type == "docx":
        return extract_from_docx(file_path)
    return ExtractionResult(text="", error=f"Unsupported file type: {file_type}")
