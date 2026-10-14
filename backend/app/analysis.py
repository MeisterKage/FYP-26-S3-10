"""Tone and trend for one article. Pure functions; the database is in analysis_service.

Tone (sentiment) uses VADER (Hutto and Gilbert, 2014), a lexicon and rule
model that scores each sentence from -1 (very negative) to +1 (very positive)
and runs locally with no service. An article's tone is the mean over its
sentences, which is steadier than scoring whole paragraphs: VADER saturates on
long text. The bands are set for news, which VADER reads as mildly positive on
the whole (the demo articles' median is about +0.08), so "Neutral" spans a
little above zero rather than sitting on it.

Tone is about the language, not the facts: a careful report of bad news reads
negative, and that says nothing about its accuracy.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from . import insights

_analyzer = SentimentIntensityAnalyzer()

BANDS = (
    (0.25, "positive", "Positive"),
    (0.10, "leans_positive", "Leans positive"),
    (-0.05, "neutral", "Neutral"),
    (-0.20, "leans_negative", "Leans negative"),
)
STRONG = 0.3  # a sentence this far from zero is worth quoting as an extreme


def band(score: float) -> tuple[str, str]:
    for floor, key, label in BANDS:
        if score >= floor:
            return key, label
    return "negative", "Negative"


def sentence_score(text: str) -> float:
    return _analyzer.polarity_scores(text)["compound"]


def tone(body_html: str) -> dict:
    """The article's overall tone, its tone paragraph by paragraph, and its extremes."""
    paras = [p for p in insights.paragraphs(body_html) if not p.heading]
    scored_paras, every = [], []
    for p in paras:
        scores = [(s, sentence_score(s)) for s in insights.sentences(p.text)]
        if not scores:
            continue
        every.extend(scores)
        scored_paras.append(round(mean(v for _, v in scores), 3))
    if not every:
        return {"score": 0.0, "band": "neutral", "label": "Neutral", "paragraphs": [],
                "mostPositive": None, "mostNegative": None, "sentences": 0}
    overall = round(mean(v for _, v in every), 3)
    key, label = band(overall)
    best = max(every, key=lambda x: x[1])
    worst = min(every, key=lambda x: x[1])
    return {
        "score": overall,
        "band": key,
        "label": label,
        "paragraphs": scored_paras,
        "mostPositive": {"text": best[0], "score": round(best[1], 3)} if best[1] >= STRONG else None,
        "mostNegative": {"text": worst[0], "score": round(worst[1], 3)} if worst[1] <= -STRONG else None,
        "sentences": len(every),
        "share": {
            "positive": round(sum(1 for _, v in every if v >= 0.05) / len(every), 3),
            "negative": round(sum(1 for _, v in every if v <= -0.05) / len(every), 3),
        },
    }


def daily_series(counts: dict[date, int], today: date, days: int = 14) -> list[dict]:
    """The last `days` days, oldest first, with zero for days without any."""
    start = today - timedelta(days=days - 1)
    return [{"day": (start + timedelta(d)).isoformat(), "count": counts.get(start + timedelta(d), 0)}
            for d in range(days)]


def direction(series: list[dict]) -> str:
    """Rising, steady or falling: this week against the week before."""
    half = len(series) // 2
    before = sum(p["count"] for p in series[:half])
    recent = sum(p["count"] for p in series[half:])
    if recent == 0 and before == 0:
        return "quiet"
    if before == 0:
        return "rising"
    ratio = recent / before
    if ratio >= 1.15:
        return "rising"
    if ratio <= 0.85:
        return "falling"
    return "steady"


def weekly(dates: list[date], today: date, weeks: int = 8) -> list[dict]:
    """How many of these dates fall in each of the last `weeks` weeks, oldest first."""
    out = []
    for w in range(weeks - 1, -1, -1):
        end = today - timedelta(days=7 * w)
        start = end - timedelta(days=6)
        out.append({"weekEnding": end.isoformat(),
                    "count": sum(1 for d in dates if start <= d <= end)})
    return out
