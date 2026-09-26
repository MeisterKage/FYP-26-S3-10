"""The accuracy rate cannot be gamed, and a correction costs what it says.

Two holes these close:

  * Unpublishing a corrected article used to drop it from the writer's record,
    so their accuracy rate went back up. A correction could be laundered away.
  * A correction was charged to the corrected article twice: once as the
    correction penalty, and again through the writer's lower accuracy, which
    feeds that same article. It cost about 18 points, not the stated 15.
"""
import pytest

from app.enums import ArticleStatus, CorrectionType, Role
from app.extensions import db as _db
from app.models import Article, Category, Correction, User
from app.scoring_service import explain_article, rescore_contributor_articles


@pytest.fixture()
def record(app):
    category = Category(name="Politics", slug="politics")
    writer = User(email="w@example.com", display_name="W", password_hash="x",
                  role=Role.VERIFIED_CONTRIBUTOR)
    editor = User(email="e@example.com", display_name="E", password_hash="x", role=Role.EDITOR)
    _db.session.add_all([category, writer, editor])
    _db.session.commit()
    articles = []
    for i in range(10):
        a = Article(contributor_id=writer.id, category_id=category.id, title=f"A{i}",
                    slug=f"a{i}", body="<p>b</p>", status=ArticleStatus.PUBLISHED)
        _db.session.add(a)
        articles.append(a)
    _db.session.commit()
    rescore_contributor_articles(writer)
    _db.session.commit()
    return {"writer": writer, "editor": editor, "articles": articles}


def correct(record, article):
    _db.session.add(Correction(article_id=article.id, issued_by_id=record["editor"].id,
                               correction_type=CorrectionType.CORRECTION, reason="Wrong."))
    _db.session.commit()
    _db.session.refresh(article)
    rescore_contributor_articles(record["writer"])
    _db.session.commit()


def test_unpublishing_a_corrected_article_does_not_restore_accuracy(record):
    corrected = record["articles"][0]
    correct(record, corrected)
    after_correction = record["writer"].accuracy_rate

    corrected.status = ArticleStatus.UNPUBLISHED
    _db.session.commit()
    rescore_contributor_articles(record["writer"])
    _db.session.commit()

    assert record["writer"].accuracy_rate == after_correction


def test_a_correction_costs_the_corrected_article_exactly_the_penalty(record):
    corrected = record["articles"][0]
    before = explain_article(corrected)
    correct(record, corrected)
    after = explain_article(corrected)

    assert after.accuracy_component == before.accuracy_component
    assert before.score - after.score == pytest.approx(15.0)


def test_the_writers_other_articles_still_reflect_the_lower_accuracy(record):
    other = record["articles"][1]
    before = explain_article(other)
    correct(record, record["articles"][0])
    after = explain_article(other)

    assert after.accuracy_component < before.accuracy_component
    assert after.correction_penalty == 0


def test_a_retraction_costs_the_retracted_article_exactly_its_penalty(record):
    retracted = record["articles"][0]
    before = explain_article(retracted)
    retracted.status = ArticleStatus.RETRACTED
    _db.session.commit()
    rescore_contributor_articles(record["writer"])
    _db.session.commit()
    after = explain_article(retracted)

    assert after.accuracy_component == before.accuracy_component
    assert before.score - after.score == pytest.approx(40.0)
