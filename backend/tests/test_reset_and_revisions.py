"""Password reset through the logged link, and who may read revision history."""
import logging
import re

import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleRevision, Category, User
from app.security import hash_password

PASSWORD = "IntegrationTest123!"
NEW_PASSWORD = "AnotherGoodPass456!"


def make_user(email, role=Role.FREE_REGISTERED):
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


def headers_for(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.get_json()
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def logged_token(caplog):
    """The token from the link in the log, read the way an administrator would."""
    match = re.search(r"https?://\S+/reset-password\?token=(\S+)", caplog.text)
    assert match, "no reset link in the server log"
    return match.group(1)


#--------------------------------------------------------------------------- #
# Password reset
#--------------------------------------------------------------------------- #

def test_reset_link_reaches_the_log_at_a_level_production_shows(client, caplog):
    make_user("known@example.com")

    #WARNING is the level an unconfigured logger prints under gunicorn.
    with caplog.at_level(logging.WARNING):
        client.post("/api/auth/password-reset/request", json={"email": "known@example.com"})

    assert logged_token(caplog)


def test_unknown_email_logs_no_link(client, caplog):
    with caplog.at_level(logging.WARNING):
        client.post("/api/auth/password-reset/request", json={"email": "no@example.com"})

    assert "reset-password" not in caplog.text


def test_logged_link_sets_a_new_password_once(client, caplog):
    make_user("known@example.com")
    with caplog.at_level(logging.WARNING):
        client.post("/api/auth/password-reset/request", json={"email": "known@example.com"})
    token = logged_token(caplog)

    confirmed = client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )
    assert confirmed.status_code == 200, confirmed.get_json()

    old = client.post("/api/auth/login", json={"email": "known@example.com", "password": PASSWORD})
    new = client.post("/api/auth/login", json={"email": "known@example.com", "password": NEW_PASSWORD})
    assert old.status_code == 401
    assert new.status_code == 200

    again = client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "password": PASSWORD}
    )
    assert again.status_code == 400


def test_reset_ends_sessions_opened_with_the_old_password(client, caplog):
    make_user("known@example.com")
    old_session = headers_for(client, "known@example.com")
    assert client.get("/api/auth/me", headers=old_session).status_code == 200

    with caplog.at_level(logging.WARNING):
        client.post("/api/auth/password-reset/request", json={"email": "known@example.com"})
    client.post(
        "/api/auth/password-reset/confirm",
        json={"token": logged_token(caplog), "password": NEW_PASSWORD},
    )

    assert client.get("/api/auth/me", headers=old_session).status_code == 401

    login = client.post(
        "/api/auth/login", json={"email": "known@example.com", "password": NEW_PASSWORD}
    )
    new_session = {"Authorization": f"Bearer {login.get_json()['token']}"}
    assert client.get("/api/auth/me", headers=new_session).status_code == 200


#--------------------------------------------------------------------------- #
# Revision history
#--------------------------------------------------------------------------- #

@pytest.fixture()
def writer(app):
    return make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR)


def article_with_revision(writer, status, slug):
    category = Category.query.filter_by(slug="technology").first()
    if category is None:
        category = Category(name="Technology", slug="technology")
        _db.session.add(category)
        _db.session.commit()
    article = Article(
        contributor_id=writer.id, category_id=category.id, title="Current title",
        slug=slug, body="<p>current body</p>", status=status,
    )
    _db.session.add(article)
    _db.session.commit()
    _db.session.add(
        ArticleRevision(
            article_id=article.id, editor_id=writer.id, title="Old title",
            body="<p>old body</p>", change_note="Corrected a figure",
        )
    )
    _db.session.commit()
    return article


def test_visitor_reads_history_of_a_published_article(client, writer):
    article = article_with_revision(writer, ArticleStatus.PUBLISHED, "open")

    response = client.get(f"/api/articles/{article.id}/revisions")

    assert response.status_code == 200
    assert response.get_json()["revisions"][0]["changeNote"] == "Corrected a figure"


def test_signed_in_reader_reads_history_of_a_published_article(client, writer):
    article = article_with_revision(writer, ArticleStatus.PUBLISHED, "open")
    make_user("reader@example.com")

    response = client.get(
        f"/api/articles/{article.id}/revisions", headers=headers_for(client, "reader@example.com")
    )

    assert response.status_code == 200


def test_history_never_carries_the_article_body(client, writer):
    #The article itself may be behind the paywall, so old bodies stay out of this route.
    article = article_with_revision(writer, ArticleStatus.PUBLISHED, "open")

    response = client.get(f"/api/articles/{article.id}/revisions")

    assert response.status_code == 200
    assert "old body" not in response.get_data(as_text=True)


@pytest.mark.parametrize("status", [ArticleStatus.DRAFT, ArticleStatus.PENDING, ArticleStatus.UNPUBLISHED])
def test_history_of_an_unpublished_article_stays_private(client, writer, status):
    article = article_with_revision(writer, status, "private")
    make_user("reader@example.com")

    anonymous = client.get(f"/api/articles/{article.id}/revisions")
    reader = client.get(
        f"/api/articles/{article.id}/revisions", headers=headers_for(client, "reader@example.com")
    )
    author = client.get(
        f"/api/articles/{article.id}/revisions", headers=headers_for(client, "writer@example.com")
    )

    assert anonymous.status_code == 401
    assert reader.status_code == 403
    assert author.status_code == 200
