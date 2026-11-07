"""Similar articles from the database, with the corpus kept in memory.

Building the TF-IDF vectors reads every published article, so it is done once
and reused until the set of published articles changes (a cheap query on each
request compares the count and newest id), and at most ten minutes otherwise,
so an edited article is picked up. Not keyed on updated_at: counting a view
touches that, and would rebuild the corpus on every page.
"""
from __future__ import annotations

import threading
import time

from sqlalchemy import func

from . import similar
from .enums import ArticleStatus
from .extensions import db
from .models import Article

_lock = threading.Lock()
_state: dict = {"signature": None, "built": 0.0, "docs": [], "vectors": {}}
MAX_AGE = 600


def _signature():
    return db.session.query(func.count(Article.id), func.max(Article.id)).filter(
        Article.status == ArticleStatus.PUBLISHED).one()


def _corpus():
    signature = tuple(str(x) for x in _signature())
    with _lock:
        if _state["signature"] == signature and time.monotonic() - _state["built"] < MAX_AGE:
            return _state["docs"], _state["vectors"]
    rows = db.session.query(
        Article.id, Article.title, Article.summary, Article.body,
        Article.category_id, Article.country_code,
    ).filter(Article.status == ArticleStatus.PUBLISHED).all()
    docs = [similar.Doc(r.id, r.category_id, r.country_code, similar.terms(r.title, r.summary, r.body))
            for r in rows]
    vecs = similar.vectors(docs)
    with _lock:
        _state.update(signature=signature, built=time.monotonic(), docs=docs, vectors=vecs)
    return docs, vecs


def clear() -> None:
    with _lock:
        _state.update(signature=None, built=0.0, docs=[], vectors={})


def similar_to(article: Article, limit: int = 4) -> list[Article]:
    """Published articles most like this one, best first."""
    docs, vecs = _corpus()
    target = next((d for d in docs if d.id == article.id), None)
    if target is None:
        #Not published (a writer previewing a draft): compare it all the same.
        target = similar.Doc(article.id, article.category_id, article.country_code,
                             similar.terms(article.title, article.summary, article.body))
        vecs = {**vecs, **similar.vectors(docs + [target])}
    ranked = similar.most_similar(target, docs, vecs, limit)
    if not ranked:
        return []
    from .modules.articles import list_loads

    found = {a.id: a for a in Article.query.options(*list_loads())
             .filter(Article.id.in_([i for i, _ in ranked]))}
    return [found[i] for i, _ in ranked if i in found]
