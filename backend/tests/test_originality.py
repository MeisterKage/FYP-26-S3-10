"""Originality checking: the engine, the source fetcher's guards, and the workflow.

What has to hold: copied text is found even when lightly reworded, quotations
are never counted as copying, a cited page copied without quotation marks is
caught, the fetcher cannot be pointed at the server's own network, and a
writer's check never reveals another writer's unpublished draft.
"""
import io
import socket
import urllib.error

import pytest

from app import originality as engine
from app import source_fetch
from app import triage
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleSource, Category, EditorCategory, User
from app.originality_service import index_article
from app.security import hash_password

ORIGINAL = (
    "<p>The regional council voted on Tuesday to expand the coastal cycleway by a further "
    "twelve kilometres, linking the northern beaches with the harbour precinct. Engineers "
    "expect construction to begin in autumn once the environmental assessment is complete, "
    "and the project budget has been set at forty million dollars over three years.</p>"
    "<p>Residents raised concerns about parking along the foreshore during public hearings, "
    "while cycling groups argued the route would ease weekend congestion on the main road.</p>"
)
UNRELATED = (
    "<p>Researchers at the marine institute have catalogued a new species of reef fish "
    "after a survey of deep coral gardens off the continental shelf. The fish, which glows "
    "faintly under ultraviolet light, was found at depths below two hundred metres.</p>"
    "<p>The team plans further expeditions next summer to map the extent of the habitat.</p>"
)


def pct(submission, other):
    doc = engine.parse(submission)
    other_hashes = set(engine.kgrams(engine.parse(other).tokens))
    return engine.coverage(doc, engine.matched_positions(doc, other_hashes))


# =========================================================================== #
#  Engine
# =========================================================================== #

def test_a_verbatim_copy_is_a_complete_match():
    assert pct(ORIGINAL, ORIGINAL) == 100.0


def test_unrelated_articles_do_not_match():
    assert pct(UNRELATED, ORIGINAL) == 0.0


def test_a_copied_paragraph_inside_new_text_is_measured_proportionally():
    first_paragraph = ORIGINAL.split("</p>")[0] + "</p>"
    mixed = first_paragraph + UNRELATED
    result = pct(mixed, ORIGINAL)
    assert 30 < result < 70


def test_light_paraphrase_does_not_hide_a_copy():
    reworded = (
        "<p>The regional council votes on Tuesday to expand its coastal cycleway by a further "
        "12 kilometres, linking northern beaches with harbour precinct. Engineers expected "
        "construction to begin in autumn once an environmental assessment is completed, "
        "and the project budget has been set at 40 million dollars over 3 years.</p>"
    )
    assert pct(reworded, ORIGINAL) >= 80


def test_the_winnowing_guarantee_finds_any_eight_word_shared_run():
    shared = "harbour precinct engineers expect construction begin autumn environmental"
    a = f"<p>Alpha bravo charlie delta echo foxtrot {shared} golf hotel india juliet</p>"
    b = f"<p>Kilo lima mike november oscar papa {shared} quebec romeo sierra tango</p>"
    assert pct(a, b) > 0


def test_quoted_text_is_never_counted_as_copying():
    quoted = f"<p>The council said: “{engine.parse(ORIGINAL).text}”</p>"
    assert pct(quoted, ORIGINAL) == 0.0


def test_a_blockquote_is_never_counted_as_copying():
    quoted = f"<blockquote>{ORIGINAL}</blockquote><p>Our reporter adds a short note.</p>"
    assert pct(quoted, ORIGINAL) == 0.0


def test_matched_passages_are_returned_as_text():
    doc = engine.parse(ORIGINAL + UNRELATED)
    positions = engine.matched_positions(doc, set(engine.kgrams(engine.parse(ORIGINAL).tokens)))
    passages = engine.passages(doc, positions)
    assert passages and "coastal cycleway" in passages[0].text


@pytest.mark.parametrize("percent,expected", [
    (0, "original"), (19.9, "original"), (20, "partial"), (49.9, "partial"), (50, "substantial"),
])
def test_levels_follow_the_thresholds(percent, expected):
    assert engine.level(percent) == expected


def test_quotes_are_verified_against_the_cited_source():
    source = engine.parse(
        "The minister told parliament that the scheme would be reviewed every twelve months "
        "and that funding was secure until the end of the decade.", html=False)
    article = engine.parse(
        "<p>“The scheme would be reviewed every twelve months and funding was secure until "
        "the end of the decade,” the minister said. She also claimed “unemployment has "
        "halved since the programme began in the northern districts.”</p>")
    quotes = engine.verify_quotes(article, {"https://example.org/hansard": source})
    assert [q["verified"] for q in quotes] == [True, False]
    assert quotes[0]["source"] == "https://example.org/hansard"


# =========================================================================== #
#  Source fetcher: server-side request forgery guards
# =========================================================================== #

