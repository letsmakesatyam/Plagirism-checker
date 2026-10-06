"""
Document viewer and layout highlighting service.

Provides:
1. Accurate page layout metadata and highlight coordinates for uploaded documents.
2. High-resolution rendered page images directly from the original document (or
   headless LibreOffice converted PDF for DOCX).
3. Trustworthy ordered text span alignment without arbitrary guessing or misleading fallbacks.
4. Downloadable annotated PDF copy with embedded highlights.
"""
import io
import logging
import re
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF
from PIL import Image
from sqlalchemy.orm import Session

from app.models.report import Report
from app.models.submission import Submission, FileType
from app.services.docx_converter import get_converted_docx_pdf_path, DocxConversionError
from app.services.internal_plagiarism import copied_from_summary
from app.services.internet_plagiarism import internet_sources_summary

logger = logging.getLogger(__name__)

# Colors for in-document highlighting (RGB floats 0..1 for PyMuPDF)
COLOR_CONFIG = {
    "internal": {
        "stroke": (0.75, 0.15, 0.15),
        "fill": (0.95, 0.45, 0.45),
        "css_color": "rust",
        "label": "Matches another submission (Internal)",
    },
    "internet": {
        "stroke": (0.85, 0.50, 0.05),
        "fill": (0.98, 0.75, 0.25),
        "css_color": "brass",
        "label": "Matches indexed source (Internet)",
    },
    "ai": {
        "stroke": (0.50, 0.25, 0.90),
        "fill": (0.75, 0.55, 1.0),
        "css_color": "violet",
        "label": "AI writing signal",
    },
}


