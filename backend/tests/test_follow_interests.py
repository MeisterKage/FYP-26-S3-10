"""Any registered reader can follow a section or a country, and its news joins their front page."""
import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, User, utcnow
from app.security import hash_password

PASSWORD = "FollowTopics12345!"


@pytest.fixture()
def world(app):
    loose = Category(name="Uncategorised", slug="uncategorised", is_system=True)
    health = Category(name="Health", slug="health")
    sport = Category(name="Sport", slug="sport")
    writer = User(email="w@example.com", display_name="W", role=Role.VERIFIED_CONTRIBUTOR,
                  password_hash=hash_password(PASSWORD))
    reader = User(email="r@example.com", display_name="R", role=Role.FREE_REGISTERED,
                  password_hash=hash_password(PASSWORD))
    _db.session.add_all([loose, health, sport, writer, reader])
    _db.session.commit()
    for slug, cat, country in [("my-sport", sport, "MY"), ("au-health", health, "AU"), ("au-sport", sport, "AU")]:
        _db.session.add(Article(contributor_id=writer.id, category_id=cat.id, title=slug, slug=slug,
                                body="<p>Text.</p>", status=ArticleStatus.PUBLISHED,
                                published_at=utcnow(), country_code=country))
    _db.session.commit()
    return {"loose": loose, "health": health, "sport": sport}


def auth(client):
    token = client.post("/api/auth/login", json={"email": "r@example.com", "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def slugs(payload):
    return sorted(a["slug"] for a in payload["forYou"])


def test_following_a_country_fills_the_front_page(client, world):
    h = auth(client)
    r = client.put("/api/me/interests/countries/my", headers=h)
    assert r.status_code == 200 and r.get_json()["countryCodes"] == ["MY"]
    assert client.get("/api/auth/me", headers=h).get_json()["user"]["countryCodes"] == ["MY"]
    assert slugs(client.get("/api/feed/personalised", headers=h).get_json()) == ["my-sport"]


def test_sections_and_countries_combine(client, world):
    h = auth(client)
    client.put(f"/api/me/interests/categories/{world['health'].id}", headers=h)
    client.put("/api/me/interests/countries/MY", headers=h)
    assert slugs(client.get("/api/feed/personalised", headers=h).get_json()) == ["au-health", "my-sport"]


def test_unfollowing_takes_it_off_again(client, world):
    h = auth(client)
    client.put("/api/me/interests/countries/MY", headers=h)
    client.put(f"/api/me/interests/categories/{world['sport'].id}", headers=h)
    r = client.delete("/api/me/interests/countries/MY", headers=h).get_json()
    assert r["countryCodes"] == [] and r["categoryIds"] == [world["sport"].id]
    r = client.delete(f"/api/me/interests/categories/{world['sport'].id}", headers=h).get_json()
    assert r["categoryIds"] == []
    #Nothing followed: trending, not an empty page.
    assert "articles" in client.get("/api/feed/personalised", headers=h).get_json()


def test_following_twice_is_harmless(client, world):
    h = auth(client)
    client.put("/api/me/interests/countries/AU", headers=h)
    assert client.put("/api/me/interests/countries/au", headers=h).get_json()["countryCodes"] == ["AU"]


def test_unknown_country_and_uncategorised_cannot_be_followed(client, world):
    h = auth(client)
    assert client.put("/api/me/interests/countries/XX", headers=h).status_code == 404
    assert client.put(f"/api/me/interests/categories/{world['loose'].id}", headers=h).status_code == 404


def test_signed_out_readers_are_asked_to_sign_in(client, world):
    assert client.put("/api/me/interests/countries/AU").status_code == 401


def test_account_settings_save_countries_too(client, world):
    h = auth(client)
    assert client.patch("/api/me", json={"countryCodes": ["sg", "AU"]}, headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).get_json()["user"]["countryCodes"] == ["AU", "SG"]
    assert client.patch("/api/me", json={"countryCodes": ["Narnia"]}, headers=h).status_code == 422
