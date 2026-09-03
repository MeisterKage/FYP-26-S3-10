"""Unit tests for the scoring engine (PRD 7.5.1 names this explicitly).

The engine is pure, so these tests need no database, no app context, and no
fixtures -- which is the whole reason `credibility.py` does no I/O.
"""
import pytest

from app.credibility import DEFAULTS, accuracy_rate, band_for, credibility_score


# --------------------------------------------------------------------------- #
#  Accuracy rate
# --------------------------------------------------------------------------- #

def test_accuracy_withheld_below_minimum():
    """PRD 1.3.3: the rate appears only after a set minimum number of articles."""
    assert accuracy_rate(published_count=4, corrected_or_retracted_count=0) is None


def test_accuracy_none_is_not_zero():
    """A new contributor has no accuracy rate. That is not the same as a bad one."""
    assert accuracy_rate(0, 0) is None


def test_accuracy_all_clean():
    assert accuracy_rate(10, 0) == 100.0


def test_accuracy_with_corrections():
    assert accuracy_rate(10, 3) == 70.0


def test_accuracy_all_corrected():
    assert accuracy_rate(5, 5) == 0.0


def test_accuracy_respects_admin_threshold():
    settings = {"min_articles_for_accuracy": 2}
    assert accuracy_rate(3, 0, settings) == 100.0


# --------------------------------------------------------------------------- #
#  Credibility score
# --------------------------------------------------------------------------- #

def _score(**overrides):
    kwargs = {
        "contributor_accuracy": 100.0,
        "source_count": 0,
        "correction_count": 0,
        "is_retracted": False,
        "upheld_report_count": 0,
    }
    kwargs.update(overrides)
    return credibility_score(**kwargs)


def test_perfect_article_scores_100():
    """Ceiling check: 100% accuracy (75) + five sources capped at 25 = 100."""
    assert _score(source_count=5).score == 100.0


def test_sources_are_capped():
    five = _score(source_count=5).score
    fifty = _score(source_count=50).score
    assert five == fifty == 100.0


def test_each_source_is_worth_its_stated_points():
    assert _score(source_count=1).score - _score(source_count=0).score == (
        DEFAULTS["source_points"]
    )


def test_new_contributor_uses_provisional_accuracy():
    result = _score(contributor_accuracy=None, source_count=2)
    assert result.used_provisional_accuracy is True
    # 0.75 * 70 provisional  +  2 * 5 sources  =  62.5
    assert result.score == 62.5


def test_correction_lowers_the_score():
    clean = _score(source_count=5).score
    corrected = _score(source_count=5, correction_count=1).score
    assert clean - corrected == DEFAULTS["correction_penalty"]


def test_corrections_accumulate():
    one = _score(source_count=5, correction_count=1).score
    two = _score(source_count=5, correction_count=2).score
    assert one - two == DEFAULTS["correction_penalty"]


def test_retraction_applies_once_and_is_heavier_than_a_correction():
    retracted = _score(source_count=5, is_retracted=True).score
    corrected = _score(source_count=5, correction_count=1).score
    assert retracted < corrected


def test_report_penalty_only_applies_at_the_threshold():
    threshold = int(DEFAULTS["report_threshold"])
    below = _score(source_count=5, upheld_report_count=threshold - 1).score
    at = _score(source_count=5, upheld_report_count=threshold).score

    assert below == 100.0
    assert at == 100.0 - DEFAULTS["report_penalty"]


def test_report_penalty_does_not_stack_beyond_the_threshold():
    threshold = int(DEFAULTS["report_threshold"])
    at = _score(source_count=5, upheld_report_count=threshold).score
    far_past = _score(source_count=5, upheld_report_count=threshold * 10).score
    assert at == far_past


def test_score_is_clamped_to_zero():
    result = _score(
        contributor_accuracy=0.0,
        correction_count=10,
        is_retracted=True,
        upheld_report_count=99,
    )
    assert result.score == 0.0


def test_score_is_clamped_to_100():
    assert _score(contributor_accuracy=100.0, source_count=99).score == 100.0


def test_engine_is_deterministic():
    """The disclosure claim in PRD 1.3.3 requires identical inputs to give
    identical outputs, every time."""
    # 0.75 * 100 accuracy  +  3 * 5 sources  =  90.0
    assert [_score(source_count=3).score for _ in range(20)].count(90.0) == 20


def test_admin_thresholds_change_the_result():
    strict = credibility_score(
        contributor_accuracy=100.0,
        source_count=1,
        correction_count=1,
        is_retracted=False,
        upheld_report_count=0,
        settings={"correction_penalty": 50.0},
    )
    assert strict.score == 30.0  # 75 + 5 - 50


# --------------------------------------------------------------------------- #
#  Disclosure
# --------------------------------------------------------------------------- #

def test_breakdown_components_reconstruct_the_score():
    """Readers must be able to trace exactly why a score is what it is."""
    result = _score(contributor_accuracy=80.0, source_count=3, correction_count=1)

    total = (
        result.accuracy_component
        + result.source_component
        - result.correction_penalty
        - result.retraction_penalty
        - result.report_penalty
    )
    assert round(total, 2) == result.score


def test_breakdown_serialises_for_the_client():
    payload = _score(source_count=2).as_dict()
    assert payload["breakdown"]["sources"] == 10.0
    assert payload["breakdown"]["accuracy"] == 75.0
    assert payload["score"] == 85.0
    assert payload["band"] == "High"
    assert payload["provisional"] is False


@pytest.mark.parametrize(
    "score,expected",
    [(100, "High"), (80, "High"), (79.9, "Moderate"), (60, "Moderate"),
     (59, "Low"), (40, "Low"), (39, "Disputed"), (0, "Disputed")],
)
def test_bands(score, expected):
    assert band_for(score) == expected
