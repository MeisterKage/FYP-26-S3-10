"""New articles are translated into Mandarin and Malay as they are published.

The translation service is replaced by a stand-in that answers the way the
Messages API does; nothing here leaves the machine.
"""
import io
import json
import re
import urllib.request

import pytest

from app import translation_service as ts
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleTranslation, Category, User, utcnow
from app.security import hash_password
from demo_bodies import body_for

PASSWORD = "Translate12345!"
LONG = "Grid operators report record renewable share in Q3"


class FakeApi:
    """Answers like api.anthropic.com/v1/messages, marking each text as translated."""

    def __init__(self):
        self.requests = []
        self.mangle = None

    def __call__(self, req, timeout=None):
        payload = json.loads(req.data.decode("utf-8"))
        self.requests.append({"headers": dict(req.header_items()), "payload": payload})
        article = json.loads(payload["messages"][0]["content"].split("\n\n", 1)[1])
        mark = "译" if "Chinese" in payload["system"] else "Terjemahan "
        body = re.sub(r">([^<]+)<", lambda m: f">{mark}{m.group(1)}<", article["body_html"])
        if self.mangle:
            body = self.mangle(body)
        answer = {"stop_reason": "tool_use", "content": [{
            "type": "tool_use", "name": "save_translation", "input": {
                "title": mark + article["title"], "summary": mark + article["summary"],
                "body_html": body, "points": [mark + p for p in article["points"]],
            }}]}
        return io.BytesIO(json.dumps(answer).encode("utf-8"))


@pytest.fixture()
def api(app, monkeypatch):
    app.config.update(TRANSLATION_PROVIDER="auto", ANTHROPIC_API_KEY="test-key",
                      TRANSLATION_MODEL="claude-test")
    fake = FakeApi()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    ts.reset_jobs()
    yield fake
    ts.reset_jobs()


@pytest.fixture()
def world(app):
    env = Category(name="Environment", slug="environment")
    writer = User(email="w@example.com", display_name="W", role=Role.VERIFIED_CONTRIBUTOR,
                  password_hash=hash_password(PASSWORD))
    admin = User(email="a@example.com", display_name="A", role=Role.SYSTEM_ADMIN,
                 password_hash=hash_password(PASSWORD))
    _db.session.add_all([env, writer, admin])
    _db.session.commit()
    return {"env": env, "writer": writer}


def story(world, status=ArticleStatus.PENDING, slug="grid"):
    a = Article(contributor_id=world["writer"].id, category_id=world["env"].id, title=LONG, slug=slug,
                summary="Wind and solar.", body=body_for(LONG), status=status, submitted_at=utcnow(),
                published_at=utcnow() if status == ArticleStatus.PUBLISHED else None)
    _db.session.add(a)
    _db.session.commit()
    return a


def auth(client):
    token = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def read(client, slug="grid", lang="zh", **params):
    query = "&".join([f"lang={lang}"] + [f"{k}={v}" for k, v in params.items()])
    return client.get(f"/api/articles/{slug}?{query}").get_json()["article"]


def test_publishing_translates_into_both_languages(client, world, api):
    a = story(world)
    assert client.post(f"/api/review/{a.id}/approve", headers=auth(client)).status_code == 200
    assert ts.run_held() == 2

    zh = read(client, lang="zh")
    assert zh["title"] == "译" + LONG and zh["body"].count("<p>") == a.body.count("<p>")
    assert zh["translation"] == {"lang": "zh", "available": True, "provider": "claude",
                                 "note": ts.LABELS["zh"]["translated"]}
    assert all(p.startswith("译") for p in zh["inBrief"]["points"])
    assert read(client, lang="ms")["title"] == "Terjemahan " + LONG


def test_the_request_is_a_forced_tool_call_with_the_key(client, world, api):
    a = story(world)
    client.post(f"/api/review/{a.id}/approve", headers=auth(client))
    ts.run_held()
    sent = api.requests[0]
    headers = {k.lower(): v for k, v in sent["headers"].items()}
    assert headers["x-api-key"] == "test-key" and headers["anthropic-version"] == "2023-06-01"
    assert sent["payload"]["model"] == "claude-test"
    assert sent["payload"]["tool_choice"] == {"type": "tool", "name": "save_translation"}


def test_a_reader_who_arrives_first_is_told_it_is_on_its_way(client, world, api):
    story(world, ArticleStatus.PUBLISHED)
    first = read(client)
    assert first["title"] == LONG
    assert first["translation"]["preparing"] is True
    assert first["translation"]["note"] == ts.LABELS["zh"]["preparing"]
    status = client.get("/api/articles/grid/translation?lang=zh").get_json()["translation"]
    assert status["preparing"] is True and status["available"] is False

    ts.run_held()
    status = client.get("/api/articles/grid/translation?lang=zh").get_json()["translation"]
    assert status["available"] is True
    assert read(client)["title"] == "译" + LONG


def test_a_changed_english_is_translated_again(client, world, api):
    a = story(world, ArticleStatus.PUBLISHED)
    read(client)
    ts.run_held()
    a.body = a.body + "<p>A late correction.</p>"
    _db.session.commit()

    assert read(client)["translation"]["preparing"] is True
    ts.run_held()
    assert "译A late correction." in read(client)["body"]
    assert ArticleTranslation.query.filter_by(article_id=a.id, lang="zh").count() == 1


def test_a_translation_that_loses_the_layout_is_refused(client, world, api, app):
    a = story(world, ArticleStatus.PUBLISHED)
    api.mangle = lambda body: body.replace("<h3>", "<p>").replace("</h3>", "</p>")
    read(client)
    ts.run_held()
    assert ArticleTranslation.query.filter_by(article_id=a.id).count() == 0
    # And it is not asked for again straight away.
    again = read(client)["translation"]
    assert again["preparing"] is False and again["note"] == ts.LABELS["zh"]["unavailable"]
    assert ts.run_held() == 0


def test_markup_in_a_translation_is_cleaned(client, world, api):
    a = story(world, ArticleStatus.PUBLISHED)
    api.mangle = lambda body: body.replace("</p>", "<script>alert(1)</script></p>", 1)
    read(client)
    ts.run_held()
    stored = ArticleTranslation.query.filter_by(article_id=a.id, lang="zh").one()
    assert "<script" not in stored.body


def test_without_a_key_nothing_is_sent(client, world, app, monkeypatch):
    app.config.update(TRANSLATION_PROVIDER="auto", ANTHROPIC_API_KEY=None)
    ts.reset_jobs()
    fake = FakeApi()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    story(world, ArticleStatus.PUBLISHED)
    note = read(client)["translation"]
    assert note["preparing"] is False and note["note"] == ts.LABELS["zh"]["unavailable"]
    assert ts.run_held() == 0 and fake.requests == []


def test_reloading_for_a_translation_is_not_another_view(client, world, api):
    a = story(world, ArticleStatus.PUBLISHED)
    read(client)
    read(client, seen=1)
    _db.session.expire_all()
    assert _db.session.get(Article, a.id).view_count == 1
