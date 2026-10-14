"""Articles download as PDF and PowerPoint, within the paywall."""
import io

import pytest
from pptx import Presentation

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, Category, User, utcnow
from app.security import hash_password
from demo_bodies import body_for

PASSWORD = "Downloads12345!"
LONG = "Grid operators report record renewable share in Q3"


@pytest.fixture()
def story(app):
    env = Category(name="Environment", slug="environment")
    w = User(email="w@example.com", display_name="Marcus", role=Role.VERIFIED_CONTRIBUTOR,
             password_hash=hash_password(PASSWORD))
    _db.session.add_all([env, w])
    _db.session.commit()
    a = Article(contributor_id=w.id, category_id=env.id, title=LONG, slug="grid", summary="Wind and solar.",
                body=body_for(LONG), status=ArticleStatus.PUBLISHED, published_at=utcnow(),
                credibility_score=91.0, credibility_band="High")
    _db.session.add(a)
    _db.session.commit()
    return a


def test_a_pdf_download(client, story):
    r = client.get("/api/articles/grid/download.pdf")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF") and 'filename="grid-operators' in r.headers["Content-Disposition"]


def test_a_slide_deck_download(client, story):
    r = client.get("/api/articles/grid/download.pptx")
    assert r.status_code == 200
    deck = Presentation(io.BytesIO(r.data))
    texts = [[sh.text_frame.text for sh in s.shapes if sh.has_text_frame] for s in deck.slides]
    assert LONG in texts[0]
    headings = [t[0] for t in texts[1:]]
    assert "In brief" in headings and "Rooftops lead the growth" in headings
    assert headings[-1] == "Sourcing and score"


def test_subscriber_only_articles_are_not_given_away(client, story):
    story.is_premium = True
    _db.session.commit()
    assert client.get("/api/articles/grid/download.pdf").status_code == 403
    token = client.post("/api/auth/login", json={"email": "w@example.com", "password": PASSWORD}).get_json()["token"]
    assert client.get("/api/articles/grid/download.pdf", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_other_formats_are_refused(client, story):
    assert client.get("/api/articles/grid/download.docx").status_code == 404
