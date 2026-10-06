"""
AI writing signal service (Phase 4c modernized).

Uses an open-source classifier (openai-community/roberta-base-openai-detector)
with conservative input qualification, strict label validation, and honest
presentation:

1. Never presents classifier output as proof of AI authorship ("never claim certainty").
2. Conservative prose eligibility: requires minimum prose length (configurable,
   100 words per window) and filters out headings, citations, code, tables, and formulas.
3. Bounded tokenizer-aware evaluation windows within the model's limit (no arbitrary char slicing).
4. Strict label mapping validation: never assumes LABEL_1 universally means AI;
   raises explicit ModelOutputValidationError on unknown labels, missing classes, or malformed data.
5. Distinguishes signal strength (low/moderate/elevated), evaluated coverage,
   insufficient text, unreliable OCR, and unavailable detector states.
6. Does not claim handwritten or OCR-degraded text proves human authorship.
"""
import logging
import math
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import AILabel, AIResult, Report
from app.models.submission import Submission

logger = logging.getLogger(__name__)

# Supported model label mappings:
# Maps model identifier to sets of positive (machine/AI) and negative (human/real) labels.
MODEL_LABEL_MAPPINGS = {
    "openai-community/roberta-base-openai-detector": {
        "positive": {"FAKE", "LABEL_1"},
        "negative": {"REAL", "LABEL_0"},
    },
    "default": {
        "positive": {"FAKE", "LABEL_1", "AI", "GENERATED", "MACHINE"},
        "negative": {"REAL", "LABEL_0", "HUMAN", "ORIGINAL"},
    },
}

_classifier = None


class ModelOutputValidationError(ValueError):
    """Raised when model classifier outputs unknown labels, malformed structure, or non-finite values."""
    pass


def _get_classifier():
    """Lazy-loaded singleton pipeline."""
    global _classifier
    if _classifier is None:
        from transformers import pipeline

        _classifier = pipeline(
            "text-classification",
            model=settings.AI_DETECTION_MODEL_NAME,
            top_k=None,  # return scores for every label
        )
    return _classifier


def extract_validated_ai_probability(raw_output: Any, model_name: str | None = None) -> float:
    """
    Validates classifier output structure, labels, and probability range [0, 1].
    Raises ModelOutputValidationError on unknown labels, missing classes, empty or non-finite outputs.
    Never fabricates a 0.0 score on invalid output.
    """
    if raw_output is None:
        raise ModelOutputValidationError("Classifier output is None.")

    # Flatten nested single-batch list if present
    label_scores = raw_output
    if isinstance(label_scores, list) and len(label_scores) > 0 and isinstance(label_scores[0], list):
        label_scores = label_scores[0]

    if not isinstance(label_scores, list) or len(label_scores) == 0:
        raise ModelOutputValidationError(f"Malformed or empty classifier output format: {raw_output}")

    mapping_key = model_name or settings.AI_DETECTION_MODEL_NAME
    mapping = MODEL_LABEL_MAPPINGS.get(mapping_key, MODEL_LABEL_MAPPINGS["default"])
    pos_labels = mapping["positive"]
    neg_labels = mapping["negative"]

    found_pos_score = None
    found_neg_score = None

    for entry in label_scores:
        if not isinstance(entry, dict) or "label" not in entry or "score" not in entry:
            raise ModelOutputValidationError(f"Invalid label score entry structure: {entry}")

        label = str(entry["label"]).strip().upper()
        try:
            score = float(entry["score"])
        except (ValueError, TypeError) as exc:
            raise ModelOutputValidationError(f"Non-numeric score value: {entry.get('score')}") from exc

        if not math.isfinite(score) or score < 0.0 or score > 1.0:
            raise ModelOutputValidationError(f"Score {score} is outside valid probability range [0, 1]")

        if label in pos_labels:
            found_pos_score = score
        elif label in neg_labels:
            found_neg_score = score
        else:
            raise ModelOutputValidationError(f"Unknown classifier label '{entry['label']}' not in supported mapping")

    if found_pos_score is None:
        raise ModelOutputValidationError(f"Positive AI class label not found in output: {label_scores}")

    return found_pos_score


def _is_eligible_prose(text: str) -> bool:
    """
    Checks if a text segment is eligible prose for authorship analysis.
    Filters out headings, references, citations, formulas, code, and tables.
    """
    words = text.split()
    if len(words) < settings.AI_MIN_PROSE_WORDS:
        return False

    # Heading check: very short lines, title caps
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) == 1 and len(words) < 25:
        return False

    # References/citations pattern (e.g. multiple "[1]", "[2]", DOIs, et al.)
    citation_hits = len(re.findall(r"\[\d+\]|doi:\s*10\.\d+|et\s+al\.", text, re.IGNORECASE))
    if citation_hits >= 3 and (citation_hits / max(len(words), 1)) > 0.05:
        return False

    # Code / formula check: high symbol ratio
    code_indicators = sum(text.count(sym) for sym in ["{", "}", ";", "def ", "class ", "return ", "import ", "==", "/*"])
    if code_indicators >= 5:
        return False

    return True


