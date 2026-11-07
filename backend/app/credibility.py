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
            + min(best sources_counted sources, source_cap)  # verifiable sourcing
            - corrections * correction_penalty           # each logged correction
            - retraction_penalty   if retracted
            - report_penalty       if upheld_reports >= report_threshold

    clamped to [0, 100].

Only the best `sources_counted` sources (five) earn points, each worth up to
`source_points` (five) by its rating. Adding more links cannot raise a score;
adding better ones can. So five strong sources earn the full 25, and three
strong ones padded with five unrated sites earn 5+5+5+2+2 = 19.

With shipped defaults the ceiling is exactly 100: a contributor at 100% accuracy
(0.75 * 100 = 75) who cites five well-rated sources (25) scores 100.

Every constant is a row in PlatformSetting, editable by a System Administrator
(PRD Section 1.3.2, administrator power 5). Defaults live in DEFAULTS below and
are used whenever a setting has not been overridden.
"""
from dataclasses import dataclass

#: Shipped defaults for every tunable constant. Admin overrides live in
#: PlatformSetting rows keyed by these same names.
DEFAULTS: dict[str, float] = {
    #Accuracy rate
    "min_articles_for_accuracy": 5,     #below this, show "New Contributor"
    "provisional_accuracy": 70.0,
    #: How many articles' worth of the baseline is blended into an accuracy
    #: rate. Higher means a record moves more slowly and small samples are
    #: treated more cautiously.
    "smoothing_articles": 5.0,       #stand-in accuracy for new contributors
    #Credibility score
    "accuracy_weight": 0.75,            #accuracy 0-100 contributes 0-75
    "source_points": 5.0,               #points per verifiable source link
    "source_cap": 25.0,                 #sourcing cannot contribute more than this
    "sources_counted": 5,               #only the best this many sources earn points
    "correction_penalty": 15.0,         #per logged correction
    "retraction_penalty": 40.0,         #one-off, if retracted
    "report_threshold": 10,             #upheld reports needed to trigger penalty
    "report_penalty": 10.0,             #applied once the threshold is crossed
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
    score is what it is. The transparency claim in PRD Section 1.3.3 holds only
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
    #: How many sources were eligible and how many earned points, so the
    #: ledger can say "best 5 of 8" instead of an unexplained figure.
    sources_cited: int = 0
    sources_counted: int = 0

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
            "sourcing": {"cited": self.sources_cited, "counted": self.sources_counted},
        }


def band_for(score: float) -> str:
    for floor, label in BANDS:
        if score >= floor:
            return label
    return BANDS[-1][1]


def smoothed_accuracy(
    published_count: int,
    corrected_or_retracted_count: int,
    settings: dict | None = None,
) -> float:
    """The accuracy figure the scoring engine uses, at any article count.

    Always a number. `accuracy_rate` below is the same curve, withheld from
    display until the contributor has published enough to show it.
    """
    cfg = {**DEFAULTS, **(settings or {})}

    clean = max(0, published_count - corrected_or_retracted_count)
    k = float(cfg["smoothing_articles"])
    prior = float(cfg["provisional_accuracy"]) / 100.0

    return round(100.0 * (clean + k * prior) / (max(0, published_count) + k), 2)


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

    #Smoothed toward the platform baseline rather than a raw clean/total ratio.
    #
    #A raw ratio punishes small records unfairly hard. With five articles, one
    #correction took a writer from 100% to 80%, removing 15 points from every
    #article they had ever published; the same correction against a writer with
    #forty articles cost under two. Same mistake, eight times the penalty,
    #purely for being new.
    #
    #It is the same adjustment used for rating averages everywhere: an average
    #over few observations is pulled toward the population mean until there is
    #enough evidence to trust it.
    return smoothed_accuracy(published_count, corrected_or_retracted_count, cfg)


def credibility_score(
    *,
    contributor_accuracy: float | None,
    source_count: int,
    correction_count: int,
    is_retracted: bool,
    upheld_report_count: int,
    settings: dict | None = None,
    accuracy_withheld: bool = False,
    source_points: float | None = None,
) -> ScoreBreakdown:
    """Score one article. Pure: no database access, no clock, no randomness.

    `contributor_accuracy` is the smoothed figure from `smoothed_accuracy`, which
    exists at every article count. Passing None falls back to the bare baseline,
    which is only useful for a contributor with no record at all.

    `accuracy_withheld` says the contributor has not yet published enough for
    their rate to be shown publicly. It changes nothing about the arithmetic; it
    marks the ledger so a reader is told the writer is new rather than being
    shown a figure the profile page refuses to display.
    """
    cfg = {**DEFAULTS, **(settings or {})}

    accuracy = (
        cfg["provisional_accuracy"] if contributor_accuracy is None else contributor_accuracy
    )
    used_provisional = accuracy_withheld or contributor_accuracy is None

    accuracy_component = cfg["accuracy_weight"] * accuracy
    #`source_points` is the sum of each cited source's rating
    #(source_rating.py): a government page or a reliable outlet is worth more
    #than an unrated site, and a placeholder or retracted paper nothing. Without
    #it, every source counts the flat `source_points`. Either way only the best
    #`sources_counted` sources count (the caller picks them for rated sources).
    limit = int(cfg["sources_counted"])
    counted = min(max(0, source_count), limit)
    raw_sources = (
        counted * cfg["source_points"] if source_points is None
        else max(0.0, source_points)
    )
    source_component = min(raw_sources, cfg["source_cap"])

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
        sources_cited=max(0, source_count),
        sources_counted=counted,
    )
