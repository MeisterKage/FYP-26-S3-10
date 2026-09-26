"""Source ratings: what a cited link is worth, and who has the final word.

A source used to earn full points for starting with http. These tests pin
down the replacement: points follow what kind of source it is, taken from
rules and public lists; placeholders, missing pages and retracted papers earn
nothing; and an editor can overrule the automatic rating, with a reason.
"""
import pytest

from app import source_rating as sr
from app import source_service
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleSource, AuditLog, Category, EditorCategory, User
from app.scoring_service import explain_article
from app.security import hash_password

PASSWORD = "SourceRating123!"


# =========================================================================== #
#  Rules
# =========================================================================== #

@pytest.mark.parametrize("url,tier", [
    ("https://www.abs.gov.au/statistics", "official"),
    ("https://www.aph.gov.au/Parliamentary_Business", "official"),
    ("https://www.stats.govt.nz/", "official"),
    ("https://www.gov.uk/government/organisations/environment-agency", "official"),
    ("https://www.bankofengland.co.uk/", "official"),
    ("https://data.un.org/", "official"),
    ("https://www.who.int/news", "official"),
    ("https://www.uow.edu.au/research", "institution"),
    ("https://www.ox.ac.uk/", "institution"),
    ("https://www.bbc.co.uk/news/articles/x", "reliable"),
    ("https://www.reuters.com/world/", "reliable"),
    ("https://www.dailymail.co.uk/news/x", "deprecated"),
    ("https://www.breitbart.com/x", "deprecated"),          # blacklisted on the list
    ("https://en.wikipedia.org/wiki/Privacy_Act_1988", "unreliable"),
    ("https://x.com/someone/status/1", "unreliable"),
    ("https://someblog.substack.com/p/post", "unreliable"),
    ("https://www.foxnews.com/politics", "unrated"),        # "no consensus" on the list
    ("https://a-small-local-site.com.au/", "unrated"),
    ("https://example.org/source/1", "invalid"),
    ("https://news.test/", "invalid"),
])
def test_each_kind_of_source_gets_its_tier(url, tier):
    assert sr.classify(url).tier == tier


def test_points_by_tier():
    assert sr.classify("https://www.abs.gov.au/").points == 5
    assert sr.classify("https://a-small-local-site.com.au/").points == 2
    assert sr.classify("https://en.wikipedia.org/wiki/X").points == 0


def test_a_listed_source_says_where_its_rating_came_from():
    reason = sr.classify("https://www.reuters.com/").reason
    assert "generally reliable" in reason and "Wikipedia" in reason and "Reuters" in reason


def test_a_missing_page_is_not_a_source():
    assert sr.classify("https://www.abs.gov.au/nope", exists=False).tier == "invalid"


def test_a_site_that_blocks_scripts_keeps_its_rating():
    """Unknown existence (blocked, timed out) is not held against a source."""
    assert sr.classify("https://www.reuters.com/", exists=None).tier == "reliable"


@pytest.mark.parametrize("status,tier,flagged", [
    ("ok", "research", False),
    ("retracted", "retracted", True),
    ("unknown", "invalid", False),
    (None, "research", False),
])
def test_papers_are_checked_for_retraction(status, tier, flagged):
    rating = sr.classify("https://doi.org/10.1016/S0140-6736(97)11096-0", doi_status=status)
    assert (rating.tier, rating.flagged) == (tier, flagged)


def test_a_doi_inside_a_publisher_url_is_recognised():
    rating = sr.classify("https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.116.061102",
                         doi_status="ok")
    assert rating.tier == "research"
    assert rating.doi == "10.1103/physrevlett.116.061102"


def test_deprecated_sources_are_flagged_for_the_editor():
    assert sr.classify("https://www.dailymail.co.uk/").flagged is True
    assert sr.classify("https://www.bbc.co.uk/").flagged is False


def test_an_editor_verdict_overrides_the_tier():
    unrated = sr.classify("https://a-small-local-site.com.au/")
    assert sr.points_for(unrated, "accepted") == 5
    assert sr.points_for(sr.classify("https://www.bbc.co.uk/"), "rejected") == 0
    assert sr.points_for(unrated, None) == 2


# =========================================================================== #
#  Against the database
# =========================================================================== #

def make_user(email, role):
    u = User(email=email, display_name=email.split("@")[0],
             password_hash=hash_password(PASSWORD), role=role)
    _db.session.add(u)
    _db.session.commit()
    return u


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def world(app):
    politics = Category(name="Politics", slug="politics")
    sport = Category(name="Sport", slug="sport")
    _db.session.add_all([politics, sport])
    _db.session.commit()
    editor = make_user("editor@example.com", Role.EDITOR)
    other = make_user("other.editor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=politics.id))
    _db.session.add(EditorCategory(editor_id=other.id, category_id=sport.id))
    _db.session.commit()
    return {"politics": politics, "editor": editor,
            "writer": make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR)}


