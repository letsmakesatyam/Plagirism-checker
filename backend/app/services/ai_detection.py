"""
AI-generated-text detection (Phase 4c).

Uses an open-source RoBERTa classifier (`openai-community/roberta-base-openai-detector`,
originally released to detect GPT-2 output) via Hugging Face `transformers`, run locally
per paragraph — same "download once, run offline" shape as embeddings.py's
sentence-transformers model, just a different model.

`run_ai_check` follows the exact same contract as run_internal_check /
run_internet_check: it writes its results onto the given Report and adds AIResult
rows, but does not commit or touch report.status — see report_generation.py for
the orchestration that owns those.

IMPORTANT LIMITATION — read before trusting this output (spec requirement: "never
claim certainty"). This classifier was trained to separate GPT-2 output from human
text. It was NOT trained on modern LLMs (GPT-4, Claude, Gemini, Llama, etc.), so its
accuracy against contemporary AI writing is unverified and likely lower than its
original published benchmarks. It is included as a documented, honestly-caveated,
working open-source baseline — not a certainty detector, and not a substitute for
academic judgment. Every score is stored as a probability (see AIResult.ai_probability),
and scoring always uses three buckets (likely_human / uncertain / likely_ai) rather
than a binary verdict specifically so borderline paragraphs land in "uncertain"
instead of being forced into a confident label they don't deserve. See README
section 12 for the full discussion, including how to swap in a newer model later
(any Hugging Face `text-classification` model with a "this text is AI-generated"-style
label works as a drop-in replacement — change AI_DETECTION_MODEL_NAME in config.py
and adjust `_ai_probability`'s label matching if the new model's label names differ).
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import AILabel, AIResult, Report
from app.models.submission import Submission

# Paragraphs shorter than this have too little text for the classifier to say
# anything meaningful, so they're skipped entirely rather than forced through
# (a one-line heading scored "likely AI" would be a meaningless, misleading result).
MIN_WORDS_FOR_AI_CHECK = 20

# The model's own max input length; longer paragraphs are truncated for scoring
# only (the full original text is still stored on the AIResult row).
MAX_CHARS_FOR_AI_CHECK = 2000

_classifier = None


def _get_classifier():
    """Lazy-loaded singleton, mirrors app/services/embeddings.py's pattern —
    avoids importing torch/transformers or downloading the model until the
    first time an AI check actually runs."""
    global _classifier
    if _classifier is None:
        from transformers import pipeline

        _classifier = pipeline(
            "text-classification",
            model=settings.AI_DETECTION_MODEL_NAME,
            top_k=None,  # return scores for every label, not just the top one
        )
    return _classifier


def _ai_probability(label_scores: list[dict]) -> float:
    """
    The model's two labels are 'Real' (human-written) and 'Fake' (machine-generated)
    — naming inherited from its original GPT-2-detector release. Returns P(machine
    generated). Falls back to 0.0 (i.e. "assume human") if the label names ever
    don't match what's expected, rather than raising and failing the whole check.
    """
    for entry in label_scores:
        if entry["label"].upper() in ("FAKE", "LABEL_1"):
            return float(entry["score"])
    return 0.0


def _label_for(probability: float) -> AILabel:
    if probability >= settings.AI_LIKELY_THRESHOLD:
        return AILabel.LIKELY_AI
    if probability <= settings.AI_HUMAN_THRESHOLD:
        return AILabel.LIKELY_HUMAN
    return AILabel.UNCERTAIN


def run_ai_check(submission: Submission, report: Report, db: Session) -> None:
    own_rows = (
        db.query(ParagraphEmbedding)
        .filter(ParagraphEmbedding.submission_id == submission.id)
        .order_by(ParagraphEmbedding.paragraph_index)
        .all()
    )
    if not own_rows:
        raise ValueError(
            "Submission has no indexed paragraphs; cannot run AI-text detection."
        )

    # Wipe any previous run's results before recomputing (report can be regenerated).
    db.query(AIResult).filter(AIResult.report_id == report.id).delete()

    classifier = _get_classifier()

    likely_ai = likely_human = uncertain = 0
    new_results: list[AIResult] = []
    for row in own_rows:
        text = row.paragraph_text
        if len(text.split()) < MIN_WORDS_FOR_AI_CHECK:
            continue

        raw_output = classifier(text[:MAX_CHARS_FOR_AI_CHECK], truncation=True)
        # top_k=None returns [[{"label": ..., "score": ...}, ...]] (batch of 1); some
        # transformers versions instead return the inner list directly for single inputs.
        label_scores = raw_output[0] if isinstance(raw_output[0], list) else raw_output
        probability = _ai_probability(label_scores)
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

    evaluated = likely_ai + likely_human + uncertain
    # ai_score mirrors internal_score/internet_score's shape: a paragraph-coverage
    # percentage ("what fraction of this document looks AI-written"). None (not 0)
    # when nothing was long enough to evaluate, so the UI can distinguish
    # "checked, found nothing" from "too short to check at all".
    report.ai_score = round((likely_ai / evaluated) * 100, 2) if evaluated else None
    report.likely_ai_count = likely_ai
    report.likely_human_count = likely_human
    report.uncertain_count = uncertain
