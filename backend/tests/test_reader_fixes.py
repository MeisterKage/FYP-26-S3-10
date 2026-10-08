"""Liked articles, saved front-page sections, topic counts and platform figures."""
import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, Like, User, utcnow
from app.security import hash_password

PASSWORD = "ReaderFixes12345!"


@pytest.fixture()
def world(app):
    politics, sport = Category(name="Politics", slug="politics"), Category(name="Sport", slug="sport")
    writer = User(email="w@example.com", display_name="W", role=Role.VERIFIED_CONTRIBUTOR,
                  password_hash=hash_password(PASSWORD))
    reader = User(email="r@example.com", display_name="R", role=Role.FREE_REGISTERED,
                  password_hash=hash_password(PASSWORD))
    editor = User(email="e@example.com", display_name="E", role=Role.EDITOR,
                  password_hash=hash_password(PASSWORD))
    _db.session.add_all([politics, sport, writer, reader, editor])
    _db.session.commit()
    stories = []
    for n, (cat, status) in enumerate([(politics, ArticleStatus.PUBLISHED),
                                       (politics, ArticleStatus.PUBLISHED),
                                       (sport, ArticleStatus.UNPUBLISHED)]):
        a = Article(contributor_id=writer.id, category_id=cat.id, title=f"Story {n}",
                    slug=f"story-{n}", body="<p>b</p>", status=status, published_at=utcnow(),
                    country_code="AU")
        _db.session.add(a)
        stories.append(a)
    _db.session.commit()
    return {"politics": politics, "sport": sport, "reader": reader, "stories": stories}


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_reader_can_list_what_they_liked(client, world):
    h = auth(client, "r@example.com")
    for a in world["stories"]:
        _db.session.add(Like(article_id=a.id, user_id=world["reader"].id))
    _db.session.commit()
    titles = [a["title"] for a in client.get("/api/me/liked", headers=h).get_json()["articles"]]
    assert sorted(titles) == ["Story 0", "Story 1"]          # the unpublished one is left out
    assert client.get("/api/me/liked").status_code == 401


def test_saved_sections_come_back_with_the_account(client, world):
    h = auth(client, "r@example.com")
    client.patch("/api/me", json={"categoryIds": [world["sport"].id]}, headers=h)
    me = client.get("/api/auth/me", headers=h).get_json()["user"]
    assert me["categoryIds"] == [world["sport"].id]


def test_topics_carry_their_published_article_counts(client, world):
    cats = {c["slug"]: c["articleCount"] for c in client.get("/api/categories").get_json()["categories"]}
    assert cats == {"politics": 2, "sport": 0}


def test_platform_figures_count_only_published_work(client, world):
    f = client.get("/api/platform").get_json()
    assert (f["articles"], f["writers"], f["editors"], f["countries"], f["sections"]) == (2, 1, 1, 1, 2)


def test_the_batched_duplicate_check_agrees_with_the_single_one(app, world):
    from app.review_service import duplicated_titles, has_duplicate_title
    twin = Article(contributor_id=world["stories"][0].contributor_id,
                   category_id=world["politics"].id, title="  story 0 ", slug="story-0-copy",
                   body="<p>b</p>", status=ArticleStatus.PENDING)
    _db.session.add(twin)
    _db.session.commit()
    articles = world["stories"] + [twin]
    assert duplicated_titles(articles) == {a.id for a in articles if has_duplicate_title(a)}
    assert duplicated_titles(articles) == {world["stories"][0].id, twin.id}
