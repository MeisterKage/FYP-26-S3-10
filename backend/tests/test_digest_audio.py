"""The audio edition of a monthly digest: chapters, summaries, and what is never read out."""
import json
from datetime import datetime, timezone

import pytest

from app.digest_service import compile_month
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.insights import key_points
from app.insights_service import clear_cache
from app.models import Article, Category, User
from app.security import hash_password
from demo_bodies import body_for

PASSWORD = "DigestAudio12345!"
LONG = "Tokyo hospitals trial robotic lifting assistance in elderly care wards"
AFTER_SEPTEMBER = datetime(2026, 10, 1, 3, tzinfo=timezone.utc)


@pytest.fixture()
def world(app):
    clear_cache()
    tech = Category(name="Technology", slug="technology")
    writer = User(email="w@example.com", display_name="Mei Tanaka",
                  password_hash=hash_password(PASSWORD), role=Role.VERIFIED_CONTRIBUTOR)
    reader = User(email="r@example.com", display_name="Reader",
                  password_hash=hash_password(PASSWORD), role=Role.FREE_REGISTERED)
    _db.session.add_all([tech, writer, reader])
    _db.session.commit()
    stories = {}
    for n, (slug, score, extra) in enumerate([
        ("long", 90, {}),
        ("premium", 85, {"is_premium": True, "summary": "A subscriber-only look at robots."}),
        ("republished", 80, {"summary": "Robots are arriving on hospital wards. Nurses are cautious.",
                             "republication": json.dumps({"publisher": "The Conversation",
                                                          "authors": ["A. Author, Uni"],
                                                          "url": "https://theconversation.com/x-1"})}),
        ("repeats", 75, {"is_premium": True, "summary": "Repeats its headline. What the change means."}),
    ]):
        stories[slug] = Article(
            contributor_id=writer.id, category_id=tech.id,
            title="Repeats its headline" if slug == "repeats" else f"Story {slug}",
            slug=slug, body=body_for(LONG), status=ArticleStatus.PUBLISHED,
            published_at=datetime(2026, 9, 10 + n, 12, tzinfo=timezone.utc),
            credibility_score=score, **extra)
        _db.session.add(stories[slug])
    _db.session.commit()
    compile_month("2026-09", now=AFTER_SEPTEMBER)
    return stories


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def listen(client, headers=None):
    return client.get("/api/digests/2026-09/technology", headers=headers or {}
                      ).get_json()["edition"]["listen"]


def chapter(book, slug):
    return next(c for c in book["chapters"] if c.get("slug") == slug)


def test_the_edition_reads_as_a_book_in_chapters(client, world):
    book = listen(client)
    kinds = [c["kind"] for c in book["chapters"]]
    assert kinds[:2] == ["intro", "overview"] and kinds[-1] == "closing"
    assert kinds.count("article") == 4
    assert "The Technology digest for September 2026" in book["chapters"][0]["parts"][0]
    assert len(book["chapters"][1]["parts"]) == 4          # one line per article
    assert book["minutes"] >= 1 and all(c["seconds"] > 0 for c in book["chapters"])
    assert book["narration"]["mode"] == "browser"


def test_an_article_chapter_reads_its_key_points(client, world):
    parts = chapter(listen(client), "long")["parts"]
    assert parts[0] == "Number 1. Story long."
    assert "Mei Tanaka" in parts[1] and "rated High" in parts[1]
    assert parts[2:] == key_points(body_for(LONG))


def test_subscriber_only_articles_are_summarised_only_for_subscribers(client, world):
    parts = chapter(listen(client), "premium")["parts"]
    assert "A subscriber-only look at robots." in parts
    assert not set(key_points(body_for(LONG))) & set(parts)
    as_writer = chapter(listen(client, auth(client, "w@example.com")), "premium")["parts"]
    assert set(key_points(body_for(LONG))) <= set(as_writer)


def test_republished_articles_are_credited_and_read_unchanged(client, world):
    parts = chapter(listen(client), "republished")["parts"]
    assert "By A. Author, Uni. Republished from The Conversation" in parts[1]
    assert parts[2:4] == ["Robots are arriving on hospital wards.", "Nurses are cautious."]
    assert not set(key_points(body_for(LONG))) & set(parts)


def test_a_summary_that_repeats_the_headline_is_not_read_twice(client, world):
    overview = listen(client)["chapters"][1]["parts"]
    line = next(p for p in overview if "Repeats its headline" in p)
    assert line.count("Repeats its headline") == 1


def test_no_narration_provider_means_no_audio_edition(client, world, app):
    app.config["NARRATION_PROVIDER"] = "cloud"
    r = client.get("/api/digests/2026-09/technology")
    assert r.status_code == 200 and r.get_json()["edition"]["listen"] is None
