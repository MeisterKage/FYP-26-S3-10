"""Integration tests across the API, RBAC, and database (PRD 7.5.2).

These walk the v1 journeys end to end: register, submit, review, publish, read,
and the paywall. They run against SQLite in memory, so they need no Supabase
connection and are safe to run in CI.
"""
import pytest

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleSource, Category, EditorCategory, User
from app.security import hash_password

PASSWORD = "IntegrationTest123!"


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


def token_for(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
#  Health and registration
# --------------------------------------------------------------------------- #

def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_register_creates_a_free_reader(client, category):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "New.Reader@example.com",
            "displayName": "New Reader",
            "password": PASSWORD,
            "categoryIds": [category.id],
        },
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["user"]["role"] == Role.FREE_REGISTERED.value
    # Email is normalised to lowercase, or duplicate detection can be bypassed.
    assert body["user"]["email"] == "new.reader@example.com"
    assert body["token"]


def test_register_rejects_a_short_password(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "displayName": "A", "password": "short"},
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "password"


def test_register_rejects_a_duplicate_email(client):
    make_user("taken@example.com", Role.FREE_REGISTERED)
    response = client.post(
        "/api/auth/register",
        json={"email": "taken@example.com", "displayName": "B", "password": PASSWORD},
    )
    assert response.status_code == 409


def test_login_failures_are_indistinguishable(client):
    """A wrong password and an unknown account must give the same response,
    or the form becomes an account-enumeration oracle."""
    make_user("real@example.com", Role.FREE_REGISTERED)

    wrong = client.post(
        "/api/auth/login", json={"email": "real@example.com", "password": "WrongPassword1!"}
    )
    missing = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "WrongPassword1!"}
    )

    assert wrong.status_code == missing.status_code == 401
    assert wrong.get_json() == missing.get_json()


def test_password_reset_does_not_reveal_whether_an_email_exists(client):
    make_user("known@example.com", Role.FREE_REGISTERED)

    known = client.post("/api/auth/password-reset/request", json={"email": "known@example.com"})
    unknown = client.post("/api/auth/password-reset/request", json={"email": "no@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()


# --------------------------------------------------------------------------- #
#  RBAC
# --------------------------------------------------------------------------- #

def test_reader_cannot_create_an_article(client, category):
    make_user("reader@example.com", Role.FREE_REGISTERED)
    token = token_for(client, "reader@example.com")

    response = client.post(
        "/api/articles",
        json={"title": "Nope", "categoryId": category.id, "body": "<p>x</p>"},
        headers=auth(token),
    )
    assert response.status_code == 403


def test_anonymous_request_is_401_not_403(client):
    assert client.get("/api/articles/mine").status_code == 401


def test_suspended_account_cannot_use_a_valid_token(client):
    user = make_user("suspended@example.com", Role.FREE_REGISTERED)
    token = token_for(client, "suspended@example.com")

    user.is_suspended = True
    _db.session.commit()

    assert client.get("/api/auth/me", headers=auth(token)).status_code == 403


def test_editor_cannot_review_outside_assigned_categories(client, category):
    contributor = make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR)
    make_user("editor@example.com", Role.EDITOR)  # assigned to nothing

    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="Pending piece",
        slug="pending-piece",
        body="<p>Body</p>",
        status=ArticleStatus.PENDING,
    )
    _db.session.add(article)
    _db.session.commit()

    token = token_for(client, "editor@example.com")
    response = client.post(f"/api/review/{article.id}/approve", headers=auth(token))
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
#  The publishing workflow
# --------------------------------------------------------------------------- #

