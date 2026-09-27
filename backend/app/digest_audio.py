"""The audio edition of a monthly digest: an e-book a reader can listen to.

An edition becomes a short book in chapters:

    Introduction        what the edition covers, and the month in numbers
    The month in brief  one line on every ranked article
    One per article     its key points, in its writer's own sentences
    Corrections         what was corrected or retracted, and why
    Closing

Every chapter is a list of spoken parts (one sentence or short line each), so
the player can highlight what is being read and jump between chapters.

Two things are never read out in full:
  * a subscriber-only article, for a listener who does not subscribe: its
    headline and public summary only, as on any list;
  * a republished article: its licence (CC BY-ND) forbids adaptations, and a
    summary is one, so it gets its credit and its own opening paragraph,
    unchanged.
"""
from __future__ import annotations

import calendar
import json
from datetime import datetime

from . import credibility, insights
from .enums import ArticleStatus
from .insights_service import ProviderNotConfigured, narrator, summariser, _cached
from .models import Article, Category, DigestEdition

SITE = "Wollongong News"
#: Speaking pace used for the running time, in words per minute at 1x.
SPOKEN_WPM = 160


def _day(dt: datetime | None) -> str:
    return f"{dt.day} {calendar.month_name[dt.month]}" if dt else ""


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _plain(text: str) -> str:
    return " ".join(insights.words(text)).lower()


def _summary_sentences(article: Article) -> list[str]:
    """The article's public summary, minus any sentence that only repeats its headline."""
    headline = _plain(article.title)
    return [s for s in insights.sentences(article.summary or "") if _plain(s) != headline]


def _key_points(article: Article) -> list[str]:
    s = summariser()
    summary = _cached("summary", s.name, article.body, lambda: s.summarise(article.body))
    return summary.points


def _article_chapter(entry, viewer, may_read) -> dict:
    article: Article = entry.article
    title = article.title.rstrip(".")
    chapter = {
        "id": f"article-{article.id}",
        "kind": "article",
        "rank": entry.rank,
        "title": article.title,
        "slug": article.slug if article.status in (ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED) else None,
        "parts": [f"Number {entry.rank}. {title}."],
    }
    parts = chapter["parts"]

    if article.status != ArticleStatus.PUBLISHED:
        parts.append("This article has been retracted since the digest was compiled, so it is not read here."
                     if article.status == ArticleStatus.RETRACTED
                     else "This article is no longer published, so it is not read here.")
        chapter["lead"] = None
        return chapter

    republished = json.loads(article.republication) if article.republication else None
    if republished:
        authors = "; ".join(republished.get("authors") or [])
        parts.append(f"By {authors}. Republished from {republished.get('publisher')} "
                     "under a Creative Commons licence.")
        opening = _summary_sentences(article)
        parts.extend(opening)
        parts.append(f"The full article is on {SITE}, with a link to the original.")
        chapter["lead"] = opening[0] if opening else None
        return chapter

    score = article.credibility_score or 0
    parts.append(f"By {article.contributor.byline}, published {_day(article.published_at)}. "
                 f"Credibility score {round(score)}, rated {credibility.band_for(score)}.")

    if article.is_premium and not may_read(article, viewer):
        parts.extend(_summary_sentences(article))
        parts.append(f"The full article is for {article.contributor.byline}'s subscribers.")
        chapter["lead"] = " ".join(_summary_sentences(article)) or None
        return chapter

    points = _key_points(article)
    if not points:
        points = _summary_sentences(article)
    parts.extend(points)
    chapter["lead"] = points[0] if points else None
    return chapter


def audio_edition(edition: DigestEdition, category: Category, *, topic: str, month_label: str,
                  provisional: bool, viewer=None) -> dict | None:
    """The chapters, running time and narration mode. None if narration is off."""
    from .modules.articles import may_read

    try:
        voice = narrator().narrate_book()
    except ProviderNotConfigured:
        return None

    data = json.loads(edition.data)
    stats = data["stats"]
    entries = list(edition.entries)
    articles = [_article_chapter(e, viewer, may_read) for e in entries]

    intro = [f"{SITE}. The {topic} digest for {month_label}."]
    if provisional:
        intro.append("This edition is still in progress. The final edition follows when the month ends.")
    intro.append(
        f"This month we published {_count(stats['articleCount'], 'article')} in {topic}, "
        f"by {_count(stats['writerCount'], 'writer')}, with an average credibility score of "
        f"{round(stats['averageCredibility'])}."
    )
    corrections = data["corrections"]
    intro.append(
        "No corrections were logged." if not stats["correctionCount"]
        else f"{_count(stats['correctionCount'], 'correction')} logged, read at the end."
    )
    ranked = ("Here is the most credible article" if len(entries) == 1
              else f"Here are the {len(entries)} most credible articles")
    intro.append(f"{ranked}, ranked by credibility score.")

    overview = []
    for chapter in articles:
        line = f"Number {chapter['rank']}. {chapter['title'].rstrip('.')}."
        if chapter.get("lead"):
            line = f"{line} {chapter['lead']}"
        overview.append(line)

    chapters = [
        {"id": "intro", "kind": "intro", "title": "Introduction", "parts": intro},
        {"id": "overview", "kind": "overview", "title": "The month in brief", "parts": overview},
        *[{k: v for k, v in c.items() if k != "lead"} for c in articles],
    ]
    if corrections:
        spoken = ["What we corrected this month."]
        for c in corrections:
            verb = "Retracted" if c["type"] == "retraction" else "Corrected"
            line = f"{verb}: {c['title'].rstrip('.')}. {c['reason'].rstrip('.')}."
            if c.get("overturned"):
                line += " This was later overturned on appeal."
            spoken.append(line)
        chapters.append({"id": "corrections", "kind": "corrections", "title": "Corrections", "parts": spoken})
    chapters.append({
        "id": "closing", "kind": "closing", "title": "Closing",
        "parts": [f"That is the {topic} digest for {month_label}.",
                  f"Every article is on {SITE} to read in full, with its sources and its score."],
    })

    total = 0
    for c in chapters:
        words = sum(len(p.split()) for p in c["parts"])
        c["seconds"] = round(words * 60 / SPOKEN_WPM)
        total += words
    return {
        "chapters": chapters,
        "minutes": max(1, round(total / SPOKEN_WPM)),
        "narration": voice,
    }
