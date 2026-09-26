"""Real sources for the demo articles, in place of example.org placeholders.

    py demo_sources.py      # after seed.py; needs internet access

The demo articles are fictional, so no source here documents the story it is
attached to. Each points to the *institution* a reporter on that beat would
cite, usually its home page, so nothing implies a real body said something it
did not. Writers keep the sourcing habits the seed gives them: the veteran
cites five sources, the mid-career writer three, the newcomer one.

A few articles carry a deliberate problem, so the rating system has something
real to show:

  * a pending housing story cites the Daily Mail, which Wikipedia's editors
    have deprecated, so it is flagged in the review queue;
  * a published bowel-screening story cites the 1998 Wakefield paper, which
    The Lancet retracted in 2010, so it is flagged as a retracted paper;
  * the ice-core and gravitational-wave stories cite real, unretracted papers
    by DOI.

Safe to run again: only articles whose sources are all placeholders (or have
none) are changed, plus, with --overrides, the deliberate cases above and
international stories. Sources are then rated and scores recalculated.
"""
from __future__ import annotations

import sys

from app import create_app
from app.extensions import db
from app.models import Article, ArticleSource, Category
from app.scoring_service import rescore_contributor_articles
from app.source_service import rate_sources

#: Official source for each section, by country.
OFFICIAL = {
    "AU": {
        "Politics": ("https://www.aph.gov.au/", "Parliament of Australia"),
        "Business": ("https://www.rba.gov.au/", "Reserve Bank of Australia"),
        "Health": ("https://www.health.gov.au/", "Department of Health"),
        "Science": ("https://www.csiro.au/", "CSIRO"),
        "Environment": ("https://www.bom.gov.au/", "Bureau of Meteorology"),
        "Sport": ("https://www.ausport.gov.au/", "Australian Sports Commission"),
        "Technology": ("https://www.acma.gov.au/", "Australian Communications and Media Authority"),
    },
    "NZ": {
        "Politics": ("https://www.parliament.nz/", "New Zealand Parliament"),
        "Business": ("https://www.rbnz.govt.nz/", "Reserve Bank of New Zealand"),
        "Health": ("https://www.health.govt.nz/", "Ministry of Health"),
        "Science": ("https://niwa.co.nz/", "NIWA"),
        "Environment": ("https://www.doc.govt.nz/", "Department of Conservation"),
        "Sport": ("https://sportnz.org.nz/", "Sport NZ"),
        "Technology": ("https://www.digital.govt.nz/", "Digital.govt.nz"),
    },
    "SG": {
        "Politics": ("https://www.parliament.gov.sg/", "Parliament of Singapore"),
        "Business": ("https://www.mas.gov.sg/", "Monetary Authority of Singapore"),
        "Health": ("https://www.moh.gov.sg/", "Ministry of Health"),
        "Science": ("https://www.a-star.edu.sg/", "A*STAR"),
        "Environment": ("https://www.nea.gov.sg/", "National Environment Agency"),
        "Sport": ("https://www.sportsingapore.gov.sg/", "Sport Singapore"),
        "Technology": ("https://www.imda.gov.sg/", "Infocomm Media Development Authority"),
    },
    "JP": {
        "Politics": ("https://www.shugiin.go.jp/", "House of Representatives"),
        "Business": ("https://www.boj.or.jp/en/", "Bank of Japan"),
        "Health": ("https://www.mhlw.go.jp/english/", "Ministry of Health, Labour and Welfare"),
        "Science": ("https://www.jma.go.jp/jma/indexe.html", "Japan Meteorological Agency"),
        "Environment": ("https://www.env.go.jp/en/", "Ministry of the Environment"),
        "Sport": ("https://www.mext.go.jp/en/", "Ministry of Education, Culture, Sports, Science and Technology"),
        "Technology": ("https://www.meti.go.jp/english/", "Ministry of Economy, Trade and Industry"),
    },
    "GB": {
        "Politics": ("https://www.parliament.uk/", "UK Parliament"),
        "Business": ("https://www.bankofengland.co.uk/", "Bank of England"),
        "Health": ("https://www.nhs.uk/", "NHS"),
        "Science": ("https://www.ukri.org/", "UK Research and Innovation"),
        "Environment": ("https://www.gov.uk/government/organisations/environment-agency", "Environment Agency"),
        "Sport": ("https://www.uksport.gov.uk/", "UK Sport"),
        "Technology": ("https://www.ofcom.org.uk/", "Ofcom"),
    },
    "US": {
        "Politics": ("https://www.congress.gov/", "Congress.gov"),
        "Business": ("https://www.federalreserve.gov/", "Federal Reserve"),
        "Health": ("https://www.cdc.gov/", "Centers for Disease Control and Prevention"),
        "Science": ("https://www.nsf.gov/", "National Science Foundation"),
        "Environment": ("https://www.noaa.gov/", "NOAA"),
        "Sport": ("https://www.ncaa.org/", "NCAA"),
        "Technology": ("https://www.ftc.gov/", "Federal Trade Commission"),
    },
}
STATISTICS = {
    "AU": ("https://www.abs.gov.au/", "Australian Bureau of Statistics"),
    "NZ": ("https://www.stats.govt.nz/", "Stats NZ"),
    "SG": ("https://www.singstat.gov.sg/", "Department of Statistics Singapore"),
    "JP": ("https://www.stat.go.jp/english/", "Statistics Bureau of Japan"),
    "GB": ("https://www.ons.gov.uk/", "Office for National Statistics"),
    "US": ("https://www.bls.gov/", "Bureau of Labor Statistics"),
    None: ("https://www.oecd.org/", "OECD"),
}
#: Outlets, strongest first. The last one is often unrated, by design: a
#: realistic mix shows the grades working.
OUTLETS = {
    "AU": [("https://www.smh.com.au/", "The Sydney Morning Herald"),
           ("https://www.theguardian.com/australia-news", "Guardian Australia"),
           ("https://www.illawarramercury.com.au/", "Illawarra Mercury")],
    "NZ": [("https://www.nzherald.co.nz/", "NZ Herald"),
           ("https://www.rnz.co.nz/", "RNZ"),
           ("https://www.stuff.co.nz/", "Stuff")],
    "SG": [("https://www.straitstimes.com/", "The Straits Times"),
           ("https://www.channelnewsasia.com/", "CNA"),
           ("https://www.todayonline.com/", "TODAY")],
    "JP": [("https://www.reuters.com/world/japan/", "Reuters"),
           ("https://www3.nhk.or.jp/nhkworld/", "NHK World"),
           ("https://www.japantimes.co.jp/", "The Japan Times")],
    "GB": [("https://www.bbc.co.uk/news", "BBC News"),
           ("https://www.theguardian.com/uk", "The Guardian"),
           ("https://www.ft.com/", "Financial Times")],
    "US": [("https://apnews.com/", "Associated Press"),
           ("https://www.reuters.com/world/us/", "Reuters"),
           ("https://www.npr.org/", "NPR")],
    None: [("https://www.reuters.com/", "Reuters"),
           ("https://apnews.com/", "Associated Press"),
           ("https://www.bbc.co.uk/news/world", "BBC World")],
}
INTERNATIONAL = {
    "Politics": ("https://www.un.org/", "United Nations"),
    "Business": ("https://www.worldbank.org/", "World Bank"),
    "Health": ("https://www.who.int/", "World Health Organization"),
    "Science": ("https://www.unesco.org/", "UNESCO"),
    "Environment": ("https://www.ipcc.ch/", "IPCC"),
    "Sport": ("https://www.reuters.com/sports/", "Reuters Sport"),
    "Technology": ("https://www.oecd.org/digital/", "OECD Digital"),
}

