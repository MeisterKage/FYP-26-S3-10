"""Similar articles: the published articles closest in what they are about.

Each article becomes a bag of its content words (stemmed, stop words removed),
headline words counted three times and standfirst words twice, because those
say what the piece is about more reliably than any one body paragraph. Words
are weighted by TF-IDF, so a word every article uses counts for little, and
articles are compared by cosine similarity. Sharing a section or a country adds
a small bonus, enough to break near-ties, never enough to beat real overlap.

Pure functions; the cache and the database live in similar_service.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from . import insights

SAME_SECTION = 0.05
SAME_COUNTRY = 0.03
MIN_SCORE = 0.06  #below this, two articles share little more than common words


@dataclass(frozen=True)
class Doc:
    id: int
    category_id: int | None
    country: str | None
    terms: Counter


def terms(title: str, summary: str, body_html: str) -> Counter:
    body = " ".join(p.text for p in insights.paragraphs(body_html))
    bag = Counter(insights._content(body))
    for word in insights._content(title or ""):
        bag[word] += 3
    for word in insights._content(summary or ""):
        bag[word] += 2
    return bag


def vectors(docs: list[Doc]) -> dict[int, dict[str, float]]:
    """TF-IDF vectors, unit length, keyed by article id."""
    n = len(docs)
    df = Counter()
    for d in docs:
        df.update(d.terms.keys())
    out = {}
    for d in docs:
        total = sum(d.terms.values()) or 1
        vec = {w: (c / total) * math.log((1 + n) / (1 + df[w])) for w, c in d.terms.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        out[d.id] = {w: v / norm for w, v in vec.items()}
    return out


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(w, 0.0) for w, v in a.items())


def most_similar(target: Doc, docs: list[Doc], vecs: dict[int, dict[str, float]],
                 limit: int = 4) -> list[tuple[int, float]]:
    """The ids of the closest articles to `target`, best first, with their scores."""
    mine = vecs.get(target.id)
    if not mine:
        return []
    scored = []
    for d in docs:
        if d.id == target.id:
            continue
        s = cosine(mine, vecs[d.id])
        if s < MIN_SCORE:
            continue
        if target.category_id and d.category_id == target.category_id:
            s += SAME_SECTION
        if target.country and d.country == target.country:
            s += SAME_COUNTRY
        scored.append((d.id, round(s, 4)))
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]
