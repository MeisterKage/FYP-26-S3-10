"""Article summaries, narration and writing signals, behind swappable providers.

Built the same way as payments.py: the application only talks to the three
interfaces below, and configuration picks the provider. Each has a built-in
provider that works today with no account, key or cost, and a skeleton for an
external service that names the calls it needs and refuses to run until it is
completed and configured.

    Feature            Built in (default)               External (skeleton)
    -----------------  -------------------------------  -------------------------------
    In brief summary   extractive (app/insights.py)     claude   (Claude Messages API)
    Narration          browser  (reader's own browser   cloud    (any text-to-speech API
                       speech, Web Speech API)                    returning an audio file)
    Writing signals    stylometric (app/insights.py)    external (a detection API)

Configuration (Render environment):
    SUMMARY_PROVIDER=extractive | claude
    NARRATION_PROVIDER=browser | cloud
    WRITING_SIGNALS_PROVIDER=stylometric | external
    IN_BRIEF_MIN_WORDS=350         articles shorter than this get no summary

Results are cached in process by (provider, article text), so a busy article is
summarised once, not on every read. An external provider that costs money per
call should also store its results; see the note on ClaudeSummariser.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field

from flask import current_app

from . import insights
from .models import Article


class ProviderNotConfigured(Exception):
    """The configured provider is not set up on this deployment."""


# --------------------------------------------------------------------------- #
#  A small cache shared by every provider
# --------------------------------------------------------------------------- #

_CACHE: OrderedDict[str, object] = OrderedDict()
_CACHE_SIZE = 512


def _cached(kind: str, provider: str, text: str, compute):
    key = f"{kind}:{provider}:{hashlib.blake2b(text.encode(), digest_size=16).hexdigest()}"
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    value = compute()
    _CACHE[key] = value
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return value


def clear_cache() -> None:
    _CACHE.clear()


# --------------------------------------------------------------------------- #
#  Summaries
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Summary:
    points: list[str]
    method: str          # shown to readers: how the summary was made
    provider: str


class Summariser:
    name = "base"

    def summarise(self, body_html: str) -> Summary:
        raise NotImplementedError


class ExtractiveSummariser(Summariser):
    """Picks the article's own key sentences. Cannot invent anything."""

    name = "extractive"

    def summarise(self, body_html: str) -> Summary:
        return Summary(insights.key_points(body_html),
                       "AI generated", self.name)


class ClaudeSummariser(Summariser):
    """Skeleton for an abstractive summary from Claude. Not functional yet.

    Completing it: POST https://api.anthropic.com/v1/messages with headers
    x-api-key (ANTHROPIC_API_KEY), anthropic-version: 2023-06-01, and a body of
    {"model": SUMMARY_MODEL, "max_tokens": 400, "system": <instructions: three
    or four bullet points, only facts stated in the article, no opinions, no
    new names or numbers>, "messages": [{"role": "user", "content": <article
    text>}]}. Parse the bullets from content[0].text into Summary.points, and
    set method to say the summary was written by AI and checked by nobody.

    Because each call costs money, store the result (for example a column on
    Article keyed by a hash of the body) instead of relying on the in-process
    cache, and generate it at publication rather than on first read.

    Never use it on republished articles: their licence forbids adaptations.

    Configuration: SUMMARY_PROVIDER=claude, ANTHROPIC_API_KEY=..., and
    optionally SUMMARY_MODEL (default claude-sonnet-5).
    """

    name = "claude"

    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model

    def summarise(self, body_html: str) -> Summary:
        raise ProviderNotConfigured("AI-written summaries are not switched on for this site yet.")


def summariser() -> Summariser:
    cfg = current_app.config
    name = cfg.get("SUMMARY_PROVIDER", "extractive")
    if name == "extractive":
        return ExtractiveSummariser()
    if name == "claude":
        return ClaudeSummariser(cfg.get("ANTHROPIC_API_KEY"), cfg.get("SUMMARY_MODEL", "claude-sonnet-5-5"))
    raise ProviderNotConfigured(f"Unknown summary provider '{name}'.")


# --------------------------------------------------------------------------- #
#  Narration
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Narration:
    mode: str                       # "browser": speak `text` on the device; "audio": play `url`
    text: str
    url: str | None = None
    provider: str = ""
    voice: dict = field(default_factory=dict)


class Narrator:
    name = "base"

    def narrate(self, title: str, points: list[str]) -> Narration:
        raise NotImplementedError

    def narrate_book(self) -> dict:
        """How a long, chaptered text (a digest's audio edition) is voiced."""
        raise NotImplementedError


def narration_script(title: str, points: list[str]) -> str:
    """What is read aloud: the headline, then the key points."""
    return " ".join([f"{title}.", "In brief."] + points)


class BrowserNarrator(Narrator):
    """The reader's own browser reads the summary aloud (Web Speech API).

    Free, and private on a local voice (the page prefers one, so the text stays
    on the device; some browsers only offer online voices). Works offline once the
    page has loaded. Voices depend on the reader's system; the page asks for
    an English voice from the site's region first.
    """

    name = "browser"

    def narrate(self, title: str, points: list[str]) -> Narration:
        return Narration("browser", narration_script(title, points), provider=self.name,
                         voice={"lang": "en-AU", "rate": 1.0})

    def narrate_book(self) -> dict:
        return {"mode": "browser", "voice": {"lang": "en-AU", "rate": 1.0}}