#: Deliberate cases, by headline. Replaces the whole list for that article.
OVERRIDES = {
    "Housing grant changes take effect for first-time buyers": [
        ("https://www.dailymail.co.uk/news/index.html", "Daily Mail"),
    ],
    # A bowel-screening story citing a discredited paper on bowel inflammation:
    # the retraction check flags it for the editor.
    "Health ministry expands subsidised screening programme": [
        ("https://www.moh.gov.sg/", "Ministry of Health"),
        ("https://www.straitstimes.com/", "The Straits Times"),
        ("https://doi.org/10.1016/S0140-6736(97)11096-0",
         "Wakefield et al., The Lancet, 1998"),
    ],
    "UK polar researchers retrieve their deepest ice core yet": [
        ("https://www.ukri.org/", "UK Research and Innovation"),
        ("https://www.bas.ac.uk/", "British Antarctic Survey"),
        ("https://doi.org/10.1038/nature02599",
         "EPICA community members, Nature, 2004"),
        ("https://www.bbc.co.uk/news", "BBC News"),
        ("https://www.theguardian.com/uk", "The Guardian"),
    ],
    "Observatory upgrade sharpens gravitational wave detection": [
        ("https://doi.org/10.1103/PhysRevLett.116.061102",
         "LIGO and Virgo Collaborations, Physical Review Letters, 2016"),
        ("https://www.nsf.gov/", "National Science Foundation"),
        ("https://www.nature.com/", "Nature"),
    ],
}

