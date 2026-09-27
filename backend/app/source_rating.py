"""Rating the sources an article cites. Pure: no database, no network, no clock.

A source link earns points toward an article's credibility score according to
what kind of source it is. Every tier comes from a rule or a published list
anyone can check, never from this system's opinion:

    tier            how it is recognised                                points
    ------------    -------------------------------------------------   ------
    official        government, parliament, courts, intergovernmental      5
                    bodies (.gov, .gov.au, .govt.nz, who.int ...)
    research        a DOI (a published paper), unless Crossref /             5
                    Retraction Watch records it as retracted
    institution     a university or research institute (.edu, .ac.uk ...)  5
    reliable        "generally reliable" on Wikipedia's Perennial Sources  5
    unrated         "no consensus" there, or on no list at all              2
    unreliable      "generally unreliable" there, or social media and       0
                    self-published platforms
    deprecated      "deprecated" or "blacklisted" there                     0, flagged
    retracted       a DOI Crossref records as retracted                     0, flagged
    invalid         a placeholder or reserved domain, or a page that        0
                    does not exist

The order they are checked in:

    1. placeholder addresses and pages that do not exist (never a source)
    2. papers, by DOI, checked for retraction
    3. an administrator's grade for the domain (source_domain_rules)
    4. government, parliamentary and academic address endings
    5. Wikipedia's Perennial Sources list
    6. who owns the domain, per Wikidata: a government body that is not a
       media organisation counts as official
    7. self-published platforms
    8. otherwise unrated

An editor has the final word: "accepted" gives a source full points, "not
credible" gives it none, and either needs a reason, which is logged. The tier
is where review starts, not where it ends.

Wikipedia's list: https://en.wikipedia.org/wiki/Wikipedia:Reliable_sources/Perennial_sources
(CC BY-SA 4.0), kept as a dated copy in app/data/perennial_sources.json.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

FULL, PARTIAL, NONE = 5.0, 2.0, 0.0

TIER_POINTS = {
    "official": FULL, "research": FULL, "institution": FULL, "reliable": FULL,
    "unrated": PARTIAL,
    "unreliable": NONE, "deprecated": NONE, "retracted": NONE, "invalid": NONE,
}
TIER_LABELS = {
    "official": "Official source",
    "research": "Published research",
    "institution": "Academic institution",
    "reliable": "Established outlet",
    "unrated": "Unrated",
    "unreliable": "Unreliable",
    "deprecated": "Deprecated",
    "retracted": "Retracted paper",
    "invalid": "Not a real source",
}
#: These are shown to the editor before they approve.
FLAGGED_TIERS = {"deprecated", "retracted"}

#: Government and parliamentary domains, by suffix.
OFFICIAL_SUFFIXES = (
    ".gov", ".gov.au", ".gov.uk", ".govt.nz", ".gov.sg", ".go.jp", ".gc.ca", ".gov.in",
    ".gov.ie", ".gouv.fr", ".bund.de", ".europa.eu", ".mil", ".int", ".parliament.uk",
    ".nsw.gov.au", ".vic.gov.au",
)
#: Major intergovernmental and parliamentary bodies, so the most common
#: official sources need no lookup. Other official bodies on ordinary addresses
#: (central banks, regulators, research agencies) are found through Wikidata,
#: and anything Wikidata misses an administrator can grade.
OFFICIAL_DOMAINS = {
    "un.org", "who.int", "oecd.org", "imf.org", "worldbank.org", "wto.org", "ilo.org",
    "parliament.uk", "parliament.nz", "aph.gov.au", "legislation.gov.au", "bis.org",
    "nhs.uk", "ecb.europa.eu", "unesco.org", "unicef.org", "ipcc.ch",
}
ACADEMIC_SUFFIXES = (
    ".edu", ".edu.au", ".ac.uk", ".ac.nz", ".edu.sg", ".ac.jp", ".edu.cn", ".ac.in",
)
#: Platforms where anyone can publish. Wikipedia's list covers most of these;
#: this catches the rest.
SELF_PUBLISHED = {
    "twitter.com", "x.com", "facebook.com", "instagram.com", "tiktok.com", "reddit.com",
    "medium.com", "substack.com", "blogspot.com", "wordpress.com", "tumblr.com",
    "linkedin.com", "quora.com", "youtube.com", "threads.net", "pinterest.com",
}
#: Reserved for documentation and testing (RFC 2606, RFC 6761). Never a source.
RESERVED = ("example.com", "example.org", "example.net", ".example", ".test", ".invalid",
            ".localhost", "localhost")

DOI_HOSTS = {"doi.org", "dx.doi.org"}
DOI_IN_PATH = re.compile(r"(10\.\d{4,9}/[^\s?#]+)")

DATA_FILE = Path(__file__).parent / "data" / "perennial_sources.json"


@dataclass(frozen=True)
class Rating:
    tier: str
    points: float
    reason: str
    flagged: bool = False
    doi: str | None = None

    @property
    def label(self) -> str:
        return TIER_LABELS[self.tier]


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def doi_of(url: str) -> str | None:
    """A DOI in the link's path: doi.org/10.x/y, or a publisher URL containing one."""
    match = DOI_IN_PATH.search(urlparse(url).path)
    return match.group(1).rstrip(".").lower() if match else None


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


