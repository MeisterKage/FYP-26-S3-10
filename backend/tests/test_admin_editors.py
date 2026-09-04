"""Editor-to-category assignment.

review.py has always scoped an editor's queue to their assigned categories, but
until now nothing could write those assignments through the API, only seed.py,
by inserting rows directly. That meant a newly promoted editor had a permanently
empty review queue and no administrator could do anything about it.
"""
import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, EditorCategory, User
from app.security import hash_password

PASSWORD = "AdminEditors123!"


@pytest.fixture()
def categories(app):
    rows = [
        Category(name="Technology", slug="technology"),
        Category(name="Politics", slug="politics"),
    ]
    _db.session.add_all(rows)
    _db.session.commit()
    return rows


def make_user(email, role):
    user = User(
        email=email, display_name=email.split("@")[0],
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


def test_unassigned_editor_is_visible_to_the_admin(client, categories):
    """The state that silently breaks the review queue is reported, not hidden."""
    make_user("admin@example.com", Role.SYSTEM_ADMIN)
    make_user("editor@example.com", Role.EDITOR)

    listing = client.get(
        "/api/admin/editors", headers=auth_for(client, "admin@example.com")
    ).get_json()

    editor = next(e for e in listing["editors"] if e["email"] == "editor@example.com")
    assert editor["categories"] == []
    assert editor["hasNoCategories"] is True


def test_assigning_categories_makes_the_review_queue_work(client, categories):
    """The end-to-end point of the feature."""
    make_user("admin2@example.com", Role.SYSTEM_ADMIN)
    editor = make_user("editor2@example.com", Role.EDITOR)
    contributor = make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR)

    tech = categories[0]
    _db.session.add(
        Article(
            contributor_id=contributor.id, category_id=tech.id,
            title="Pending piece", slug="pending-piece", body="<p>b</p>",
            status=ArticleStatus.PENDING,
        )
    )
    _db.session.commit()

    editor_headers = auth_for(client, "editor2@example.com")

    # Before assignment: empty queue, with an explanation rather than silence.
    before = client.get("/api/review/queue", headers=editor_headers).get_json()
    assert before["articles"] == []
    assert "note" in before

    assigned = client.put(
        f"/api/admin/editors/{editor.id}/categories",
        json={"categoryIds": [tech.id]},
        headers=auth_for(client, "admin2@example.com"),
    )
    assert assigned.status_code == 200

    after = client.get("/api/review/queue", headers=editor_headers).get_json()
    assert [a["title"] for a in after["articles"]] == ["Pending piece"]


def test_assignment_replaces_rather_than_appends(client, categories):
    make_user("admin3@example.com", Role.SYSTEM_ADMIN)
    editor = make_user("editor3@example.com", Role.EDITOR)
    headers = auth_for(client, "admin3@example.com")
    url = f"/api/admin/editors/{editor.id}/categories"

    client.put(url, json={"categoryIds": [c.id for c in categories]}, headers=headers)
    assert EditorCategory.query.filter_by(editor_id=editor.id).count() == 2

    client.put(url, json={"categoryIds": [categories[0].id]}, headers=headers)
    assert EditorCategory.query.filter_by(editor_id=editor.id).count() == 1


def test_assignments_can_be_cleared(client, categories):
    make_user("admin4@example.com", Role.SYSTEM_ADMIN)
    editor = make_user("editor4@example.com", Role.EDITOR)
    headers = auth_for(client, "admin4@example.com")
    url = f"/api/admin/editors/{editor.id}/categories"

    client.put(url, json={"categoryIds": [categories[0].id]}, headers=headers)
    response = client.put(url, json={"categoryIds": []}, headers=headers)

    assert response.status_code == 200
    assert response.get_json()["categories"] == []


def test_cannot_assign_categories_to_a_non_editor(client, categories):
    make_user("admin5@example.com", Role.SYSTEM_ADMIN)
    reader = make_user("reader@example.com", Role.FREE_REGISTERED)

    response = client.put(
        f"/api/admin/editors/{reader.id}/categories",
        json={"categoryIds": [categories[0].id]},
        headers=auth_for(client, "admin5@example.com"),
    )
    assert response.status_code == 422
    assert EditorCategory.query.count() == 0


def test_unknown_category_is_rejected_without_partial_write(client, categories):
    make_user("admin6@example.com", Role.SYSTEM_ADMIN)
    editor = make_user("editor6@example.com", Role.EDITOR)

    response = client.put(
        f"/api/admin/editors/{editor.id}/categories",
        json={"categoryIds": [categories[0].id, 999999]},
        headers=auth_for(client, "admin6@example.com"),
    )
    assert response.status_code == 422
    # The valid half of the request must not have been applied.
    assert EditorCategory.query.filter_by(editor_id=editor.id).count() == 0


