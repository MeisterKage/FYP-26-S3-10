"""Rate limiting on the endpoints an attacker hammers.

The rest of the suite runs with RATELIMIT_ENABLED = False, because it signs in
repeatedly and would otherwise trip its own limits. This module turns limiting
back on so the protection itself is actually exercised.
"""
import pytest

from app import create_app
from app.enums import Role
from app.extensions import db as _db
from app.models import User
from app.security import hash_password
from config import TestConfig

PASSWORD = "RateLimit12345!"


class LimitedConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"


@pytest.fixture()
def limited_app():
    application = create_app(LimitedConfig)
    with application.app_context():
        _db.create_all()
        _db.session.add(
            User(
                email="target@example.com", display_name="Target",
                password_hash=hash_password(PASSWORD), role=Role.FREE_REGISTERED,
            )
        )
        _db.session.commit()
        yield application
        _db.session.remove()
        _db.drop_all()

    # Limiter state is process-global; clear it so ordering cannot couple tests.
    from app.ratelimit import limiter

    limiter.reset()


@pytest.fixture()
def limited_client(limited_app):
    return limited_app.test_client()


def attempt(client, email="target@example.com", password="WrongPassword1!"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_repeated_failed_logins_are_eventually_blocked(limited_client):
    statuses = [attempt(limited_client).status_code for _ in range(15)]

    assert 429 in statuses, "brute force was never throttled"
    # The limit must not be so tight that a couple of typos lock someone out.
    assert statuses[:3] == [401, 401, 401]


def test_a_blocked_response_keeps_the_api_error_shape(limited_client):
    for _ in range(15):
        response = attempt(limited_client)
        if response.status_code == 429:
            break

    assert response.status_code == 429
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.get_json()["error"]["message"]


def test_the_block_message_reveals_nothing_useful(limited_client):
    """No remaining budget, window size, or limit value in the body."""
    for _ in range(15):
        response = attempt(limited_client)
        if response.status_code == 429:
            break

    message = response.get_json()["error"]["message"].lower()
    for leak in ("10 per", "15 minute", "remaining", "quota"):
        assert leak not in message


def test_throttling_one_target_does_not_lock_out_another(limited_client):
    """The key includes the email, so exhausting one account's budget must not
    deny service to everyone else behind the same address."""
    for _ in range(15):
        attempt(limited_client, email="victim@example.com")

    # A different account is still served (401 for unknown, not 429).
    other = attempt(limited_client, email="bystander@example.com")
    assert other.status_code == 401


def test_password_reset_requests_are_throttled(limited_client):
    """Each request sends mail to an address the caller chose, unthrottled,
    that is an outbound spam relay."""
    statuses = [
        limited_client.post(
            "/api/auth/password-reset/request", json={"email": "target@example.com"}
        ).status_code
        for _ in range(10)
    ]
    assert 429 in statuses


def test_registration_is_throttled(limited_client):
    statuses = [
        limited_client.post(
            "/api/auth/register",
            json={
                "email": f"bulk{i}@example.com", "displayName": f"Bulk {i}",
                "password": PASSWORD,
            },
        ).status_code
        for i in range(15)
    ]
    assert 429 in statuses


def test_reading_articles_is_not_rate_limited(limited_client):
    """No blanket default limit: ordinary browsing must not be throttled."""
    statuses = [limited_client.get("/api/feed/trending").status_code for _ in range(40)]
    assert set(statuses) == {200}


def test_a_correct_password_still_works_within_the_limit(limited_client):
    response = limited_client.post(
        "/api/auth/login", json={"email": "target@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
