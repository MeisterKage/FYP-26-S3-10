"""Republish real articles that are licensed for it, with full credit.

    py import_republished.py      # needs internet access

Two sources, both of which allow republication:

  * The Conversation (https://theconversation.com/au/republishing-and-media),
    under CC BY-ND 4.0. Its conditions, all met here: credit the authors and
    their institutions (the article page shows them under the headline); link
    to the original; do not edit the text (it is stored as published, less
    images); do not reuse images (every image and figure is removed, because
    The Conversation's photos are not covered by the licence); include its
    page-view counter (the article page loads it).
  * Wikinews (https://en.wikinews.org/), under CC BY 2.5: credit Wikinews and
    link to the original. Wikinews closed in 2026; its archive stays licensed.

Each publisher gets its own account, so no demo writer's name is ever put on
someone else's work. Articles keep their original publication dates. Links
the article itself cites become its sources and are graded like any other.

Safe to run again: an article whose original URL is already here is skipped.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from app import create_app
from app.enums import ArticleStatus, Role
from app.extensions import db
from app.models import Article, ArticleSource, Category, EditorCategory, User
from app.modules.articles import slugify
from app.originality_service import index_article
from app.sanitize import clean_article_body, clean_plain_text
from app.scoring_service import rescore_contributor_articles
from app.security import hash_password
from app.source_service import rate_sources

AGENT = "SterlingWire-Republish/1.0 (+https://fyp-26-s3-10-web.onrender.com)"
CONVERSATION_FEED = "https://theconversation.com/au/articles.atom"
ATOM = {"a": "http://www.w3.org/2005/Atom"}

#: Chosen from the feed by a phrase in the headline. (phrase, section, country)
CONVERSATION_PICKS = [
    ("Manchester City cheating scandal", "Sport", "GB"),
    ("Card surcharges are banned", "Business", "AU"),
    ("Unemployment rises to 4.6%", "Business", "AU"),
    ("Australian AI", "Technology", "AU"),
    ("ozone hole was the biggest", "Environment", "NZ"),
    ("Heroin used more often", "Health", "AU"),
    ("supply chains are highly exposed", "Technology", "NZ"),
    ("Sharks often swim across national borders", "Science", "AU"),
    ("space race should not endanger", "Environment", "AU"),
    ("ratings drop to new record low", "Politics", "US"),
]
#: (Wikinews page title, section, country)
WIKINEWS_PICKS = [
    ("NSW government proposes rezoning to create residences midway between Sydney and Parramatta",
     "Politics", "AU"),
    ("Australian Minister for Energy lowers fuel standards for 60 days amid rising oil prices, panic buying",
     "Environment", "AU"),
    ("Caloundra win round 3 game in Australian soccer's Football Queensland Premier League 2 competition",
     "Sport", "AU"),
]
MIN_WORDS = 600  #the point of importing is articles worth reading
MAX_SOURCES = 8

PUBLISHERS = {
    "The Conversation": {
        "email": "republished.conversation@newsrelease.test",
        "bio": "Articles by academics and researchers, republished from The Conversation "
               "under a Creative Commons licence (CC BY-ND 4.0).",
        "licence": "CC BY-ND 4.0",
        "licenceUrl": "https://creativecommons.org/licenses/by-nd/4.0/",
    },
    "Wikinews": {
        "email": "republished.wikinews@newsrelease.test",
        "bio": "Articles from the Wikinews archive, republished under a Creative Commons "
               "licence (CC BY 2.5).",
        "licence": "CC BY 2.5",
        "licenceUrl": "https://creativecommons.org/licenses/by/2.5/",
    },
}


def get(url: str) -> bytes:
    time.sleep(1)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}),
                                timeout=60) as r:
        return r.read()


def strip_images(body: str) -> str:
    body = re.sub(r"<figure\b.*?</figure>", "", body, flags=re.S | re.I)
    body = re.sub(r"<img\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"<iframe\b.*?</iframe>", "", body, flags=re.S | re.I)
    return body


def words(body: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", body).split())


def summary_from(body: str) -> str:
    first = re.search(r"<p>(.*?)</p>", body, flags=re.S)
    text = clean_plain_text(htmllib.unescape(re.sub(r"<[^>]+>", "", first.group(1) if first else "")))
    if len(text) <= 280:
        return text
    return text[:277].rsplit(" ", 1)[0] + "…"


def cited_links(body: str, own_domain: str) -> list[tuple[str, str]]:
    """Links the article cites, one per domain, as its sources."""
    out, seen = [], set()
    for href, label in re.findall(r'<a [^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', body, flags=re.S):
        host = urllib.parse.urlparse(href).hostname or ""
        host = host[4:] if host.startswith("www.") else host
        if not host or own_domain in host or host in seen:
            continue
        seen.add(host)
        text = clean_plain_text(htmllib.unescape(re.sub(r"<[^>]+>", "", label)))[:250]
        out.append((htmllib.unescape(href)[:1000], text or host))
        if len(out) >= MAX_SOURCES - 1:
            break
    return out


def publisher_account(name: str) -> User:
    info = PUBLISHERS[name]
    user = User.query.filter_by(email=info["email"]).first()
    if user is None:
        user = User(email=info["email"], display_name=name, bio=info["bio"],
                    role=Role.VERIFIED_CONTRIBUTOR,
                    #Nobody signs in as a publisher: an unguessable password.
                    password_hash=hash_password(secrets.token_urlsafe(32)))
        db.session.add(user)
        db.session.flush()
    return user


def already_here(url: str) -> bool:
    return Article.query.filter(Article.republication.ilike(f'%"{url}"%')).first() is not None


def conversation_items() -> list[dict]:
    root = ET.fromstring(get(CONVERSATION_FEED))
    entries = root.findall("a:entry", ATOM)
    items = []
    for phrase, section, country in CONVERSATION_PICKS:
        entry = next((e for e in entries if phrase.lower() in e.find("a:title", ATOM).text.lower()), None)
        if entry is None:
            print(f"  not in the feed now: {phrase}")
            continue
        url = entry.find("a:link", ATOM).get("href")
        article_id = re.search(r"-(\d+)$", url).group(1)
        body = strip_images(htmllib.unescape(entry.find("a:content", ATOM).text or ""))
        items.append({
            "publisher": "The Conversation",
            "title": entry.find("a:title", ATOM).text.strip(),
            "url": url,
            "authors": [a.find("a:name", ATOM).text.strip() for a in entry.findall("a:author", ATOM)],
            "published": datetime.fromisoformat(entry.find("a:published", ATOM).text.replace("Z", "+00:00")),
            "body": body,
            "section": section, "country": country,
            "counterUrl": f"https://counter.theconversation.com/content/{article_id}/count.gif"
                          "?distributor=republish-lightbox-basic",
            "own": "theconversation.com",
        })
    return items


def wikinews_items() -> list[dict]:
    items = []
    for title, section, country in WIKINEWS_PICKS:
        q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text",
                                    "format": "json", "formatversion": 2, "disableeditsection": 1})
        data = json.loads(get(f"https://en.wikinews.org/w/api.php?{q}"))
        if "parse" not in data:
            print(f"  not found on Wikinews: {title}")
            continue
        raw = data["parse"]["text"]
        #Keep the report: paragraphs and subheadings before "Sources".
        raw = re.split(r'<h2[^>]*>\s*(?:<span[^>]*>)?\s*(?:Sources|Related news)', raw)[0]
        blocks = re.findall(r"<(?:p|h2|h3|ul|blockquote)\b[^>]*>.*?</(?:p|h2|h3|ul|blockquote)>", raw, flags=re.S)
        body = "".join(b for b in blocks if not re.search(r'class="[^"]*(?:published|dateline)', b))
        #The first paragraph is the dateline ("Sunday, March 15, 2026"); drop it.
        body = re.sub(r"^<p>\s*<strong[^>]*>[^<]*</strong>\s*</p>", "", body)
        rq = urllib.parse.urlencode({"action": "query", "prop": "revisions", "titles": title,
                                     "rvlimit": 1, "rvdir": "newer", "rvprop": "timestamp",
                                     "format": "json", "formatversion": 2})
        first = json.loads(get(f"https://en.wikinews.org/w/api.php?{rq}"))
        stamp = first["query"]["pages"][0]["revisions"][0]["timestamp"]
        items.append({
            "publisher": "Wikinews",
            "title": title,
            "url": "https://en.wikinews.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "authors": ["Wikinews contributors"],
            "published": datetime.fromisoformat(stamp.replace("Z", "+00:00")),
            "body": strip_images(body),
            "section": section, "country": country,
            "counterUrl": None,
            "own": "wikinews.org",
        })
    return items


def main() -> None:
    sections = {c.name: c for c in Category.query.filter_by(deleted_at=None)}
    admin = User.query.filter_by(email="admin@newsrelease.test").one()
    editor_for: dict[int, int] = {}
    for row in EditorCategory.query.order_by(EditorCategory.id):
        editor_for.setdefault(row.category_id, row.editor_id)

    items = conversation_items() + wikinews_items()
    if "--dry-run" in sys.argv:
        for item in items:
            body = clean_article_body(item["body"])
            print(f"  {words(body):5} words  {item['publisher']:16} {item['section']:11} "
                  f"{item['country']}  {item['title'][:60]}")
            print(f"        {summary_from(body)[:110]}")
        return

    added, skipped = [], []
    for item in items:
        if already_here(item["url"]):
            skipped.append(item["title"])
            continue
        body = clean_article_body(item["body"])
        if words(body) < MIN_WORDS:
            print(f"  too short ({words(body)} words), skipped: {item['title']}")
            continue
        writer = publisher_account(item["publisher"])
        category = sections[item["section"]]
        info = PUBLISHERS[item["publisher"]]
        article = Article(
            contributor_id=writer.id,
            category_id=category.id,
            country_code=item["country"],
            title=clean_plain_text(item["title"])[:255],
            slug=slugify(item["title"]),
            summary=summary_from(body),
            body=body,
            status=ArticleStatus.PUBLISHED,
            published_at=item["published"],
            submitted_at=item["published"],
            reviewed_by_id=editor_for.get(category.id, admin.id),
            republication=json.dumps({
                "publisher": item["publisher"],
                "authors": item["authors"],
                "url": item["url"],
                "publishedAt": item["published"].isoformat(),
                "licence": info["licence"],
                "licenceUrl": info["licenceUrl"],
                "counterUrl": item["counterUrl"],
            }),
        )
        db.session.add(article)
        db.session.flush()
        article.slug = slugify(item["title"], article.id)
        db.session.add(ArticleSource(article_id=article.id, url=item["url"],
                                     label=f"Original article, {item['publisher']}"))
        for url, label in cited_links(body, item["own"]):
            db.session.add(ArticleSource(article_id=article.id, url=url, label=label))
        db.session.flush()
        db.session.expire(article, ["sources"])
        index_article(article)
        rate_sources(article)
        added.append(article)
        print(f"  added ({words(body)} words): {article.title[:70]}")

    db.session.flush()
    for writer in {a.contributor for a in added}:
        rescore_contributor_articles(writer)
    db.session.commit()
    print(f"Republished {len(added)} article(s); {len(skipped)} already here.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with create_app().app_context():
        main()