def test_editors_cannot_assign_their_own_categories(client, categories):
    """Otherwise an editor grants themselves the whole platform."""
    editor = make_user("editor7@example.com", Role.EDITOR)

    response = client.put(
        f"/api/admin/editors/{editor.id}/categories",
        json={"categoryIds": [categories[0].id]},
        headers=auth_for(client, "editor7@example.com"),
    )
    assert response.status_code == 403


def test_listing_requires_an_administrator(client):
    make_user("editor8@example.com", Role.EDITOR)
    assert client.get(
        "/api/admin/editors", headers=auth_for(client, "editor8@example.com")
    ).status_code == 403


# --------------------------------------------------------------------------- #
#  Deleting an account: what happens to what they published (PDD Figure 5.87)
# --------------------------------------------------------------------------- #

def _published_by(writer, categories, title, slug):
    article = Article(
        contributor_id=writer.id, category_id=categories[0].id, title=title,
        slug=slug, body="<p>Body</p>", status=ArticleStatus.PUBLISHED,
    )
    _db.session.add(article)
    _db.session.commit()
    return article


def test_removing_an_account_keeps_its_articles_by_default(client, categories):
    make_user("delkeepadmin@example.com", Role.SYSTEM_ADMIN)
    writer = make_user("delkeepwriter@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = _published_by(writer, categories, "Stays up", "stays-up")

    response = client.delete(
        f"/api/admin/users/{writer.id}", headers=auth_for(client, "delkeepadmin@example.com")
    )

    assert response.status_code == 200
    assert Article.query.get(article.id).status == ArticleStatus.PUBLISHED


def test_an_administrator_can_take_the_articles_down_with_the_account(client, categories):
    make_user("delrmadmin@example.com", Role.SYSTEM_ADMIN)
    writer = make_user("delrmwriter@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = _published_by(writer, categories, "Comes down", "comes-down")

    response = client.delete(
        f"/api/admin/users/{writer.id}",
        json={"articles": "remove"},
        headers=auth_for(client, "delrmadmin@example.com"),
    )

    assert response.status_code == 200
    # Unpublished, never destroyed: the revision and correction history is the
    # record of what was corrected, and deleting the row takes the evidence too.
    assert Article.query.get(article.id).status == ArticleStatus.UNPUBLISHED


def test_an_unknown_articles_choice_is_rejected(client, categories):
    make_user("delbadadmin@example.com", Role.SYSTEM_ADMIN)
    victim = make_user("delbadvictim@example.com", Role.FREE_REGISTERED)

    response = client.delete(
        f"/api/admin/users/{victim.id}",
        json={"articles": "incinerate"},
        headers=auth_for(client, "delbadadmin@example.com"),
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
#  Renaming a category (PDD Figure 5.95)
# --------------------------------------------------------------------------- #

def test_renaming_a_category_keeps_its_address(client, categories):
    """Renaming "Tech" to "Technology" must not break every link anyone has
    shared to /categories/tech."""
    make_user("renameadmin@example.com", Role.SYSTEM_ADMIN)
    target = categories[0]
    original_slug = target.slug

    response = client.patch(
        f"/api/admin/categories/{target.id}",
        json={"name": "Science and Technology"},
        headers=auth_for(client, "renameadmin@example.com"),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == "Science and Technology"
    assert body["slug"] == original_slug


def test_renaming_onto_an_existing_name_is_refused(client, categories):
    make_user("renameadmin2@example.com", Role.SYSTEM_ADMIN)

    response = client.patch(
        f"/api/admin/categories/{categories[0].id}",
        json={"name": categories[1].name},
        headers=auth_for(client, "renameadmin2@example.com"),
    )
    assert response.status_code == 409


def test_a_category_cannot_be_renamed_to_nothing(client, categories):
    make_user("renameadmin3@example.com", Role.SYSTEM_ADMIN)

    response = client.patch(
        f"/api/admin/categories/{categories[0].id}",
        json={"name": "   "},
        headers=auth_for(client, "renameadmin3@example.com"),
    )
    assert response.status_code == 422


def test_an_editor_cannot_rename_a_category(client, categories):
    make_user("renameeditor@example.com", Role.EDITOR)

    response = client.patch(
        f"/api/admin/categories/{categories[0].id}",
        json={"name": "Mine now"},
        headers=auth_for(client, "renameeditor@example.com"),
    )
    assert response.status_code == 403