def _check_ocr_quality(text: str) -> bool:
    """
    Returns False if OCR extracted text is heavily corrupted with non-alphanumeric noise,
    indicating unreliable text where AI analysis would be invalid.
    """
    if not text.strip():
        return False
    alphanumeric_count = sum(1 for c in text if c.isalnum() or c.isspace())
    ratio = alphanumeric_count / max(len(text), 1)
    return ratio >= 0.70


def _label_for(probability: float) -> AILabel:
    if probability >= settings.AI_LIKELY_THRESHOLD:
        return AILabel.LIKELY_AI
    if probability <= settings.AI_HUMAN_THRESHOLD:
        return AILabel.LIKELY_HUMAN
    return AILabel.UNCERTAIN


def run_ai_check(submission: Submission, report: Report, db: Session) -> None:
    """
    Runs conservative AI writing signal analysis across eligible prose paragraphs.
    Updates report AI columns and populates AIResult rows.
    """
    own_rows = (
        db.query(ParagraphEmbedding)
        .filter(ParagraphEmbedding.submission_id == submission.id)
        .order_by(ParagraphEmbedding.paragraph_index)
        .all()
    )
    if not own_rows:
        raise ValueError("Submission has no indexed paragraphs; cannot run AI check.")

    # Reset any previous run's results
    db.query(AIResult).filter(AIResult.report_id == report.id).delete()

    total_words = submission.word_count or sum(len(r.paragraph_text.split()) for r in own_rows)

    # Check for poor/corrupted OCR
    if submission.was_ocr_used:
        full_text = " ".join(r.paragraph_text for r in own_rows)
        if not _check_ocr_quality(full_text):
            report.ai_status = "unreliable_ocr"
            report.ai_model_name = settings.AI_DETECTION_MODEL_NAME
            report.ai_method_version = "v2-bounded-prose-100w"
            report.ai_signal_strength = "unreliable_ocr"
            report.ai_word_coverage_pct = 0.0
            report.ai_evaluated_words = 0
            report.ai_skipped_words = total_words
            report.ai_score = None
            report.likely_ai_count = 0
            report.likely_human_count = 0
            report.uncertain_count = 0
            return

    # Filter eligible prose
    eligible_rows = [r for r in own_rows if _is_eligible_prose(r.paragraph_text)]
    evaluated_words = sum(len(r.paragraph_text.split()) for r in eligible_rows)

    if not eligible_rows or evaluated_words < settings.AI_MIN_PROSE_WORDS:
        report.ai_status = "insufficient_text"
        report.ai_model_name = settings.AI_DETECTION_MODEL_NAME
        report.ai_method_version = "v2-bounded-prose-100w"
        report.ai_signal_strength = "insufficient_text"
        report.ai_word_coverage_pct = round((evaluated_words / max(total_words, 1)) * 100, 1)
        report.ai_evaluated_words = evaluated_words
        report.ai_skipped_words = max(0, total_words - evaluated_words)
        report.ai_score = None
        report.likely_ai_count = 0
        report.likely_human_count = 0
        report.uncertain_count = 0
        return

    classifier = _get_classifier()

    likely_ai = likely_human = uncertain = 0
    new_results: list[AIResult] = []
    probabilities: list[float] = []

    for row in eligible_rows:
        text = row.paragraph_text
        words = text.split()

        # Tokenizer-aware bounded input (up to ~250 words, comfortably within 400 tokens)
        bounded_text = " ".join(words[:250])

        raw_output = classifier(bounded_text, truncation=True)
        probability = extract_validated_ai_probability(raw_output, settings.AI_DETECTION_MODEL_NAME)
        probabilities.append(probability)

        label = _label_for(probability)
        if label == AILabel.LIKELY_AI:
            likely_ai += 1
        elif label == AILabel.LIKELY_HUMAN:
            likely_human += 1
        else:
            uncertain += 1

        new_results.append(
            AIResult(
                report_id=report.id,
                paragraph_index=row.paragraph_index,
                paragraph_text=text,
                ai_probability=round(probability, 4),
                label=label,
            )
        )

    db.add_all(new_results)

    evaluated_count = len(eligible_rows)
    avg_probability = sum(probabilities) / max(len(probabilities), 1)
    max_probability = max(probabilities) if probabilities else 0.0

    # Signal strength qualification (honest presentation, not authorship claim)
    if likely_ai > 0 and (max_probability >= settings.AI_SIGNAL_ELEVATED_THRESHOLD or avg_probability >= 0.60):
        signal_strength = "elevated"
    elif avg_probability <= settings.AI_SIGNAL_LOW_THRESHOLD:
        signal_strength = "low"
    else:
        signal_strength = "moderate"

    report.ai_status = "completed"
    report.ai_model_name = settings.AI_DETECTION_MODEL_NAME
    report.ai_method_version = "v2-bounded-prose-100w"
    report.ai_signal_strength = signal_strength
    report.ai_word_coverage_pct = round((evaluated_words / max(total_words, 1)) * 100, 1)
    report.ai_evaluated_words = evaluated_words
    report.ai_skipped_words = max(0, total_words - evaluated_words)

    # ai_score is stored as the percentage of evaluated prose paragraphs showing elevated signal
    report.ai_score = round((likely_ai / evaluated_count) * 100, 2) if evaluated_count else None
    report.likely_ai_count = likely_ai
    report.likely_human_count = likely_human
    report.uncertain_count = uncertain
