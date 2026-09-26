"""Originality: how much of an article's text also appears somewhere else.

Pure, in the same discipline as `credibility.py` and `triage.py`: no database,
no network, no clock. Text in, fingerprints and matches out, so every rule here
is unit-tested directly.

--------------------------------------------------------------------------------
HOW TEXT IS COMPARED
--------------------------------------------------------------------------------

1. Normalise. Lowercase, numbers become "#", common filler words ("the", "of",
   "and"...) are dropped, and word endings are trimmed ("rises", "rising" and
   "rise" all become "ris"). Light paraphrase, the kind that swaps a tense or
   deletes a few small words, therefore no longer hides a copy.

2. Fingerprint. Every run of K consecutive normalised words is hashed. From
   those, winnowing (Schleimer, Wilkerson and Aiken, 2003, the algorithm behind
   Stanford's MOSS) keeps the smallest hash in each window of W, which stores a
   fraction of the hashes but still guarantees that any shared passage of at
   least K + W - 1 normalised words is found.

3. Measure. The share of an article's own (unquoted) words that fall inside a
   passage also found elsewhere. "34%" means 34% of the words, and the matching
   passages are returned so an editor judges the evidence, not the number.

Quotations are measured separately. Text inside quotation marks or a
blockquote is not counted as copying: quoting a statement is journalism. It is
checked against the article's cited sources instead, and a quote the sources
contain is reported as verified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import blake2b
from html.parser import HTMLParser

#: Normalised words per fingerprint. Five content words is roughly eight to ten
#: words of ordinary prose: long enough that a match is not a stock phrase.
K = 5
#: Winnowing window. Any shared run of K + W - 1 = 8 content words is detected.
W = 4

#: Settings, overridable by an administrator through PlatformSetting. Kept with
#: the review-automation settings (triage.DEFAULTS) because they act on review.
DEFAULTS: dict[str, float] = {
    "originality_flag_percent": 20.0,         # at or above: flagged to the editor
    "originality_substantial_percent": 50.0,  # at or above: "substantially matches"
}

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because
been before being below between both but by can could did do does doing down
during each few for from further had has have having he her here hers herself
him himself his how i if in into is it its itself just me more most my myself
no nor not now of off on once only or other our ours ourselves out over own
said same she should so some such than that the their theirs them themselves
then there these they this those through to too under until up very was we
were what when where which while who whom why will with would you your yours
yourself yourselves
""".split())

_SUFFIXES = ("ingly", "edly", "ings", "ing", "ies", "ied", "ed", "es", "ly", "s")
#: Written-out numbers count as numbers, so "twelve" and "12" are the same word.
NUMBER_WORDS = frozenset("""
zero one two three four five six seven eight nine ten eleven twelve thirteen
fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty
sixty seventy eighty ninety hundred thousand
""".split())
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
#: A quotation: straight or curly double quotes around at least a few words.
_QUOTE = re.compile(r"[\"“]([^\"“”]{12,}?)[\"”]")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    # "complete" and "completed" should meet at "complet".
    if word.endswith("e") and len(word) > 4:
        word = word[:-1]
    return word


def _hash(gram: tuple[str, ...]) -> int:
    digest = blake2b(" ".join(gram).encode(), digest_size=8).digest()
    # Shifted to fit a signed 64-bit database column.
    return int.from_bytes(digest, "big") >> 1


# --------------------------------------------------------------------------- #
#  Text
# --------------------------------------------------------------------------- #

class _TextExtractor(HTMLParser):
    """HTML to plain text, recording which character ranges sit in a blockquote."""

    SKIP = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
             "section", "article", "tr", "td", "th", "ul", "ol", "figcaption"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.length = 0
        self.skip_depth = 0
        self.quote_depth = 0
        self.quote_start = 0
        self.quoted: list[tuple[int, int]] = []

    def _emit(self, text: str):
        self.parts.append(text)
        self.length += len(text)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag in self.BLOCK:
            self._emit("\n")
        if tag == "blockquote":
            if self.quote_depth == 0:
                self.quote_start = self.length
            self.quote_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "blockquote" and self.quote_depth:
            self.quote_depth -= 1
            if self.quote_depth == 0:
                self.quoted.append((self.quote_start, self.length))
        if tag in self.BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self._emit(data)


@dataclass(frozen=True)
class Token:
    norm: str
    start: int
    end: int
    quoted: bool


@dataclass(frozen=True)
class Document:
    text: str
    tokens: list[Token]
    quotes: list[tuple[int, int]]

    @property
    def word_count(self) -> int:
        return len(_WORD.findall(self.text))


def parse(content: str, *, html: bool = True) -> Document:
    """Plain text, its content-word tokens, and which of them are quoted."""
    if html:
        extractor = _TextExtractor()
        extractor.feed(content or "")
        extractor.close()
        raw = "".join(extractor.parts)
        block_quotes = extractor.quoted
    else:
        raw, block_quotes = content or "", []

    # Collapse whitespace while keeping character offsets consistent: offsets
    # are computed on the collapsed text, so blockquote ranges are remapped.
    text_chars, index_map = [], []
    previous_space = True
    for i, ch in enumerate(raw):
        if ch.isspace():
            if previous_space:
                continue
            ch = " "
            previous_space = True
        else:
            previous_space = False
        index_map.append(i)
        text_chars.append(ch)
    text = "".join(text_chars).strip()

    def remap(pos: int) -> int:
        # First collapsed index whose source index is >= pos.
        lo, hi = 0, len(index_map)
        while lo < hi:
            mid = (lo + hi) // 2
            if index_map[mid] < pos:
                lo = mid + 1
            else:
                hi = mid
        return lo

    quotes = [(remap(a), remap(b)) for a, b in block_quotes]
    quotes += [(m.start(), m.end()) for m in _QUOTE.finditer(text)]
    quotes.sort()

    def in_quote(start: int) -> bool:
        return any(a <= start < b for a, b in quotes)

    tokens = []
    for m in _WORD.finditer(text):
        word = m.group(0).lower().replace("’", "'")
        if word in STOPWORDS:
            continue
        norm = "#" if word.isdigit() or word in NUMBER_WORDS else _stem(word.split("'")[0])
        tokens.append(Token(norm, m.start(), m.end(), in_quote(m.start())))
    return Document(text=text, tokens=tokens, quotes=_merge(quotes))


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


