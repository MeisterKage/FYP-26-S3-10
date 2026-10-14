"""AI translations of the demo articles into Mandarin (zh) and Bahasa Melayu (ms).

Each module holds T = {English headline: {"title", "summary", "paragraphs",
"points"}}, paragraphs in the same order as the English, "## " marking a
subheading, and "points" the In brief key points in the same order as the
English ones. Loaded by `py seed.py --translations`.
"""
from __future__ import annotations

import importlib
import pkgutil


def load(lang: str) -> dict:
    """Every translation for one language, keyed by the English headline."""
    out: dict = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith(f"{lang}_"):
            out.update(importlib.import_module(f"{__name__}.{info.name}").T)
    return out
