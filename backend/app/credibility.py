"""The scoring engine (PDD Section 2.2, PRD Section 1.3.3).

Both published figures come from a *fixed, disclosed formula*. Nothing here is
learned, predicted, or weighted by a model: given the same inputs, this module
returns the same number every time, and every constant is visible to readers on
the About page.

--------------------------------------------------------------------------------
ACCURACY RATE  (per contributor, 0-100)
--------------------------------------------------------------------------------

    clean      = published articles never corrected and never retracted
    total      = published articles
    accuracy   = 100 * clean / total

Withheld until the contributor has published at least `min_articles_for_accuracy`
articles; until then the profile shows "New Contributor" (PRD Section 1.3.3) and
scoring substitutes `provisional_accuracy` so a first article is neither
rewarded nor punished for having no track record.

--------------------------------------------------------------------------------
CREDIBILITY SCORE  (per article, 0-100)
--------------------------------------------------------------------------------

    score =   accuracy_weight * accuracy_rate            # contributor track record
            + min(sources * source_points, source_cap)   # verifiable sourcing
            - corrections * correction_penalty           # each logged correction
            - retraction_penalty   if retracted
            - report_penalty       if upheld_reports >= report_threshold

    clamped to [0, 100].

With shipped defaults the ceiling is exactly 100: a contributor at 100% accuracy
(0.75 * 100 = 75) who tags five or more sources (capped at 25) scores 100.

Every constant is a row in PlatformSetting, editable by a System Administrator
(PRD Section 1.3.2, administrator power 5). Defaults live in DEFAULTS below and
are used whenever a setting has not been overridden.
"""
from dataclasses import dataclass

#: Shipped defaults for every tunable constant. Admin overrides live in
#: PlatformSetting rows keyed by these same names.
DEFAULTS: dict[str, float] = {
    # Accuracy rate
    "min_articles_for_accuracy": 5,     # below this, show "New Contributor"
    "provisional_accuracy": 70.0,       # stand-in accuracy for new contributors
    # Credibility score
    "accuracy_weight": 0.75,            # accuracy 0-100 contributes 0-75
    "source_points": 5.0,               # points per verifiable source link
    "source_cap": 25.0,                 # sourcing cannot contribute more than this
    "correction_penalty": 15.0,         # per logged correction
    "retraction_penalty": 40.0,         # one-off, if retracted
    "report_threshold": 10,             # upheld reports needed to trigger penalty
    "report_penalty": 10.0,             # applied once the threshold is crossed
}

#: Disclosed bands, used for the reader-facing label beside the numeric score.
BANDS: tuple[tuple[float, str], ...] = (
    (80.0, "High"),
    (60.0, "Moderate"),
    (40.0, "Low"),
    (0.0, "Disputed"),
)


@dataclass(frozen=True)
class ScoreBreakdown:
    """A score plus the arithmetic that produced it.

    Returned to the client so the article page can show readers exactly why the
    score is what it is -- the transparency claim in PRD Section 1.3.3 holds only
    if the breakdown travels with the number.
    """

    score: float
    band: str
    accuracy_component: float
    source_component: float
    correction_penalty: float
    retraction_penalty: float
    report_penalty: float
    used_provisional_accuracy: bool

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "band": self.band,
            "breakdown": {
                "accuracy": self.accuracy_component,
                "sources": self.source_component,
                "corrections": -self.correction_penalty,
                "retraction": -self.retraction_penalty,
                "reports": -self.report_penalty,
            },
            "provisional": self.used_provisional_accuracy,
        }


def band_for(score: float) -> str:
    for floor, label in BANDS:
        if score >= floor:
            return label
    return BANDS[-1][1]


def accuracy_rate(
    published_count: int,
    corrected_or_retracted_count: int,
    settings: dict | None = None,
) -> float | None:
    """Contributor accuracy, or None while the contributor is still 'New'.

    None is a meaningful value here and must not be coerced to 0.0: a new
    contributor has *no* accuracy rate, which is not the same as a bad one.
    """
    cfg = {**DEFAULTS, **(settings or {})}

    if published_count < int(cfg["min_articles_for_accuracy"]):
        return None
    if published_count <= 0:
        return None

    clean = max(0, published_count - corrected_or_retracted_count)
    return round(100.0 * clean / published_count, 2)


def credibility_score(
    *,
    contributor_accuracy: float | None,
    source_count: int,
    correction_count: int,
    is_retracted: bool,
    upheld_report_count: int,
    settings: dict | None = None,
) -> ScoreBreakdown:
    """Score one article. Pure: no database access, no clock, no randomness.

    `contributor_accuracy` of None means the contributor has not yet reached the
    minimum article count, so the provisional rate stands in for it.
    """
    cfg = {**DEFAULTS, **(settings or {})}

    used_provisional = contributor_accuracy is None
    accuracy = cfg["provisional_accuracy"] if used_provisional else contributor_accuracy

    accuracy_component = cfg["accuracy_weight"] * accuracy
    source_component = min(max(0, source_count) * cfg["source_points"], cfg["source_cap"])

    corrections = max(0, correction_count) * cfg["correction_penalty"]
    retraction = cfg["retraction_penalty"] if is_retracted else 0.0
    reports = (
        cfg["report_penalty"]
        if upheld_report_count >= int(cfg["report_threshold"])
        else 0.0
    )

    raw = accuracy_component + source_component - corrections - retraction - reports
    score = round(min(100.0, max(0.0, raw)), 2)

    return ScoreBreakdown(
        score=score,
        band=band_for(score),
        accuracy_component=round(accuracy_component, 2),
        source_component=round(source_component, 2),
        correction_penalty=round(corrections, 2),
        retraction_penalty=round(retraction, 2),
        report_penalty=round(reports, 2),
        used_provisional_accuracy=used_provisional,
    )