def test_draft_to_published_journey(client, category):
    contributor = make_user("author@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("tech.editor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    _db.session.commit()

    author_token = token_for(client, "author@example.com")

    created = client.post(
        "/api/articles",
        json={
            "title": "Grid operators report record renewable share",
            "categoryId": category.id,
            "summary": "What the figures show.",
            "body": "<p>The operator published quarterly figures this week.</p>",
            "sources": [
                {"url": "https://example.org/a", "label": "Operator statement"},
                {"url": "https://example.org/b", "label": "Regulator filing"},
            ],
        },
        headers=auth(author_token),
    )
    assert created.status_code == 201
    article_id = created.get_json()["id"]
    assert created.get_json()["status"] == "draft"
    assert len(created.get_json()["sources"]) == 2

    submitted = client.post(f"/api/articles/{article_id}/submit", headers=auth(author_token))
    assert submitted.get_json()["status"] == "pending"

    editor_token = token_for(client, "tech.editor@example.com")

    queue = client.get("/api/review/queue", headers=auth(editor_token)).get_json()
    assert [a["id"] for a in queue["articles"]] == [article_id]

    approved = client.post(f"/api/review/{article_id}/approve", headers=auth(editor_token))
    assert approved.status_code == 200
    payload = approved.get_json()

    assert payload["article"]["status"] == "published"
    # PRD 1.3.3: the score is visible from the moment the article goes live.
    assert payload["article"]["credibility"]["score"] > 0
    # First article, so the contributor is still "New Contributor".
    assert payload["credibility"]["provisional"] is True
    # 0.75 * 70 provisional + 2 sources * 5 = 62.5
    assert payload["credibility"]["score"] == 62.5

    slug = payload["article"]["slug"]
    public = client.get(f"/api/articles/{slug}")
    assert public.status_code == 200
    assert "body" in public.get_json()["article"]


def test_rejection_requires_a_reason(client, category):
    contributor = make_user("author2@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("editor2@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))

    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="Thin piece",
        slug="thin-piece",
        body="<p>Body</p>",
        status=ArticleStatus.PENDING,
    )
    _db.session.add(article)
    _db.session.commit()

    token = token_for(client, "editor2@example.com")
    response = client.post(f"/api/review/{article.id}/reject", json={}, headers=auth(token))
    assert response.status_code == 422


def test_unpublished_article_is_not_publicly_readable(client, category):
    contributor = make_user("author3@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="Draft only",
        slug="draft-only",
        body="<p>Secret</p>",
        status=ArticleStatus.DRAFT,
    )
    _db.session.add(article)
    _db.session.commit()

    assert client.get("/api/articles/draft-only").status_code == 404


# --------------------------------------------------------------------------- #
#  The paywall  (the response must not contain the body at all)
# --------------------------------------------------------------------------- #

def test_premium_body_is_omitted_for_a_non_subscriber(client, category):
    contributor = make_user("premium.author@example.com", Role.VERIFIED_CONTRIBUTOR)
    make_user("freeloader@example.com", Role.FREE_REGISTERED)

    # The paywall permits a short opening preview, so the marker goes past it.
    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="Members only",
        slug="members-only",
        body="<p>" + ("Opening paragraph. " * 40) + "SECRET_PREMIUM_CONTENT</p>",
        status=ArticleStatus.PUBLISHED,
        is_premium=True,
    )
    _db.session.add(article)
    _db.session.commit()

    token = token_for(client, "freeloader@example.com")
    response = client.get("/api/articles/members-only", headers=auth(token))
    payload = response.get_json()["article"]

    assert payload["paywalled"] is True
    assert "body" not in payload
    # The preview is bounded, and the withheld content is nowhere in the bytes.
    assert len(payload["bodyPreview"]) <= 310
    assert b"SECRET_PREMIUM_CONTENT" not in response.data


def test_author_can_always_read_their_own_premium_article(client, category):
    contributor = make_user("owner@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="My own premium piece",
        slug="my-own-premium-piece",
        body="<p>Mine</p>",
        status=ArticleStatus.PUBLISHED,
        is_premium=True,
    )
    _db.session.add(article)
    _db.session.commit()

    token = token_for(client, "owner@example.com")
    payload = client.get(
        "/api/articles/my-own-premium-piece", headers=auth(token)
    ).get_json()["article"]
    assert payload["body"] == "<p>Mine</p>"


# --------------------------------------------------------------------------- #
#  Sanitisation
# --------------------------------------------------------------------------- #

def test_script_tags_are_stripped_from_an_article_body(client, category):
    make_user("xss@example.com", Role.VERIFIED_CONTRIBUTOR)
    token = token_for(client, "xss@example.com")

    response = client.post(
        "/api/articles",
        json={
            "title": "Harmless title",
            "categoryId": category.id,
            "body": "<p>Real text</p><script>alert('xss')</script><img src=x onerror=alert(1)>",
        },
        headers=auth(token),
    )
    body = response.get_json()["body"]

    assert "<script>" not in body
    assert "onerror" not in body
    assert "Real text" in body


