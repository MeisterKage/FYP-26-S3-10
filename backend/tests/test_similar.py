"""Similar articles: closest in subject, never the article itself, nothing unrelated."""
import pytest

from app import similar
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, User, utcnow
from app.similar_service import clear


def doc(i, title, body, cat=1, country=None):
    return similar.Doc(i, cat, country, similar.terms(title, "", f"<p>{body}</p>"))


def test_articles_on_the_same_subject_rank_first():
    docs = [
        doc(1, "Wind farms overtake coal", "Wind turbines and solar farms now supply the grid."),
        doc(2, "Solar and wind supply record share of grid", "Renewable wind and solar output hit a record on the grid."),
        doc(3, "Hospital waiting lists grow", "Patients wait longer for surgery at public hospitals."),
        doc(4, "Rugby season shortened", "The league cut two rounds from the rugby season."),
    ]
    vecs = similar.vectors(docs)
    ranked = similar.most_similar(docs[0], docs, vecs)
    assert ranked[0][0] == 2
    assert all(i != 1 for i, _ in ranked)          # never itself
    assert 4 not in [i for i, _ in ranked]          # nothing in common, not listed


@pytest.fixture()
def world(app):
    clear()
    energy, health = Category(name="Environment", slug="environment"), Category(name="Health", slug="health")
    w = User(email="w@example.com", display_name="W", password_hash="x", role=Role.VERIFIED_CONTRIBUTOR)
    _db.session.add_all([energy, health, w])
    _db.session.commit()
    for slug, cat, title, body in [
        ("wind", energy, "Wind power overtakes coal on the grid", "Wind turbines now supply more power to the grid than coal."),
        ("solar", energy, "Wind and solar power set a grid record", "Solar panels and wind turbines supplied record power to the grid."),
        ("draft", energy, "Wind and solar draft", "Wind turbines solar grid."),
        ("clinic", health, "Clinics share records", "Doctors and nurses share patient records."),
    ]:
        _db.session.add(Article(contributor_id=w.id, category_id=cat.id, title=title, slug=slug,
                                body=f"<p>{body}</p>", published_at=utcnow(),
                                status=ArticleStatus.DRAFT if slug == "draft" else ArticleStatus.PUBLISHED))
    _db.session.commit()


def test_the_article_page_lists_published_similar_articles(client, world):
    titles = [a["title"] for a in client.get("/api/articles/wind").get_json()["article"]["similar"]]
    assert titles[0] == "Wind and solar power set a grid record"
    assert "Wind and solar draft" not in titles             # drafts are never suggested
