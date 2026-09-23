"""Editor automation: risk-ordered review, batch approval, and the auto-publish valve.

The pure rules in `app.triage` are tested directly, without an application
context, the same way the scoring engine is. The rest runs against the API and a
real database, because the properties that matter here are about what actually
reaches readers and what the audit log records.
"""
from datetime import timedelta

import pytest

from app import triage
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import (
    Article, ArticleSource, AuditLog, Category, EditorCategory, PlatformSetting, User,
    utcnow,
)
from app.review_service import run_autopublish
from app.security import hash_password

PASSWORD = "AutomationTest123!"


# =========================================================================== #
#  Pure rules
# =========================================================================== #

def priority(**overrides):
    inputs = dict(
        contributor_accuracy=95.0,
        source_count=3,
        has_duplicate_title=False,
        hours_waiting=0.0,
    )
    inputs.update(overrides)
    return triage.review_priority(**inputs).priority


def test_a_new_writer_outranks_a_veteran_on_an_identical_article():
    assert priority(contributor_accuracy=None) > priority(contributor_accuracy=95.0)


def test_a_clean_well_sourced_article_from_a_trusted_writer_scores_zero():
    assert priority() == 0.0


def test_each_signal_raises_priority_on_its_own():
    base = priority()
    assert priority(contributor_accuracy=60.0) > base
    assert priority(source_count=0) > base
    assert priority(has_duplicate_title=True) > base
    assert priority(hours_waiting=10) > base


def test_fewer_sources_rank_higher_than_more():
    assert priority(source_count=0) > priority(source_count=1) > priority(source_count=3)


def test_sources_beyond_the_expected_number_add_nothing():
    assert priority(source_count=3) == priority(source_count=10)


def test_waiting_eventually_lifts_a_safe_article_above_a_risky_new_one():
    """Nothing starves. A trusted article that has waited long enough surfaces."""
    risky_just_arrived = priority(contributor_accuracy=None, source_count=0)
    safe_after_six_weeks = priority(hours_waiting=24 * 42)
    assert safe_after_six_weeks > risky_just_arrived


def test_risk_still_sets_the_order_in_a_two_week_backlog():
    """Waiting must stay a tiebreaker. Found on the live site, not in review.

    The first shipped wait weight overtook a whole new-writer flag in three
    days, so in a genuine backlog the queue silently reverted to oldest-first.
    """
    risky_just_arrived = priority(contributor_accuracy=None, source_count=0)
    safe_after_two_weeks = priority(hours_waiting=24 * 14)
    assert risky_just_arrived > safe_after_two_weeks

    new_writer_just_arrived = priority(contributor_accuracy=None)
    veteran_after_one_week = priority(hours_waiting=24 * 7)
    assert new_writer_just_arrived > veteran_after_one_week


def test_the_breakdown_adds_up_to_the_total():
    result = triage.review_priority(
        contributor_accuracy=None, source_count=1, has_duplicate_title=True, hours_waiting=4
    )
    parts = result.as_dict()["breakdown"]
    assert round(sum(parts.values()), 2) == result.priority


def test_the_valve_is_closed_by_default_however_bad_the_backlog():
    assert not triage.valve_open(queue_depth=10_000, oldest_wait_hours=10_000)


def test_the_valve_opens_on_depth_or_on_wait_when_enabled():
    on = {"autopublish_enabled": 1, "autopublish_queue_depth": 25, "autopublish_max_wait_hours": 48}
    assert not triage.valve_open(queue_depth=25, oldest_wait_hours=1, settings=on)
    assert triage.valve_open(queue_depth=26, oldest_wait_hours=1, settings=on)
    assert triage.valve_open(queue_depth=1, oldest_wait_hours=48, settings=on)


def eligibility(**overrides):
    inputs = dict(
        contributor_accuracy=95.0,
        published_count=20,
        suspended=False,
        source_count=2,
        has_duplicate_title=False,
        is_premium=False,
    )
    inputs.update(overrides)
    return triage.autopublish_eligibility(**inputs)