def _clean_text_for_search(text: str) -> str:
    """Normalizes text whitespace and punctuation for search matching."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _merge_rects_on_lines(rects: list[fitz.Rect], y_tolerance: float = 6.0, x_gap_tolerance: float = 25.0) -> list[fitz.Rect]:
    """
    Merges adjacent word rectangles on the same horizontal line into clean highlight strips.
    """
    if not rects:
        return []

    # Deduplicate near-identical rects
    unique: list[fitz.Rect] = []
    for r in rects:
        if not any(
            abs(r.x0 - u.x0) < 2 and abs(r.y0 - u.y0) < 2 and abs(r.x1 - u.x1) < 2 and abs(r.y1 - u.y1) < 2
            for u in unique
        ):
            unique.append(r)

    sorted_rects = sorted(unique, key=lambda r: (r.y0, r.x0))
    merged: list[fitz.Rect] = []
    curr = fitz.Rect(sorted_rects[0])

    for r in sorted_rects[1:]:
        if abs(r.y0 - curr.y0) <= y_tolerance and (r.x0 - curr.x1) <= x_gap_tolerance:
            curr = fitz.Rect(min(curr.x0, r.x0), min(curr.y0, r.y0), max(curr.x1, r.x1), max(curr.y1, r.y1))
        else:
            merged.append(curr)
            curr = fitz.Rect(r)
    merged.append(curr)
    return merged


def _find_ordered_spans_in_pdf(
    doc: fitz.Document,
    para_text: str,
) -> dict[int, list[fitz.Rect]]:
    """
    Locates where paragraph text appears across PDF pages using ordered sequence alignment.
    Never guesses placement and never uses arbitrary full-page rectangle fallbacks.
    Returns: { page_index: [fitz.Rect, ...] }
    """
    cleaned_para = _clean_text_for_search(para_text)
    if not cleaned_para or len(cleaned_para) < 5:
        return {}

    page_count = len(doc)
    matched_by_page: dict[int, list[fitz.Rect]] = {}

    # Extract sentences or ordered phrases (chunks of 4 to 8 words)
    words = cleaned_para.split()
    if len(words) <= 3:
        phrases = [cleaned_para]
    else:
        # Create overlapping ordered phrases
        chunk_size = 5
        phrases = []
        for i in range(0, len(words), 3):
            phrase_chunk = " ".join(words[i : i + chunk_size])
            if len(phrase_chunk) >= 10:
                phrases.append(phrase_chunk)
        if not phrases:
            phrases = [cleaned_para[:60]]

    # Search for phrases across all pages
    for pno in range(page_count):
        page = doc[pno]
        page_hits: list[fitz.Rect] = []

        # 1. Try exact paragraph search first
        if len(cleaned_para) < 150:
            exact_hits = page.search_for(cleaned_para)
            if exact_hits:
                page_hits.extend(exact_hits)

        # 2. Try phrase matching if exact search did not hit
        if not page_hits:
            for phrase in phrases:
                hits = page.search_for(phrase)
                if hits:
                    page_hits.extend(hits)

        if page_hits:
            merged = _merge_rects_on_lines(page_hits)
            if merged:
                matched_by_page[pno] = merged

    return matched_by_page


def build_submission_highlights_map(submission: Submission, report: Optional[Report], db: Session) -> dict[int, list[dict[str, Any]]]:
    """
    Builds a list of highlight descriptor dicts for each paragraph index.
    Returns: { paragraph_index: [highlight_info, ...] }
    """
    if not report:
        return {}

    highlights_by_para: dict[int, list[dict[str, Any]]] = {}

    # Internal matches
    student_names = {}
    copied_summary = copied_from_summary(report, db) if db else []
    for c in copied_summary:
        sub_id = getattr(c, "matched_submission_id", None) or (c.get("matched_submission_id") if isinstance(c, dict) else None)
        stu_name = getattr(c, "matched_student_name", None) or (c.get("matched_student_name") if isinstance(c, dict) else None)
        if sub_id:
            student_names[str(sub_id)] = stu_name or "Another student"

    for m in (report.internal_matches or []):
        p_idx = m.source_paragraph_index
        matched_student = student_names.get(str(m.matched_submission_id), "Another student")
        sim_pct = int(round(m.similarity * 100))
        h_info = {
            "type": "internal",
            "color": "rust",
            "title": f"Internal Match ({sim_pct}%)",
            "description": f"Similar passage to submission from {matched_student} ({sim_pct}% similarity).",
            "confidence": m.similarity,
            "badge": f"{sim_pct}% match",
            "evidence_kind": "Similar passage",
            "matched_submission_id": str(m.matched_submission_id),
            "matched_text": m.matched_paragraph_text[:200] if m.matched_paragraph_text else None,
        }
        highlights_by_para.setdefault(p_idx, []).append(h_info)

    # Internet matches
    internet_summary = internet_sources_summary(report, db) if db else []
    source_titles = {}
    for s in internet_summary:
        src_id = getattr(s, "matched_source_id", None) or (s.get("matched_source_id") if isinstance(s, dict) else None)
        title = getattr(s, "title", None) or (s.get("title") if isinstance(s, dict) else None)
        if src_id:
            source_titles[str(src_id)] = title or "Indexed Internet Source"

    for m in (report.internet_matches or []):
        p_idx = m.source_paragraph_index
        source_title = source_titles.get(str(m.matched_source_id), "Indexed Internet Source")
        sim_pct = int(round(m.similarity * 100))
        h_info = {
            "type": "internet",
            "color": "brass",
            "title": f"Internet Match ({sim_pct}%)",
            "description": f"Similar passage to '{source_title}' ({sim_pct}% similarity).",
            "confidence": m.similarity,
            "badge": f"{sim_pct}% source",
            "evidence_kind": "Similar passage",
            "matched_source_id": str(m.matched_source_id),
            "matched_text": m.matched_paragraph_text[:200] if m.matched_paragraph_text else None,
        }
        highlights_by_para.setdefault(p_idx, []).append(h_info)

    # AI results
    for a in (report.ai_results or []):
        label_val = getattr(a.label, "value", str(a.label))
        if label_val == "likely_ai":
            p_idx = a.paragraph_index
            h_info = {
                "type": "ai",
                "color": "violet",
                "title": "Elevated AI Writing Signal",
                "description": "Statistical language patterns match machine-generated text signal (review required).",
                "confidence": a.ai_probability,
                "badge": "Elevated signal",
                "evidence_kind": "Statistical text signal",
            }
            highlights_by_para.setdefault(p_idx, []).append(h_info)

    return highlights_by_para


def get_preview_pdf_path(submission: Submission) -> tuple[str, bool, str | None]:
    """
    Returns (pdf_path, is_converted, error_message).
    For PDF, returns the original file path.
    For DOCX, converts via LibreOffice and returns cached PDF path.
    """
    file_path = submission.file_path
    if submission.file_type == FileType.PDF:
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Original PDF file not found: {file_path}")
        return file_path, False, None

    # DOCX: convert to PDF preview
    try:
        converted_pdf = get_converted_docx_pdf_path(file_path)
        return converted_pdf, True, None
    except Exception as exc:
        logger.warning(f"DOCX conversion to PDF preview failed: {exc}")
        return file_path, False, str(exc)


def get_submission_document_pages(submission: Submission, report: Optional[Report], db: Session) -> dict[str, Any]:
    """
    Computes all page metadata and highlight bounding boxes for the submission.
    Preserves original PDF layout or genuine LibreOffice converted DOCX layout.
    """
    file_path, is_converted, conv_error = get_preview_pdf_path(submission)
    paragraphs = submission.paragraphs or []
    highlights_map = build_submission_highlights_map(submission, report, db)

    pages_data = []

    # If we have a valid PDF (original PDF or converted DOCX PDF)
    is_pdf_renderable = submission.file_type == FileType.PDF or (is_converted and Path(file_path).exists())

    if is_pdf_renderable:
        doc = fitz.open(file_path)
        page_count = len(doc)
        page_highlights_map: dict[int, list[dict[str, Any]]] = {pno: [] for pno in range(page_count)}
        unmapped_highlights: list[dict[str, Any]] = []

        for p_idx, para_text in enumerate(paragraphs):
            h_list = highlights_map.get(p_idx, [])
            if not h_list:
                continue

            rects_by_page = _find_ordered_spans_in_pdf(doc, para_text)

            if not rects_by_page:
                # Location cannot be accurately aligned — mark explicitly rather than drawing fake box!
                for h in h_list:
                    unmapped_highlights.append({
                        **h,
                        "paragraph_index": p_idx,
                        "location_available": False,
                        "status_text": "Match found; location unavailable in page layout",
                    })
                continue

            for h in h_list:
                for page_no, rects in rects_by_page.items():
                    if 0 <= page_no < page_count:
                        page = doc[page_no]
                        p_w = page.rect.width
                        p_h = page.rect.height

                        rect_dicts = []
                        for r in rects:
                            rx0 = max(0.0, min(r.x0, p_w))
                            ry0 = max(0.0, min(r.y0, p_h))
                            rx1 = max(rx0, min(r.x1, p_w))
                            ry1 = max(ry0, min(r.y1, p_h))
                            rw = rx1 - rx0
                            rh = ry1 - ry0
                            if rw > 1 and rh > 1:
                                rect_dicts.append({
                                    "x": round(rx0, 1),
                                    "y": round(ry0, 1),
                                    "w": round(rw, 1),
                                    "h": round(rh, 1),
                                    "left_pct": round((rx0 / p_w) * 100, 2),
                                    "top_pct": round((ry0 / p_h) * 100, 2),
                                    "width_pct": round((rw / p_w) * 100, 2),
                                    "height_pct": round((rh / p_h) * 100, 2),
                                })

                        if rect_dicts:
                            page_highlights_map[page_no].append({
                                "id": f"hl_{p_idx}_{page_no}_{h['type']}",
                                "paragraph_index": p_idx,
                                "type": h["type"],
                                "color": h["color"],
                                "title": h["title"],
                                "description": h["description"],
                                "badge": h["badge"],
                                "confidence": h["confidence"],
                                "evidence_kind": h.get("evidence_kind", "Similar passage"),
                                "matched_submission_id": h.get("matched_submission_id"),
                                "matched_source_id": h.get("matched_source_id"),
                                "matched_text": h.get("matched_text"),
                                "location_available": True,
                                "rects": rect_dicts,
                            })

        for pno in range(page_count):
            p = doc[pno]
            hl_list = page_highlights_map[pno]
            pages_data.append({
                "page_number": pno + 1,
                "width": round(p.rect.width, 1),
                "height": round(p.rect.height, 1),
                "aspect_ratio": round(p.rect.width / max(p.rect.height, 1.0), 3),
                "image_url": f"/api/submissions/{submission.id}/pages/{pno + 1}/image",
                "annotated_image_url": f"/api/submissions/{submission.id}/pages/{pno + 1}/image?annotated=true",
                "has_highlights": len(hl_list) > 0,
                "highlights": hl_list,
            })
        doc.close()
    else:
        # Conversion failed or unsupported format: do NOT generate fake simulated pages.
        # Report 0 visual pages and provide clear fallback message
        pages_data = []
        unmapped_highlights = [
            {**h, "paragraph_index": p_idx, "location_available": False, "status_text": "Visual layout unavailable; use Extracted Text view"}
            for p_idx, h_list in highlights_map.items()
            for h in h_list
        ]

    total_hl = sum(len(p["highlights"]) for p in pages_data)
    internal_count = sum(1 for p in pages_data for h in p["highlights"] if h["type"] == "internal")
    internet_count = sum(1 for p in pages_data for h in p["highlights"] if h["type"] == "internet")
    ai_count = sum(1 for p in pages_data for h in p["highlights"] if h["type"] == "ai")

    preview_label = "PDF preview converted from original DOCX" if is_converted else "Original PDF document"
    if not is_pdf_renderable:
        preview_label = "Document layout preview unavailable (use Extracted Text view)"

    return {
        "submission_id": str(submission.id),
        "file_type": submission.file_type.value,
        "original_filename": submission.original_filename,
        "is_converted_preview": is_converted,
        "preview_label": preview_label,
        "conversion_error": conv_error,
        "page_count": len(pages_data),
        "pages": pages_data,
        "unmapped_highlights": unmapped_highlights,
        "summary": {
            "total_highlights": total_hl,
            "internal_count": internal_count,
            "internet_count": internet_count,
            "ai_count": ai_count,
        },
    }


def render_page_image_bytes(
    submission: Submission,
    report: Optional[Report],
    db: Session,
    page_number: int,
    annotated: bool = False,
    dpi: int = 150,
) -> bytes:
    """
    Renders a page of the submission to PNG bytes.
    Default annotated=False renders the authentic unannotated document page image.
    If annotated=True, highlights are drawn into the image (for download or static rendering).
    """
    file_path, is_converted, _ = get_preview_pdf_path(submission)

    if not Path(file_path).exists():
        raise FileNotFoundError(f"Preview document file not found: {file_path}")

    doc = fitz.open(file_path)
    try:
        page_count = len(doc)
        if page_number < 1 or page_number > page_count:
            raise ValueError(f"Page {page_number} is out of range (1-{page_count})")

        page = doc[page_number - 1]

        if annotated and report:
            doc_data = get_submission_document_pages(submission, report, db)
            if page_number - 1 < len(doc_data["pages"]):
                p_data = doc_data["pages"][page_number - 1]
                for h in p_data["highlights"]:
                    cfg = COLOR_CONFIG.get(h["type"], COLOR_CONFIG["ai"])
                    for r_dict in h.get("rects", []):
                        rect = fitz.Rect(r_dict["x"], r_dict["y"], r_dict["x"] + r_dict["w"], r_dict["y"] + r_dict["h"])
                        page.draw_rect(
                            rect,
                            color=cfg["stroke"],
                            fill=cfg["fill"],
                            fill_opacity=0.32,
                            width=1.5,
                            overlay=True,
                        )

        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()


def generate_annotated_document_pdf(
    submission: Submission,
    report: Optional[Report],
    db: Session,
) -> bytes:
    """
    Returns an annotated copy of the PDF (original PDF or converted DOCX preview),
    with highlights visually drawn into the document pages.
    """
    file_path, is_converted, _ = get_preview_pdf_path(submission)

    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found for annotated PDF generation: {file_path}")

    doc = fitz.open(file_path)
    try:
        if report:
            doc_data = get_submission_document_pages(submission, report, db)
            for p_idx, page_info in enumerate(doc_data["pages"]):
                if p_idx < len(doc):
                    page = doc[p_idx]
                    for h in page_info.get("highlights", []):
                        cfg = COLOR_CONFIG.get(h["type"], COLOR_CONFIG["ai"])
                        for r_dict in h.get("rects", []):
                            rect = fitz.Rect(
                                r_dict["x"],
                                r_dict["y"],
                                r_dict["x"] + r_dict["w"],
                                r_dict["y"] + r_dict["h"],
                            )
                            page.draw_rect(
                                rect,
                                color=cfg["stroke"],
                                fill=cfg["fill"],
                                fill_opacity=0.32,
                                width=1.5,
                                overlay=True,
                            )

        return doc.tobytes(deflate=True)
    finally:
        doc.close()
