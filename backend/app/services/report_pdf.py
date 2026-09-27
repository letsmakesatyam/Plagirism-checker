"""
PDF report export (Phase 5). Renders a Report + its matches into a
downloadable PDF using `reportlab` — pure-Python, no system dependencies
(unlike wkhtmltopdf or a headless browser), so it behaves identically in
Docker and on a bare host with just `pip install`.

generate_report_pdf() returns raw PDF bytes; the route
(app/api/routes/reports.py) wraps them in a Response with the right
Content-Disposition header. Kept as its own module, not inline in the
route, so layout can be adjusted without touching request handling.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.report import Report
from app.models.submission import Submission

MAX_MATCHES_PER_SECTION = 20  # keeps the PDF a reasonable length for long submissions


def _fmt_score(value) -> str:
    return f"{value:.1f}%" if value is not None else "N/A"


def _escape(text: str) -> str:
    # reportlab's Paragraph treats these characters as markup, so plain
    # extracted text must be escaped before being passed in.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_report_pdf(report: Report, submission: Submission) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("SmallGrey", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    story = [
        Paragraph("Plagiarism Report", styles["Title"]),
        Paragraph(f"Submission: {_escape(submission.original_filename)}", styles["Normal"]),
        Paragraph(
            f"Assignment: {_escape(submission.assignment.title) if submission.assignment else '-'}", styles["Normal"]
        ),
        Paragraph(
            f"Student: {_escape(submission.student.full_name) if submission.student else '-'}", styles["Normal"]
        ),
        Paragraph(
            f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC') if report.generated_at else '-'}", small
        ),
        Spacer(1, 0.5 * cm),
    ]

    score_rows = [
        ["Metric", "Score"],
        ["Overall Originality", _fmt_score(report.overall_originality_score)],
        ["Internal Similarity", _fmt_score(report.internal_score)],
        ["Internet Similarity", _fmt_score(report.internet_score)],
        ["AI-Generated (likely)", _fmt_score(report.ai_score)],
    ]
    table = Table(score_rows, colWidths=[8 * cm, 4 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.7 * cm))
    story.append(
        Paragraph(
            "AI-detection note: the AI-Generated score comes from an open-source classifier "
            "trained on older AI-generated text and should not be treated as certain proof — "
            "see docs/README.md section 12 for its documented limitations.",
            small,
        )
    )
    story.append(Spacer(1, 0.7 * cm))

    if report.internal_matches:
        story.append(Paragraph("Internal Matches (other submissions)", styles["Heading2"]))
        for m in report.internal_matches[:MAX_MATCHES_PER_SECTION]:
            story.append(
                Paragraph(f"Paragraph {m.source_paragraph_index} — similarity {m.similarity:.0%}", styles["Heading4"])
            )
            story.append(Paragraph(_escape(m.source_paragraph_text[:400]), styles["Normal"]))
            story.append(Spacer(1, 0.3 * cm))

    if report.internet_matches:
        story.append(PageBreak())
        story.append(Paragraph("Internet Matches", styles["Heading2"]))
        for m in report.internet_matches[:MAX_MATCHES_PER_SECTION]:
            source_title = m.matched_source.title if m.matched_source else "Unknown source"
            story.append(
                Paragraph(
                    f"Paragraph {m.source_paragraph_index} — similarity {m.similarity:.0%} — {_escape(source_title)}",
                    styles["Heading4"],
                )
            )
            story.append(Paragraph(_escape(m.source_paragraph_text[:400]), styles["Normal"]))
            story.append(Spacer(1, 0.3 * cm))

    doc.build(story)
    return buffer.getvalue()