def test_html_in_a_title_is_stripped(client, category):
    make_user("xss2@example.com", Role.VERIFIED_CONTRIBUTOR)
    token = token_for(client, "xss2@example.com")

    response = client.post(
        "/api/articles",
        json={
            "title": "<script>alert(1)</script>Clean headline",
            "categoryId": category.id,
            "body": "<p>Body</p>",
        },
        headers=auth(token),
    )
    assert response.get_json()["title"] == "Clean headline"


# --------------------------------------------------------------------------- #
#  Disclosure — the score's arithmetic reaches the reader and the editor
# --------------------------------------------------------------------------- #

def test_published_article_carries_its_breakdown(client, category):
    """PRD 1.3.3 promises a reader can trace exactly why a score is what it is,
    so the article payload carries the arithmetic, not just the total."""
    contributor = make_user("tracer@example.com", Role.VERIFIED_CONTRIBUTOR)
    article = Article(
        contributor_id=contributor.id, category_id=category.id,
        title="Traceable", slug="traceable", body="<p>b</p>",
        status=ArticleStatus.PUBLISHED, credibility_score=62.5,
    )
    _db.session.add(article)
    _db.session.commit()

    payload = client.get("/api/articles/traceable").get_json()["article"]
    breakdown = payload["credibility"]["breakdown"]

    # The parts must reconstruct the whole, or the disclosure is decorative.
    total = (
        breakdown["accuracy"] + breakdown["sources"] + breakdown["corrections"]
        + breakdown["retraction"] + breakdown["reports"]
    )
    assert round(total, 2) == payload["credibility"]["score"]


def test_review_queue_shows_the_prospective_score_not_zero(client, category):
    """A pending article has never been scored, so its stored score is 0.0.
    Showing that to an editor reads as "worthless" rather than "not yet scored"
    — on the one screen where it would bias the decision."""
    contributor = make_user("pending.writer@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("queue.editor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))

    article = Article(
        contributor_id=contributor.id, category_id=category.id,
        title="Not yet scored", slug="not-yet-scored", body="<p>b</p>",
        status=ArticleStatus.PENDING,
    )
    _db.session.add(article)
    _db.session.commit()
    _db.session.add(ArticleSource(article_id=article.id, url="https://example.org/a"))
    _db.session.commit()

    assert article.credibility_score == 0.0  # nothing has scored it yet

    queue = client.get(
        "/api/review/queue", headers=auth(token_for(client, "queue.editor@example.com"))
    ).get_json()

    shown = queue["articles"][0]["credibility"]
    assert shown["score"] > 0, "editor was shown a 0 for an unscored article"
    assert shown["prospective"] is True
    assert shown["breakdown"]["sources"] > 0


def test_what_counts_is_public(client):
    """The inputs are published for readers, most of whom are not signed in."""
    payload = client.get("/api/scoring/formula").get_json()

    assert len(payload["bands"]) == 4
    names = {i["name"] for i in payload["inputs"]}
    assert "Contributor accuracy" in names
    assert "Verifiable sources" in names
    assert {i["effect"] for i in payload["inputs"]} == {"raises", "lowers"}
    # "New contributor" is otherwise an unexplained state on a profile.
    assert "New contributor" in payload["newContributor"]


def test_the_tuning_constants_are_not_published(client):
    """Team decision: the inputs are disclosed, the weights are not.

    This asserts the absence rather than trusting the shape, because a weight
    leaks the moment someone adds `**cfg` back into the payload for debugging.
    """
    body = client.get("/api/scoring/formula").get_data(as_text=True)

    assert "constants" not in body
    for key in (
        "accuracy_weight",
        "source_points",
        "source_cap",
        "correction_penalty",
        "retraction_penalty",
        "report_threshold",
        "report_penalty",
        "min_articles_for_accuracy",
    ):
        assert key not in body, f"{key} is exposed on the public formula endpoint"


# --------------------------------------------------------------------------- #
#  Authoring: what the editing screen needs (PDD Figures 5.41-5.42)
# --------------------------------------------------------------------------- #

