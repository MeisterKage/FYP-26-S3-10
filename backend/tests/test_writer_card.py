"""The writer card at the end of an article, and the profile's follow state.

A reader who liked an article can follow or subscribe to its writer from the
article itself, so the article response says who the writer is and whether
this reader already follows or subscribes.
"""
from datetime import timedelta

import pytest

from app.enums import ArticleStatus, Role, SubscriptionStatus
from app.extensions import db as _db
from app.models import Article, Category, Subscription, User, utcnow
from app.security import hash_password

PASSWORD = "WriterCard12345!"


def make_user(email, role, bio=None):
    u = User(email=email, display_name=email.split("@")[0], bio=bio,
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
    category = Category(name="Politics", slug="politics")
    _db.session.add(category)
    _db.session.commit()
    writer = make_user("aisha@example.com", Role.VERIFIED_CONTRIBUTOR, bio="Tech and business.")
    reader = make_user("reader@example.com", Role.FREE_REGISTERED)
    article = Article(contributor_id=writer.id, category_id=category.id, title="A story",
                      slug="a-story", body="<p>b</p>", status=ArticleStatus.PUBLISHED,
                      published_at=utcnow())
    _db.session.add(article)
    _db.session.commit()
    return {"writer": writer, "reader": reader}


def writer_of(client, headers=None):
    return client.get("/api/articles/a-story", headers=headers or {}).get_json()["article"]["writer"]


def test_the_article_names_its_writer_with_their_bio(client, world):
    w = writer_of(client)
    assert w["name"] == "aisha" and w["bio"] == "Tech and business."
    assert w["offersSubscription"] is True
    assert (w["following"], w["subscribed"], w["isSelf"]) == (False, False, False)


def test_following_shows_on_the_article_and_the_profile(client, world):
    headers = auth(client, "reader@example.com")
    client.post(f"/api/contributors/{world['writer'].id}/follow", headers=headers)
    assert writer_of(client, headers)["following"] is True
    assert writer_of(client, headers)["followerCount"] == 1
    profile = client.get(f"/api/contributors/{world['writer'].id}", headers=headers).get_json()
    assert profile["contributor"]["isFollowedByViewer"] is True


def test_an_active_subscription_shows_as_subscribed(client, world):
    now = utcnow()
    _db.session.add(Subscription(subscriber_id=world["reader"].id,
                                 contributor_id=world["writer"].id, price_cents=500,
                                 period_start=now, period_end=now + timedelta(days=30),
                                 status=SubscriptionStatus.ACTIVE))
    _db.session.commit()
    assert writer_of(client, auth(client, "reader@example.com"))["subscribed"] is True


def test_the_writer_sees_their_own_article_as_theirs(client, world):
    assert writer_of(client, auth(client, "aisha@example.com"))["isSelf"] is True