@lru_cache(maxsize=1)
def perennial() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def perennial_entry(host: str) -> tuple[str, dict] | None:
    """The most specific listed domain covering this host, if any."""
    domains = perennial()["domains"]
    parts = host.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in domains:
            return candidate, domains[candidate]
    return None


#: Grades an administrator may give a domain. Research, retracted and invalid
#: are facts about a particular link, not judgements about a domain.
ADMIN_TIERS = ("official", "institution", "reliable", "unrated", "unreliable", "deprecated")


def normalise_domain(value: str) -> str | None:
    """A bare lower-case domain from whatever an administrator typed, or None."""
    value = (value or "").strip().lower()
    if "://" in value:
        value = urlparse(value).hostname or ""
    value = value.split("/")[0].rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
        return None
    return value


def rule_for(host: str, rules: dict[str, tuple[str, str]]) -> tuple[str, str, str] | None:
    """The most specific administrator rule covering a host: (domain, tier, reason)."""
    parts = host.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in rules:
            return (candidate, *rules[candidate])
    return None


def classify(url: str, *, exists: bool | None = True, doi_status: str | None = None,
             list_date: str | None = None, admin_rules: dict | None = None,
             official_owner: str | None = None) -> Rating:
    """Rate one source link.

    `exists` is False when the page could not be found at all (no such host, or
    404/410). A site that answers but refuses automated requests (403, 429)
    still exists: many reputable outlets block scripts.

    `doi_status` is what Crossref said about the link's DOI: "ok", "retracted",
    "unknown" (Crossref has no such paper), or None (no DOI, or not checked).

    `admin_rules` maps domain to (tier, reason). `official_owner` is the name
    of the government body Wikidata says owns the domain, if any.
    """
    host = host_of(url)
    if not host or any(host == r.lstrip(".") or host.endswith(r) for r in RESERVED):
        return Rating("invalid", NONE, "A placeholder address reserved for examples, not a real source.")
    if exists is False:
        return Rating("invalid", NONE, "The page could not be found.")

    doi = doi_of(url)
    if doi and doi_status == "retracted":
        return Rating("retracted", NONE,
                      "Crossref and Retraction Watch record this paper as retracted.",
                      flagged=True, doi=doi)
    if doi and doi_status == "ok":
        return Rating("research", FULL,
                      f"A published paper (DOI {doi}), not retracted per Crossref and "
                      "Retraction Watch.", doi=doi)
    if doi and host in DOI_HOSTS:
        if doi_status == "unknown":
            return Rating("invalid", NONE, f"No published paper has the DOI {doi}.", doi=doi)
        return Rating("research", FULL, f"A published paper (DOI {doi}). Not yet checked "
                                        "for retraction.", doi=doi)

    ruled = rule_for(host, admin_rules or {})
    if ruled:
        domain, tier, reason = ruled
        return Rating(tier, TIER_POINTS[tier], f"Graded by this site's administrators: {reason}",
                      flagged=tier in FLAGGED_TIERS)

    if any(_matches(host, d) for d in OFFICIAL_DOMAINS) or any(
            host.endswith(s) or host == s[1:] for s in OFFICIAL_SUFFIXES):
        return Rating("official", FULL, "A government, parliamentary or intergovernmental source.")
    if any(host.endswith(s) for s in ACADEMIC_SUFFIXES):
        return Rating("institution", FULL, "A university or research institution.")

    listed = perennial_entry(host)
    when = list_date or perennial().get("retrieved", "")
    if listed:
        domain, entry = listed
        status = entry["status"]
        said = f"Rated “{perennial()['statuses'][status]}” ({entry['name']}) by Wikipedia's reliable-sources consensus, list of {when}."
        if status == "gr":
            return Rating("reliable", FULL, said)
        if status == "nc":
            return Rating("unrated", PARTIAL, said)
        if status == "gu":
            return Rating("unreliable", NONE, said)
        return Rating("deprecated", NONE, said, flagged=True)

    if official_owner:
        return Rating("official", FULL,
                      f"The official website of {official_owner}, a government body, "
                      "according to Wikidata.")

    if any(_matches(host, d) for d in SELF_PUBLISHED):
        return Rating("unreliable", NONE, "A platform where anyone can publish.")

    return Rating("unrated", PARTIAL, "Not on any list this site uses. An editor can accept it.")


def points_for(rating: Rating, editor_verdict: str | None) -> float:
    """The points a source earns once any editor verdict is applied."""
    if editor_verdict == "accepted":
        return FULL
    if editor_verdict == "rejected":
        return NONE
    return rating.points
