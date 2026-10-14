"""An article must be in a real section, not Uncategorised, before it can be published."""
import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, User, utcnow
from app.security import hash_password

PASSWORD = "CategoryRule12345!"


@pytest.fixture()
def world(app):
    loose = Category(name="Uncategorised", slug="uncategorised", is_system=True)
    politics = Category(name="Politics", slug="politics")
    writer = User(email="w@example.com", display_name="W", role=Role.VERIFIED_CONTRIBUTOR,
                  password_hash=hash_password(PASSWORD))
    admin = User(email="a@example.com", display_name="A", role=Role.SYSTEM_ADMIN,
                 password_hash=hash_password(PASSWORD))
    _db.session.add_all([loose, politics, writer, admin])
    _db.session.commit()
    return {"loose": loose, "politics": politics, "writer": writer}


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def article(world, category, status=ArticleStatus.DRAFT, slug="a"):
    a = Article(contributor_id=world["writer"].id, category_id=world[category].id, title=slug,
                slug=slug, body="<p>Some text.</p>", status=status, submitted_at=utcnow())
    _db.session.add(a)
    _db.session.commit()
    return a


def test_a_draft_in_uncategorised_cannot_be_submitted(client, world):
    a = article(world, "loose")
    r = client.post(f"/api/articles/{a.id}/submit", headers=auth(client, "w@example.com"))
    assert r.status_code == 422 and "Uncategorised" in r.get_json()["error"]["message"]
    assert _db.session.get(Article, a.id).status == ArticleStatus.DRAFT


def test_an_editor_cannot_approve_one(client, world):
    a = article(world, "loose", ArticleStatus.PENDING)
    r = client.post(f"/api/review/{a.id}/approve", headers=auth(client, "a@example.com"))
    assert r.status_code == 422
    assert _db.session.get(Article, a.id).status == ArticleStatus.PENDING


def test_batch_approval_reports_it_and_approves_the_rest(client, world):
    bad = article(world, "loose", ArticleStatus.PENDING, slug="bad")
    good = article(world, "politics", ArticleStatus.PENDING, slug="good")
    r = client.post("/api/review/batch-approve", json={"articleIds": [bad.id, good.id]},
                    headers=auth(client, "a@example.com")).get_json()
    assert r["approved"] == [good.id]
    assert r["failed"][0]["id"] == bad.id
