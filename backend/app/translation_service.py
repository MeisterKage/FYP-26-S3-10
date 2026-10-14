"""Articles in English, Mandarin (Simplified Chinese) and Bahasa Melayu.

English is the language articles are written and reviewed in. A translation
is stored per article and language, with a fingerprint of the English it was
made from: if the writer edits the article afterwards, the translation is
stale and readers get the English, with a note, rather than a translation of
text that no longer exists.

Where translations come from (the provider) is configuration, like payments:

    auto    (default) claude when ANTHROPIC_API_KEY is set, stored otherwise
    stored  serve translations already in the database: the demo articles
            were translated in advance, labelled AI translated
    claude  translate each article with Claude once it is published, and
            again when its English changes (ANTHROPIC_API_KEY)

With claude, translating happens in the background: publishing is never held
up by it, and a reader who arrives first is told the translation is on its way
and shown the English meanwhile.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from flask import current_app, has_request_context, request
from sqlalchemy import event
from sqlalchemy.orm import Session

from .enums import ArticleStatus
from .extensions import db
from .models import Article, ArticleTranslation

LANGS = {"en": "English", "zh": "中文", "ms": "Bahasa Melayu"}
#: The voice to read each language in (useSpeech picks a soft female one).
VOICE_LANG = {"en": "en-AU", "zh": "zh-CN", "ms": "ms-MY"}
LABELS = {
    "zh": {"translated": "由人工智能从英文翻译", "unavailable": "此文章尚无中文版本，以下为英文原文。",
           "preparing": "此文章正在翻译成中文，几分钟内即可阅读。以下暂为英文原文。"},
    "ms": {"translated": "Diterjemah oleh AI daripada bahasa Inggeris",
           "unavailable": "Artikel ini belum tersedia dalam Bahasa Melayu. Ini versi asal dalam bahasa Inggeris.",
           "preparing": "Artikel ini sedang diterjemah ke dalam Bahasa Melayu dan akan siap dalam beberapa minit. "
                        "Buat masa ini, ini versi asal dalam bahasa Inggeris."},
}
#: The language names a translator is asked for.
TARGETS = {"zh": "Simplified Chinese (Mandarin, as written in mainland China and Singapore)",
           "ms": "Bahasa Melayu (standard Malaysian Malay)"}


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


def note(lang: str, tr: ArticleTranslation | None, preparing: bool = False) -> dict:
    """What the page says about the language it is showing."""
    labels = LABELS.get(lang, {})
    if tr is None:
        return {"lang": lang, "available": False, "preparing": preparing,
                "note": labels.get("preparing" if preparing else "unavailable")}
    return {"lang": lang, "available": True, "provider": tr.provider, "note": labels.get("translated")}


# --------------------------------------------------------------------------- #
#  Providers
# --------------------------------------------------------------------------- #

class ProviderNotConfigured(Exception):
    """The configured translation provider is not set up on this deployment."""


class TranslationFailed(Exception):
    """A translation came back unusable, so nothing was stored."""


class StoredTranslations:
    """Serves only translations already stored. Translates nothing new."""

    name = "stored"
    automatic = False

    def translate(self, article: Article, lang: str) -> dict | None:
        return None


_SYSTEM = """You translate news articles from English for a news site's readers.

Translate into {target}. Write it as a careful newspaper translator would:
natural, plain and faithful, neither adding nor leaving out anything.

- Keep every name, number, date, figure and unit exactly as in the English.
  Write people's and places' names the way readers of the language usually
  see them, and keep the English if there is no settled local form.
- Quotations stay quotations, translated, with the language's own quotation
  marks.
- The body is HTML. Translate only the text. Keep every tag, in the same order,
  with its attributes unchanged, and add no tags of your own.
- Translate the key points too: each is a sentence from the article, so use
  the same wording as in your translation of the body.

