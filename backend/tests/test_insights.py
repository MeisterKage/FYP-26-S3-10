"""In brief summaries, narration, and writing signals for editors."""
import json

import pytest

from app import insights
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.insights_service import clear_cache
from app.models import Article, Category, EditorCategory, User, utcnow
from app.security import hash_password
from demo_bodies import body_for

PASSWORD = "Insights12345!"
LONG = "Tokyo hospitals trial robotic lifting assistance in elderly care wards"

GENERATED = "".join(f"<p>{x}</p>" for x in [
    "In today's fast-paced world, renewable energy plays a crucial role in shaping the future "
    "of our communities. It is important to note that this transition is multifaceted and "
    "requires careful consideration from all stakeholders involved.",
    "Moreover, the landscape of energy production is ever-evolving. Communities must navigate "
    "the complexities of change while fostering innovation and resilience. This shift serves as "
    "a reminder that progress requires collaboration and shared commitment.",
    "Furthermore, solar power offers a seamless way to unlock the potential of local resources. "
    "It stands as a testament to human ingenuity and highlights the vital role of forward-"
    "thinking policy in creating lasting change.",
    "Additionally, wind energy represents another pivotal opportunity for sustainable growth. It "
    "delivers robust benefits for the environment and the economy alike, paving the way for a "
    "cleaner and brighter tomorrow for everyone.",
    "In conclusion, the journey toward clean energy is complex yet rewarding. By embracing these "
    "changes together, communities can harness the power of innovation and build a more "
    "sustainable future for generations to come.",
])


def make_user(email, role):
    u = User(email=email, display_name=email.split("@")[0],
             password_hash=hash_password(PASSWORD), role=role)
    _db.session.add(u)
    _db.session.commit()
    return u


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def world(app):
    clear_cache()
    health, sport = Category(name="Health", slug="health"), Category(name="Sport", slug="sport")
    _db.session.add_all([health, sport])
    _db.session.commit()
    writer = make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("editor@example.com", Role.EDITOR)
    other = make_user("sport.editor@example.com", Role.EDITOR)
    _db.session.add_all([EditorCategory(editor_id=editor.id, category_id=health.id),
                         EditorCategory(editor_id=other.id, category_id=sport.id)])
    articles = {}
    for slug, body in [("long", body_for(LONG)), ("short", "<p>One short paragraph.</p>")]:
        articles[slug] = Article(contributor_id=writer.id, category_id=health.id, title=slug.title(),
                                 slug=slug, body=body, status=ArticleStatus.PUBLISHED,
                                 published_at=utcnow())
        _db.session.add(articles[slug])
    _db.session.commit()
    return articles


def read(client, slug):
    return client.get(f"/api/articles/{slug}").get_json()["article"]


# --- key points ------------------------------------------------------------- #

def test_key_points_are_the_articles_own_sentences_in_order():
    body = body_for(LONG)
    points = insights.key_points(body)
    text = " ".join(p.text for p in insights.paragraphs(body))
    assert 3 <= len(points) <= 4
    positions = [text.index(p) for p in points]
    assert positions == sorted(positions)
    assert not any("“" in p or '"' in p for p in points)  # quotes stay with their speaker


def test_sentence_splitting_survives_abbreviations_and_quotes():
    assert insights.sentences("Dr. Lee spoke first. “It works,” she said. Then we left.") == [
        "Dr. Lee spoke first.", "“It works,” she said.", "Then we left."]


def test_a_long_article_gets_in_brief_with_narration(client, world):
    brief = read(client, "long")["inBrief"]
    assert brief["points"] and brief["readingMinutes"] >= 2
    assert brief["narration"]["mode"] == "browser"
    assert brief["narration"]["text"].startswith("Long. In brief. " + brief["points"][0])


def test_short_and_republished_articles_get_none(client, world):
    assert read(client, "short")["inBrief"] is None
    world["long"].republication = json.dumps({"publisher": "X", "authors": ["A"], "url": "https://x.org/1"})
    _db.session.commit()
    assert read(client, "long")["inBrief"] is None


def test_an_unconfigured_provider_hides_the_block_instead_of_failing(client, world, app):
    app.config["SUMMARY_PROVIDER"] = "claude"
    r = client.get("/api/articles/long")
    assert r.status_code == 200 and r.get_json()["article"]["inBrief"] is None


# --- writing signals -------------------------------------------------------- #

def test_generated_prose_shows_many_signals_and_reporting_few():
    assert insights.writing_signals(GENERATED)["level"] == "many"
    assert insights.writing_signals(body_for(LONG))["level"] == "few"
    assert insights.writing_signals("<p>Too short.</p>")["level"] == "too_short"


def test_only_the_sections_editor_sees_writing_signals(client, world):
    url = f"/api/articles/{world['long'].id}/writing-signals"
    ok = client.get(url, headers=auth(client, "editor@example.com"))
    assert ok.status_code == 200
    body = ok.get_json()["signals"]
    assert body["level"] == "few" and "not proof" in body["disclaimer"]
    assert client.get(url, headers=auth(client, "writer@example.com")).status_code == 404
    assert client.get(url, headers=auth(client, "sport.editor@example.com")).status_code == 404
    assert client.get(url).status_code == 401


def test_writing_signals_never_touch_the_score(client, world):
    before = read(client, "long")["credibility"]["score"]
    client.get(f"/api/articles/{world['long'].id}/writing-signals",
               headers=auth(client, "editor@example.com"))
    assert read(client, "long")["credibility"]["score"] == before
