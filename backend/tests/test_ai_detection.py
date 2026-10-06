"""
Unit and integration tests for AI writing signal service (backend/app/services/ai_detection.py).
Tests label validation, prose eligibility, OCR degradation handling, coverage calculations,
and graceful degradation.
"""
import math
import pytest
from unittest.mock import MagicMock, patch

from app.models.paragraph_embedding import ParagraphEmbedding
from app.models.report import AILabel, AIResult, Report
from app.models.submission import Submission
from app.services.ai_detection import (
    ModelOutputValidationError,
    _check_ocr_quality,
    _is_eligible_prose,
    _label_for,
    extract_validated_ai_probability,
    run_ai_check,
)


class TestAILabelValidation:
    """Tests for extract_validated_ai_probability."""

    def test_valid_label_1_and_label_0(self):
        output = [
            {"label": "LABEL_1", "score": 0.88},
            {"label": "LABEL_0", "score": 0.12},
        ]
        prob = extract_validated_ai_probability(output, "openai-community/roberta-base-openai-detector")
        assert prob == 0.88

    def test_valid_fake_and_real_labels(self):
        output = [
            {"label": "fake", "score": 0.654},
            {"label": "real", "score": 0.346},
        ]
        prob = extract_validated_ai_probability(output, "openai-community/roberta-base-openai-detector")
        assert prob == 0.654

    def test_nested_single_batch_list(self):
        output = [[
            {"label": "LABEL_1", "score": 0.77},
            {"label": "LABEL_0", "score": 0.23},
        ]]
        prob = extract_validated_ai_probability(output)
        assert prob == 0.77

    def test_default_mapping_labels(self):
        output = [
            {"label": "AI", "score": 0.91},
            {"label": "HUMAN", "score": 0.09},
        ]
        prob = extract_validated_ai_probability(output, "custom-model")
        assert prob == 0.91

    def test_none_output_raises_validation_error(self):
        with pytest.raises(ModelOutputValidationError, match="Classifier output is None"):
            extract_validated_ai_probability(None)

    def test_empty_list_raises_validation_error(self):
        with pytest.raises(ModelOutputValidationError, match="Malformed or empty"):
            extract_validated_ai_probability([])

    def test_malformed_entry_structure_raises(self):
        with pytest.raises(ModelOutputValidationError, match="Invalid label score entry structure"):
            extract_validated_ai_probability([{"label": "LABEL_1"}])

    def test_unknown_label_raises(self):
        output = [
            {"label": "UNKNOWN_PREDICTION_CLASS", "score": 0.5},
            {"label": "LABEL_0", "score": 0.5},
        ]
        with pytest.raises(ModelOutputValidationError, match="Unknown classifier label"):
            extract_validated_ai_probability(output)

    def test_missing_positive_label_raises(self):
        output = [
            {"label": "LABEL_0", "score": 0.95},
        ]
        with pytest.raises(ModelOutputValidationError, match="Positive AI class label not found"):
            extract_validated_ai_probability(output)

    def test_non_finite_scores_raise(self):
        nan_output = [
            {"label": "LABEL_1", "score": float("nan")},
            {"label": "LABEL_0", "score": 0.5},
        ]
        with pytest.raises(ModelOutputValidationError, match="outside valid probability range"):
            extract_validated_ai_probability(nan_output)

        inf_output = [
            {"label": "LABEL_1", "score": float("inf")},
            {"label": "LABEL_0", "score": 0.0},
        ]
        with pytest.raises(ModelOutputValidationError, match="outside valid probability range"):
            extract_validated_ai_probability(inf_output)

    def test_out_of_range_scores_raise(self):
        negative_output = [
            {"label": "LABEL_1", "score": -0.05},
            {"label": "LABEL_0", "score": 1.05},
        ]
        with pytest.raises(ModelOutputValidationError, match="outside valid probability range"):
            extract_validated_ai_probability(negative_output)

    def test_non_numeric_score_raises(self):
        invalid_type_output = [
            {"label": "LABEL_1", "score": "not-a-number"},
            {"label": "LABEL_0", "score": 0.5},
        ]
        with pytest.raises(ModelOutputValidationError, match="Non-numeric score"):
            extract_validated_ai_probability(invalid_type_output)


