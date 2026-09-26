"""Review triage: which pending article needs a human first, and which may skip one.

Built to the same discipline as `credibility.py`: pure, no database access, no
clock, no randomness. Every input arrives as an argument, including how long an
article has been waiting, so the same inputs always give the same answer and
every rule here can be unit-tested without an application context.

--------------------------------------------------------------------------------
REVIEW PRIORITY  (per pending article, higher = a human is needed sooner)
--------------------------------------------------------------------------------

    priority =  new_contributor_weight                    if the writer is new
             |  accuracy_weight * (baseline - accuracy)   otherwise, if below
             +  missing_source_weight * missing sources
             +  duplicate_weight                           if the title repeats
             +  wait_weight * hours waiting

The wait term is the anti-starvation guarantee. Without it a trusted writer's
article can sit at the bottom of a busy queue indefinitely. With it, everything
surfaces eventually, however safe it looks.

It has to stay a tiebreaker, though, not a driver. The first shipped value, 0.5
an hour, overtook a whole new-writer flag in three days, so in a real backlog,
where articles wait days, the queue quietly reverted to oldest-first: the very
behaviour this module replaces. At 0.1 an hour (2.4 a day) two weeks of waiting
adds about 34, less than a single risk signal, so risk still sets the order; past
roughly a month a safe article outranks even an unsourced one from a new writer
(40 + 30), so nothing starves.

--------------------------------------------------------------------------------
AUTO-PUBLISH  (a pressure valve, off by default)
--------------------------------------------------------------------------------

The valve opens only when the queue is genuinely overloaded, and even then only
for articles that pass every eligibility rule below. Anything it publishes is
labelled for readers until an editor confirms it. The rules exist because a
per-writer trust score invites one specific attack: publish a run of accurate
articles, clear the bar, then spend the standing once on something false.
Revocation (in the service layer) is what makes that expensive.
"""
from dataclasses import dataclass, field

from .originality import DEFAULTS as ORIGINALITY_DEFAULTS

#: Shipped defaults. Admin overrides live in PlatformSetting rows keyed by these
#: same names. Kept apart from credibility.DEFAULTS so the scoring engine stays
#: about scoring; the admin endpoint validates against the union of the two.
DEFAULTS: dict[str, float] = {
    # ---- queue ordering ----
    "triage_new_contributor_weight": 40.0,  # a writer with no record yet
    "triage_accuracy_baseline": 90.0,       # accuracy at or above adds nothing
    "triage_accuracy_weight": 1.0,          # per accuracy point below baseline
    "triage_expected_sources": 3,           # sourcing below this adds priority
    "triage_missing_source_weight": 10.0,   # per missing source
    "triage_duplicate_weight": 30.0,        # title matches another article
    # Text matching elsewhere, scaled by how much: 50% overlap adds 30, 100%
    # adds 60, as much as a new writer and an unsourced article combined.
    # Applied only at or above originality_flag_percent.
    "triage_similarity_weight": 60.0,
    **ORIGINALITY_DEFAULTS,
    "triage_wait_weight": 0.1,              # per hour waiting: 2.4 a day, see below
    # ---- auto-publish valve ----
    "autopublish_enabled": 0,               # 0 = off, 1 = on. Off by default.
    "autopublish_queue_depth": 25,          # opens above this many pending...
    "autopublish_max_wait_hours": 48,       # ...or once the oldest waits this long
    "autopublish_min_accuracy": 90.0,       # writer must be at least this accurate
    "autopublish_min_articles": 10,         # over at least this many articles
    "autopublish_suspension_days": 90,      # lost after a correction on one
    "autopublish_max_per_run": 20,          # blast radius of a single sweep
}

@dataclass(frozen=True)
class PriorityBreakdown:
    """A priority plus the arithmetic that produced it.

    Sent to the review queue so an editor can see why an article is where it is,
    in the same spirit as the credibility ledger a reader sees.
    """

    priority: float
    new_contributor: float
    accuracy: float
    sources: float
    duplicate: float
    waiting: float
    similarity: float = 0.0

    def as_dict(self) -> dict:
        return {
            "priority": self.priority,
            "breakdown": {
                "newContributor": self.new_contributor,
                "accuracy": self.accuracy,
                "sources": self.sources,
                "duplicate": self.duplicate,
                "similarity": self.similarity,
                "waiting": self.waiting,
            },
        }


