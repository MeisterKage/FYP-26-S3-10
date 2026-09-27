"""Only the best five sources earn points, and an article cannot cite itself."""
import json

from app import credibility
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleSource, Category, User, utcnow
from app.scoring_service import explain_article


def make_article(sources, republished_from=None):
    category = Category(name="Science", slug="science")
    writer = User(email="w@example.com", display_name="W", password_hash="x",
                  role=Role.VERIFIED_CONTRIBUTOR)
    _db.session.add_all([category, writer])
    _db.session.commit()
    article = Article(contributor_id=writer.id, category_id=category.id, title="T", slug="t",
                      body="<p>b</p>", status=ArticleStatus.PUBLISHED, published_at=utcnow(),
                      republication=json.dumps({"url": republished_from}) if republished_from else None)
    _db.session.add(article)
    _db.session.flush()
    for i, (tier, points) in enumerate(sources):
        url = republished_from if (republished_from and i == 0) else f"https://site{i}.org/page"
        _db.session.add(ArticleSource(article_id=article.id, url=url, label="s",
                                      tier=tier, points=points))
    _db.session.commit()
    return article


def test_flat_counting_stops_at_five_sources():
    r = credibility.credibility_score(contributor_accuracy=80, source_count=8, correction_count=0,
                                      is_retracted=False, upheld_report_count=0)
    assert r.source_component == 25.0
    assert r.as_dict()["sourcing"] == {"cited": 8, "counted": 5}


def test_weak_links_cannot_pad_a_score_to_the_cap(app):
    article = make_article([("reliable", 5.0)] * 3 + [("unrated", 2.0)] * 5)
    b = explain_article(article)
    assert b.source_component == 19.0          # 5 + 5 + 5 + 2 + 2
    assert b.as_dict()["sourcing"] == {"cited": 8, "counted": 5}


def test_five_strong_sources_still_earn_the_full_25(app):
    article = make_article([("official", 5.0)] * 5 + [("unrated", 2.0)] * 3)
    assert explain_article(article).source_component == 25.0


def test_a_republished_article_does_not_count_its_own_original(app):
    original = "https://theconversation.com/some-article-123"
    article = make_article([("reliable", 5.0)] + [("unrated", 2.0)] * 3, republished_from=original)
    b = explain_article(article)
    assert b.source_component == 6.0           # the three unrated sources only
    assert b.as_dict()["sourcing"]["cited"] == 3
