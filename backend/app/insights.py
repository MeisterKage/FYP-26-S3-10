"""Reading aids and writing signals, computed from an article's own text.

Pure functions, no I/O, like originality.py. The services that choose between
these built-in methods and an external provider live in insights_service.py.

Two things are here:

  * key_points: an extractive summary. It picks the sentences that carry the
    article's most frequent ideas, in the order they appear. Every word is the
    writer's own, so a summary can never state something the article does not.
  * writing_signals: stylistic signals that are common in machine-generated
    text. They are signals, not a verdict: no detector, commercial or not, can
    tell reliably whether a person or a model wrote a piece, and all of them
    misfire on some human writing (plain styles, non-native writers, formulaic
    genres). So the result is shown to editors only, as a list of observations
    they can check for themselves, and it never changes a score or blocks
    anything.
"""
from __future__ import annotations

import html as htmllib
import math
import re
from dataclasses import dataclass

from .originality import STOPWORDS, _stem

WORDS_PER_MINUTE = 230

_BLOCK = re.compile(r"<(p|h[1-6]|li|blockquote)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
# A sentence ends at . ! or ? (optionally followed by a closing quote) before a
# space and a capital or an opening quote. Good enough for edited news copy.
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"”’]?\s+(?=[\"“‘A-Z0-9])")
_ABBREV = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|St|No|vs|etc|e\.g|i\.e|U\.S|U\.K)\.$")


@dataclass(frozen=True)
class Paragraph:
    text: str
    heading: bool


def paragraphs(body_html: str) -> list[Paragraph]:
    """The article's blocks as plain text, with subheadings marked."""
    out = []
    for tag, inner in _BLOCK.findall(body_html or ""):
        text = htmllib.unescape(_TAG.sub("", inner)).strip()
        if text:
            out.append(Paragraph(text, tag.lower().startswith("h")))
    if not out and body_html:
        text = htmllib.unescape(_TAG.sub(" ", body_html)).strip()
        if text:
            out.append(Paragraph(text, False))
    return out


def sentences(text: str) -> list[str]:
    parts, out = _SENTENCE_END.split(text), []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Rejoin a split after an abbreviation ("Dr. Smith").
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def word_count(body_html: str) -> int:
    return sum(len(words(p.text)) for p in paragraphs(body_html))


def reading_minutes(count: int) -> int:
    return max(1, round(count / WORDS_PER_MINUTE))


def _content(text: str) -> list[str]:
    return [_stem(w.lower()) for w in words(text) if w.lower() not in STOPWORDS and len(w) > 2]


# --------------------------------------------------------------------------- #
#  Key points
# --------------------------------------------------------------------------- #

def key_points(body_html: str, limit: int | None = None) -> list[str]:
    """The sentences that best cover the article, in reading order.

    Scores each sentence by how many of the article's frequent content words it
    contains, favours the opening (news puts the substance first), and skips
    direct quotes, very short or very long sentences, and near-repeats.
    """
    body = [p for p in paragraphs(body_html) if not p.heading]
    candidates = []  # (position, paragraph index, sentence)
    for pi, para in enumerate(body):
        for sentence in sentences(para.text):
            candidates.append((len(candidates), pi, sentence))
    if not candidates:
        return []

    total = sum(len(words(s)) for _, _, s in candidates)
    if limit is None:
        limit = 3 if total < 600 else 4

    freq: dict[str, int] = {}
    for _, _, s in candidates:
        for w in set(_content(s)):
            freq[w] = freq.get(w, 0) + 1
    top = max(freq.values(), default=1)

    scored = []
    for pos, pi, s in candidates:
        n = len(words(s))
        if n < 8 or n > 45:
            continue
        if re.search(r"[\"“”]", s):
            continue  # a quote belongs to the person who said it, not a summary
        terms = set(_content(s))
        if not terms:
            continue
        score = sum(freq[w] / top for w in terms) / math.sqrt(len(terms))
        if pi == 0:
            score *= 1.6 if pos == 0 else 1.25
        scored.append((score, pos, s, terms))

    chosen: list[tuple[int, str, set[str]]] = []
    for score, pos, s, terms in sorted(scored, key=lambda x: -x[0]):
        if any(len(terms & t) / len(terms | t) > 0.45 for _, _, t in chosen):
            continue
        chosen.append((pos, s, terms))
        if len(chosen) == limit:
            break
    return [s for _, s, _ in sorted(chosen)]