@dataclass(frozen=True)
class Eligibility:
    """Whether an article may be auto-published, and every reason it may not."""

    eligible: bool
    reasons: list[str] = field(default_factory=list)


def _cfg(settings: dict | None) -> dict:
    return {**DEFAULTS, **(settings or {})}


def review_priority(
    *,
    contributor_accuracy: float | None,
    source_count: int,
    has_duplicate_title: bool,
    hours_waiting: float,
    similarity_percent: float | None = None,
    settings: dict | None = None,
) -> PriorityBreakdown:
    """Rank one pending article. Pure: the caller supplies the wait time.

    `contributor_accuracy` is the public accuracy rate, which is None while the
    writer is still new. None is treated as its own signal rather than as zero:
    a new writer has no record, which is not the same as a bad one, but it does
    mean nobody has any evidence yet, and that is exactly when a human should look.
    """
    cfg = _cfg(settings)

    if contributor_accuracy is None:
        new_contributor = float(cfg["triage_new_contributor_weight"])
        accuracy = 0.0
    else:
        new_contributor = 0.0
        shortfall = max(0.0, float(cfg["triage_accuracy_baseline"]) - contributor_accuracy)
        accuracy = float(cfg["triage_accuracy_weight"]) * shortfall

    missing = max(0, int(cfg["triage_expected_sources"]) - max(0, source_count))
    sources = float(cfg["triage_missing_source_weight"]) * missing

    duplicate = float(cfg["triage_duplicate_weight"]) if has_duplicate_title else 0.0
    waiting = float(cfg["triage_wait_weight"]) * max(0.0, hours_waiting)

    percent = similarity_percent or 0.0
    similarity = (
        float(cfg["triage_similarity_weight"]) * percent / 100.0
        if percent >= float(cfg["originality_flag_percent"]) else 0.0
    )

    total = new_contributor + accuracy + sources + duplicate + waiting + similarity
    return PriorityBreakdown(
        priority=round(total, 2),
        new_contributor=round(new_contributor, 2),
        accuracy=round(accuracy, 2),
        sources=round(sources, 2),
        duplicate=round(duplicate, 2),
        waiting=round(waiting, 2),
        similarity=round(similarity, 2),
    )


def valve_open(
    *,
    queue_depth: int,
    oldest_wait_hours: float,
    settings: dict | None = None,
) -> bool:
    """Is the queue overloaded enough, and the feature switched on, to auto-publish?"""
    cfg = _cfg(settings)
    if not int(cfg["autopublish_enabled"]):
        return False
    return (
        queue_depth > int(cfg["autopublish_queue_depth"])
        or oldest_wait_hours >= float(cfg["autopublish_max_wait_hours"])
    )


def autopublish_eligibility(
    *,
    contributor_accuracy: float | None,
    published_count: int,
    suspended: bool,
    source_count: int,
    has_duplicate_title: bool,
    is_premium: bool,
    similarity_percent: float | None = 0.0,
    settings: dict | None = None,
) -> Eligibility:
    """May this one article skip review? Returns every failing rule, not the first.

    Collecting all the reasons rather than returning early is deliberate: an
    administrator tuning the thresholds needs to see everything that held an
    article back, and a test can assert on a precise set of reasons.
    """
    cfg = _cfg(settings)
    reasons: list[str] = []

    if contributor_accuracy is None:
        reasons.append("writer has no accuracy record yet")
    elif contributor_accuracy < float(cfg["autopublish_min_accuracy"]):
        reasons.append("writer accuracy below the auto-publish bar")

    if published_count < int(cfg["autopublish_min_articles"]):
        reasons.append("writer has too few published articles")
    if suspended:
        reasons.append("writer is suspended from auto-publish")
    if source_count < 1:
        reasons.append("no verified source tagged")
    if has_duplicate_title:
        reasons.append("title matches another article")
    if similarity_percent is None:
        reasons.append("originality has not been checked")
    elif similarity_percent >= float(cfg["originality_flag_percent"]):
        # Anything flagged waits for a person. Auto-publish is for articles
        # with nothing to judge, and matching text is always a judgement.
        reasons.append("text matches another article or a cited source")
    if is_premium:
        # A reader who is paying gets an article a human has read.
        reasons.append("premium articles always need an editor")

    return Eligibility(eligible=not reasons, reasons=reasons)
