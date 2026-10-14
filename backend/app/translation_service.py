"""Articles in English, Mandarin (Simplified Chinese) and Bahasa Melayu.

English is the language articles are written and reviewed in. A translation
is stored per article and language, with a fingerprint of the English it was
made from: if the writer edits the article afterwards, the translation is
stale and readers get the English, with a note, rather than a translation of
text that no longer exists.

Where translations come from (the provider) is configuration, like payments:

    stored  (default) serve translations already in the database: the demo
            articles were translated in advance, labelled AI translated
    claude  skeleton: translate new articles with Claude when they are
            published (ANTHROPIC_API_KEY). Not functional until completed.
"""
from __future__ import annotations

import hashlib
import json

from flask import current_app, has_request_context, request

from .models import Article, ArticleTranslation

LANGS = {"en": "English", "zh": "中文", "ms": "Bahasa Melayu"}
#: The voice to read each language in (useSpeech picks a soft female one).
VOICE_LANG = {"en": "en-AU", "zh": "zh-CN", "ms": "ms-MY"}
LABELS = {
    "zh": {"translated": "由人工智能从英文翻译", "unavailable": "此文章尚无中文版本，以下为英文原文。"},
    "ms": {"translated": "Diterjemah oleh AI daripada bahasa Inggeris",
           "unavailable": "Artikel ini belum tersedia dalam Bahasa Melayu. Ini versi asal dalam bahasa Inggeris."},
}


def request_lang() -> str:
    """The language this request asked for (?lang=zh), English if none or unknown."""
    if not has_request_context():
        return "en"
    lang = (request.args.get("lang") or "en").lower()
    return lang if lang in LANGS else "en"


def source_hash(title: str, summary: str | None, body: str) -> str:
    text = "\n".join([title or "", summary or "", body or ""])
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def fresh(article: Article, lang: str) -> ArticleTranslation | None:
    """The stored translation, if there is one and it matches the current English."""
    if lang == "en":
        return None
    for tr in article.translations:
        if tr.lang == lang:
            if tr.source_hash == source_hash(article.title, article.summary, article.body):
                return tr
            return None
    return None


def points(tr: ArticleTranslation) -> list[str]:
    try:
        return json.loads(tr.points or "[]")
    except ValueError:
        return []


def note(lang: str, tr: ArticleTranslation | None) -> dict:
    """What the page says about the language it is showing."""
    labels = LABELS.get(lang, {})
    if tr is None:
        return {"lang": lang, "available": False, "note": labels.get("unavailable")}
    return {"lang": lang, "available": True, "provider": tr.provider, "note": labels.get("translated")}


# --------------------------------------------------------------------------- #
#  Providers
# --------------------------------------------------------------------------- #

class ProviderNotConfigured(Exception):
    """The configured translation provider is not set up on this deployment."""


class StoredTranslations:
    """Serves only translations already stored. Translates nothing new."""

    name = "stored"

    def translate(self, article: Article, lang: str) -> dict | None:
        return None


class ClaudeTranslator:
    """Skeleton: translate an article with Claude when it is published.

    Completing it: POST https://api.anthropic.com/v1/messages (headers
    x-api-key: ANTHROPIC_API_KEY, anthropic-version: 2023-06-01) with model
    TRANSLATION_MODEL (default claude-sonnet-5), a system prompt to translate
    news faithfully into the target language (Simplified Chinese for zh,
    Bahasa Melayu for ms), keeping names, numbers and quotations exact and the
    paragraph and subheading structure unchanged, and the title, standfirst,
    body paragraphs and key points as JSON. Store the result as an
    ArticleTranslation with provider "claude" and the source_hash of the
    English, from the publish step, so readers never wait for it.
    """

    name = "claude"

    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model

    def translate(self, article: Article, lang: str) -> dict | None:
        raise ProviderNotConfigured("Automatic translation is not switched on for this site yet.")


def provider():
    cfg = current_app.config
    name = cfg.get("TRANSLATION_PROVIDER", "stored")
    if name == "stored":
        return StoredTranslations()
    if name == "claude":
        return ClaudeTranslator(cfg.get("ANTHROPIC_API_KEY"), cfg.get("TRANSLATION_MODEL", "claude-sonnet-5"))
    raise ProviderNotConfigured(f"Unknown translation provider '{name}'.")
