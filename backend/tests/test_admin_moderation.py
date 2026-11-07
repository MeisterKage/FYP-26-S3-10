"""Administrator authority over articles, and credibility disputes.

PDD Figures 5.93 and 5.94.

Two powers that belong to an administrator and to nobody else. An editor works
inside their assigned sections; an administrator answers for the whole platform,
which is why article moderation here is not scoped by category. And reversing a
correction is explicitly an administrator's call, because an editor deciding a
dispute about their own correction is not review.
"""
import pytest

from app.enums import ArticleStatus, CorrectionType, Role
from app.extensions import db as _db
from app.models import Article, Category, Correction, EditorCategory, User
from app.security import hash_password

PASSWORD = "AdminModeration123!"


@pytest.fixture()
def category(app):
    row = Category(name="Technology", slug="technology")
    _db.session.add(row)
    _db.session.commit()
    return row


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


def article_in(status, category, contributor, title, slug):
    article = Article(
        contributor_id=contributor.id, category_id=category.id, title=title,
        slug=slug, body="<p>Body</p>", status=status,
    )
    _db.session.add(article)
    _db.session.commit()
    return article


#--------------------------------------------------------------------------- #
# Article moderation (Figure 5.93)
#--------------------------------------------------------------------------- #

def test_an_administrator_can_suspend_a_published_article(client, category):
    make_user("modadmin@example.com", Role.SYSTEM_ADMIN)
    writer = make_user("modwriter@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = article_in(ArticleStatus.PUBLISHED, category, writer, "Live", "live-one")

    response = client.post(
        f"/api/admin/articles/{article.id}/moderate",
        json={"action": "suspend"},
        headers=auth_for(client, "modadmin@example.com"),
    )

    assert response.status_code == 200
    #Unpublished, never deleted: a corrected article is the record of that
    #correction, and dropping the row takes the evidence with it.
    assert Article.query.get(article.id).status == ArticleStatus.UNPUBLISHED


def test_a_suspended_article_can_be_reinstated(client, category):
    make_user("modadmin2@example.com", Role.SYSTEM_ADMIN)
    writer = make_user("modwriter2@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = article_in(ArticleStatus.UNPUBLISHED, category, writer, "Down", "down-one")

    response = client.post(
        f"/api/admin/articles/{article.id}/moderate",
        json={"action": "reinstate"},
        headers=auth_for(client, "modadmin2@example.com"),
    )

    assert response.status_code == 200
    assert Article.query.get(article.id).status == ArticleStatus.PUBLISHED


def test_an_action_that_does_not_apply_to_the_status_is_refused(client, category):
    """The interface renders only the relevant actions. The server enforces the
    same table rather than trusting that it did."""
    make_user("modadmin3@example.com", Role.SYSTEM_ADMIN)
    writer = make_user("modwriter3@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = article_in(ArticleStatus.DRAFT, category, writer, "Draft", "draft-one")

    response = client.post(
        f"/api/admin/articles/{article.id}/moderate",
        json={"action": "suspend"},
        headers=auth_for(client, "modadmin3@example.com"),
    )
    assert response.status_code == 409


def test_the_listing_reports_which_actions_apply(client, category):
    make_user("modadmin4@example.com", Role.SYSTEM_ADMIN)
    writer = make_user("modwriter5@example.com", Role.VERIFIED_CONTRIBUTOR)
    article_in(ArticleStatus.PUBLISHED, category, writer, "Up", "up-one")
    article_in(ArticleStatus.UNPUBLISHED, category, writer, "Off", "off-one")

    payload = client.get(
        "/api/admin/articles", headers=auth_for(client, "modadmin4@example.com")
    ).get_json()

    actions = {a["title"]: a["actions"] for a in payload["articles"]}
    assert actions["Up"] == ["suspend"]
    assert actions["Off"] == ["reinstate"]


def test_an_editor_cannot_moderate_platform_wide(client, category):
    make_user("modeditor@example.com", Role.EDITOR)
    writer = make_user("modwriter4@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = article_in(ArticleStatus.PUBLISHED, category, writer, "Theirs", "theirs-one")

    response = client.post(
        f"/api/admin/articles/{article.id}/moderate",
        json={"action": "suspend"},
        headers=auth_for(client, "modeditor@example.com"),
    )
    assert response.status_code == 403


#--------------------------------------------------------------------------- #
# Credibility disputes (Figure 5.94)
#--------------------------------------------------------------------------- #

@pytest.fixture()
def corrected(client, category):
    """A published article with a correction logged against it."""
    writer = make_user("disputer@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("disputeeditor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))

    article = article_in(
        ArticleStatus.PUBLISHED, category, writer, "Corrected", "corrected-one"
    )
    correction = Correction(
        article_id=article.id, issued_by_id=editor.id,
        correction_type=CorrectionType.CORRECTION, reason="Figure was wrong.",
    )
    _db.session.add(correction)
    _db.session.commit()
    return writer, article, correction


def test_a_writer_can_dispute_a_correction_against_their_own_work(client, corrected):
    _, _, correction = corrected

    response = client.post(
        f"/api/corrections/{correction.id}/dispute",
        json={"case": "The figure came from the ministry's own release."},
        headers=auth_for(client, "disputer@example.com"),
    )
    assert response.status_code == 201


def test_a_writer_cannot_dispute_a_correction_on_someone_elses_article(client, corrected):
    _, _, correction = corrected
    make_user("stranger2@example.com", Role.VERIFIED_CONTRIBUTOR)

    response = client.post(
        f"/api/corrections/{correction.id}/dispute",
        json={"case": "not mine"},
        headers=auth_for(client, "stranger2@example.com"),
    )
    assert response.status_code == 403


def test_a_dispute_needs_a_case(client, corrected):
    _, _, correction = corrected

    response = client.post(
        f"/api/corrections/{correction.id}/dispute",
        json={},
        headers=auth_for(client, "disputer@example.com"),
    )
    assert response.status_code == 422


def test_the_same_correction_cannot_be_disputed_twice(client, corrected):
    """A second filing is the same argument again, not new information."""
    _, _, correction = corrected
    headers = auth_for(client, "disputer@example.com")

    client.post(f"/api/corrections/{correction.id}/dispute",
                json={"case": "first"}, headers=headers)
    second = client.post(f"/api/corrections/{correction.id}/dispute",
                         json={"case": "again"}, headers=headers)
    assert second.status_code == 409


def test_the_queue_carries_everything_needed_to_decide(client, corrected):
    """An administrator should not open three screens to answer one question."""
    _, _, correction = corrected
    make_user("disputeadmin@example.com", Role.SYSTEM_ADMIN)

    client.post(f"/api/corrections/{correction.id}/dispute",
                json={"case": "It was sourced."},
                headers=auth_for(client, "disputer@example.com"))

    payload = client.get(
        "/api/moderation/disputes", headers=auth_for(client, "disputeadmin@example.com")
    ).get_json()

    assert len(payload["disputes"]) == 1
    entry = payload["disputes"][0]
    assert entry["case"] == "It was sourced."
    assert entry["correction"]["reason"] == "Figure was wrong."
    assert entry["article"]["title"] == "Corrected"
    assert entry["contributor"]["name"]


def test_reversing_a_dispute_overturns_the_correction(client, corrected):
    _, _, correction = corrected
    make_user("disputeadmin2@example.com", Role.SYSTEM_ADMIN)
    admin = auth_for(client, "disputeadmin2@example.com")

    client.post(f"/api/corrections/{correction.id}/dispute",
                json={"case": "sourced"},
                headers=auth_for(client, "disputer@example.com"))
    entry = client.get("/api/moderation/disputes", headers=admin).get_json()["disputes"][0]

    response = client.post(
        f"/api/moderation/disputes/{entry['id']}/resolve",
        json={"outcome": "reverse", "note": "Accepted."}, headers=admin,
    )

    assert response.status_code == 200
    assert Correction.query.get(correction.id).overturned_at is not None


def test_upholding_a_dispute_leaves_the_correction_standing(client, corrected):
    _, _, correction = corrected
    make_user("disputeadmin3@example.com", Role.SYSTEM_ADMIN)
    admin = auth_for(client, "disputeadmin3@example.com")

    client.post(f"/api/corrections/{correction.id}/dispute",
                json={"case": "please"},
                headers=auth_for(client, "disputer@example.com"))
    entry = client.get("/api/moderation/disputes", headers=admin).get_json()["disputes"][0]

    client.post(f"/api/moderation/disputes/{entry['id']}/resolve",
                json={"outcome": "uphold"}, headers=admin)

    assert Correction.query.get(correction.id).overturned_at is None


def test_a_decided_dispute_cannot_be_decided_again(client, corrected):
    _, _, correction = corrected
    make_user("disputeadmin4@example.com", Role.SYSTEM_ADMIN)
    admin = auth_for(client, "disputeadmin4@example.com")

    client.post(f"/api/corrections/{correction.id}/dispute",
                json={"case": "x"}, headers=auth_for(client, "disputer@example.com"))
    entry = client.get("/api/moderation/disputes", headers=admin).get_json()["disputes"][0]

    client.post(f"/api/moderation/disputes/{entry['id']}/resolve",
                json={"outcome": "uphold"}, headers=admin)
    again = client.post(f"/api/moderation/disputes/{entry['id']}/resolve",
                        json={"outcome": "reverse"}, headers=admin)
    assert again.status_code == 409


def test_an_editor_cannot_decide_a_dispute(client, corrected):
    """PRD 1.3.2 power 4 belongs to administrators. An editor deciding a dispute
    about their own correction is not review."""
    _, _, correction = corrected

    client.post(f"/api/corrections/{correction.id}/dispute",
                json={"case": "x"}, headers=auth_for(client, "disputer@example.com"))

    response = client.get(
        "/api/moderation/disputes", headers=auth_for(client, "disputeeditor@example.com")
    )
    assert response.status_code == 403