Give the result with the save_translation tool."""

_TOOL = {
    "name": "save_translation",
    "description": "Save the translated article.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The headline, translated."},
            "summary": {"type": "string", "description": "The standfirst, translated. Empty if there is none."},
            "body_html": {"type": "string", "description": "The body, translated, with the HTML tags unchanged."},
            "points": {"type": "array", "items": {"type": "string"},
                       "description": "The key points, translated, in order: as many as were given."},
        },
        "required": ["title", "summary", "body_html", "points"],
    },
}

_TAG_NAME = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)")
_LINK = re.compile(r"""\b(?:href|src)\s*=\s*["']([^"']*)["']""", re.I)


def _skeleton(html: str) -> tuple[list[str], list[str]]:
    """The tags of an HTML body in order, and its links: what a translation keeps."""
    return ([f"{slash}{name.lower()}" for slash, name in _TAG_NAME.findall(html or "")],
            sorted(_LINK.findall(html or "")))


def english_points(article: Article) -> list[str]:
    """The article's In brief points, which are translated with it."""
    from .insights_service import in_brief

    brief = in_brief(article)
    return list(brief["points"]) if brief else []


class ClaudeTranslator:
    """Translates an article with Claude (Anthropic's Messages API).

    One request per article and language: the headline, standfirst, HTML body
    and key points go together, and come back through a tool so the answer is
    structured. A translation that loses or adds a tag or a link, or a key
    point, is refused rather than stored; the body is cleaned like anything a
    writer submits.
    """

    name = "claude"
    automatic = True
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str | None, model: str, timeout: float = 180):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def translate(self, article: Article, lang: str) -> dict:
        from .sanitize import clean_article_body

        if not self.api_key:
            raise ProviderNotConfigured("Automatic translation needs ANTHROPIC_API_KEY.")
        if lang not in TARGETS:
            raise TranslationFailed(f"No translation into '{lang}'.")
        english = english_points(article)
        article_json = json.dumps({
            "title": article.title, "summary": article.summary or "",
            "body_html": article.body, "points": english,
        }, ensure_ascii=False)
        answer = self._call({
            "model": self.model,
            "max_tokens": 16000,
            "system": _SYSTEM.format(target=TARGETS[lang]),
            "tools": [_TOOL],
            "tool_choice": {"type": "tool", "name": _TOOL["name"]},
            "messages": [{"role": "user", "content": f"The article, as JSON:\n\n{article_json}"}],
        })
        if answer.get("stop_reason") == "max_tokens":
            raise TranslationFailed("The translation was cut off before the end.")
        result = next((block.get("input") for block in answer.get("content", [])
                       if block.get("type") == "tool_use"), None)
        if not isinstance(result, dict):
            raise TranslationFailed("No translation came back.")

        title = str(result.get("title") or "").strip()
        body = clean_article_body(str(result.get("body_html") or ""))
        translated_points = [str(p).strip() for p in result.get("points") or [] if str(p).strip()]
        if not title or not body.strip():
            raise TranslationFailed("The translation had no headline or no text.")
        if _skeleton(body) != _skeleton(article.body):
            raise TranslationFailed("The translation changed the article's layout or links.")
        if len(translated_points) != len(english):
            raise TranslationFailed(
                f"{len(translated_points)} key points came back for {len(english)}.")
        return {"title": title[:400], "summary": str(result.get("summary") or "").strip() or None,
                "body": body, "points": translated_points}

    def _call(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self.URL, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise TranslationFailed(f"The translation service said {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise TranslationFailed(f"The translation service could not be reached: {exc}") from exc


def provider():
    cfg = current_app.config
    name = cfg.get("TRANSLATION_PROVIDER", "auto")
    if name == "auto":
        name = "claude" if cfg.get("ANTHROPIC_API_KEY") else "stored"
    if name == "stored":
        return StoredTranslations()
    if name == "claude":
        return ClaudeTranslator(cfg.get("ANTHROPIC_API_KEY"), cfg.get("TRANSLATION_MODEL", "claude-sonnet-5-5"))
    raise ProviderNotConfigured(f"Unknown translation provider '{name}'.")


def automatic() -> bool:
    """Whether this site translates articles itself, rather than only serving stored ones."""
    try:
        return provider().automatic
    except ProviderNotConfigured:
        return False


# --------------------------------------------------------------------------- #
#  Translating articles as they are published
# --------------------------------------------------------------------------- #

#: After a failure, how long before the same article and language are tried again.
RETRY_AFTER_SECONDS = 600

_lock = threading.Lock()
_queued: set[tuple[int, str]] = set()
_failed: dict[tuple[int, str], float] = {}
#: With TRANSLATE_IN_BACKGROUND off (the tests), jobs wait here for run_held().
_held: list[tuple[int, str]] = []
_pool: ThreadPoolExecutor | None = None
_PUBLISHED_KEY = "translate_after_commit"


def translate_now(article: Article, lang: str) -> ArticleTranslation | None:
    """Translate one article into one language and store it. The caller commits."""
    fingerprint = source_hash(article.title, article.summary, article.body)
    translator = provider()
    result = translator.translate(article, lang)
    if result is None:
        return None
    ArticleTranslation.query.filter_by(article_id=article.id, lang=lang).delete()
    tr = ArticleTranslation(
        article_id=article.id, lang=lang, title=result["title"], summary=result["summary"],
        body=result["body"], points=json.dumps(result["points"], ensure_ascii=False),
        provider=translator.name, source_hash=fingerprint,
    )
    db.session.add(tr)
    return tr


def queue_translation(article_id: int, lang: str) -> bool:
    """Ask for an article in a language. True if a translation is now on its way."""
    global _pool
    key = (article_id, lang)
    with _lock:
        if key in _queued:
            return True
        failed_at = _failed.get(key)
        if failed_at is not None and time.monotonic() - failed_at < RETRY_AFTER_SECONDS:
            return False
        _queued.add(key)
        app = current_app._get_current_object()
        if not app.config.get("TRANSLATE_IN_BACKGROUND", True):
            _held.append(key)
            return True
        if _pool is None:
            # Two at a time: enough to keep up, gentle on the API and the server.
            _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="translate")
    _pool.submit(_job, app, article_id, lang)
    return True


def pending(article: Article, lang: str) -> bool:
    """Whether a translation of a published article is on its way, asking for one if not."""
    if lang == "en" or article.status != ArticleStatus.PUBLISHED or not automatic():
        return False
    return queue_translation(article.id, lang)


def translate_when_published(article: Article) -> None:
    """Translate an article into every language once its publication is committed."""
    if automatic():
        db.session.info.setdefault(_PUBLISHED_KEY, set()).add(article.id)


def run_held() -> int:
    """Run the jobs held while TRANSLATE_IN_BACKGROUND is off. Returns how many ran."""
    app = current_app._get_current_object()
    ran = 0
    while _held:
        _job(app, *_held.pop(0))
        ran += 1
    return ran


def _job(app, article_id: int, lang: str) -> None:
    from . import response_cache

    with app.app_context():
        try:
            article = db.session.get(Article, article_id)
            if (article is not None and article.status == ArticleStatus.PUBLISHED
                    and fresh(article, lang) is None):
                translate_now(article, lang)
                db.session.commit()
                # Signed-out pages remembered in English must not outlive the translation.
                response_cache.clear()
            with _lock:
                _failed.pop((article_id, lang), None)
        except Exception:  # noqa: BLE001 - a failed translation must never take anything else down
            db.session.rollback()
            with _lock:
                _failed[(article_id, lang)] = time.monotonic()
            app.logger.exception("Translating article %s into %s failed", article_id, lang)
        finally:
            with _lock:
                _queued.discard((article_id, lang))


@event.listens_for(Session, "after_commit")
def _queue_published(session) -> None:
    for article_id in session.info.pop(_PUBLISHED_KEY, ()):
        for lang in LANGS:
            if lang != "en":
                queue_translation(article_id, lang)


@event.listens_for(Session, "after_rollback")
def _forget_published(session) -> None:
    session.info.pop(_PUBLISHED_KEY, None)


def reset_jobs() -> None:
    """Forget queued, held and failed jobs (tests)."""
    with _lock:
        _queued.clear()
        _failed.clear()
        _held.clear()