def test_a_trusted_clean_article_is_eligible():
    assert eligibility().eligible


def test_eligibility_reports_every_failing_rule_not_just_the_first():
    verdict = eligibility(
        contributor_accuracy=None,
        published_count=0,
        suspended=True,
        source_count=0,
        has_duplicate_title=True,
        is_premium=True,
    )
    assert not verdict.eligible
    assert len(verdict.reasons) == 6


@pytest.mark.parametrize(
    "override",
    [
        {"contributor_accuracy": None},
        {"contributor_accuracy": 80.0},
        {"published_count": 3},
        {"suspended": True},
        {"source_count": 0},
        {"has_duplicate_title": True},
        {"is_premium": True},
    ],
)
def test_any_single_failing_rule_blocks_auto_publish(override):
    assert not eligibility(**override).eligible


# =========================================================================== #
#  Fixtures for the integration tests
# =========================================================================== #

@pytest.fixture()
def category(app):
    category = Category(name="Technology", slug="technology")
    _db.session.add(category)
    _db.session.commit()
    return category


def make_user(email, role, accuracy=None):
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(PASSWORD),
        role=role,
        accuracy_rate=accuracy,
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


_counter = {"n": 0}


def make_article(writer, category, *, status=ArticleStatus.PENDING, sources=0,
                 title=None, premium=False, submitted_hours_ago=1):
    _counter["n"] += 1
    n = _counter["n"]
    now = utcnow()
    article = Article(
        contributor_id=writer.id,
        category_id=category.id,
        title=title or f"Article number {n}",
        slug=f"article-{n}",
        body="<p>Body.</p>",
        status=status,
        is_premium=premium,
        submitted_at=now - timedelta(hours=submitted_hours_ago),
        published_at=now if status == ArticleStatus.PUBLISHED else None,
    )
    _db.session.add(article)
    _db.session.flush()
    for i in range(sources):
        _db.session.add(ArticleSource(article_id=article.id, url=f"https://example.org/{n}/{i}"))
    _db.session.commit()
    return article


def give_record(writer, category, count):
    """A published back catalogue, so eligibility's article-count rule is satisfied."""
    for _ in range(count):
        make_article(writer, category, status=ArticleStatus.PUBLISHED, sources=2)


def set_settings(**values):
    for key, value in values.items():
        _db.session.merge(PlatformSetting(key=key, value=float(value)))
    _db.session.commit()


