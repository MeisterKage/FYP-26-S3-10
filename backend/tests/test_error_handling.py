"""Error-handling contract.

Each test below corresponds to a defect found by probing the running app. They
exist so the fixes stay fixed: several of these failures were silent, and a
silent failure that comes back is one nobody notices until a demo.
"""
import math

import pytest

from app.credibility import credibility_score
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, Comment, PlatformSetting, User
from app.security import hash_password

PASSWORD = "ErrorHandling123!"


@pytest.fixture()
def category(app):
    category = Category(name="Technology", slug="technology")
    _db.session.add(category)
    _db.session.commit()
    return category


def make_user(email, role):
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


def auth_for(client, email):
    token = client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


#--------------------------------------------------------------------------- #
# Every response is JSON in one shape
#--------------------------------------------------------------------------- #

def assert_error_shape(response):
    """The contract frontend/src/api.js is written against."""
    assert response.headers["Content-Type"].startswith("application/json"), (
        f"got {response.headers['Content-Type']}, the client calls .json() on this "
        "and would throw a parse error instead of showing the message"
    )
    body = response.get_json()
    assert isinstance(body, dict) and "error" in body
    assert isinstance(body["error"].get("message"), str)
    assert body["error"]["message"]


def test_wrong_method_returns_json_not_html(client):
    """Werkzeug's default 405 is an HTML page, which breaks the client contract."""
    assert_error_shape(client.get("/api/auth/login"))


def test_unknown_route_returns_json(client):
    assert_error_shape(client.get("/api/does-not-exist"))


def test_malformed_json_body_returns_json(client):
    response = client.post(
        "/api/auth/register", data="{not json", content_type="application/json"
    )
    assert_error_shape(response)


def test_json_array_body_is_rejected_cleanly(client):
    """A top-level array would hit .get() on a list deeper in the handler."""
    response = client.post("/api/auth/register", json=["not", "an", "object"])
    assert response.status_code == 400
    assert_error_shape(response)


def test_error_messages_do_not_leak_internals(client):
    """No routing detail, SQL, or file path in anything the client can see."""
    for response in (
        client.get("/api/auth/login"),
        client.get("/api/nope"),
        client.post("/api/auth/register", json=["bad"]),
    ):
        message = response.get_json()["error"]["message"]
        for leak in ("Traceback", "SELECT", "sqlalchemy", "/api/", "\\", ".py"):
            assert leak not in message, f"{leak!r} leaked in: {message!r}"


#--------------------------------------------------------------------------- #
# NaN and infinity in the scoring thresholds
#--------------------------------------------------------------------------- #

def test_nan_threshold_is_rejected(client, category):
    """The worst of the bugs found: `nan < 0` is False, so a naive range check
    passes NaN through, and Postgres stores it happily as a valid float."""
    make_user("admin@example.com", Role.SYSTEM_ADMIN)
    headers = auth_for(client, "admin@example.com")

    response = client.put(
        "/api/admin/settings", json={"settings": {"accuracy_weight": "nan"}},
        headers=headers,
    )
    assert response.status_code == 422
    assert PlatformSetting.query.get("accuracy_weight") is None


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "NaN", "Infinity"])
def test_non_finite_thresholds_are_rejected(client, category, value):
    make_user(f"admin.{value.lower()}@example.com", Role.SYSTEM_ADMIN)
    headers = auth_for(client, f"admin.{value.lower()}@example.com")

    response = client.put(
        "/api/admin/settings", json={"settings": {"source_points": value}}, headers=headers
    )
    assert response.status_code == 422
    assert PlatformSetting.query.get("source_points") is None


def test_why_a_nan_threshold_mattered():
    """Demonstrates the damage the validation prevents, without the database.

    A NaN weight drives every article to 0 and brands the whole platform
    'Disputed', with no exception raised anywhere.
    """
    poisoned = credibility_score(
        contributor_accuracy=100.0, source_count=5, correction_count=0,
        is_retracted=False, upheld_report_count=0,
        settings={"accuracy_weight": float("nan")},
    )
    assert math.isnan(poisoned.accuracy_component)
    assert poisoned.score == 0.0
    assert poisoned.band == "Disputed"


def test_unknown_setting_key_is_rejected(client):
    make_user("admin2@example.com", Role.SYSTEM_ADMIN)
    headers = auth_for(client, "admin2@example.com")

    response = client.put(
        "/api/admin/settings", json={"settings": {"made_up_key": 1}}, headers=headers
    )
    assert response.status_code == 422


