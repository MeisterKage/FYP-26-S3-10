"""Ninety more demo articles: ten for each country, spread across every section.

Fictional demo reporting, like demo_expansion.py: no real person is named or
quoted; officials, residents and analysts are invented or unnamed. Each entry is
(country, section, writer email, headline, standfirst, paragraphs), and "## "
starts a subheading.
"""
import importlib
import pkgutil

ARTICLES: list = []
for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    ARTICLES.extend(importlib.import_module(f"{__name__}.{_info.name}").ARTICLES)