COUNTS = {"veteran@newsrelease.test": 5, "contributor@newsrelease.test": 3}


def sources_for(title: str, country: str | None, section: str, writer_email: str) -> list[tuple]:
    if title in OVERRIDES:
        return OVERRIDES[title]
    official = OFFICIAL.get(country, {}).get(section, INTERNATIONAL.get(section))
    outlets = OUTLETS.get(country, OUTLETS[None])
    stats = STATISTICS.get(country, STATISTICS[None])
    intl = INTERNATIONAL.get(section, INTERNATIONAL["Politics"])
    count = COUNTS.get(writer_email, 1)
    if count == 1:
        # The newcomer cites a single outlet, which is why their scores are lower.
        return [outlets[-1]]
    picks = ([official, outlets[0], outlets[-1]] if count == 3
             else [official, stats, outlets[0], outlets[1], intl])
    # A story with no country can draw the same body twice (the UN as both its
    # official and its international source); fall back to other outlets.
    spare = [o for o in outlets + OUTLETS[None] if o not in picks]
    unique = []
    for pick in picks:
        unique.append(pick if pick not in unique else spare.pop(0))
    return unique


def is_placeholder(article: Article) -> bool:
    return all("example.org" in s.url for s in article.sources)


def should_refresh(article: Article) -> bool:
    if is_placeholder(article):
        return True
    return "--overrides" in sys.argv and (
        article.title in OVERRIDES or article.country_code is None)


def main() -> None:
    changed = []
    for article in Article.query.all():
        if not should_refresh(article):
            continue
        section = db.session.get(Category, article.category_id).name
        wanted = sources_for(article.title, article.country_code, section,
                             article.contributor.email)
        ArticleSource.query.filter_by(article_id=article.id).delete()
        for url, label in wanted:
            db.session.add(ArticleSource(article_id=article.id, url=url, label=label))
        changed.append(article)
    db.session.flush()

    tiers: dict[str, int] = {}
    for article in changed:
        db.session.expire(article, ["sources"])
        for source in rate_sources(article):
            tiers[source.tier] = tiers.get(source.tier, 0) + 1
    db.session.flush()
    for writer in {a.contributor for a in changed}:
        rescore_contributor_articles(writer)
    db.session.commit()
    print(f"Replaced the sources of {len(changed)} article(s): "
          + ", ".join(f"{k} {v}" for k, v in sorted(tiers.items())))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with create_app().app_context():
        main()