def test_the_writers_list_withholds_bodies(client, category):
    """/articles/mine is a list, so it omits bodies on purpose.

    The editing screen therefore cannot be built on it, which is why the
    owner-scoped single read below exists.
    """
    make_user("listauthor@example.com", Role.VERIFIED_CONTRIBUTOR)
    token = token_for(client, "listauthor@example.com")

    client.post(
        "/api/articles",
        json={"title": "Listed", "body": "<p>Full body</p>", "categoryId": category.id},
        headers=auth(token),
    )

    listed = client.get("/api/articles/mine", headers=auth(token)).get_json()["articles"][0]
    assert "body" not in listed


def test_an_author_can_load_their_own_article_body_for_editing(client, category):
    make_user("owner@example.com", Role.VERIFIED_CONTRIBUTOR)
    token = token_for(client, "owner@example.com")

    created = client.post(
        "/api/articles",
        json={
            "title": "Editable",
            "body": "<p>The body</p>",
            "categoryId": category.id,
            "sources": [{"url": "https://example.com/a", "label": "A"}],
        },
        headers=auth(token),
    ).get_json()
    article_id = created["id"]

    response = client.get(f"/api/articles/{article_id}", headers=auth(token))
    assert response.status_code == 200

    article = response.get_json()["article"]
    assert article["body"] == "<p>The body</p>"
    assert article["sources"][0]["url"] == "https://example.com/a"


def test_one_author_cannot_load_another_authors_draft(client, category):
    owner = make_user("owner2@example.com", Role.VERIFIED_CONTRIBUTOR)
    make_user("stranger@example.com", Role.VERIFIED_CONTRIBUTOR)

    article = Article(
        contributor_id=owner.id,
        category_id=category.id,
        title="Not yours",
        slug="not-yours",
        body="<p>Private</p>",
        status=ArticleStatus.DRAFT,
    )
    _db.session.add(article)
    _db.session.commit()

    token = token_for(client, "stranger@example.com")
    response = client.get(f"/api/articles/{article.id}", headers=auth(token))
    assert response.status_code == 403


def test_a_rejected_article_carries_its_reason_back_to_the_writer(client, category):
    """A writer cannot act on a rejection they cannot read."""
    contributor = make_user("returned@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("editor4@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))

    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="Needs work",
        slug="needs-work",
        body="<p>Body</p>",
        status=ArticleStatus.PENDING,
    )
    _db.session.add(article)
    _db.session.commit()

    editor_token = token_for(client, "editor4@example.com")
    client.post(
        f"/api/review/{article.id}/reject",
        json={"reason": "Second source needed for the funding figure."},
        headers=auth(editor_token),
    )

    author_token = token_for(client, "returned@example.com")
    mine = client.get("/api/articles/mine", headers=auth(author_token)).get_json()["articles"][0]
    assert mine["status"] == "rejected"
    assert mine["rejectionReason"] == "Second source needed for the funding figure."


# --------------------------------------------------------------------------- #
#  Moderation queue (PDD Figure 5.50)
# --------------------------------------------------------------------------- #