@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.org/file",
    "http://localhost/",
    "http://127.0.0.1:5000/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata
    "http://[::1]/",
    "http://user:pass@example.org/",
    "http://example.org:5432/",
])
def test_the_fetcher_refuses_anything_but_public_web_pages(url):
    with pytest.raises(source_fetch.SourceUnavailable):
        source_fetch.check_url(url)


def test_a_public_name_resolving_to_a_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))])
    with pytest.raises(source_fetch.SourceUnavailable, match="public internet"):
        source_fetch.check_url("https://innocent-looking.example.com/")


def test_a_redirect_to_an_internal_address_is_refused(monkeypatch):
    monkeypatch.setattr(source_fetch, "_public_host",
                        lambda host: None if host == "example.com" else (_ for _ in ()).throw(
                            source_fetch.SourceUnavailable("The address is not on the public internet.")))

    def open_(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 302, "Found",
                                     {"Location": "http://127.0.0.1/admin"}, io.BytesIO())
    monkeypatch.setattr(source_fetch._opener, "open", open_)
    with pytest.raises(source_fetch.SourceUnavailable, match="public internet"):
        source_fetch.fetch("https://example.com/story")


def test_a_non_page_is_refused(monkeypatch):
    monkeypatch.setattr(source_fetch, "_public_host", lambda host: None)

    class Response(io.BytesIO):
        headers = type("H", (), {
            "get": staticmethod(lambda k, d=None: "application/pdf"),
            "get_content_charset": staticmethod(lambda: None),
        })()
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(source_fetch._opener, "open", lambda r, timeout: Response(b"%PDF"))
    with pytest.raises(source_fetch.SourceUnavailable, match="not a web page"):
        source_fetch.fetch("https://example.com/report.pdf")


# =========================================================================== #
#  Workflow
# =========================================================================== #

PASSWORD = "OriginalityTest1!"


def make_user(email, role):
    user = User(email=email, display_name=email.split("@")[0],
                password_hash=hash_password(PASSWORD), role=role)
    _db.session.add(user)
    _db.session.commit()
    return user


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
    other_editor = make_user("sport.editor@example.com", Role.EDITOR)
    _db.session.add(EditorCategory(editor_id=editor.id, category_id=politics.id))
    _db.session.add(EditorCategory(editor_id=other_editor.id, category_id=sport.id))
    _db.session.commit()
    return {
        "politics": politics,
        "original_writer": make_user("first@example.com", Role.VERIFIED_CONTRIBUTOR),
        "copier": make_user("copier@example.com", Role.VERIFIED_CONTRIBUTOR),
    }


def existing(world, body, status=ArticleStatus.PUBLISHED, title="Cycleway expansion approved",
             writer="original_writer"):
    article = Article(contributor_id=world[writer].id, category_id=world["politics"].id,
                      title=title, slug=title.lower().replace(" ", "-"), body=body, status=status)
    _db.session.add(article)
    _db.session.flush()
    index_article(article)
    _db.session.commit()
    return article


def submit(client, headers, world, body, sources=()):
    created = client.post("/api/articles", json={
        "title": "My own scoop", "categoryId": world["politics"].id, "body": body,
        "sources": [{"url": u, "label": "Source"} for u in sources],
    }, headers=headers).get_json()
    response = client.post(f"/api/articles/{created['id']}/submit", headers=headers)
    assert response.status_code == 200, response.get_json()
    return created["id"]


def test_a_copied_submission_reaches_the_editor_with_its_report(client, world):
    existing(world, ORIGINAL)
    article_id = submit(client, auth(client, "copier@example.com"), world, ORIGINAL)

    report = client.get(f"/api/articles/{article_id}/originality",
                        headers=auth(client, "editor@example.com")).get_json()["report"]
    assert report["percent"] == 100.0
    assert report["level"] == "substantial"
    match = report["matches"][0]
    assert match["title"] == "Cycleway expansion approved"
    assert match["sameWriter"] is False
    assert "coastal cycleway" in match["passages"][0]["otherText"]
    assert "wider web is not searched" in report["scope"]


def test_an_original_submission_comes_out_clean(client, world):
    existing(world, ORIGINAL)
    article_id = submit(client, auth(client, "copier@example.com"), world, UNRELATED)
    article = _db.session.get(Article, article_id)
    assert article.originality_percent == 0.0


def test_a_writer_cannot_read_another_writers_pending_draft_through_a_check(client, world):
    existing(world, ORIGINAL, status=ArticleStatus.PENDING, title="Secret pending story")
    headers = auth(client, "copier@example.com")
    article_id = submit(client, headers, world, ORIGINAL)

    report = client.get(f"/api/articles/{article_id}/originality", headers=headers).get_json()["report"]
    match = report["matches"][0]
    assert match["title"] is None
    assert all("otherText" not in p for p in match["passages"])
    assert "Secret pending story" not in str(report)


