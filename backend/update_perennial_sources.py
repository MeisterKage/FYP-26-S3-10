"""Refresh the dated copy of Wikipedia's Perennial Sources list.

    py update_perennial_sources.py      # needs internet access; commit the result

Wikipedia's editors keep a public, discussed classification of frequently used
sources (https://en.wikipedia.org/wiki/Wikipedia:Reliable_sources/Perennial_sources).
The source-rating system (app/source_rating.py) looks domains up in a copy of
it, saved to app/data/perennial_sources.json with the revision and date it was
taken from, so every rating can say exactly what it was based on.

The list is licensed CC BY-SA 4.0. The About page credits it.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
BASE = "Wikipedia:Reliable sources/Perennial sources"
USER_AGENT = "WollongongNews-SourceRatings/1.0 (university student project)"
OUT = Path(__file__).parent / "app" / "data" / "perennial_sources.json"

STATUSES = {
    "gr": "generally reliable",
    "nc": "no consensus",
    "gu": "generally unreliable",
    "d": "deprecated",
    "b": "blacklisted",
}

ROW = re.compile(r'^\|-\s*class="s-(\w+)[^"]*"\s*id="([^"]*)"', re.M)
USES = re.compile(r"\{\{WP:RSPUSES\|([^}]*)\}\}")


def fetch(title: str) -> dict:
    params = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp",
        "rvslots": "main", "format": "json", "formatversion": 2, "titles": title,
    })
    request = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        page = json.loads(response.read())["query"]["pages"][0]
    if "revisions" not in page:
        return {}
    rev = page["revisions"][0]
    return {"text": rev["slots"]["main"]["content"], "revid": rev["revid"],
            "timestamp": rev["timestamp"]}


def domains_in(uses: str) -> list[str]:
    out = []
    for part in uses.split("|"):
        part = part.strip().lower()
        if not part or "=" in part:
            continue  # named parameters, not domains
        part = re.sub(r"^https?://", "", part).split("/")[0]
        if part.startswith("www."):
            part = part[4:]
        if "." in part:
            out.append(part)
    return out


def parse(text: str) -> list[dict]:
    rows = []
    matches = list(ROW.finditer(text))
    for i, m in enumerate(matches):
        status = m.group(1)
        if status not in STATUSES:
            continue
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        domains = [d for uses in USES.findall(body) for d in domains_in(uses)]
        if domains:
            rows.append({"name": m.group(2), "status": status, "domains": domains})
    return rows


def main() -> None:
    entries: dict[str, dict] = {}
    revisions = {}
    for n in range(1, 21):
        title = f"{BASE}/{n}"
        page = fetch(title)
        if not page:
            break
        revisions[title] = page["revid"]
        for row in parse(page["text"]):
            for domain in row["domains"]:
                # A domain listed twice keeps its first classification; the
                # list is maintained so that this does not happen in practice.
                entries.setdefault(domain, {"name": row["name"], "status": row["status"]})
        time.sleep(1)

    if len(entries) < 200:
        sys.exit(f"Only {len(entries)} domains parsed; the page format may have changed. Not saving.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "https://en.wikipedia.org/wiki/Wikipedia:Reliable_sources/Perennial_sources",
        "license": "CC BY-SA 4.0",
        "retrieved": datetime.now(timezone.utc).date().isoformat(),
        "revisions": revisions,
        "statuses": STATUSES,
        "domains": dict(sorted(entries.items())),
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    counts: dict[str, int] = {}
    for e in entries.values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"Saved {len(entries)} domains from {len(revisions)} pages to {OUT}")
    print("  " + ", ".join(f"{STATUSES[k]}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
