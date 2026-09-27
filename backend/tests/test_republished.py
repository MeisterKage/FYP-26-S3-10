"""Republished articles: credited, not treated as copying their original, not subscribable."""
import json

import pytest

from app import source_fetch
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleSource, Category, User, utcnow
from app.originality_service import check

TEXT = ("<p>Unemployment rose to 4.6% in August, new figures show, the highest level in "
        "several years, and economists expect the central bank to hold rates steady while "
        "it watches whether the rise in joblessness continues into the spring.</p>")
ORIGINAL = "https://theconversation.com/unemployment-rises-123"


@pytest.fixture()
def republished(app):
    category = Category(name="Business", slug="business")
    publisher = User(email="pub@example.com", display_name="The Conversation",
                     password_hash="x", role=Role.VERIFIED_CONTRIBUTOR)
    _db.session.add_all([category, publisher])
    _db.session.commit()
    article = Article(
        contributor_id=publisher.id, category_id=category.id, title="Unemployment rises",
        slug="unemployment-rises", body=TEXT, status=ArticleStatus.PUBLISHED,
        published_at=utcnow(),
        republication=json.dumps({
            "publisher": "The Conversation", "authors": ["Jeff Borland, University of Melbourne"],
            "url": ORIGINAL, "licence": "CC BY-ND 4.0",
            "licenceUrl": "https://creativecommons.org/licenses/by-nd/4.0/",
            "counterUrl": "https://counter.theconversation.com/content/123/count.gif",
        }),
    )
    _db.session.add(article)
    _db.session.flush()
    _db.session.add(ArticleSource(article_id=article.id, url=ORIGINAL, label="Original"))
    _db.session.commit()
    return article


def test_the_article_carries_its_credits(client, republished):
    a = client.get("/api/articles/unemployment-rises").get_json()["article"]
    assert a["republication"]["authors"] == ["Jeff Borland, University of Melbourne"]
    assert a["republication"]["url"] == ORIGINAL
    assert a["writer"]["offersSubscription"] is False


def test_matching_its_own_original_is_not_counted_as_copying(app, republished, monkeypatch):
    page = source_fetch.Fetched(ORIGINAL, "text/html", TEXT)
    monkeypatch.setattr("app.originality_service.fetch", lambda url: page)
    report = check(republished, fetch_sources=True)
    assert report["percent"] == 0.0
    assert report["republishedFrom"]["publisher"] == "The Conversation"
