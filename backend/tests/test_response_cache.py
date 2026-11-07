"""The short-lived cache of public pages: fast for signed-out readers, never stale after a write."""
import pytest

from app import response_cache
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, User, utcnow
from app.security import hash_password

PASSWORD = "CacheTests12345!"


@pytest.fixture()
def world(app):
    app.config["RESPONSE_CACHE_SECONDS"] = 60
    response_cache.clear()
    politics = Category(name="Politics", slug="politics")
    writer = User(email="w@example.com", display_name="W", role=Role.VERIFIED_CONTRIBUTOR,
                  password_hash=hash_password(PASSWORD))
    _db.session.add_all([politics, writer])
    _db.session.commit()
    article = Article(contributor_id=writer.id, category_id=politics.id, title="First",
                      slug="first", body="<p>b</p>", status=ArticleStatus.PUBLISHED,
                      published_at=utcnow())
    _db.session.add(article)
    _db.session.commit()
    yield {"article": article, "politics": politics}
    response_cache.clear()


def titles(client, headers=None):
    r = client.get("/api/feed/trending", headers=headers or {})
    return r, [a["title"] for a in r.get_json()["articles"]]


def test_a_repeat_signed_out_request_is_served_from_memory(client, world):
    first, _ = titles(client)
    second, _ = titles(client)
    assert first.headers["X-Cache"] == "MISS" and second.headers["X-Cache"] == "HIT"
    #The security headers still apply to a cached answer.
    assert second.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_signed_in_requests_bypass_the_cache(client, world):
    token = client.post("/api/auth/login", json={"email": "w@example.com", "password": PASSWORD}
                        ).get_json()["token"]
    titles(client)
    r, _ = titles(client, {"Authorization": f"Bearer {token}"})
    assert "X-Cache" not in r.headers


def test_any_write_through_the_api_clears_it(client, world):
    titles(client)
    #A failed write changes nothing, so the cache stays.
    client.post("/api/auth/login", json={"email": "w@example.com", "password": "wrong"})
    assert titles(client)[0].headers["X-Cache"] == "HIT"
    client.post("/api/auth/login", json={"email": "w@example.com", "password": PASSWORD})
    assert titles(client)[0].headers["X-Cache"] == "MISS"


def test_a_cached_article_still_counts_every_view(client, world):
    for _ in range(3):
        assert client.get("/api/articles/first").status_code == 200
    _db.session.expire_all()
    assert _db.session.get(Article, world["article"].id).view_count == 3


def test_changes_outside_the_api_show_once_the_entry_expires(client, world, app):
    titles(client)
    _db.session.add(Article(contributor_id=world["article"].contributor_id,
                            category_id=world["politics"].id, title="Second", slug="second",
                            body="<p>b</p>", status=ArticleStatus.PUBLISHED, published_at=utcnow()))
    _db.session.commit()
    assert "Second" not in titles(client)[1]
    response_cache.clear()          #what expiry does after a minute
    assert "Second" in titles(client)[1]