# --------------------------------------------------------------------------- #
#  Fingerprints
# --------------------------------------------------------------------------- #

def kgrams(tokens: list[Token]) -> list[int]:
    """The hash of every run of K tokens, in order. Position i covers tokens i..i+K-1."""
    norms = [t.norm for t in tokens]
    return [_hash(tuple(norms[i:i + K])) for i in range(len(norms) - K + 1)]


def winnow(hashes: list[int]) -> list[tuple[int, int]]:
    """(hash, position) pairs selected by winnowing: the rightmost minimum of each window."""
    if not hashes:
        return []
    if len(hashes) < W:
        i = min(range(len(hashes)), key=lambda j: (hashes[j], -j))
        return [(hashes[i], i)]
    selected: list[tuple[int, int]] = []
    last = -1
    for start in range(len(hashes) - W + 1):
        window = range(start, start + W)
        i = min(window, key=lambda j: (hashes[j], -j))
        if i != last:
            selected.append((hashes[i], i))
            last = i
    return selected


def fingerprint(doc: Document) -> list[tuple[int, int]]:
    """What an article contributes to the index: winnowed fingerprints of all its text."""
    return winnow(kgrams(doc.tokens))


# --------------------------------------------------------------------------- #
#  Matching
# --------------------------------------------------------------------------- #

@dataclass
class Passage:
    start: int
    end: int
    text: str
    #: Positions (k-gram indexes) in the other document, when known.
    other_positions: list[int] = field(default_factory=list)


def _runs(positions: set[int]) -> list[tuple[int, int]]:
    """Token-index runs covered by matched k-grams at the given positions."""
    covered = sorted({i + j for i in positions for j in range(K)})
    runs: list[tuple[int, int]] = []
    for i in covered:
        if runs and i == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs


def matched_positions(doc: Document, other_hashes: set[int], *, quoted: bool = False) -> set[int]:
    """k-gram positions of `doc` found in the other text, restricted to quoted or unquoted words.

    A k-gram belongs to the unquoted text only if none of its words is quoted,
    and to the quoted text only if all of them are.
    """
    hashes = kgrams(doc.tokens)
    out = set()
    for i, h in enumerate(hashes):
        if h not in other_hashes:
            continue
        flags = [t.quoted for t in doc.tokens[i:i + K]]
        if (quoted and all(flags)) or (not quoted and not any(flags)):
            out.add(i)
    return out


def coverage(doc: Document, positions: set[int]) -> float:
    """Percentage of the document's unquoted words covered by the matched positions."""
    unquoted = sum(1 for t in doc.tokens if not t.quoted)
    if unquoted == 0:
        return 0.0
    covered = {i + j for i in positions for j in range(K)}
    hits = sum(1 for i in covered if i < len(doc.tokens) and not doc.tokens[i].quoted)
    return round(100.0 * hits / unquoted, 1)


def passages(doc: Document, positions: set[int]) -> list[Passage]:
    out = []
    for a, b in _runs(positions):
        start, end = doc.tokens[a].start, doc.tokens[b].end
        out.append(Passage(start=start, end=end, text=doc.text[start:end]))
    return out


def level(percent: float, settings: dict | None = None) -> str:
    cfg = {**DEFAULTS, **(settings or {})}
    if percent >= float(cfg["originality_substantial_percent"]):
        return "substantial"
    if percent >= float(cfg["originality_flag_percent"]):
        return "partial"
    return "original"


def verify_quotes(doc: Document, source_texts: dict[str, Document]) -> list[dict]:
    """For each quotation in the article, which cited source (if any) contains it.

    A quote is verified when at least 80% of its word runs appear in one source.
    Quotes too short to fingerprint are compared as normalised word sequences.
    """
    results = []
    source_hashes = {url: set(kgrams(src.tokens)) for url, src in source_texts.items()}
    source_norms = {url: " ".join(t.norm for t in src.tokens) for url, src in source_texts.items()}
    for a, b in doc.quotes:
        quote_tokens = [t for t in doc.tokens if a <= t.start < b]
        if not quote_tokens:
            continue
        text = doc.text[a:b].strip(" \"“”")
        found = None
        if len(quote_tokens) >= K:
            grams = kgrams(quote_tokens)
            for url, hashes in source_hashes.items():
                if grams and sum(1 for g in grams if g in hashes) / len(grams) >= 0.8:
                    found = url
                    break
        else:
            needle = " ".join(t.norm for t in quote_tokens)
            found = next((u for u, hay in source_norms.items() if needle in hay), None)
        results.append({"text": text[:400], "verified": found is not None, "source": found})
    return results
