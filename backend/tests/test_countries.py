"""Country-based news: tagging an article with the country it is about.

The list is fixed server-side, so the properties that matter are that nothing
off the list gets in, that only published work is counted, and that the
country plus section view (which the monthly digest will compile) filters
correctly.
"""
import pytest

from app import countries
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, User, utcnow
from app.security import hash_password

PASSWORD = "CountriesTest123!"


def test_the_list_is_the_249_current_iso_countries():
    assert len(countries.COUNTRIES) == 249
    assert countries.COUNTRIES["AU"] == "Australia"
    assert "SU" not in countries.COUNTRIES  # the Soviet Union is history


@pytest.mark.parametrize("raw,expected", [("au", "AU"), (" nz ", "NZ"), (None, None), ("", None)])
def test_codes_are_normalised(raw, expected):
    assert countries.normalise(raw) == expected


@pytest.mark.parametrize("raw", ["XX", "Australia", "AUS", 36, ["AU"]])
def test_anything_off_the_list_is_rejected(raw):
    with pytest.raises(ValueError):
        countries.normalise(raw)


def test_name_search_needs_three_letters():
    assert "JP" in countries.codes_matching("japan")
    assert countries.codes_matching("an") == []


# --------------------------------------------------------------------------- #

@pytest.fixture()
def world(app):
    politics = Category(name="Politics", slug="politics")
    sport = Category(name="Sport", slug="sport")
    _db.session.add_all([politics, sport])
    writer = User(
        email="writer@example.com", display_name="Writer",
        password_hash=hash_password(PASSWORD), role=Role.VERIFIED_CONTRIBUTOR,
    )
    _db.session.add(writer)
    _db.session.commit()
    return {"politics": politics, "sport": sport, "writer": writer}


def auth(client):
    token = client.post(
        "/api/auth/login", json={"email": "writer@example.com", "password": PASSWORD}
    ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


_n = {"n": 0}


def article(world, country, category=None, status=ArticleStatus.PUBLISHED, title=None):
    _n["n"] += 1
    a = Article(
        contributor_id=world["writer"].id,
        category_id=(category or world["politics"]).id,
        country_code=country,
        title=title or f"Story {_n['n']}", slug=f"story-{_n['n']}", body="<p>b</p>",
        status=status,
        published_at=utcnow() if status == ArticleStatus.PUBLISHED else None,
    )
    _db.session.add(a)
    _db.session.commit()
    return a


def test_a_writer_sets_and_changes_the_country(client, world):
    headers = auth(client)
    created = client.post(
        "/api/articles",
        json={"title": "About Japan", "categoryId": world["politics"].id, "countryCode": "jp"},
        headers=headers,
    ).get_json()
    assert created["country"] == {"code": "JP", "name": "Japan"}

    cleared = client.patch(
        f"/api/articles/{created['id']}", json={"countryCode": None}, headers=headers
    ).get_json()
    assert cleared["country"] is None  # international


def test_an_invalid_country_is_refused_with_a_field_error(client, world):
    response = client.post(
        "/api/articles",
        json={"title": "Nowhere", "categoryId": world["politics"].id, "countryCode": "ZZ"},
        headers=auth(client),
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "countryCode"


def test_the_country_list_counts_only_published_articles(client, world):
    article(world, "AU")
    article(world, "AU")
    article(world, "NZ")
    article(world, "SG", status=ArticleStatus.PENDING)
    article(world, None)

    listed = client.get("/api/countries").get_json()["countries"]
    assert listed == [
        {"code": "AU", "name": "Australia", "articleCount": 2},
        {"code": "NZ", "name": "New Zealand", "articleCount": 1},
    ]


def test_a_country_page_filters_by_section(client, world):
    article(world, "AU", world["politics"], title="Council vote")
    article(world, "AU", world["sport"], title="Carnival")
    article(world, "NZ", world["sport"], title="Elsewhere")

    everything = client.get("/api/countries/au/articles").get_json()
    assert {a["title"] for a in everything["articles"]} == {"Council vote", "Carnival"}
    assert [s["slug"] for s in everything["sections"]] == ["politics", "sport"]

    sport = client.get("/api/countries/AU/articles?category=sport").get_json()
    assert [a["title"] for a in sport["articles"]] == ["Carnival"]
    assert sport["selectedSection"] == "sport"
    # Every chip stays visible while one is selected.
    assert len(sport["sections"]) == 2


def test_unknown_countries_and_sections_are_not_found(client, world):
    assert client.get("/api/countries/xx/articles").status_code == 404
    assert client.get("/api/countries/au/articles?category=nope").status_code == 404


def test_search_finds_an_article_by_its_country_name(client, world):
    article(world, "JP", title="Battery recycling standard agreed")
    results = client.get("/api/search?q=japan").get_json()["articles"]
    assert [a["title"] for a in results] == ["Battery recycling standard agreed"]


def test_the_demo_seed_gives_six_countries_at_least_five_articles(app):
    """The sample data promised for the demo: a good size for every country."""
    import seed

    seed.seed()
    rows = dict(
        _db.session.query(Article.country_code, _db.func.count())
        .filter(Article.status == ArticleStatus.PUBLISHED)
        .group_by(Article.country_code)
        .all()
    )
    for code in ("AU", "NZ", "SG", "JP", "GB", "US"):
        assert rows.get(code, 0) >= 5, (code, rows.get(code))

    # Running it again adds nothing.
    before = Article.query.count()
    seed.seed_countries()
    assert Article.query.count() == before
