"""Monthly digests: ranking, the month's corrections, and what readers are told.

The properties that matter: articles are ranked by credibility not views, a
topic with too few articles gets no edition, a mid-month edition is marked in
progress and completed after the month ends, subscribers hear about each
edition exactly once, and an edition never keeps recommending an article that
was later corrected or retracted without saying so.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import digest
from app.digest_service import compile_month
from app.enums import ArticleStatus, CorrectionType, Role
from app.extensions import db as _db
from app.models import (
    Article, Category, Correction, DigestEdition, Notification, User,
)
from app.security import hash_password

UTC = timezone.utc
PASSWORD = "DigestTest12345!"


def at(day, month=9, hour=12):
    return datetime(2026, month, day, hour, tzinfo=UTC)


#=========================================================================== #
# Pure rules
#=========================================================================== #

def cand(i, score, day=10, writer=1):
    return digest.Candidate(i, writer, score, at(day))


def test_articles_are_ranked_by_credibility_not_recency():
    edition = digest.compile_edition([cand(1, 60, day=28), cand(2, 90, day=2), cand(3, 75)], [])
    assert [c.article_id for c in edition.ranked] == [2, 3, 1]


def test_ties_go_to_the_more_recent_article():
    edition = digest.compile_edition([cand(1, 80, day=3), cand(2, 80, day=20), cand(3, 50)], [])
    assert [c.article_id for c in edition.ranked][:2] == [2, 1]


def test_too_few_articles_means_no_edition():
    assert digest.compile_edition([cand(1, 90), cand(2, 80)], []) is None


def test_an_edition_lists_at_most_ten():
    edition = digest.compile_edition([cand(i, i) for i in range(1, 15)], [])
    assert len(edition.ranked) == 10
    assert edition.stats["articleCount"] == 14


def test_stats_describe_the_whole_month():
    corrections = [
        digest.CorrectionRecord(1, "A", "correction", "Wrong figure", at(5), overturned=False),
        digest.CorrectionRecord(2, "B", "correction", "Wrong date", at(6), overturned=True),
    ]
    edition = digest.compile_edition(
        [cand(1, 80, writer=1), cand(2, 60, writer=2), cand(3, 70, writer=1)], corrections)
    assert edition.stats == {
        "articleCount": 3, "averageCredibility": 70.0, "writerCount": 2, "correctionCount": 1,
    }
    assert [c["reason"] for c in edition.corrections] == ["Wrong figure", "Wrong date"]


@pytest.mark.parametrize("month,start,end", [
    ("2026-09", at(1, 9, 0), at(1, 10, 0)),
    ("2026-12", datetime(2026, 12, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
])
def test_months_are_calendar_months(month, start, end):
    assert digest.parse_month(month) == (start, end)


@pytest.mark.parametrize("bad", ["2026-13", "2026-9", "September", "", None, 202609])
def test_malformed_months_are_refused(bad):
    with pytest.raises(ValueError):
        digest.parse_month(bad)


def test_previous_month_wraps_the_year():
    assert digest.previous_month(at(15, 1)) == "2025-12"
    assert digest.previous_month(at(1, 10)) == "2026-09"


#=========================================================================== #
# Compiling against the database
#=========================================================================== #

@pytest.fixture()
def world(app):
    tech = Category(name="Technology", slug="technology")
    politics = Category(name="Politics", slug="politics")
    _db.session.add_all([tech, politics])
    writer = User(email="w@example.com", display_name="Writer",
                  password_hash=hash_password(PASSWORD), role=Role.VERIFIED_CONTRIBUTOR)
    editor = User(email="e@example.com", display_name="Editor",
                  password_hash=hash_password(PASSWORD), role=Role.EDITOR)
    reader = User(email="r@example.com", display_name="Reader",
                  password_hash=hash_password(PASSWORD), role=Role.FREE_REGISTERED)
    _db.session.add_all([writer, editor, reader])
    _db.session.commit()
    return {"tech": tech, "politics": politics, "writer": writer, "editor": editor,
            "reader": reader}


_n = {"n": 0}


def publish(world, category, score, day, country=None, month=9):
    _n["n"] += 1
    a = Article(contributor_id=world["writer"].id, category_id=world[category].id,
                title=f"Story {_n['n']}", slug=f"story-{_n['n']}", body="<p>b</p>",
                status=ArticleStatus.PUBLISHED, published_at=at(day, month),
                credibility_score=score, country_code=country)
    _db.session.add(a)
    _db.session.commit()
    return a


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


AFTER_SEPTEMBER = at(1, 10, 3)
MID_SEPTEMBER = at(20, 9)


def test_editions_are_made_per_topic_and_per_country(world):
    for score, country in ((90, "AU"), (80, "AU"), (70, "AU"), (60, "JP")):
        publish(world, "tech", score, day=10, country=country)
    publish(world, "politics", 88, day=10)                        #too few for politics
    publish(world, "tech", 99, day=3, month=8)                   #wrong month

    result = compile_month("2026-09", now=AFTER_SEPTEMBER)
    assert sorted(result["created"]) == ["technology", "technology-au"]

    edition = DigestEdition.query.filter_by(key="technology").one()
    assert [e.score_at_compile for e in edition.entries] == [90, 80, 70, 60]


def test_a_mid_month_edition_is_provisional_and_completed_later(client, world):
    for score in (90, 80, 70):
        publish(world, "tech", score, day=5)
    compile_month("2026-09", now=MID_SEPTEMBER)
    first = client.get("/api/digests/2026-09/technology").get_json()["edition"]
    assert first["provisional"] is True

    publish(world, "tech", 95, day=25)
    result = compile_month("2026-09", now=AFTER_SEPTEMBER)
    assert result["recompiled"] == ["technology"]
    final = client.get("/api/digests/2026-09/technology").get_json()["edition"]
    assert final["provisional"] is False
    assert final["entries"][0]["scoreAtCompile"] == 95


def test_a_final_edition_is_not_recompiled_unless_forced(world):
    for score in (90, 80, 70):
        publish(world, "tech", score, day=5)
    compile_month("2026-09", now=AFTER_SEPTEMBER)
    publish(world, "tech", 99, day=6)

    assert compile_month("2026-09", now=AFTER_SEPTEMBER)["unchanged"] == ["technology"]
    assert compile_month("2026-09", force=True, now=AFTER_SEPTEMBER)["recompiled"] == ["technology"]


def test_subscribers_are_notified_once_when_the_edition_becomes_final(client, world):
    headers = auth(client, "r@example.com")
    assert client.post("/api/digests/subscriptions", json={"categoryId": world["tech"].id},
                       headers=headers).status_code == 201
    for score in (90, 80, 70):
        publish(world, "tech", score, day=5)

    compile_month("2026-09", now=MID_SEPTEMBER)          #provisional: no one told yet
    assert Notification.query.filter_by(event_type="monthly_digest").count() == 0
    compile_month("2026-09", now=AFTER_SEPTEMBER)        #final: told once
    compile_month("2026-09", force=True, now=AFTER_SEPTEMBER)  #forced again: not twice
    notes = Notification.query.filter_by(event_type="monthly_digest").all()
    assert len(notes) == 1
    assert notes[0].link == "/digests/2026-09/technology"


def test_a_country_subscription_hears_only_about_that_country(client, world):
    headers = auth(client, "r@example.com")
    client.post("/api/digests/subscriptions",
                json={"categoryId": world["tech"].id, "countryCode": "jp"}, headers=headers)
    for score in (90, 80, 70):
        publish(world, "tech", score, day=5, country="AU")
    compile_month("2026-09", now=AFTER_SEPTEMBER)
    assert Notification.query.filter_by(event_type="monthly_digest").count() == 0


def test_a_later_correction_is_shown_against_the_article(client, world):
    articles = [publish(world, "tech", s, day=5) for s in (90, 80, 70)]
    compile_month("2026-09", now=AFTER_SEPTEMBER)

    _db.session.add(Correction(article_id=articles[0].id, issued_by_id=world["editor"].id,
                               correction_type=CorrectionType.CORRECTION, reason="Wrong figure",
                               created_at=at(12, 10)))
    articles[1].status = ArticleStatus.RETRACTED
    _db.session.commit()

    entries = client.get("/api/digests/2026-09/technology").get_json()["edition"]["entries"]
    assert entries[0]["since"] == "Corrected on 12 October 2026."
    assert entries[1]["since"] == "Retracted since this digest was compiled."
    assert entries[2]["since"] is None
    #Still in its original place: the edition is fixed, the note is the update.
    assert [e["rank"] for e in entries] == [1, 2, 3]


def test_the_months_corrections_are_listed(client, world):
    articles = [publish(world, "tech", s, day=5) for s in (90, 80, 70)]
    _db.session.add(Correction(article_id=articles[2].id, issued_by_id=world["editor"].id,
                               correction_type=CorrectionType.CORRECTION,
                               reason="Quote attributed to the wrong official",
                               created_at=at(18)))
    _db.session.commit()
    compile_month("2026-09", now=AFTER_SEPTEMBER)
    edition = client.get("/api/digests/2026-09/technology").get_json()["edition"]
    assert edition["stats"]["correctionCount"] == 1
    assert edition["corrections"][0]["reason"] == "Quote attributed to the wrong official"


def test_an_unpublished_article_is_named_but_not_served(client, world):
    articles = [publish(world, "tech", s, day=5) for s in (90, 80, 70)]
    compile_month("2026-09", now=AFTER_SEPTEMBER)
    articles[0].status = ArticleStatus.UNPUBLISHED
    _db.session.commit()
    first = client.get("/api/digests/2026-09/technology").get_json()["edition"]["entries"][0]
    assert first["available"] is False
    assert set(first["article"]) == {"id", "title"}


#=========================================================================== #
# API
#=========================================================================== #

def test_the_archive_is_public_and_filterable(client, world):
    for score in (90, 80, 70):
        publish(world, "tech", score, day=5)
        publish(world, "politics", score, day=5)
    compile_month("2026-09", now=AFTER_SEPTEMBER)

    everything = client.get("/api/digests").get_json()
    assert everything["months"] == ["2026-09"]
    assert len(everything["editions"]) == 2
    tech = client.get("/api/digests?category=technology").get_json()["editions"]
    assert [e["title"] for e in tech] == ["Technology, September 2026"]


def test_subscribing_twice_is_harmless_and_unsubscribing_works(client, world):
    headers = auth(client, "r@example.com")
    body = {"categoryId": world["tech"].id}
    assert client.post("/api/digests/subscriptions", json=body, headers=headers).status_code == 201
    assert client.post("/api/digests/subscriptions", json=body, headers=headers).status_code == 200
    subs = client.get("/api/digests/subscriptions", headers=headers).get_json()["subscriptions"]
    assert len(subs) == 1
    assert client.delete(f"/api/digests/subscriptions/{subs[0]['id']}",
                         headers=headers).status_code == 204


def test_subscribing_needs_an_account(client, world):
    response = client.post("/api/digests/subscriptions", json={"categoryId": world["tech"].id})
    assert response.status_code == 401


def test_only_an_administrator_compiles(client, world):
    response = client.post("/api/admin/digests/compile", json={"month": "2026-08"},
                           headers=auth(client, "e@example.com"))
    assert response.status_code == 403


@pytest.mark.parametrize("month", ["2026-13", 202608, "2999-01"])
def test_compile_refuses_bad_or_future_months(client, world, month):
    admin = User(email="a@example.com", display_name="Admin",
                 password_hash=hash_password(PASSWORD), role=Role.SYSTEM_ADMIN)
    _db.session.add(admin)
    _db.session.commit()
    response = client.post("/api/admin/digests/compile", json={"month": month},
                           headers=auth(client, "a@example.com"))
    assert response.status_code == 422


def test_a_provisional_edition_that_falls_below_the_minimum_is_withdrawn(world):
    articles = [publish(world, "tech", s, day=5) for s in (90, 80, 70)]
    compile_month("2026-09", now=MID_SEPTEMBER)
    articles[0].status = ArticleStatus.UNPUBLISHED
    _db.session.commit()

    result = compile_month("2026-09", now=AFTER_SEPTEMBER)
    assert result["withdrawn"] == ["technology"]
    assert DigestEdition.query.count() == 0