# --------------------------------------------------------------------------- #
#  Writing signals
# --------------------------------------------------------------------------- #

#: Phrases that turn up far more often in model-written prose than in edited
#: news copy. Any one of them is ordinary English; a cluster is the signal.
STOCK_PHRASES = (
    "delve", "delves", "delving", "tapestry", "testament to", "in today's",
    "fast-paced world", "ever-evolving", "ever-changing landscape", "it is important to note",
    "it's important to note", "it is worth noting", "it's worth noting", "plays a crucial role",
    "plays a pivotal role", "pivotal", "multifaceted", "navigate the complexities",
    "navigating the complexities", "in conclusion", "in summary", "overall,", "furthermore",
    "moreover", "additionally,", "unlock the potential", "harness the power", "seamless",
    "seamlessly", "robust", "foster", "fostering", "underscore", "underscores", "a myriad of",
    "myriad", "realm", "embark", "landscape of", "stands as", "serves as a reminder",
    "shed light on", "sheds light on", "paving the way", "game-changer", "cutting-edge",
    "at the end of the day", "not only", "a rich", "vibrant", "bustling", "nestled",
    "intricate", "holistic", "leverage", "leveraging", "crucial", "vital role",
)

MIN_WORDS_TO_JUDGE = 150


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    value: float
    display: str
    typical: str
    flagged: bool
    explain: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _cv(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(var) / mean


def writing_signals(body_html: str) -> dict:
    """Stylistic observations an editor can check. Never a verdict."""
    paras = [p for p in paragraphs(body_html) if not p.heading]
    text = " ".join(p.text for p in paras)
    tokens = words(text)
    n = len(tokens)
    if n < MIN_WORDS_TO_JUDGE:
        return {"level": "too_short", "words": n, "flagged": 0, "signals": []}

    sents = [s for p in paras for s in sentences(p.text)]
    lengths = [len(words(s)) for s in sents]
    lower = text.lower()

    # 1. Sentence rhythm. People vary sentence length a lot; generated prose
    #    tends to settle into a steady medium length.
    rhythm = _cv(lengths)
    signals = [Signal(
        "rhythm", "Sentence rhythm", round(rhythm, 2),
        f"{rhythm:.2f} variation", "0.30 or more (edited news is usually 0.40 or more)",
        rhythm < 0.30,
        "How much sentence length varies. Very even sentence lengths are common in "
        "generated text; human writers mix short and long sentences.",
    )]

    # 2. Stock phrases per thousand words.
    hits = []
    for phrase in STOCK_PHRASES:
        found = len(re.findall(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", lower))
        if found:
            hits.append((phrase, found))
    per_k = sum(c for _, c in hits) * 1000 / n
    signals.append(Signal(
        "stock_phrases", "Stock phrases", round(per_k, 1),
        (f"{per_k:.1f} per 1,000 words ("
         + ", ".join(f"“{p}”" for p, _ in sorted(hits, key=lambda h: -h[1])[:4]) + ")")
        if hits else "none found",
        "under 3 per 1,000 words",
        per_k >= 3,
        "Words and phrases generated text leans on, such as “delve”, “moreover” or "
        "“it is important to note”. Each is ordinary English; a cluster is the signal.",
    ))

    # 3. Paragraph uniformity.
    plens = [len(words(p.text)) for p in paras]
    para_cv = _cv(plens)
    signals.append(Signal(
        "paragraphs", "Paragraph shape", round(para_cv, 2),
        f"{para_cv:.2f} variation", "0.25 or more",
        len(plens) >= 4 and para_cv < 0.25,
        "Whether paragraphs are all about the same size. Generated text often "
        "produces blocks of near-identical length.",
    ))

    # 4. Repeated sentence openings. "The" and "A" are left out: news copy
    #    opens with them constantly, whoever writes it.
    openers: dict[str, int] = {}
    for s in sents:
        first = words(s)[:1]
        if first and first[0].lower() not in {"the", "a", "an"}:
            key = first[0].lower()
            openers[key] = openers.get(key, 0) + 1
    common, count = max(openers.items(), key=lambda kv: kv[1]) if openers else ("", 0)
    share = count / len(sents) if sents else 0.0
    signals.append(Signal(
        "openings", "Sentence openings", round(share, 2),
        f"{share:.0%} start with “{common}”" if common else "n/a",
        "under 25% sharing one opening word, not counting “the” and “a”",
        len(sents) >= 8 and share >= 0.25,
        "Whether many sentences begin the same way, a pattern typical of templated "
        "or generated prose.",
    ))

    # 5. Concrete detail: numbers, names and quotations per hundred words.
    #    Reporting is full of them; generated filler tends to stay general.
    numbers = len(re.findall(r"\b\d[\d,.%]*\b", text))
    names = sum(1 for s in sents for w in words(s)[1:] if w[:1].isupper() and w.lower() not in STOPWORDS)
    quotes = len(re.findall(r"[\"“][^\"“”]{12,}[\"”]", text))
    detail = (numbers + names + 3 * quotes) * 100 / n
    signals.append(Signal(
        "detail", "Concrete detail", round(detail, 1),
        f"{detail:.1f} per 100 words", "4 or more per 100 words in most reporting",
        detail < 4,
        "Numbers, names and direct quotations. Reporting is dense with checkable "
        "specifics; vague, general prose is a reason to look closer.",
    ))

    flagged = sum(s.flagged for s in signals)
    share, passages = ai_share(body_html)
    if flagged >= 3 or share >= 50:
        level = "many"
    elif flagged == 2 or share >= 20:
        level = "some"
    else:
        level = "few"
    return {
        "level": level,
        "words": n,
        "flagged": flagged,
        "aiShare": share,
        "passages": passages,
        "signals": [s.as_dict() for s in signals],
    }


# --------------------------------------------------------------------------- #
#  Share of AI-like text
# --------------------------------------------------------------------------- #

PASSAGE_WORDS = 110


def _passages(body_html: str) -> list[str]:
    """The article in passages of about PASSAGE_WORDS words, at paragraph breaks."""
    paras = [p.text for p in paragraphs(body_html) if not p.heading]
    out, current = [], []
    for para in paras:
        current.append(para)
        if len(words(" ".join(current))) >= PASSAGE_WORDS:
            out.append(" ".join(current))
            current = []
    if current:
        tail = " ".join(current)
        if out and len(words(tail)) < PASSAGE_WORDS / 2:
            out[-1] = f"{out[-1]} {tail}"
        else:
            out.append(tail)
    return out


def _passage_reasons(text: str) -> list[str]:
    """Which AI-like patterns one passage shows."""
    sents = sentences(text)
    lengths = [len(words(s)) for s in sents]
    n = max(1, len(words(text)))
    lower = text.lower()
    reasons = []
    if len(lengths) >= 3 and _cv(lengths) < 0.30:
        reasons.append("even sentence lengths")
    stock = sum(len(re.findall(rf"(?<![a-z]){re.escape(p)}(?![a-z])", lower)) for p in STOCK_PHRASES)
    if stock >= 2:
        reasons.append("stock phrases")
    numbers = len(re.findall(r"\b\d[\d,.%]*\b", text))
    names = sum(1 for s in sents for w in words(s)[1:] if w[:1].isupper() and w.lower() not in STOPWORDS)
    quotes = len(re.findall(r"[\"“][^\"“”]{12,}[\"”]", text))
    if (numbers + names + 3 * quotes) * 100 / n < 3:
        reasons.append("few concrete details")
    return reasons


def ai_share(body_html: str) -> tuple[int, list[dict]]:
    """Estimated share of the text (by words) in passages that read as AI-like.

    A passage counts when it shows at least two of: very even sentence
    lengths, repeated stock phrases, and almost no names, numbers or quotes.
    An estimate of how much of the writing has the patterns of generated text,
    never a measure of who or what wrote it.
    """
    total, flagged, out = 0, 0, []
    for text in _passages(body_html):
        n = len(words(text))
        reasons = _passage_reasons(text)
        ai_like = len(reasons) >= 2
        total += n
        flagged += n if ai_like else 0
        out.append({
            "excerpt": text[:140].rsplit(" ", 1)[0] + "…" if len(text) > 140 else text,
            "words": n,
            "aiLike": ai_like,
            "reasons": reasons,
        })
    return (round(100 * flagged / total) if total else 0), out
