"""Rich-text sanitisation.

PDD Figure 5.41 gives contributors a rich-text editor, and readers see the result
rendered as HTML. That is a stored-XSS hole unless the markup is cleaned. Clean on
*write*, never on read: a body that is already in the database unclean will be
served unclean by any code path that forgets to filter.
"""
from __future__ import annotations

import re

import bleach

#: Tags a news article legitimately needs. Deliberately narrow.
ALLOWED_TAGS = [
    "p", "br", "hr",
    "h2", "h3", "h4",
    "strong", "em", "u", "s",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "a", "img",
    "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "*": ["class"],
}

#: No `javascript:` and no `data:`; both are script-execution vectors in an href.
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def clean_article_body(raw_html: str) -> str:
    cleaned = bleach.clean(
        raw_html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    #Outbound links from user content get noopener/noreferrer.
    return bleach.linkifier.Linker(
        callbacks=[bleach.callbacks.nofollow, bleach.callbacks.target_blank],
        skip_tags=["pre", "code"],
    ).linkify(cleaned)


#: Tags whose *contents* are discarded, not just their angle brackets. Bleach's
#: strip=True keeps inner text, so "<script>alert(1)</script>Headline" would
#: otherwise survive as the literal title "alert(1)Headline": safe to render,
#: but garbage to read.
_CONTENT_BEARING = re.compile(
    r"<\s*(script|style|template)\b.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL
)


def clean_plain_text(raw: str) -> str:
    """For comments, bios, and titles: no markup permitted at all."""
    without_scripts = _CONTENT_BEARING.sub("", raw or "")
    return bleach.clean(without_scripts, tags=[], attributes={}, strip=True).strip()


def preview_text(html: str, limit: int = 300) -> str:
    """A bounded plain-text opening for a paywalled article (PDD Figure 5.6).

    Deliberately capped: this is the one place premium body text is allowed past
    the paywall, so the cap is the control. Never widen it to "most of" an article.
    """
    text = " ".join(clean_plain_text(html).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."