def test_a_bad_value_applies_none_of_the_batch(client):
    """Validation runs over the whole payload before any write."""
    make_user("admin3@example.com", Role.SYSTEM_ADMIN)
    headers = auth_for(client, "admin3@example.com")

    response = client.put(
        "/api/admin/settings",
        json={"settings": {"source_points": 7, "correction_penalty": "nan"}},
        headers=headers,
    )
    assert response.status_code == 422
    assert PlatformSetting.query.get("source_points") is None


#--------------------------------------------------------------------------- #
# Wrong-typed fields
#--------------------------------------------------------------------------- #

def test_string_where_a_list_belongs_is_a_422_not_a_500(client, category):
    """This raised an unhandled SQLAlchemy ArgumentError before the fix."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": "typed@example.com", "displayName": "Typed",
            "password": PASSWORD, "categoryIds": "oops",
        },
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "categoryIds"


def test_tags_as_a_string_is_rejected_rather_than_iterated(client, category):
    """Iterating a string does not raise; it silently produces one tag per
    character, which is a bug that survives all the way to a demo."""
    make_user("tagger@example.com", Role.VERIFIED_CONTRIBUTOR)
    headers = auth_for(client, "tagger@example.com")

    response = client.post(
        "/api/articles",
        json={
            "title": "Tagged", "categoryId": category.id,
            "body": "<p>b</p>", "tags": "news",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "tags"


def test_valid_tags_still_work(client, category):
    make_user("tagger2@example.com", Role.VERIFIED_CONTRIBUTOR)
    headers = auth_for(client, "tagger2@example.com")

    response = client.post(
        "/api/articles",
        json={
            "title": "Tagged well", "categoryId": category.id,
            "body": "<p>b</p>", "tags": ["policy", "analysis", "policy"],
        },
        headers=headers,
    )
    assert response.status_code == 201
    #Duplicates collapse.
    assert response.get_json()["tags"] == ["policy", "analysis"]


def test_non_string_title_is_a_422_not_a_sanitiser_crash(client, category):
    make_user("typer@example.com", Role.VERIFIED_CONTRIBUTOR)
    headers = auth_for(client, "typer@example.com")

    created = client.post(
        "/api/articles",
        json={"title": "Fine", "categoryId": category.id, "body": "<p>b</p>"},
        headers=headers,
    )
    article_id = created.get_json()["id"]

    #bleach raises TypeError on a non-string, which would be a 500.
    response = client.patch(
        f"/api/articles/{article_id}", json={"title": {"nested": "object"}}, headers=headers
    )
    assert response.status_code == 422


def test_non_numeric_category_id_is_a_422(client, category):
    make_user("cat@example.com", Role.VERIFIED_CONTRIBUTOR)
    headers = auth_for(client, "cat@example.com")

    response = client.post(
        "/api/articles",
        json={"title": "T", "categoryId": "abc", "body": "<p>b</p>"},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "categoryId"


#--------------------------------------------------------------------------- #
# Foreign keys arriving from the client
#--------------------------------------------------------------------------- #

def test_comment_on_a_nonexistent_parent_is_rejected(client, category):
    """SQLite accepts a dangling FK by default; Postgres raises. Validating here
    means the behaviour is the same on both, and the message is useful."""
    contributor = make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR)
    make_user("commenter@example.com", Role.FREE_REGISTERED)

    article = Article(
        contributor_id=contributor.id, category_id=category.id,
        title="Open", slug="open", body="<p>b</p>", status=ArticleStatus.PUBLISHED,
    )
    _db.session.add(article)
    _db.session.commit()

    headers = auth_for(client, "commenter@example.com")
    response = client.post(
        f"/api/articles/{article.id}/comments",
        json={"body": "reply", "parentId": 999999}, headers=headers,
    )
    assert response.status_code == 422
    assert Comment.query.count() == 0


def test_cannot_reply_across_articles(client, category):
    """A parent id from another article would graft this reply onto someone
    else's discussion."""
    contributor = make_user("writer2@example.com", Role.VERIFIED_CONTRIBUTOR)
    commenter = make_user("commenter2@example.com", Role.FREE_REGISTERED)

    first = Article(contributor_id=contributor.id, category_id=category.id,
                    title="One", slug="one", body="<p>b</p>",
                    status=ArticleStatus.PUBLISHED)
    second = Article(contributor_id=contributor.id, category_id=category.id,
                     title="Two", slug="two", body="<p>b</p>",
                     status=ArticleStatus.PUBLISHED)
    _db.session.add_all([first, second])
    _db.session.commit()

    elsewhere = Comment(article_id=first.id, user_id=commenter.id, body="on article one")
    _db.session.add(elsewhere)
    _db.session.commit()

    headers = auth_for(client, "commenter2@example.com")
    response = client.post(
        f"/api/articles/{second.id}/comments",
        json={"body": "hijack", "parentId": elsewhere.id}, headers=headers,
    )
    assert response.status_code == 422