@pytest.fixture()
def people(app, category):
    editor = make_user("editor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))
    _db.session.commit()
    return {
        "editor": editor,
        "admin": make_user("admin@example.com", Role.SYSTEM_ADMIN),
        "veteran": make_user("veteran@example.com", Role.VERIFIED_CONTRIBUTOR, accuracy=96.0),
        "newbie": make_user("newbie@example.com", Role.VERIFIED_CONTRIBUTOR, accuracy=None),
    }


# =========================================================================== #
#  Risk-ordered queue
# =========================================================================== #

def test_the_queue_puts_a_risky_new_article_above_an_older_safe_one(client, category, people):
    safe_and_older = make_article(people["veteran"], category, sources=3, submitted_hours_ago=5)
    risky_and_newer = make_article(people["newbie"], category, sources=0, submitted_hours_ago=1)

    response = client.get("/api/review/queue", headers=auth(token_for(client, "editor@example.com")))
    ids = [a["id"] for a in response.get_json()["articles"]]

    assert ids == [risky_and_newer.id, safe_and_older.id]


def test_each_queued_article_carries_its_priority_breakdown(client, category, people):
    make_article(people["newbie"], category, sources=0)
    response = client.get("/api/review/queue", headers=auth(token_for(client, "editor@example.com")))
    item = response.get_json()["articles"][0]

    assert item["priority"]["priority"] > 0
    assert item["priority"]["breakdown"]["newContributor"] > 0
    assert item["priority"]["breakdown"]["sources"] > 0


def test_a_duplicate_title_is_flagged_in_the_queue(client, category, people):
    make_article(people["veteran"], category, status=ArticleStatus.PUBLISHED, title="Budget passes")
    make_article(people["veteran"], category, sources=3, title="Budget passes")

    response = client.get("/api/review/queue", headers=auth(token_for(client, "editor@example.com")))
    assert response.get_json()["articles"][0]["priority"]["breakdown"]["duplicate"] > 0


# =========================================================================== #
#  Batch approval
# =========================================================================== #

def test_batch_approve_publishes_every_chosen_article(client, category, people):
    a = make_article(people["veteran"], category, sources=2)
    b = make_article(people["veteran"], category, sources=2)

    response = client.post(
        "/api/review/batch-approve",
        json={"articleIds": [a.id, b.id]},
        headers=auth(token_for(client, "editor@example.com")),
    )

    assert response.status_code == 200
    assert response.get_json() == {"approved": [a.id, b.id], "failed": []}
    assert _db.session.get(Article, a.id).status == ArticleStatus.PUBLISHED
    assert _db.session.get(Article, b.id).status == ArticleStatus.PUBLISHED


def test_batch_approve_writes_one_audit_row_per_article(client, category, people):
    ids = [make_article(people["veteran"], category, sources=2).id for _ in range(3)]
    client.post(
        "/api/review/batch-approve",
        json={"articleIds": ids},
        headers=auth(token_for(client, "editor@example.com")),
    )

    rows = AuditLog.query.filter_by(action="article.approve").all()
    assert sorted(r.entity_id for r in rows) == sorted(ids)


def test_batch_approve_reports_failures_without_blocking_the_rest(client, category, people):
    good = make_article(people["veteran"], category, sources=2)
    already_live = make_article(people["veteran"], category, status=ArticleStatus.PUBLISHED)
    other = Category(name="Sport", slug="sport")
    _db.session.add(other)
    _db.session.commit()
    outside = make_article(people["veteran"], other, sources=2)

    response = client.post(
        "/api/review/batch-approve",
        json={"articleIds": [good.id, already_live.id, outside.id, 999999]},
        headers=auth(token_for(client, "editor@example.com")),
    )
    body = response.get_json()

    assert body["approved"] == [good.id]
    assert sorted(f["id"] for f in body["failed"]) == sorted([already_live.id, outside.id, 999999])
    assert _db.session.get(Article, outside.id).status == ArticleStatus.PENDING


def test_an_editor_cannot_batch_approve_their_own_article(client, category, people):
    own = make_article(people["editor"], category, sources=2)
    response = client.post(
        "/api/review/batch-approve",
        json={"articleIds": [own.id]},
        headers=auth(token_for(client, "editor@example.com")),
    )
    assert response.get_json()["approved"] == []
    assert _db.session.get(Article, own.id).status == ArticleStatus.PENDING


@pytest.mark.parametrize("ids", [[], ["12"], [1.5], [True]])
def test_batch_approve_rejects_malformed_ids(client, people, ids):
    response = client.post(
        "/api/review/batch-approve",
        json={"articleIds": ids},
        headers=auth(token_for(client, "editor@example.com")),
    )
    assert response.status_code == 422


def test_batch_approve_is_capped(client, people):
    response = client.post(
        "/api/review/batch-approve",
        json={"articleIds": list(range(1, 52))},
        headers=auth(token_for(client, "editor@example.com")),
    )
    assert response.status_code == 422


def test_a_reader_cannot_batch_approve(client, category, people):
    make_user("reader@example.com", Role.FREE_REGISTERED)
    article = make_article(people["veteran"], category, sources=2)
    response = client.post(
        "/api/review/batch-approve",
        json={"articleIds": [article.id]},
        headers=auth(token_for(client, "reader@example.com")),
    )
    assert response.status_code == 403


# =========================================================================== #
#  Auto-publish
# =========================================================================== #

@pytest.fixture()
def valve_open(app):
    set_settings(autopublish_enabled=1, autopublish_queue_depth=0)


def test_nothing_is_auto_published_while_the_feature_is_off(app, category, people):
    give_record(people["veteran"], category, 12)
    article = make_article(people["veteran"], category, sources=2)

    result = run_autopublish()

    assert not result["open"]
    assert _db.session.get(Article, article.id).status == ArticleStatus.PENDING


def test_under_pressure_only_eligible_articles_are_published(app, category, people, valve_open):
    give_record(people["veteran"], category, 12)
    eligible = make_article(people["veteran"], category, sources=2)
    premium = make_article(people["veteran"], category, sources=2, premium=True)
    unsourced = make_article(people["veteran"], category, sources=0)
    from_newbie = make_article(people["newbie"], category, sources=2)

    result = run_autopublish()

    assert result["open"]
    assert result["published"] == [eligible.id]
    assert set(result["held"]) == {premium.id, unsourced.id, from_newbie.id}

    published = _db.session.get(Article, eligible.id)
    assert published.status == ArticleStatus.PUBLISHED
    assert published.auto_published_at is not None
    assert published.reviewed_by_id is None


def test_a_sweep_publishes_no_more_than_its_limit(app, category, people, valve_open):
    set_settings(autopublish_max_per_run=2)
    give_record(people["veteran"], category, 12)
    for _ in range(5):
        make_article(people["veteran"], category, sources=2)

    assert len(run_autopublish()["published"]) == 2


def test_an_auto_published_article_is_labelled_for_readers(client, category, people, valve_open):
    give_record(people["veteran"], category, 12)
    article = make_article(people["veteran"], category, sources=2)
    run_autopublish()

    review = client.get(f"/api/articles/{article.slug}").get_json()["article"]["review"]
    assert review["awaitingReview"] is True
    assert review["autoPublishedAt"] is not None


def test_a_human_approved_article_is_not_labelled(client, category, people):
    article = make_article(people["veteran"], category, sources=2)
    client.post(
        f"/api/review/{article.id}/approve",
        headers=auth(token_for(client, "editor@example.com")),
    )
    review = client.get(f"/api/articles/{article.slug}").get_json()["article"]["review"]
    assert review["awaitingReview"] is False


def test_auto_publish_does_not_change_the_credibility_score(app, category, people, valve_open):
    """The label sits beside the score. The same article scores the same either way."""
    give_record(people["veteran"], category, 12)
    auto = make_article(people["veteran"], category, sources=2)
    run_autopublish()

    from app.scoring_service import explain_article

    assert _db.session.get(Article, auto.id).credibility_score == explain_article(auto).score


def test_every_auto_publish_is_audited(app, category, people, valve_open):
    give_record(people["veteran"], category, 12)
    article = make_article(people["veteran"], category, sources=2)
    run_autopublish()

    row = AuditLog.query.filter_by(action="article.autopublish", entity_id=article.id).one()
    assert row.actor_id is None
    assert "pending" in row.detail


def test_the_cli_sweep_reports_what_it_did(app, category, people, valve_open):
    give_record(people["veteran"], category, 12)
    make_article(people["veteran"], category, sources=2)

    output = app.test_cli_runner().invoke(args=["autopublish-backlog"]).output
    assert "Valve open" in output
    assert "Published 1" in output


# =========================================================================== #
#  Confirmation
# =========================================================================== #

def test_confirming_clears_the_label(client, category, people, valve_open):
    give_record(people["veteran"], category, 12)
    article = make_article(people["veteran"], category, sources=2)
    run_autopublish()
    token = token_for(client, "editor@example.com")

    queue = client.get("/api/review/queue", headers=auth(token)).get_json()
    assert [a["id"] for a in queue["awaitingConfirmation"]] == [article.id]

    response = client.post(f"/api/review/{article.id}/confirm", headers=auth(token))
    assert response.status_code == 200

    review = client.get(f"/api/articles/{article.slug}").get_json()["article"]["review"]
    assert review["awaitingReview"] is False
    queue = client.get("/api/review/queue", headers=auth(token)).get_json()
    assert queue["awaitingConfirmation"] == []


def test_only_an_auto_published_article_can_be_confirmed(client, category, people):
    article = make_article(people["veteran"], category, status=ArticleStatus.PUBLISHED)
    response = client.post(
        f"/api/review/{article.id}/confirm",
        headers=auth(token_for(client, "editor@example.com")),
    )
    assert response.status_code == 409


def test_an_editor_cannot_confirm_their_own_article(client, category, people):
    article = make_article(people["editor"], category, status=ArticleStatus.PUBLISHED)
    article.auto_published_at = utcnow()
    _db.session.commit()

    response = client.post(
        f"/api/review/{article.id}/confirm",
        headers=auth(token_for(client, "editor@example.com")),
    )
    assert response.status_code == 403


# =========================================================================== #
#  Revocation
# =========================================================================== #

def correct(client, article, token):
    return client.post(
        f"/api/moderation/articles/{article.id}/correction",
        json={"type": "correction", "reason": "The figure was wrong."},
        headers=auth(token),
    )


def test_a_correction_on_an_auto_published_article_suspends_the_writer(
    client, category, people, valve_open
):
    give_record(people["veteran"], category, 12)
    article = make_article(people["veteran"], category, sources=2)
    run_autopublish()

    correct(client, article, token_for(client, "editor@example.com"))

    writer = _db.session.get(User, people["veteran"].id)
    assert writer.autopublish_suspended_until is not None

    # And the next article waits for a human.
    next_one = make_article(people["veteran"], category, sources=2)
    result = run_autopublish()
    assert next_one.id not in result["published"]
    assert any("suspended" in r for r in result["held"][next_one.id])


def test_a_correction_on_a_human_approved_article_does_not_suspend(client, category, people):
    article = make_article(people["veteran"], category, status=ArticleStatus.PUBLISHED, sources=2)
    correct(client, article, token_for(client, "editor@example.com"))

    assert _db.session.get(User, people["veteran"].id).autopublish_suspended_until is None


def test_overturning_the_correction_lifts_the_suspension(client, category, people, valve_open):
    give_record(people["veteran"], category, 12)
    article = make_article(people["veteran"], category, sources=2)
    run_autopublish()
    correct(client, article, token_for(client, "editor@example.com"))

    correction_id = client.get(f"/api/articles/{article.slug}").get_json()["article"][
        "corrections"
    ][0]["id"]
    response = client.post(
        f"/api/moderation/corrections/{correction_id}/overturn",
        headers=auth(token_for(client, "admin@example.com")),
    )
    assert response.status_code == 200

    assert _db.session.get(User, people["veteran"].id).autopublish_suspended_until is None
    assert AuditLog.query.filter_by(action="user.autopublish_restored").count() == 1


# =========================================================================== #
#  Settings
# =========================================================================== #

def test_review_settings_appear_in_their_own_group(client, people):
    response = client.get("/api/admin/settings", headers=auth(token_for(client, "admin@example.com")))
    groups = {s["key"]: s["group"] for s in response.get_json()["settings"]}

    assert groups["accuracy_weight"] == "scoring"
    assert groups["autopublish_enabled"] == "review"
    assert groups["triage_wait_weight"] == "review"


def test_changing_a_review_setting_does_not_rescore(client, people):
    response = client.put(
        "/api/admin/settings",
        json={"settings": {"autopublish_enabled": 1}},
        headers=auth(token_for(client, "admin@example.com")),
    )
    assert response.status_code == 200
    assert response.get_json()["rescored"] is False


def test_changing_a_scoring_setting_still_rescores(client, people):
    response = client.put(
        "/api/admin/settings",
        json={"settings": {"source_points": 6}},
        headers=auth(token_for(client, "admin@example.com")),
    )
    assert response.get_json()["rescored"] is True


def test_an_unknown_setting_is_still_rejected(client, people):
    response = client.put(
        "/api/admin/settings",
        json={"settings": {"not_a_real_setting": 1}},
        headers=auth(token_for(client, "admin@example.com")),
    )
    assert response.status_code == 422