class TestProseEligibilityAndOCR:
    """Tests for prose eligibility heuristics and OCR corruption detection."""

    def test_short_text_under_100_words_rejected(self):
        short_text = "This is a brief introductory sentence that does not meet the minimum word count threshold."
        assert _is_eligible_prose(short_text) is False

    def test_long_academic_prose_accepted(self):
        prose = (
            "The rapid development of distributed operating systems has enabled scalable computing "
            "across heterogeneous hardware clusters. In modern architectures, fault tolerance and "
            "consistency protocols must be carefully balanced against communication latency and throughput. "
            "Recent advancements in consensus algorithms such as Raft and Paxos demonstrate that robust "
            "state replication is achievable even in unstable network partitions. When evaluating cluster "
            "performance, system designers must take into account message passing serialization overhead, "
            "persistent logging storage bandwidth, and thread context switching costs. Therefore, modern "
            "approaches frequently adopt asynchronous event loops and zero-copy networking abstractions "
            "to maximize processor efficiency and avoid costly kernel space transitions under heavy concurrency loads. "
            "This empirical study evaluates the latency distributions across varying packet sizes and nodal distributions, "
            "validating previous theoretical bounds in high performance distributed storage systems under realistic loads."
        )
        assert len(prose.split()) >= 100
        assert _is_eligible_prose(prose) is True

    def test_code_block_rejected(self):
        code_prose = (
            "def calculate_metrics(data):\n"
            "    import math\n"
            "    results = {}\n"
            "    for item in data:\n"
            "        if item == None:\n"
            "            return 0\n"
            "    return results\n" * 15
        )
        assert len(code_prose.split()) >= 100
        assert _is_eligible_prose(code_prose) is False

    def test_dense_citation_list_rejected(self):
        citations = " ".join([f"Study reference [{i}] shows doi: 10.1016/j.cs.202{i} et al. finding." for i in range(25)])
        assert len(citations.split()) >= 100
        assert _is_eligible_prose(citations) is False

    def test_ocr_clean_text_accepted(self):
        clean_text = "The quick brown fox jumps over the lazy dog. Academic essay writing is human prose."
        assert _check_ocr_quality(clean_text) is True

    def test_ocr_noisy_text_rejected(self):
        noisy_text = "###@@@!!! %%%&&& |||___ $$$^^^ ***~~~ 123 \x00\x01\x02 \u25a0\u25a1 \n\n ###@@@"
        assert _check_ocr_quality(noisy_text) is False

    def test_ocr_empty_text_rejected(self):
        assert _check_ocr_quality("") is False
        assert _check_ocr_quality("   \n\t  ") is False


class TestLabelThresholds:
    """Tests for score categorization into AILabel."""

    def test_likely_ai_threshold(self):
        assert _label_for(0.70) == AILabel.LIKELY_AI
        assert _label_for(0.65) == AILabel.LIKELY_AI

    def test_likely_human_threshold(self):
        assert _label_for(0.30) == AILabel.LIKELY_HUMAN
        assert _label_for(0.35) == AILabel.LIKELY_HUMAN

    def test_uncertain_threshold(self):
        assert _label_for(0.50) == AILabel.UNCERTAIN
        assert _label_for(0.40) == AILabel.UNCERTAIN
        assert _label_for(0.60) == AILabel.UNCERTAIN


class TestRunAICheckService:
    """Tests run_ai_check behavior against mock DB and mock classifier."""

    def test_unreliable_ocr_marks_status(self):
        submission = MagicMock(spec=Submission)
        submission.id = 101
        submission.was_ocr_used = True
        submission.word_count = 150

        report = MagicMock(spec=Report)
        report.id = 202

        db = MagicMock()
        corrupted_row = MagicMock(spec=ParagraphEmbedding)
        corrupted_row.paragraph_text = "$$$###!!! @@@%%% ***&&&" * 15
        corrupted_row.paragraph_index = 0
        db.query().filter().order_by().all.return_value = [corrupted_row]

        run_ai_check(submission, report, db)

        assert report.ai_status == "unreliable_ocr"
        assert report.ai_score is None
        assert report.ai_word_coverage_pct == 0.0
        assert report.ai_signal_strength == "unreliable_ocr"

    def test_insufficient_text_when_no_paragraphs_exceed_100_words(self):
        submission = MagicMock(spec=Submission)
        submission.id = 102
        submission.was_ocr_used = False
        submission.word_count = 60

        report = MagicMock(spec=Report)
        report.id = 203

        db = MagicMock()
        short_row1 = MagicMock(spec=ParagraphEmbedding)
        short_row1.paragraph_text = "Short heading one."
        short_row1.paragraph_index = 0
        short_row2 = MagicMock(spec=ParagraphEmbedding)
        short_row2.paragraph_text = "Another short note under one hundred words."
        short_row2.paragraph_index = 1

        db.query().filter().order_by().all.return_value = [short_row1, short_row2]

        run_ai_check(submission, report, db)

        assert report.ai_status == "insufficient_text"
        assert report.ai_score is None
        assert report.ai_signal_strength == "insufficient_text"

    @patch("app.services.ai_detection._get_classifier")
    def test_successful_evaluation_with_coverage(self, mock_get_classifier):
        mock_pipeline = MagicMock()
        # Mock classifier output: 0.82 AI probability
        mock_pipeline.return_value = [
            {"label": "LABEL_1", "score": 0.82},
            {"label": "LABEL_0", "score": 0.18},
        ]
        mock_get_classifier.return_value = mock_pipeline

        submission = MagicMock(spec=Submission)
        submission.id = 103
        submission.was_ocr_used = False
        submission.word_count = 250

        report = MagicMock(spec=Report)
        report.id = 204

        db = MagicMock()

        # 1 eligible long paragraph (120 words)
        long_para = " ".join(["word"] * 120)
        row1 = MagicMock(spec=ParagraphEmbedding)
        row1.paragraph_text = long_para
        row1.paragraph_index = 0

        # 1 short heading (10 words)
        short_para = "Short section heading title here."
        row2 = MagicMock(spec=ParagraphEmbedding)
        row2.paragraph_text = short_para
        row2.paragraph_index = 1

        db.query().filter().order_by().all.return_value = [row1, row2]

        run_ai_check(submission, report, db)

        assert report.ai_status == "completed"
        assert report.ai_signal_strength == "elevated"
        assert report.ai_evaluated_words == 120
        assert report.ai_skipped_words == 130
        assert report.ai_word_coverage_pct == round((120 / 250) * 100, 1)
        assert report.likely_ai_count == 1
        assert report.likely_human_count == 0
        assert report.ai_score == 100.0
