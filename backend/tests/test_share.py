"""Shared links: they go to the website, and carry a preview card crawlers can read."""
import io

import pytest
from PIL import Image

from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleImage, Category, User, utcnow


def webp(width=1200, height=630):
    out = io.BytesIO()
    Image.new("RGB", (width, height), (19, 57, 85)).save(out, format="WEBP")
    return out.getvalue()


@pytest.fixture()
def story(app):
    app.config["SITE_URL"] = "https://news.example.org"
    category = Category(name="Health", slug="health")
    writer = User(email="w@example.com", display_name="W", password_hash="x",
                  role=Role.VERIFIED_CONTRIBUTOR)
    _db.session.add_all([category, writer])
    _db.session.commit()
    image = ArticleImage(key="abc123", owner_id=writer.id, width=1200, height=630,
                         large=webp(), thumb=webp(300, 158))
    _db.session.add(image)
    _db.session.commit()
    article = Article(contributor_id=writer.id, category_id=category.id,
                      title='Robots & "lifting" on wards', slug="robots-1",
                      summary="Nurses test lifting aids.", body="<p>b</p>",
                      status=ArticleStatus.PUBLISHED, published_at=utcnow(),
                      credibility_score=82.4, credibility_band="High", cover_image_id=image.id)
    _db.session.add(article)
    _db.session.commit()
    return article


def test_share_links_point_at_the_website_not_the_api(client, story):
    data = client.get(f"/api/articles/{story.id}/share").get_json()
    assert data["url"] == "https://news.example.org/articles/robots-1"
    assert data["previewUrl"].endswith("/api/share/robots-1")
    assert "api%2Fshare%2Frobots-1" in data["targets"]["facebook"]


def test_the_preview_page_carries_the_card_and_forwards_readers(client, story):
    r = client.get("/api/share/robots-1")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.mimetype == "text/html"
    assert '<meta property="og:title" content="Robots &amp; &#34;lifting&#34; on wards">' in html
    assert "Nurses test lifting aids. · Credibility score 82/100, High" in html
    assert '/api/images/abc123/share.jpg' in html and "summary_large_image" in html
    assert 'content="0; url=https://news.example.org/articles/robots-1"' in html


def test_an_unpublished_article_has_no_card(client, story):
    story.status = ArticleStatus.UNPUBLISHED
    _db.session.commit()
    r = client.get("/api/share/robots-1")
    assert r.status_code == 404 and "Robots" not in r.get_data(as_text=True)


def test_the_card_image_is_a_jpeg(client, story):
    r = client.get("/api/images/abc123/share.jpg")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert Image.open(io.BytesIO(r.data)).format == "JPEG"