def test_the_flagged_list_carries_the_reports_behind_each_count(client, category):
    """A count alone gives a moderator nothing to act on: resolving works one
    report at a time, so the ids have to travel with the article."""
    from app.models import PlatformSetting, Report

    contributor = make_user("flagged@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("moderator@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    # Drop the escalation threshold so two reports are enough to surface it.
    _db.session.add(PlatformSetting(key="report_threshold", value=2))

    article = Article(
        contributor_id=contributor.id,
        category_id=category.id,
        title="Disputed piece",
        slug="disputed-piece",
        body="<p>Body</p>",
        status=ArticleStatus.PUBLISHED,
    )
    _db.session.add(article)
    _db.session.commit()

    for i in range(2):
        reader = make_user(f"flagger{i}@example.com", Role.FREE_REGISTERED)
        _db.session.add(
            Report(article_id=article.id, reporter_id=reader.id, reason=f"Reason {i}")
        )
    _db.session.commit()

    token = token_for(client, "moderator@example.com")
    payload = client.get("/api/moderation/reports", headers=auth(token)).get_json()

    assert payload["threshold"] == 2
    entry = next(f for f in payload["flagged"] if f["articleId"] == article.id)
    assert entry["openReports"] == 2
    assert len(entry["reports"]) == 2
    assert {r["reason"] for r in entry["reports"]} == {"Reason 0", "Reason 1"}
    assert all(isinstance(r["id"], int) for r in entry["reports"])


def test_a_moderator_only_sees_flagged_articles_in_their_own_categories(client, category):
    from app.models import PlatformSetting, Report

    other = Category(name="Sport", slug="sport")
    _db.session.add(other)
    contributor = make_user("flagged2@example.com", Role.VERIFIED_CONTRIBUTOR)
    editor = make_user("moderator2@example.com", Role.EDITOR)
    _db.session.commit()
    # Assigned to `category`, but the flagged article is in `other`.
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    _db.session.add(PlatformSetting(key="report_threshold", value=1))

    article = Article(
        contributor_id=contributor.id,
        category_id=other.id,
        title="Elsewhere",
        slug="elsewhere",
        body="<p>Body</p>",
        status=ArticleStatus.PUBLISHED,
    )
    _db.session.add(article)
    _db.session.commit()

    reader = make_user("flagger9@example.com", Role.FREE_REGISTERED)
    _db.session.add(Report(article_id=article.id, reporter_id=reader.id, reason="No"))
    _db.session.commit()

    token = token_for(client, "moderator2@example.com")
    payload = client.get("/api/moderation/reports", headers=auth(token)).get_json()
    assert all(f["articleId"] != article.id for f in payload["flagged"])


# --------------------------------------------------------------------------- #
#  Separation of duties: an editor may not approve their own article
# --------------------------------------------------------------------------- #

def _own_pending_article(author, category, title):
    article = Article(
        contributor_id=author.id,
        category_id=category.id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        body="<p>Body</p>",
        status=ArticleStatus.PENDING,
    )
    _db.session.add(article)
    _db.session.commit()
    return article


def test_an_editor_cannot_approve_their_own_article(client, category):
    """Editors may write, so without this guard an editor could write, submit,
    and publish inside their own section with nobody else ever reading it."""
    editor = make_user("selfeditor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    _db.session.commit()

    article = _own_pending_article(editor, category, "My own piece")

    token = token_for(client, "selfeditor@example.com")
    response = client.post(f"/api/review/{article.id}/approve", headers=auth(token))

    assert response.status_code == 403
    assert "another editor" in response.get_json()["error"]["message"]
    # And it must genuinely not have published.
    assert Article.query.get(article.id).status == ArticleStatus.PENDING


def test_an_editor_cannot_reject_their_own_article_either(client, category):
    """Rejection is the same authority as approval, applied the other way."""
    editor = make_user("selfeditor2@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    _db.session.commit()

    article = _own_pending_article(editor, category, "My other piece")

    token = token_for(client, "selfeditor2@example.com")
    response = client.post(
        f"/api/review/{article.id}/reject", json={"reason": "no"}, headers=auth(token)
    )
    assert response.status_code == 403


def test_another_editor_can_still_approve_it(client, category):
    """The guard must block the author, not the article."""
    author = make_user("selfeditor3@example.com", Role.EDITOR)
    colleague = make_user("colleague@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=author.id, category_id=category.id))
    _db.session.add(EditorCategory(editor_id=colleague.id, category_id=category.id))
    _db.session.commit()

    article = _own_pending_article(author, category, "Reviewed by a colleague")

    token = token_for(client, "colleague@example.com")
    assert client.post(f"/api/review/{article.id}/approve", headers=auth(token)).status_code == 200


def test_an_administrator_may_still_approve_their_own(client, category):
    """PRD 1.3.2 gives administrators oversight of everything, and they can
    already override any editorial decision, so the exemption changes nothing
    they could not do in two steps anyway."""
    admin = make_user("selfadmin@example.com", Role.SYSTEM_ADMIN)
    _db.session.commit()

    article = _own_pending_article(admin, category, "An administrator piece")

    token = token_for(client, "selfadmin@example.com")
    assert client.post(f"/api/review/{article.id}/approve", headers=auth(token)).status_code == 200
