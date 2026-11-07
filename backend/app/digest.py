"""Monthly digests: which articles make an edition, and the month in numbers.

Pure, like `credibility.py`: plain data in, an edition out, no database and no
clock, so every rule is tested directly.

An edition ranks a month's articles in one topic (optionally one country) by
credibility score, not by views. A digest is the platform's promise applied
to a whole month: the most trustworthy reporting first. It also lists every
correction logged in that topic that month. A digest that only showed what
went well would be marketing.

Months are calendar months in UTC.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

#: An edition with fewer articles than this is not worth a reader's time.
MIN_ARTICLES = 3
#: Articles listed per edition.
TOP_ARTICLES = 10

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class Candidate:
    article_id: int
    contributor_id: int
    credibility: float
    published_at: datetime


@dataclass(frozen=True)
class CorrectionRecord:
    article_id: int
    article_title: str
    kind: str          #"correction" or "retraction"
    reason: str
    issued_at: datetime
    overturned: bool


@dataclass(frozen=True)
class Edition:
    ranked: list[Candidate]
    stats: dict
    corrections: list[dict]


def parse_month(month: str) -> tuple[datetime, datetime]:
    """"2026-09" to [start, end) in UTC. Raises ValueError on anything else."""
    match = _MONTH.match(month) if isinstance(month, str) else None
    if not match:
        raise ValueError(month)
    year, mon = int(match.group(1)), int(match.group(2))
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    end = datetime(year + (mon == 12), 1 if mon == 12 else mon + 1, 1, tzinfo=timezone.utc)
    return start, end


def previous_month(now: datetime) -> str:
    year, mon = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
    return f"{year:04d}-{mon:02d}"


def edition_key(category_slug: str, country_code: str = "") -> str:
    return f"{category_slug}-{country_code.lower()}" if country_code else category_slug


def compile_edition(
    candidates: list[Candidate],
    corrections: list[CorrectionRecord],
    *,
    min_articles: int = MIN_ARTICLES,
    top: int = TOP_ARTICLES,
) -> Edition | None:
    """Rank a month's published articles in one topic. None if too few to publish.

    Ties on credibility go to the more recent article, then to the lower id, so
    the same inputs always give the same order.
    """
    if len(candidates) < min_articles:
        return None

    ranked = sorted(
        candidates,
        key=lambda c: (-c.credibility, -c.published_at.timestamp(), c.article_id),
    )[:top]
    scores = [c.credibility for c in candidates]
    stats = {
        "articleCount": len(candidates),
        "averageCredibility": round(sum(scores) / len(scores), 1),
        "writerCount": len({c.contributor_id for c in candidates}),
        "correctionCount": sum(1 for c in corrections if not c.overturned),
    }
    listed = [
        {
            "articleId": c.article_id,
            "title": c.article_title,
            "type": c.kind,
            "reason": c.reason,
            "issuedAt": c.issued_at.isoformat(),
            "overturned": c.overturned,
        }
        for c in sorted(corrections, key=lambda c: c.issued_at)
    ]
    return Edition(ranked=ranked, stats=stats, corrections=listed)