def test_reusing_your_own_published_article_is_labelled_as_such(client, world):
    existing(world, ORIGINAL, writer="copier")
    headers = auth(client, "copier@example.com")
    article_id = submit(client, headers, world, ORIGINAL)
    report = client.get(f"/api/articles/{article_id}/originality", headers=headers).get_json()["report"]
    assert report["matches"][0]["sameWriter"] is True


def test_an_editor_of_another_section_cannot_read_the_report(client, world):
    existing(world, ORIGINAL)
    article_id = submit(client, auth(client, "copier@example.com"), world, ORIGINAL)
    response = client.get(f"/api/articles/{article_id}/originality",
                          headers=auth(client, "sport.editor@example.com"))
    assert response.status_code == 404


def test_editing_the_text_clears_the_old_report(client, world):
    headers = auth(client, "copier@example.com")
    created = client.post("/api/articles", json={
        "title": "Draft", "categoryId": world["politics"].id, "body": ORIGINAL,
    }, headers=headers).get_json()
    client.post(f"/api/articles/{created['id']}/originality", headers=headers)
    assert _db.session.get(Article, created["id"]).originality_checked_at is not None

    client.patch(f"/api/articles/{created['id']}", json={"body": UNRELATED}, headers=headers)
    assert _db.session.get(Article, created["id"]).originality_checked_at is None


def test_copying_a_cited_source_without_quotation_marks_is_caught(client, world, app, monkeypatch):
    page = engine.parse(ORIGINAL).text
    monkeypatch.setattr("app.originality_service.fetch",
                        lambda url: source_fetch.Fetched(url, "text/plain", page))
    app.config["ORIGINALITY_FETCH_SOURCES"] = True

    headers = auth(client, "copier@example.com")
    article_id = submit(client, headers, world, ORIGINAL, sources=["https://council.example.gov/release"])
    report = client.get(f"/api/articles/{article_id}/originality", headers=headers).get_json()["report"]
    source_match = next(m for m in report["matches"] if m["kind"] == "source")
    assert source_match["url"] == "https://council.example.gov/release"
    assert source_match["percent"] == 100.0
    assert report["sources"][0]["status"] == "checked"


def test_quoting_a_cited_source_is_verified_not_flagged(client, world, app, monkeypatch):
    statement = engine.parse(ORIGINAL).text
    monkeypatch.setattr("app.originality_service.fetch",
                        lambda url: source_fetch.Fetched(url, "text/plain", statement))
    app.config["ORIGINALITY_FETCH_SOURCES"] = True

    body = (f"<p>In a statement the council said: “{statement.split('. ')[0]}.”</p>"
            + UNRELATED)
    headers = auth(client, "copier@example.com")
    article_id = submit(client, headers, world, body, sources=["https://council.example.gov/release"])
    report = client.get(f"/api/articles/{article_id}/originality", headers=headers).get_json()["report"]
    assert report["percent"] == 0.0
    assert report["quotes"][0]["verified"] is True


def test_an_unreachable_source_is_reported_not_fatal(client, world, app, monkeypatch):
    def refuse(url):
        raise source_fetch.SourceUnavailable("The page could not be reached.")
    monkeypatch.setattr("app.originality_service.fetch", refuse)
    app.config["ORIGINALITY_FETCH_SOURCES"] = True

    headers = auth(client, "copier@example.com")
    article_id = submit(client, headers, world, UNRELATED, sources=["https://gone-news-site.com.au/"])
    report = client.get(f"/api/articles/{article_id}/originality", headers=headers).get_json()["report"]
    assert report["sources"][0] == {
        "url": "https://gone-news-site.com.au/", "label": "Source",
        "status": "unavailable", "reason": "The page could not be reached.",
    }


def test_matching_text_raises_review_priority_and_blocks_auto_publish():
    base = dict(contributor_accuracy=95.0, source_count=3, has_duplicate_title=False,
                hours_waiting=0.0)
    assert triage.review_priority(**base, similarity_percent=10).priority == 0.0
    assert triage.review_priority(**base, similarity_percent=50).similarity == 30.0

    rules = dict(contributor_accuracy=95.0, published_count=20, suspended=False,
                 source_count=3, has_duplicate_title=False, is_premium=False)
    assert triage.autopublish_eligibility(**rules, similarity_percent=5).eligible
    flagged = triage.autopublish_eligibility(**rules, similarity_percent=25)
    assert "text matches another article or a cited source" in flagged.reasons
    unchecked = triage.autopublish_eligibility(**rules, similarity_percent=None)
    assert "originality has not been checked" in unchecked.reasons


def test_the_demo_seed_flags_the_planted_copy_and_nothing_else(app):
    """Every other demo article must come out original, or the demo cries wolf."""
    import seed

    seed.seed()
    for article in Article.query.all():
        from app.originality_service import check
        report = check(article)
        if article.title == seed.PLANTED_COPY["title"]:
            assert report["level"] != "original"
            assert report["matches"][0]["title"] == "Parliament passes revised data protection framework"
        else:
            assert report["level"] == "original", (article.title, report["percent"])
