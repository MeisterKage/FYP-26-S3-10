"""The public editor panel and the "Approved by" line on articles.

What matters here is what a reader can and cannot see: an editor's track record
including overturned corrections, never an email, never a rejected draft, and
credentials only an administrator can set.
"""
import pytest

from app.enums import ArticleStatus, CorrectionType, Role
from app.extensions import db as _db
from app.models import Article, Category, Correction, EditorCategory, User, utcnow
from app.security import hash_password

PASSWORD = "EditorPanel123!"


def make_user(email, role, name=None):
    user = User(
        email=email, display_name=name or email.split("@")[0],
        password_hash=hash_password(PASSWORD), role=role,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


def auth_for(client, email):
    token = client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


_n = {"n": 0}


def make_article(writer, category, status, reviewer=None, title=None):
    _n["n"] += 1
    article = Article(
        contributor_id=writer.id, category_id=category.id,
        title=title or f"Piece {_n['n']}", slug=f"piece-{_n['n']}", body="<p>b</p>",
        status=status, reviewed_by_id=reviewer.id if reviewer else None,
        published_at=utcnow() if status == ArticleStatus.PUBLISHED else None,
    )
    _db.session.add(article)
    _db.session.commit()
    return article


@pytest.fixture()
def world(app):
    category = Category(name="Politics", slug="politics")
    _db.session.add(category)
    _db.session.commit()

    editor = make_user("editor@example.com", Role.EDITOR, name="Dana Editor")
    editor.editor_title = "Politics Editor"
    editor.editor_credentials = "Ten years on the politics desk."
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    _db.session.commit()

    return {
        "category": category,
        "editor": editor,
        "admin": make_user("admin@example.com", Role.SYSTEM_ADMIN),
        "writer": make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR),
    }


def correct(article, editor, overturned=False):
    _db.session.add(
        Correction(
            article_id=article.id, issued_by_id=editor.id,
            correction_type=CorrectionType.CORRECTION, reason="Wrong figure.",
            overturned_at=utcnow() if overturned else None,
        )
    )
    _db.session.commit()


def test_the_panel_lists_editors_with_their_track_record(client, world):
    ed, w, cat = world["editor"], world["writer"], world["category"]
    published = [make_article(w, cat, ArticleStatus.PUBLISHED, ed) for _ in range(3)]
    make_article(w, cat, ArticleStatus.REJECTED, ed)
    correct(published[0], ed)
    correct(published[1], ed, overturned=True)

    body = client.get("/api/editors").get_json()
    assert len(body["editors"]) == 1
    entry = body["editors"][0]
    assert entry["name"] == "Dana Editor"
    assert entry["title"] == "Politics Editor"
    assert entry["sections"][0]["name"] == "Politics"
    assert entry["record"] == {
        "articlesApproved": 3,
        "articlesReturned": 1,
        "correctionsIssued": 2,
        "correctionsOverturned": 1,
        "correctionsUpheldRate": 50.0,
    }


def test_an_editor_with_no_corrections_has_no_upheld_rate(client, world):
    """Nothing to measure is withheld, not shown as a perfect 100%."""
    entry = client.get("/api/editors").get_json()["editors"][0]
    assert entry["record"]["correctionsUpheldRate"] is None


def test_the_panel_never_exposes_an_email(client, world):
    raw = client.get("/api/editors").get_data(as_text=True)
    raw += client.get(f"/api/editors/{world['editor'].id}").get_data(as_text=True)
    assert "@example.com" not in raw


def test_only_editors_are_on_the_panel(client, world):
    ids = {e["id"] for e in client.get("/api/editors").get_json()["editors"]}
    assert ids == {world["editor"].id}
    assert client.get(f"/api/editors/{world['admin'].id}").status_code == 404
    assert client.get(f"/api/editors/{world['writer'].id}").status_code == 404


def test_a_profile_shows_approved_articles_but_never_rejected_ones(client, world):
    ed, w, cat = world["editor"], world["writer"], world["category"]
    make_article(w, cat, ArticleStatus.PUBLISHED, ed, title="Approved story")
    make_article(w, cat, ArticleStatus.REJECTED, ed, title="Rejected draft")

    body = client.get(f"/api/editors/{ed.id}").get_json()
    titles = [a["title"] for a in body["articles"]]
    assert titles == ["Approved story"]
    assert "Rejected draft" not in client.get(f"/api/editors/{ed.id}").get_data(as_text=True)


def test_an_article_names_the_editor_who_approved_it(client, world):
    ed, w, cat = world["editor"], world["writer"], world["category"]
    article = make_article(w, cat, ArticleStatus.PUBLISHED, ed)

    reviewer = client.get(f"/api/articles/{article.slug}").get_json()["article"]["review"]["reviewer"]
    assert reviewer == {
        "id": ed.id, "name": "Dana Editor", "title": "Politics Editor", "onPanel": True,
    }


def test_an_unconfirmed_auto_published_article_names_no_one(client, world):
    ed, w, cat = world["editor"], world["writer"], world["category"]
    article = make_article(w, cat, ArticleStatus.PUBLISHED, ed)
    article.auto_published_at = utcnow()
    _db.session.commit()

    review = client.get(f"/api/articles/{article.slug}").get_json()["article"]["review"]
    assert review["awaitingReview"] is True
    assert review["reviewer"] is None


def test_an_admin_approval_is_named_but_not_linked_to_the_panel(client, world):
    article = make_article(world["writer"], world["category"], ArticleStatus.PUBLISHED, world["admin"])
    reviewer = client.get(f"/api/articles/{article.slug}").get_json()["article"]["review"]["reviewer"]
    assert reviewer["onPanel"] is False


def test_an_admin_sets_title_and_credentials(client, world):
    ed = world["editor"]
    response = client.put(
        f"/api/admin/editors/{ed.id}/profile",
        json={"title": "Senior Editor", "credentials": "<b>Twelve</b> years."},
        headers=auth_for(client, "admin@example.com"),
    )
    assert response.status_code == 200
    entry = client.get(f"/api/editors/{ed.id}").get_json()["editor"]
    assert entry["title"] == "Senior Editor"
    assert entry["credentials"] == "Twelve years."  # markup stripped


def test_empty_text_clears_a_field(client, world):
    ed = world["editor"]
    client.put(
        f"/api/admin/editors/{ed.id}/profile",
        json={"title": "", "credentials": ""},
        headers=auth_for(client, "admin@example.com"),
    )
    entry = client.get(f"/api/editors/{ed.id}").get_json()["editor"]
    assert entry["title"] is None and entry["credentials"] is None


@pytest.mark.parametrize("email", ["editor@example.com", "writer@example.com"])
def test_nobody_but_an_admin_sets_credentials(client, world, email):
    """An editor cannot write their own credentials; that is the point of them."""
    response = client.put(
        f"/api/admin/editors/{world['editor'].id}/profile",
        json={"title": "World's best editor"},
        headers=auth_for(client, email),
    )
    assert response.status_code == 403


def test_credentials_can_only_be_set_on_an_editor(client, world):
    response = client.put(
        f"/api/admin/editors/{world['writer'].id}/profile",
        json={"title": "Editor"},
        headers=auth_for(client, "admin@example.com"),
    )
    assert response.status_code == 422