def test_a_valid_reply_still_works(client, category):
    contributor = make_user("writer3@example.com", Role.VERIFIED_CONTRIBUTOR)
    commenter = make_user("commenter3@example.com", Role.FREE_REGISTERED)

    article = Article(contributor_id=contributor.id, category_id=category.id,
                      title="Three", slug="three", body="<p>b</p>",
                      status=ArticleStatus.PUBLISHED)
    _db.session.add(article)
    _db.session.commit()

    parent = Comment(article_id=article.id, user_id=commenter.id, body="parent")
    _db.session.add(parent)
    _db.session.commit()

    headers = auth_for(client, "commenter3@example.com")
    response = client.post(
        f"/api/articles/{article.id}/comments",
        json={"body": "a real reply", "parentId": parent.id}, headers=headers,
    )
    assert response.status_code == 201


#--------------------------------------------------------------------------- #
# Bad tokens
#--------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "header",
    ["Bearer nonsense", "Bearer ", "Bearer a.b.c", "Basic abc123", "Bearer  extra spaces"],
)
def test_bad_authorization_headers_never_crash(client, header):
    response = client.get("/api/auth/me", headers={"Authorization": header})
    assert response.status_code in (401, 403)
    assert_error_shape(response)


def test_token_without_a_usable_subject_is_a_401(client):
    """A validly-signed token whose payload we did not issue."""
    import jwt
    from flask import current_app

    token = jwt.encode(
        {"not_sub": "x"}, current_app.config["JWT_SECRET"], algorithm="HS256"
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert_error_shape(response)


#--------------------------------------------------------------------------- #
# Session hygiene
#--------------------------------------------------------------------------- #

def test_session_is_usable_after_a_rejected_request(client, category):
    """A failed request must not leave staged rows or a dirty session behind for
    whatever runs next on the same connection."""
    make_user("hygiene@example.com", Role.VERIFIED_CONTRIBUTOR)
    headers = auth_for(client, "hygiene@example.com")

    before = Article.query.count()

    bad = client.post(
        "/api/articles",
        json={"title": "Has bad tags", "categoryId": category.id,
              "body": "<p>b</p>", "tags": "notalist"},
        headers=headers,
    )
    assert bad.status_code == 422

    #Nothing partial was left staged, and the next request works normally.
    assert Article.query.count() == before

    good = client.post(
        "/api/articles",
        json={"title": "Fine article", "categoryId": category.id, "body": "<p>b</p>"},
        headers=headers,
    )
    assert good.status_code == 201


def test_bounded_reapply_window(client):
    """int('abc') would have been an unhandled ValueError."""
    make_user("admin4@example.com", Role.SYSTEM_ADMIN)
    applicant = make_user("applicant@example.com", Role.FREE_REGISTERED)
    headers = auth_for(client, "admin4@example.com")

    client.post(
        "/api/me/contributor-application",
        json={"writingSample": "x" * 250},
        headers=auth_for(client, "applicant@example.com"),
    )
    from app.models import ContributorApplication

    application = ContributorApplication.query.filter_by(user_id=applicant.id).first()

    response = client.post(
        f"/api/admin/applications/{application.id}/decide",
        json={"decision": "reject", "reason": "Not yet.", "reapplyAfterDays": "abc"},
        headers=headers,
    )
    assert response.status_code == 422
    assert_error_shape(response)


#--------------------------------------------------------------------------- #
# Security response headers
#--------------------------------------------------------------------------- #

def test_every_response_refuses_to_be_framed(client):
    """Clickjacking: without this, any site can frame ours and overlay a
    transparent control over a real one a signed-in administrator will click."""
    response = client.get("/api/health")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_every_response_forbids_mime_sniffing(client):
    """A browser that guesses a content type can be talked into running a JSON
    response as script."""
    assert client.get("/api/health").headers["X-Content-Type-Options"] == "nosniff"


def test_headers_are_present_on_errors_too(client):
    """An error path is still a response a browser acts on, so it needs the same
    headers. Handlers that build their own response can skip an after_request
    if it is wired in the wrong order."""
    response = client.get("/api/definitely-not-a-route")
    assert response.status_code == 404
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_authorised_replies_are_not_cached_by_shared_caches(client):
    assert client.get("/api/health").headers["Cache-Control"] == "no-store"


def test_referrer_is_trimmed_to_the_origin(client):
    """Article slugs travel in the URL; they should not follow a reader to a
    third-party site in the Referer header."""
    assert (
        client.get("/api/health").headers["Referrer-Policy"]
        == "strict-origin-when-cross-origin"
    )
