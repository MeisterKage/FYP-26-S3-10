"""Articles in Mandarin and Malay: translated when current, English with a note otherwise."""
import json

import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleTranslation, Category, User, utcnow
from app.translation_service import source_hash
from demo_bodies import body_for

LONG = "Grid operators report record renewable share in Q3"


@pytest.fixture()
def story(app):
    env = Category(name="Environment", slug="environment")
    w = User(email="w@example.com", display_name="W", password_hash="x", role=Role.VERIFIED_CONTRIBUTOR)
    _db.session.add_all([env, w])
    _db.session.commit()
    a = Article(contributor_id=w.id, category_id=env.id, title=LONG, slug="grid", summary="Wind and solar.",
                body=body_for(LONG), status=ArticleStatus.PUBLISHED, published_at=utcnow())
    _db.session.add(a)
    _db.session.commit()
    _db.session.add(ArticleTranslation(
        article_id=a.id, lang="zh", title="电网运营商报告第三季度可再生能源占比创新高",
        summary="风能和太阳能。", body="<p>风能和太阳能提供了超过一半的电力。</p>",
        points=json.dumps(["要点一。", "要点二。"]), provider="ai",
        source_hash=source_hash(a.title, a.summary, a.body)))
    _db.session.commit()
    return a


def get(client, path):
    return client.get(path).get_json()


def test_a_current_translation_replaces_the_words(client, story):
    a = get(client, "/api/articles/grid?lang=zh")["article"]
    assert a["title"].startswith("电网") and "风能" in a["body"]
    assert a["translation"]["available"] is True and a["translation"]["note"]
    assert a["inBrief"]["points"] == ["要点一。", "要点二。"]
    assert a["inBrief"]["narration"]["voice"]["lang"] == "zh-CN"


def test_english_is_unchanged_and_lists_are_translated_too(client, story):
    assert get(client, "/api/articles/grid")["article"]["title"] == LONG
    titles = [x["title"] for x in get(client, "/api/feed/trending?lang=zh")["articles"]]
    assert titles == ["电网运营商报告第三季度可再生能源占比创新高"]


def test_a_missing_language_falls_back_to_english_with_a_note(client, story):
    a = get(client, "/api/articles/grid?lang=ms")["article"]
    assert a["title"] == LONG and a["translation"]["available"] is False
    assert "Bahasa Melayu" in a["translation"]["note"]


def test_editing_the_english_makes_the_translation_stale(client, story):
    story.body = story.body + "<p>A late correction.</p>"
    _db.session.commit()
    a = get(client, "/api/articles/grid?lang=zh")["article"]
    assert a["title"] == LONG and a["translation"]["available"] is False


def test_a_translated_download_uses_the_translation(client, story):
    r = client.get("/api/articles/grid/download.pdf?lang=zh")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
