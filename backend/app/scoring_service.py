"""Database-facing wrapper around the pure engine in `credibility.py`.

The engine itself does no I/O so it can be unit-tested in isolation (PRD 7.5.1).
This module is the only place that reads inputs from the database and writes the
denormalised results back.

Triggers, per PDD Section 3: Article Management calls `rescore_article` on publish
and whenever an input changes; Moderation calls it when a correction or retraction
is logged, or when a report is upheld.
"""
from __future__ import annotations

from sqlalchemy import func

from . import credibility
from .enums import ArticleStatus, ReportStatus
from .extensions import db
from .models import Article, Correction, PlatformSetting, Report, User


def load_settings() -> dict[str, float]:
    """Admin overrides, merged over the shipped defaults by the engine itself."""
    return {row.key: row.value for row in PlatformSetting.query.all()}


#: Articles that count towards a writer's record: everything that was ever
#: published. UNPUBLISHED is included on purpose. Leaving it out meant a writer
#: could unpublish a corrected article and watch their accuracy rate go back up,
#: so a correction could be laundered away. Once published, an article stays on
#: the record, and so does anything logged against it.
RECORD_STATUSES = (ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED, ArticleStatus.UNPUBLISHED)


def _published_counts(contributor_id: int) -> tuple[int, int]:
    """(articles on the writer's record, of which corrected or retracted)."""
    published = (
        db.session.query(func.count(Article.id))
        .filter(
            Article.contributor_id == contributor_id,
            Article.status.in_(RECORD_STATUSES),
        )
        .scalar()
        or 0
    )

    # An article counts as blemished if it was retracted, or carries at least one
    # correction that has not been overturned on appeal (PRD 1.3.2, admin power 4).
    blemished = (
        db.session.query(func.count(func.distinct(Article.id)))
        .outerjoin(Correction, Correction.article_id == Article.id)
        .filter(
            Article.contributor_id == contributor_id,
            Article.status.in_(RECORD_STATUSES),
            db.or_(
                Article.status == ArticleStatus.RETRACTED,
                Correction.overturned_at.is_(None) & Correction.id.isnot(None),
            ),
        )
        .scalar()
        or 0
    )

    return published, blemished


def _is_blemished(article: Article) -> bool:
    """Counted as corrected or retracted in the writer's record."""
    if article.status not in RECORD_STATUSES:
        return False
    return article.status == ArticleStatus.RETRACTED or any(
        c.overturned_at is None for c in article.corrections
    )


def _accuracy_input(article: Article, cfg: dict) -> float:
    """The accuracy figure one article's score is built from.

    The writer's record, minus this article's own correction or retraction.
    That one is already charged to this article directly, as the correction or
    retraction penalty. Counting it again through the accuracy input charged the
    corrected article twice: a correction cost it about 18 points rather than
    the stated 15. Every other article by the writer still carries the lower
    accuracy, which is the intended effect of a correction on a track record.
    """
    published, blemished = _published_counts(article.contributor_id)
    if _is_blemished(article):
        blemished = max(0, blemished - 1)
    return credibility.smoothed_accuracy(published, blemished, cfg)


def _rated_source_points(article: Article, cfg: dict) -> float:
    """Sum of each source's points (source_service.source_points)."""
    from .source_service import source_points

    per_source = float({**credibility.DEFAULTS, **cfg}["source_points"])
    return sum(source_points(s, per_source) for s in article.sources)


def recalculate_accuracy(contributor: User, settings: dict | None = None) -> float | None:
    """Recompute and persist a contributor's Accuracy Rate. Returns it (or None)."""
    cfg = settings if settings is not None else load_settings()
    published, blemished = _published_counts(contributor.id)

    rate = credibility.accuracy_rate(published, blemished, cfg)
    contributor.accuracy_rate = rate
    return rate


def rescore_article(article: Article, settings: dict | None = None):
    """Recompute and persist one article's Credibility Score.

    Returns the ScoreBreakdown so the caller can hand the disclosure to the client
    without a second computation.
    """
    cfg = settings if settings is not None else load_settings()

    # Two different figures on purpose. `recalculate_accuracy` persists the
    # public rate, which is withheld below the minimum article count. The score
    # uses the same curve without that cutoff, so a contributor crossing the
    # minimum does not shift their whole back catalogue in one step.
    published_rate = recalculate_accuracy(article.contributor, cfg)
    accuracy = _accuracy_input(article, cfg)

    valid_sources = sum(1 for s in article.sources if s.is_valid)
    rated_points = _rated_source_points(article, cfg)
    corrections = sum(1 for c in article.corrections if c.overturned_at is None)
    upheld_reports = (
        db.session.query(func.count(Report.id))
        .filter(Report.article_id == article.id, Report.status == ReportStatus.UPHELD)
        .scalar()
        or 0
    )

    result = credibility.credibility_score(
        contributor_accuracy=accuracy,
        source_count=valid_sources,
        correction_count=corrections,
        is_retracted=article.is_retracted,
        upheld_report_count=upheld_reports,
        settings=cfg,
        accuracy_withheld=published_rate is None,
        source_points=rated_points,
    )

    article.credibility_score = result.score
    article.credibility_band = result.band
    return result


def explain_article(article: Article, settings: dict | None = None):
    """Recompute one article's score WITHOUT persisting anything.

    The reader-facing disclosure needs the arithmetic, not just the total, and a
    GET must never write. This reads the same inputs `rescore_article` does and
    runs the same pure function over them, so the ledger a reader sees and the
    number stored on the row cannot drift apart.
    """
    cfg = settings if settings is not None else load_settings()

    published, blemished = _published_counts(article.contributor_id)
    accuracy = _accuracy_input(article, cfg)

    upheld = (
        db.session.query(func.count(Report.id))
        .filter(Report.article_id == article.id, Report.status == ReportStatus.UPHELD)
        .scalar()
        or 0
    )

    return credibility.credibility_score(
        contributor_accuracy=accuracy,
        source_count=sum(1 for s in article.sources if s.is_valid),
        correction_count=sum(1 for c in article.corrections if c.overturned_at is None),
        is_retracted=article.is_retracted,
        upheld_report_count=upheld,
        settings=cfg,
        accuracy_withheld=credibility.accuracy_rate(published, blemished, cfg) is None,
        source_points=_rated_source_points(article, cfg),
    )


def rescore_contributor_articles(contributor: User) -> None:
    """A contributor's accuracy feeds every one of their articles.

    So a correction on one article moves the score of all of them, and we
    recompute the set in a single transaction rather than leaving the others
    stale.
    """
    cfg = load_settings()
    recalculate_accuracy(contributor, cfg)

    articles = Article.query.filter(
        Article.contributor_id == contributor.id,
        Article.status.in_([ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED]),
    ).all()

    for article in articles:
        rescore_article(article, cfg)