class CloudNarrator(Narrator):
    """Skeleton for recorded narration from a text-to-speech service.

    Completing it: send narration_script(...) to the service's synthesis
    endpoint (every major one takes text, a voice name and an audio format and
    returns MP3 or Ogg bytes), store the file (the images module shows how
    binary content is stored and served), and return Narration("audio", text,
    url=<that file's URL>). Generate it once at publication, not per listener.

    Configuration: NARRATION_PROVIDER=cloud, NARRATION_API_KEY=...,
    NARRATION_VOICE=<the service's voice name>.
    """

    name = "cloud"

    def __init__(self, api_key: str | None, voice: str | None):
        self.api_key = api_key
        self.voice = voice

    def narrate(self, title: str, points: list[str]) -> Narration:
        raise ProviderNotConfigured("Recorded narration is not switched on for this site yet.")

    def narrate_book(self) -> dict:
        # One recording per chapter, generated when the edition is compiled:
        # {"mode": "audio", "chapters": {chapter id: file URL}}.
        raise ProviderNotConfigured("Recorded narration is not switched on for this site yet.")


def narrator() -> Narrator:
    cfg = current_app.config
    name = cfg.get("NARRATION_PROVIDER", "browser")
    if name == "browser":
        return BrowserNarrator()
    if name == "cloud":
        return CloudNarrator(cfg.get("NARRATION_API_KEY"), cfg.get("NARRATION_VOICE"))
    raise ProviderNotConfigured(f"Unknown narration provider '{name}'.")


# --------------------------------------------------------------------------- #
#  Writing signals
# --------------------------------------------------------------------------- #

class SignalsProvider:
    name = "base"

    def assess(self, body_html: str) -> dict:
        raise NotImplementedError


class StylometricSignals(SignalsProvider):
    name = "stylometric"

    def assess(self, body_html: str) -> dict:
        return insights.writing_signals(body_html)


class ExternalSignals(SignalsProvider):
    """Skeleton for a commercial AI-writing detection API. Not functional yet.

    Completing it: POST the article text to the service and map its answer to
    the same shape writing_signals returns: a level (few / some / many), and
    a list of signals, each with a label, a displayable value and a short
    explanation. Keep showing the result to editors only, as a prompt to look
    closer, never as proof: every detector misfires on some human writing.

    Configuration: WRITING_SIGNALS_PROVIDER=external,
    WRITING_SIGNALS_API_URL=..., WRITING_SIGNALS_API_KEY=...
    """

    name = "external"

    def __init__(self, url: str | None, api_key: str | None):
        self.url = url
        self.api_key = api_key

    def assess(self, body_html: str) -> dict:
        raise ProviderNotConfigured("An external AI-writing check is not switched on for this site yet.")


def signals_provider() -> SignalsProvider:
    cfg = current_app.config
    name = cfg.get("WRITING_SIGNALS_PROVIDER", "stylometric")
    if name == "stylometric":
        return StylometricSignals()
    if name == "external":
        return ExternalSignals(cfg.get("WRITING_SIGNALS_API_URL"), cfg.get("WRITING_SIGNALS_API_KEY"))
    raise ProviderNotConfigured(f"Unknown writing signals provider '{name}'.")


# --------------------------------------------------------------------------- #
#  What the application calls
# --------------------------------------------------------------------------- #

def in_brief(article: Article) -> dict | None:
    """The summary block for the article page, or None if it gets none.

    Every article gets one, short ones included, except republished articles:
    their licence (CC BY-ND) forbids adaptations, and a summary is one.
    """
    if article.republication:
        return None
    count = insights.word_count(article.body)
    if count < current_app.config.get("IN_BRIEF_MIN_WORDS", 0):
        return None
    try:
        s = summariser()
        summary = _cached("summary", s.name, article.body, lambda: s.summarise(article.body))
        n = narrator()
        narration = n.narrate(article.title, summary.points)
    except ProviderNotConfigured as exc:
        current_app.logger.warning("In brief unavailable: %s", exc)
        return None
    if not summary.points:
        return None
    return {
        "points": summary.points,
        "method": summary.method,
        "words": count,
        "readingMinutes": insights.reading_minutes(count),
        "narration": {
            "mode": narration.mode,
            "text": narration.text,
            "url": narration.url,
            "voice": narration.voice,
        },
    }


DISCLAIMER = (
    "These are patterns common in machine-generated text, not proof. No checker can tell "
    "reliably who wrote a piece, and all of them misjudge some human writing, especially "
    "plain or formulaic styles and writers working in a second language. Use them as a "
    "reason to look closer, never as grounds for rejection on their own."
)


def writing_signals(article: Article) -> dict:
    p = signals_provider()
    result = _cached("signals", p.name, article.body, lambda: p.assess(article.body))
    return {**json.loads(json.dumps(result)), "provider": p.name, "disclaimer": DISCLAIMER}
