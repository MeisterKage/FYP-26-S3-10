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
    # Official bodies on ordinary addresses are found through Wikidata; see
    # test_a_domain_owned_by_a_government_body_counts_as_official.
    ("https://www.bankofengland.co.uk/", "unrated"),
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


# =========================================================================== #
#  The administrators' list, and Wikidata ownership
# =========================================================================== #

@pytest.mark.parametrize("typed,expected", [
    ("https://www.BankOfEngland.co.uk/monetary-policy", "bankofengland.co.uk"),
    ("ofcom.org.uk", "ofcom.org.uk"),
    ("www.niwa.co.nz/", "niwa.co.nz"),
    ("not a domain", None),
    ("localhost", None),
    ("evil.com; DROP TABLE", None),
])
def test_domains_are_normalised(typed, expected):
    assert sr.normalise_domain(typed) == expected


def test_an_admin_rule_overrides_the_lists_and_covers_subdomains():
    rules = {"smh.com.au": ("unreliable", "Testing an override.")}
    rating = sr.classify("https://amp.smh.com.au/story", admin_rules=rules)
    assert rating.tier == "unreliable"
    assert "administrators" in rating.reason
    assert sr.classify("https://www.smh.com.au/").tier == "reliable"  # untouched without it


def test_an_admin_rule_cannot_launder_a_retracted_paper():
    rules = {"doi.org": ("official", "Nope.")}
    rating = sr.classify("https://doi.org/10.1016/x", doi_status="retracted", admin_rules=rules)
    assert rating.tier == "retracted"


def test_a_domain_owned_by_a_government_body_counts_as_official():
    rating = sr.classify("https://www.some-regulator.com/", official_owner="Some Regulator")
    assert rating.tier == "official"
    assert "Some Regulator" in rating.reason and "Wikidata" in rating.reason


def _binding(qid, label, kind):
    return {"item": {"value": f"http://www.wikidata.org/entity/{qid}"},
            "itemLabel": {"value": label}, "kind": {"value": kind}}


def test_wikidata_official_but_not_media(app, monkeypatch):
    from app.models import DomainLookup, utcnow
    answers = {
        "bankofengland.co.uk": [_binding("Q1", "Bank of England", "official")],
        "abc.net.au": [_binding("Q2", "Australian Broadcasting Corporation", "official"),
                       _binding("Q2", "Australian Broadcasting Corporation", "media")],
        "niwa.co.nz": [_binding("Q3", "NIWA information series", "media"),
                       _binding("Q4", "National Institute of Water and Atmospheric Research", "official")],
        "smh.com.au": [_binding("Q5", "The Sydney Morning Herald", "media")],
    }
    calls = []
    monkeypatch.setattr(source_service, "_wikidata_query",
                        lambda d: calls.append(d) or answers.get(d, []))
    now = utcnow()
    assert source_service.official_owner("bankofengland.co.uk", now, fetch=True) == "Bank of England"
    assert source_service.official_owner("abc.net.au", now, fetch=True) is None
    assert source_service.official_owner("niwa.co.nz", now, fetch=True).startswith("National Institute")
    assert source_service.official_owner("smh.com.au", now, fetch=True) is None
    # Cached: asking again does not ask Wikidata again.
    source_service.official_owner("bankofengland.co.uk", now, fetch=True)
    assert calls.count("bankofengland.co.uk") == 1
    assert DomainLookup.query.count() == 4


def test_a_wikidata_outage_is_retried_sooner(app, monkeypatch):
    from datetime import timedelta
    from app.models import utcnow
    def down(d):
        raise OSError("unreachable")
    monkeypatch.setattr(source_service, "_wikidata_query", down)
    now = utcnow()
    assert source_service.official_owner("ofcom.org.uk", now, fetch=True) is None
    monkeypatch.setattr(source_service, "_wikidata_query",
                        lambda d: [_binding("Q9", "Ofcom", "official")])
    assert source_service.official_owner("ofcom.org.uk", now + timedelta(hours=2), fetch=True) is None
    assert source_service.official_owner("ofcom.org.uk", now + timedelta(days=2), fetch=True) == "Ofcom"


def test_wikidata_is_only_asked_when_nothing_else_decides(client, world, app, monkeypatch):
    asked = []
    monkeypatch.setattr(source_service, "official_owner",
                        lambda domain, now, fetch: asked.append(domain) or None)
    submit_with(client, world, ["https://www.abs.gov.au/", "https://www.reuters.com/",
                                "https://a-small-local-site.com.au/"])
    assert asked == ["a-small-local-site.com.au"]


@pytest.fixture()
def admin(app):
    return make_user("admin@example.com", Role.SYSTEM_ADMIN)


def test_an_admin_grade_regrades_articles_citing_the_domain(client, world, admin):
    article = submit_with(client, world, ["https://a-small-local-site.com.au/news"])
    assert article.sources[0].tier == "unrated"
    headers = auth(client, "admin@example.com")

    made = client.put("/api/admin/source-rules", json={
        "domain": "https://www.a-small-local-site.com.au/", "tier": "official",
        "reason": "The local council's official news site.",
    }, headers=headers)
    assert made.status_code == 201
    assert made.get_json()["regraded"] == 1
    _db.session.refresh(article.sources[0])
    assert article.sources[0].tier == "official"
    assert AuditLog.query.filter_by(action="source_rule.set").count() == 1

    listing = client.get("/api/admin/source-rules", headers=headers).get_json()
    assert listing["rules"][0]["domain"] == "a-small-local-site.com.au"

    removed = client.delete(f"/api/admin/source-rules/{listing['rules'][0]['id']}", headers=headers)
    assert removed.status_code == 200
    _db.session.refresh(article.sources[0])
    assert article.sources[0].tier == "unrated"


@pytest.mark.parametrize("body,field", [
    ({"domain": "not a domain", "tier": "official", "reason": "A good reason."}, "domain"),
    ({"domain": "ok.com.au", "tier": "research", "reason": "A good reason."}, "tier"),
    ({"domain": "ok.com.au", "tier": "official", "reason": "no"}, "reason"),
])
def test_admin_grades_are_validated(client, world, admin, body, field):
    response = client.put("/api/admin/source-rules", json=body,
                          headers=auth(client, "admin@example.com"))
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == field


def test_only_administrators_grade_domains(client, world):
    response = client.put("/api/admin/source-rules", json={
        "domain": "ok.com.au", "tier": "official", "reason": "Editors cannot do this."},
        headers=auth(client, "editor@example.com"))
    assert response.status_code == 403