def submit_with(client, world, urls):
    headers = auth(client, "writer@example.com")
    created = client.post("/api/articles", json={
        "title": "Sourced", "categoryId": world["politics"].id, "body": "<p>Text here.</p>",
        "sources": [{"url": u} for u in urls],
    }, headers=headers).get_json()
    assert client.post(f"/api/articles/{created['id']}/submit", headers=headers).status_code == 200
    return _db.session.get(Article, created["id"])


def test_submitting_rates_the_sources(client, world):
    article = submit_with(client, world, [
        "https://www.abs.gov.au/", "https://example.org/fake", "https://en.wikipedia.org/wiki/X",
    ])
    tiers = [s.tier for s in article.sources]
    assert tiers == ["official", "invalid", "unreliable"]
    assert [s.is_valid for s in article.sources] == [True, False, False]


def test_the_score_follows_source_quality(client, world):
    strong = submit_with(client, world, [
        "https://www.abs.gov.au/", "https://www.reuters.com/", "https://www.bbc.co.uk/"])
    padded = submit_with(client, world, [
        "https://example.org/1", "https://example.org/2", "https://example.org/3"])
    assert explain_article(strong).source_component == 15
    assert explain_article(padded).source_component == 0


def test_citing_the_same_link_twice_counts_once(client, world):
    article = submit_with(client, world, ["https://www.abs.gov.au/", "https://www.abs.gov.au"])
    assert [s.tier for s in article.sources] == ["official", "invalid"]


def test_an_editor_can_accept_or_reject_with_a_reason(client, world):
    article = submit_with(client, world, ["https://a-small-local-site.com.au/"])
    source = article.sources[0]
    headers = auth(client, "editor@example.com")

    no_reason = client.post(f"/api/review/{article.id}/sources/{source.id}/verdict",
                            json={"verdict": "accepted"}, headers=headers)
    assert no_reason.status_code == 422

    ok = client.post(f"/api/review/{article.id}/sources/{source.id}/verdict",
                     json={"verdict": "accepted", "reason": "Council's official newsletter."},
                     headers=headers).get_json()
    assert ok["source"]["rating"]["points"] == 5
    assert ok["source"]["rating"]["editorVerdict"] == "accepted"
    assert AuditLog.query.filter_by(action="source.accepted").count() == 1

    cleared = client.post(f"/api/review/{article.id}/sources/{source.id}/verdict",
                          json={"verdict": None}, headers=headers).get_json()
    assert cleared["source"]["rating"]["points"] == 2


def test_an_editor_of_another_section_cannot_rule_on_sources(client, world):
    article = submit_with(client, world, ["https://www.abs.gov.au/"])
    response = client.post(f"/api/review/{article.id}/sources/{article.sources[0].id}/verdict",
                           json={"verdict": "rejected", "reason": "Not relevant here."},
                           headers=auth(client, "other.editor@example.com"))
    assert response.status_code == 404


def test_a_writer_cannot_rule_on_their_own_sources(client, world):
    article = submit_with(client, world, ["https://www.abs.gov.au/"])
    response = client.post(f"/api/review/{article.id}/sources/{article.sources[0].id}/verdict",
                           json={"verdict": "accepted", "reason": "Trust me on this one."},
                           headers=auth(client, "writer@example.com"))
    assert response.status_code == 403


def test_a_retracted_paper_is_caught_and_flagged(client, world, app, monkeypatch):
    app.config["ORIGINALITY_FETCH_SOURCES"] = True
    from app.source_fetch import Fetched
    monkeypatch.setattr("app.originality_service.fetch",
                        lambda url: Fetched(url, "text/html", "<p>paper</p>"))
    monkeypatch.setattr(source_service, "crossref_status",
                        lambda doi: "retracted" if doi.startswith("10.1016") else "ok")
    article = submit_with(client, world, [
        "https://doi.org/10.1016/S0140-6736(97)11096-0",
        "https://doi.org/10.1103/PhysRevLett.116.061102",
    ])
    assert [(s.tier, s.flagged) for s in article.sources] == [
        ("retracted", True), ("research", False)]


def test_sources_rated_before_this_system_score_as_they_did(app, world):
    """Nothing moves until a source is rated."""
    article = Article(contributor_id=world["writer"].id, category_id=world["politics"].id,
                      title="Old", slug="old", body="<p>b</p>", status=ArticleStatus.PUBLISHED)
    _db.session.add(article)
    _db.session.flush()
    for i in range(3):
        _db.session.add(ArticleSource(article_id=article.id, url=f"https://example.org/{i}"))
    _db.session.commit()
    assert explain_article(article).source_component == 15
