"""Tone and trend analysis for an article."""
from datetime import timedelta

import pytest

from app import analysis
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleDailyView, Category, User, utcnow
from app.security import hash_password

GOOD = "<p>The team celebrated a wonderful, successful win. Fans were delighted and proud.</p>"
BAD = "<p>The flood destroyed homes and killed livestock. Residents were angry and afraid.</p>"


def test_tone_reads_the_language():
    assert analysis.tone(GOOD)["band"] in {"positive", "leans_positive"}
    assert analysis.tone(BAD)["band"] in {"negative", "leans_negative"}
    t = analysis.tone(GOOD + BAD)
    assert len(t["paragraphs"]) == 2 and t["mostPositive"] and t["mostNegative"]


def test_direction_compares_this_week_with_last():
    flat = [{"count": 5}] * 14
    assert analysis.direction(flat) == "steady"
    assert analysis.direction([{"count": 1}] * 7 + [{"count": 4}] * 7) == "rising"
    assert analysis.direction([{"count": 4}] * 7 + [{"count": 1}] * 7) == "falling"
    assert analysis.direction([{"count": 0}] * 14) == "quiet"


@pytest.fixture()
def story(app):
    sport = Category(name="Sport", slug="sport")
    w = User(email="w@example.com", display_name="W", role=Role.VERIFIED_CONTRIBUTOR,
             password_hash=hash_password("Analysis12345!"))
    _db.session.add_all([sport, w])
    _db.session.commit()
    a = Article(contributor_id=w.id, category_id=sport.id, title="Win", slug="win", body=GOOD,
                status=ArticleStatus.PUBLISHED, published_at=utcnow())
    _db.session.add(a)
    _db.session.commit()
    return a


def test_each_view_is_recorded_for_the_day(client, story):
    client.get("/api/articles/win")
    client.get("/api/articles/win")
    row = ArticleDailyView.query.filter_by(article_id=story.id).one()
    assert row.views == 2 and row.day == utcnow().date()


def test_the_analysis_endpoint_reports_tone_trend_and_topic(client, story):
    _db.session.add(ArticleDailyView(article_id=story.id, day=utcnow().date() - timedelta(days=10), views=3))
    _db.session.commit()
    client.get("/api/articles/win")
    data = client.get("/api/articles/win/analysis").get_json()
    assert data["tone"]["band"] in {"positive", "leans_positive"}
    assert len(data["trend"]["views"]) == 14
    assert data["trend"]["viewsInPeriod"] == 4 and data["trend"]["direction"] == "falling"
    assert data["topic"]["name"] == "Sport" and len(data["topic"]["weekly"]) == 8


def test_paywalled_text_is_not_analysed_for_outsiders(client, story):
    story.is_premium = True
    _db.session.commit()
    assert client.get("/api/articles/win/analysis").get_json()["tone"] is None
