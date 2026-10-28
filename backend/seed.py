"""Demo data.

Every wireframe in the PDD shows a populated platform. An empty demo reads as
broken, so this script builds a plausible one: six accounts covering every role,
eight categories, and ~50 articles with a realistic spread of credibility scores,
corrections, and reports.

    flask db upgrade     # schema first -- migrations own it
    py seed.py           # then load demo data
    py seed.py --reset   # empty the tables and reload
    py seed.py --countries   # tag countries and add samples to existing data
    py seed.py --originality # distinct demo bodies, index, and a planted copy
    py seed.py --long-bodies # full-length bodies for articles already seeded
    py seed.py --daily-views # a history of daily views behind each demo total
    py seed.py --expansion   # more editors, writers and articles; right sections (internet)
    py seed.py --more        # ten more articles per country (internet)
    py seed.py --translations # the demo articles in Mandarin and Malay
    flask rate-sources       # then grade every cited source (needs internet)

Passwords are all `DemoPassword123!` -- fine for a local demo, never for a
deployment anyone else can reach.
"""
from __future__ import annotations

import random
import sys
from datetime import timedelta

from app import create_app
from app.enums import (
    ArticleStatus, CorrectionType, ReportStatus, Role, SubscriptionStatus,
)
from app.extensions import db
from app.models import (
    Article, ArticleSource, Category, Comment, Correction, EditorCategory, Follow,
    Like, Report, Subscription, User, UserCategoryPreference, utcnow,
)
from app.modules.articles import slugify
from app.scoring_service import rescore_contributor_articles
from app.security import hash_password
from demo_bodies import STANDFIRSTS, body_for
from demo_sources import sources_for

DEMO_PASSWORD = "DemoPassword123!"

CATEGORIES = [
    ("Uncategorised", "Articles whose original category was removed.", True),
    ("Politics", "Government, policy, and elections.", False),
    ("Technology", "Software, hardware, and the industry around them.", False),
    ("Business", "Markets, companies, and the economy.", False),
    ("Health", "Medicine, public health, and wellbeing.", False),
    ("Science", "Research and discovery.", False),
    ("Environment", "Climate, conservation, and energy.", False),
    ("Sport", "Competition, athletes, and results.", False),
]

HEADLINES = [
    "Parliament passes revised data protection framework",
    "Regional startups raise record funding despite slowdown",
    "New study links urban green space to lower stress markers",
    "Grid operators report record renewable share in Q3",
    "Semiconductor shortage eases as new fabrication capacity opens",
    "Public transport ridership returns to pre-pandemic levels",
    "Researchers publish open dataset on coastal erosion",
    "Health ministry expands subsidised screening programme",
    "Local league announces revised season structure",
    "Central bank holds rates steady for third quarter",
    "Universities pilot shared research computing cluster",
    "Coastal reclamation project clears environmental review",
    "Retail sector reports uneven recovery across segments",
    "New guidelines issued for clinical trial transparency",
    "Wind capacity overtakes coal in regional generation mix",
    "Small businesses adopt digital payments at record pace",
    "Air quality index improves after emissions rules tighten",
    "National team qualifies after decisive away fixture",
    "Cabinet reshuffle brings three new ministers into portfolio roles",
    "Electoral boundaries review opens for public submissions",
    "Freedom of information requests rise for a fourth year",
    "Cross-border tax agreement enters its ratification stage",
    "Housing grant changes take effect for first-time buyers",
    "Container throughput steadies after a volatile first half",
    "Insurance premiums climb as claims from flooding mount",
    "Two regional carriers confirm merger talks",
    "Manufacturing output edges up on export orders",
    "Sovereign fund reports a narrower annual return",
    "Undersea cable landing adds regional bandwidth capacity",
    "Open-source licence change splits a developer community",
    "Data centre operators pledge water use disclosure",
    "Payment outage prompts review of settlement redundancy",
    "Rail signalling upgrade completes ahead of schedule",
    "Deep-sea survey records twelve previously undescribed species",
    "Long-running soil study finds nutrient decline levelling off",
    "Observatory upgrade sharpens gravitational wave detection",
    "Peer review trial publishes referee reports alongside papers",
    "Antibiotic resistance surveillance widens to private clinics",
    "Waiting times shorten at restructured outpatient units",
    "Vaccine coverage holds steady after a schedule change",
    "Mental health helpline reports sustained demand",
    "Stadium redevelopment pushes two fixtures to a neutral ground",
    "Youth academy funding tied to coaching accreditation",
    "Athletics body adopts revised qualification standards",
    "Swimming records fall at the regional championships",
    "Mangrove replanting reaches its five-year target early",
    "Fishing quota cut follows a lower stock assessment",
    "Heat advisory days double against the decade average",
    "Recycling contamination rates fall after a bin redesign",
    "Peatland restoration draws cross-border funding",
]

# The article loop below runs ARTICLE_COUNT times and indexes into HEADLINES. If
# it runs out it wraps and appends "(2)", "(3)" to the repeats, which is how the
# deployed site ended up showing the same headline three times: eighteen
# headlines were feeding fifty articles. Assert rather than wrap silently.
ARTICLE_COUNT = 50
assert len(HEADLINES) >= ARTICLE_COUNT, (
    f"HEADLINES has {len(HEADLINES)} entries for {ARTICLE_COUNT} articles; "
    "add more headlines rather than letting the seed repeat them."
)

# Article text comes from demo_bodies.py: one distinct body per headline. The
# seed once gave every article the same template, which made every demo article
# a near-total copy of every other.


# ---- countries -------------------------------------------------------------- #
#
# What each demo headline above is about. Keyed by title, not index, so the same
# map tags the live database, whose older seed repeated headlines with "(2)" and
# "(3)" suffixes. None = international.
COUNTRY_OF_HEADLINE = {
    "Parliament passes revised data protection framework": "AU",
    "Regional startups raise record funding despite slowdown": "SG",
    "New study links urban green space to lower stress markers": "GB",
    "Grid operators report record renewable share in Q3": "AU",
    "Semiconductor shortage eases as new fabrication capacity opens": "JP",
    "Public transport ridership returns to pre-pandemic levels": "NZ",
    "Researchers publish open dataset on coastal erosion": "AU",
    "Health ministry expands subsidised screening programme": "SG",
    "Local league announces revised season structure": "AU",
    "Central bank holds rates steady for third quarter": "NZ",
    "Universities pilot shared research computing cluster": "GB",
    "Coastal reclamation project clears environmental review": "SG",
    "Retail sector reports uneven recovery across segments": "US",
    "New guidelines issued for clinical trial transparency": "GB",
    "Wind capacity overtakes coal in regional generation mix": "AU",
    "Small businesses adopt digital payments at record pace": "JP",
    "Air quality index improves after emissions rules tighten": "JP",
    "National team qualifies after decisive away fixture": "NZ",
    "Cabinet reshuffle brings three new ministers into portfolio roles": "GB",
    "Electoral boundaries review opens for public submissions": "AU",
    "Freedom of information requests rise for a fourth year": "NZ",
    "Cross-border tax agreement enters its ratification stage": None,
    "Housing grant changes take effect for first-time buyers": "AU",
    "Container throughput steadies after a volatile first half": "SG",
    "Insurance premiums climb as claims from flooding mount": "AU",
    "Two regional carriers confirm merger talks": "US",
    "Manufacturing output edges up on export orders": "JP",
    "Sovereign fund reports a narrower annual return": "SG",
    "Undersea cable landing adds regional bandwidth capacity": "AU",
    "Open-source licence change splits a developer community": None,
    "Data centre operators pledge water use disclosure": "US",
    "Payment outage prompts review of settlement redundancy": "GB",
    "Rail signalling upgrade completes ahead of schedule": "GB",
    "Deep-sea survey records twelve previously undescribed species": "NZ",
    "Long-running soil study finds nutrient decline levelling off": "AU",
    "Observatory upgrade sharpens gravitational wave detection": "US",
    "Peer review trial publishes referee reports alongside papers": None,
    "Antibiotic resistance surveillance widens to private clinics": "SG",
    "Waiting times shorten at restructured outpatient units": "GB",
    "Vaccine coverage holds steady after a schedule change": "NZ",
    "Mental health helpline reports sustained demand": "AU",
    "Stadium redevelopment pushes two fixtures to a neutral ground": "GB",
    "Youth academy funding tied to coaching accreditation": "AU",
    "Athletics body adopts revised qualification standards": None,
    "Swimming records fall at the regional championships": "AU",
    "Mangrove replanting reaches its five-year target early": "SG",
    "Fishing quota cut follows a lower stock assessment": "NZ",
    "Heat advisory days double against the decade average": "US",
    "Recycling contamination rates fall after a bin redesign": "JP",
    "Peatland restoration draws cross-border funding": None,
}

# Stories written for one country, so each country page has something that could
# only be about that country. Fictional demo reporting: no real person is named,
# and every source is a real institution's page (demo_sources.py), not a
# document supporting the story.
# (country, section, writer email, title, summary, paragraphs)
COUNTRY_SAMPLES = [
    ("AU", "Politics", "veteran@newsrelease.test",
     "Wollongong council opens consultation on a revised city centre plan",
     "Residents have six weeks to comment on building heights, laneways and parking.",
     ["Wollongong City Council has opened public consultation on a revised plan for "
      "the city centre, covering building heights, laneway activation and parking.",
      "The draft keeps the tallest buildings near the station and steps heights down "
      "toward the foreshore. Submissions close in six weeks, with drop-in sessions "
      "planned at the central library.",
      "Business groups welcomed the laneway proposals. Some residents questioned "
      "whether parking forecasts reflect growth in the northern suburbs."]),
    ("AU", "Environment", "contributor@newsrelease.test",
     "Illawarra escarpment walking tracks reopen after landslip repairs",
     "Three tracks closed since the winter storms are open again, with new drainage.",
     ["Three walking tracks on the Illawarra escarpment have reopened after repairs to "
      "sections damaged by landslips during the winter storms.",
      "Crews rebuilt stairways and added drainage designed to carry heavy rain off the "
      "track surface rather than along it. Rangers ask walkers to stay on marked "
      "paths while vegetation re-establishes.",
      "One lookout remains closed while engineers monitor the slope beneath it."]),
    ("AU", "Sport", "newcontributor@newsrelease.test",
     "Wollongong prepares to host a regional surf life saving carnival",
     "More than forty clubs are expected on the northern beaches next month.",
     ["Wollongong will host a regional surf life saving carnival next month, with more "
      "than forty clubs expected across two northern beaches.",
      "Organisers say the event runs over a weekend, with junior events on the first "
      "day. Road closures near the beaches will be signposted in advance."]),
    ("AU", "Business", "veteran@newsrelease.test",
     "Port Kembla precinct courts renewable manufacturing investors",
     "A new prospectus pitches the precinct's port, rail links and skilled workforce.",
     ["A prospectus released this week pitches the Port Kembla industrial precinct to "
      "manufacturers of wind turbine components and other renewable equipment.",
      "It points to existing deep-water berths, rail links and a workforce with heavy "
      "industry experience. Local training providers have been asked to map courses "
      "against the skills manufacturers say they need.",
      "No firm commitments have been announced. Analysts say grid connection costs "
      "will weigh heavily on any final decision."]),
    ("AU", "Science", "contributor@newsrelease.test",
     "University researchers map seagrass recovery along the Illawarra coast",
     "Drone surveys show meadows returning in sheltered bays, but not on open coast.",
     ["Researchers have published drone surveys mapping seagrass along the Illawarra "
      "coast, showing recovery in sheltered bays over five years.",
      "Meadows on exposed stretches have not returned, which the team attributes to "
      "storm disturbance and sediment. The maps and raw imagery are published for "
      "other researchers to reuse."]),

    ("NZ", "Environment", "veteran@newsrelease.test",
     "New Zealand extends predator trapping network across two more regions",
     "The expansion adds thousands of traps and links community projects to one register.",
     ["New Zealand's predator-free programme is extending its trapping network across "
      "two more regions, adding thousands of traps maintained by community groups.",
      "Catch data from every trap will be recorded on a single national register, so "
      "results can be compared between regions for the first time.",
      "Conservation groups say volunteer numbers, not funding, are now the main limit."]),
    ("NZ", "Business", "contributor@newsrelease.test",
     "Dairy export prices lift as New Zealand co-operatives report stronger orders",
     "Whole milk powder led the rise at the latest auction.",
     ["Dairy export prices rose at the latest global auction, led by whole milk powder, "
      "as New Zealand co-operatives reported stronger forward orders.",
      "Economists cautioned that one auction is a thin basis for revising farm income "
      "forecasts, and noted the currency has also moved."]),
    ("NZ", "Sport", "newcontributor@newsrelease.test",
     "Wellington club confirms stadium upgrade ahead of the rugby season",
     "New lighting and a covered stand are due before the first home fixture.",
     ["A Wellington rugby club has confirmed upgrades to its home ground, including new "
      "lighting and a covered stand, due before the first home fixture.",
      "The club says the work is funded through a mix of council grants and member "
      "contributions."]),

    ("SG", "Technology", "contributor@newsrelease.test",
     "Singapore expands public trials of autonomous shuttle buses",
     "Driverless shuttles will run on two more routes, with a safety operator on board.",
     ["Singapore is expanding public trials of autonomous shuttle buses to two more "
      "routes, each with a safety operator on board during the trial.",
      "Operators will publish monthly figures on disengagements, the moments a human "
      "takes control, so the public can follow how the vehicles perform.",
      "Commuters on the existing trial route have used the service steadily since launch."]),
    ("SG", "Health", "veteran@newsrelease.test",
     "Singapore clinics pilot shared electronic records for chronic care",
     "Patients with diabetes and hypertension will have one record across clinics.",
     ["Clinics in Singapore are piloting a shared electronic record for patients with "
      "chronic conditions such as diabetes and hypertension.",
      "Patients must consent before their record is shared, and can see which clinics "
      "have accessed it. The pilot will be evaluated on missed follow-ups and "
      "duplicated tests.",
      "Privacy advocates asked for the evaluation to be published in full."]),
    ("SG", "Business", "veteran@newsrelease.test",
     "Singapore port handles record transhipment volumes this quarter",
     "Rerouted shipping and new berths pushed container handling to a quarterly high.",
     ["Singapore's port handled record transhipment volumes this quarter, as rerouted "
      "shipping lanes and newly opened berths lifted container throughput.",
      "Port authorities said automated cranes at the newest terminal accounted for a "
      "growing share of moves. Shipping analysts expect volumes to ease if routes "
      "normalise."]),

    ("JP", "Technology", "contributor@newsrelease.test",
     "Japanese carmakers agree a shared battery recycling standard",
     "A common labelling and dismantling standard aims to make recovery cheaper.",
     ["Several Japanese carmakers have agreed a shared standard for labelling and "
      "dismantling electric vehicle batteries, aimed at making recycling cheaper.",
      "Recyclers have long said inconsistent battery designs are the main cost. The "
      "standard covers labelling of cell chemistry and the placement of fasteners.",
      "It applies to new models from the next design cycle."]),
    ("JP", "Science", "veteran@newsrelease.test",
     "Japan's earthquake early warning network adds offshore sensors",
     "Seafloor sensors could add several seconds of warning for coastal areas.",
     ["Japan's earthquake early warning network is adding a line of seafloor sensors, "
      "which researchers say could give coastal areas several extra seconds of warning.",
      "The sensors detect shaking before it reaches land-based stations. Data will be "
      "made available to universities studying offshore fault behaviour."]),
    ("JP", "Health", "newcontributor@newsrelease.test",
     "Tokyo hospitals trial robotic lifting assistance in elderly care wards",
     "The trial measures staff injuries and patient comfort over twelve months.",
     ["Hospitals in Tokyo are trialling robotic lifting assistance in elderly care wards, "
      "to reduce back injuries among nursing staff.",
      "The twelve-month trial will measure staff injuries, time spent on transfers and "
      "patient comfort."]),

    ("GB", "Politics", "veteran@newsrelease.test",
     "UK councils gain new powers to convert empty shops into housing",
     "Councils can require long-vacant high street units to be offered for conversion.",
     ["Councils in the UK are gaining powers to require long-vacant high street shops to "
      "be offered for conversion into housing.",
      "Owners will be notified before any requirement takes effect and can appeal. "
      "Councils say the powers will be used sparingly, for units empty over a year.",
      "Retail groups warned the measure should not replace support for struggling "
      "high streets."]),
    ("GB", "Environment", "contributor@newsrelease.test",
     "UK water companies ordered to publish sewage overflow data daily",
     "Overflow data will be published daily for every monitored outlet.",
     ["Water companies in the UK have been ordered to publish sewage overflow data "
      "daily for every monitored outlet, replacing annual summaries.",
      "Campaigners say daily data will let swimmers and anglers check conditions before "
      "going into the water. Companies say monitors need calibrating first."]),
    ("GB", "Science", "veteran@newsrelease.test",
     "UK polar researchers retrieve their deepest ice core yet",
     "The core could extend the climate record back hundreds of thousands of years.",
     ["UK polar researchers have retrieved their deepest ice core yet, which could "
      "extend the climate record back hundreds of thousands of years.",
      "Sections will be shipped frozen for analysis of trapped air bubbles. First "
      "results are not expected for at least a year."]),

    ("US", "Technology", "contributor@newsrelease.test",
     "US states agree a common framework for data broker registration",
     "A shared registry would let residents find which brokers hold their data.",
     ["A group of US states has agreed a common framework for registering data brokers, "
      "which would let residents find which brokers hold their personal information.",
      "Each state will still set its own penalties. Privacy groups called it a useful "
      "first step; industry groups asked for a single national rule instead.",
      "The shared registry is expected to open next year."]),
    ("US", "Business", "veteran@newsrelease.test",
     "US airlines add capacity on transpacific routes to Australia",
     "More seats from the West Coast are expected to push fares down for the summer.",
     ["US airlines are adding capacity on transpacific routes to Australia, with extra "
      "services from West Coast hubs scheduled for the southern summer.",
      "Travel analysts expect fares to soften as seat numbers rise, though fuel costs "
      "remain the largest uncertainty."]),
    ("US", "Sport", "newcontributor@newsrelease.test",
     "US college sport adopts new athlete revenue-sharing rules",
     "Universities can now share part of their broadcast revenue directly with athletes.",
     ["New rules in US college sport allow universities to share a portion of broadcast "
      "revenue directly with athletes, starting this season.",
      "Smaller programmes say the change favours schools with large television deals."]),
    ("US", "Environment", "veteran@newsrelease.test",
     "US coastal cities publish shared flood maps for the first time",
     "A common mapping standard lets residents compare flood risk street by street.",
     ["A group of US coastal cities has published flood risk maps built to a shared "
      "standard, so residents can compare risk street by street across city lines.",
      "The maps combine tide gauge records with rainfall projections. Planners say the "
      "common format will make it easier to prioritise drainage upgrades.",
      "Property groups asked for an appeals process where maps differ from surveys."]),
    ("US", "Health", "contributor@newsrelease.test",
     "US rural hospitals expand telehealth links to specialist centres",
     "Video consultations aim to cut long drives for cardiology and neurology visits.",
     ["Rural hospitals in several US states are expanding telehealth links to "
      "specialist centres, starting with cardiology and neurology consultations.",
      "Patients will attend their local hospital, where a nurse joins the video call. "
      "Hospitals will report how many in-person transfers the links avoid."]),
]



def seed_countries() -> None:
    """Tag demo articles with countries and add the country sample articles.

    Safe to run more than once, and on a database that is already seeded (the
    live one): an article that already has a country keeps it, and a sample
    whose title already exists is skipped.
    """
    import re
    from sqlalchemy import func

    tagged = 0
    for article in Article.query.filter(Article.country_code.is_(None)).all():
        code = COUNTRY_OF_HEADLINE.get(re.sub(r" \(\d+\)$", "", article.title))
        if code:
            article.country_code = code
            tagged += 1

    sections = {c.name: c for c in Category.query.filter_by(deleted_at=None)}
    people = {u.email: u for u in User.query.filter(User.deleted_at.is_(None))}
    admin = people["admin@newsrelease.test"]
    # Each sample is approved by the editor who covers its section.
    editor_for: dict[int, int] = {}
    for row in EditorCategory.query.order_by(EditorCategory.id):
        editor_for.setdefault(row.category_id, row.editor_id)

    now = utcnow()
    added = 0
    writers = set()
    for n, (code, section, email, title, summary, paragraphs) in enumerate(COUNTRY_SAMPLES):
        if Article.query.filter_by(title=title).first():
            continue
        writer = people[email]
        category = sections[section]
        published_at = now - timedelta(days=n + 1, hours=(n * 5) % 20)
        article = Article(
            contributor_id=writer.id,
            category_id=category.id,
            country_code=code,
            title=title,
            slug=slugify(title),
            summary=summary,
            body=body_for(title, paragraphs),
            tags="regional,analysis",
            status=ArticleStatus.PUBLISHED,
            published_at=published_at,
            submitted_at=published_at - timedelta(hours=6),
            reviewed_by_id=editor_for.get(category.id, admin.id),
            view_count=150 + (n * 97) % 1800,
        )
        db.session.add(article)
        db.session.flush()
        article.slug = slugify(title, article.id)
        for url, label in sources_for(title, code, section, email):
            db.session.add(ArticleSource(article_id=article.id, url=url, label=label))
        writers.add(writer)
        added += 1

    db.session.flush()
    for writer in writers:
        rescore_contributor_articles(writer)
    db.session.commit()

    print(f"Countries: tagged {tagged} existing article(s), added {added} sample(s).")
    rows = (
        db.session.query(Article.country_code, func.count())
        .filter(Article.status == ArticleStatus.PUBLISHED)
        .group_by(Article.country_code)
        .all()
    )
    for code, count in sorted(rows, key=lambda r: -r[1]):
        print(f"  {code or 'international':<14} {count} published")


def seed_expansion() -> None:
    """More editors, writers and articles, and every demo article in the right section.

    Safe to run again and on the live database: accounts and articles that
    already exist are left as they are; an article is only moved when it is in
    the wrong section. Sources for moved and new articles are rated (this needs
    internet access) and every score is recalculated.
    """
    import demo_expansion as more
    from demo_bodies import render
    from app.models import EditorCategory
    from app.originality_service import index_article
    from app.source_service import rate_sources

    sections = {c.name: c for c in Category.query.filter_by(deleted_at=None)}
    now = utcnow()

    def account(email, name, role, **extra):
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email, display_name=name, role=role,
                        password_hash=hash_password(DEMO_PASSWORD), **extra)
            db.session.add(user)
            db.session.flush()
        return user

    for e in more.NEW_EDITORS:
        editor = account(e["email"], e["name"], Role.EDITOR, bio=e["bio"],
                         editor_title=e["title"], editor_credentials=e["credentials"])
        for name in e["sections"]:
            if not EditorCategory.query.filter_by(editor_id=editor.id,
                                                  category_id=sections[name].id).first():
                db.session.add(EditorCategory(editor_id=editor.id, category_id=sections[name].id))
    for w in more.NEW_WRITERS:
        account(w["email"], w["name"], Role.VERIFIED_CONTRIBUTOR, bio=w["bio"])
    db.session.flush()

    touched = []

    def resource(article, section_name):
        ArticleSource.query.filter_by(article_id=article.id).delete()
        for url, label in sources_for(article.title, article.country_code, section_name,
                                      article.contributor.email):
            db.session.add(ArticleSource(article_id=article.id, url=url, label=label))

    moved = 0
    for title, section_name in more.SECTION_FIX.items():
        for article in Article.query.filter_by(title=title):
            if article.category_id != sections[section_name].id:
                article.category_id = sections[section_name].id
                resource(article, section_name)
                touched.append(article)
                moved += 1

    added = 0
    for n, (code, section_name, email, title, standfirst, paragraphs) in enumerate(more.NEW_ARTICLES):
        if Article.query.filter_by(title=title).first():
            continue
        writer = User.query.filter_by(email=email).one()
        published_at = now - timedelta(days=1 + (n * 37) % 22, hours=(n * 7) % 18)
        article = Article(
            contributor_id=writer.id, category_id=sections[section_name].id, country_code=code,
            title=title, slug=slugify(title), summary=standfirst, body=render(paragraphs),
            tags="regional,analysis", status=ArticleStatus.PUBLISHED,
            published_at=published_at, submitted_at=published_at - timedelta(hours=5),
            view_count=140 + (n * 131) % 1500,
        )
        db.session.add(article)
        db.session.flush()
        article.slug = slugify(title, article.id)
        resource(article, section_name)
        touched.append(article)
        added += 1
    db.session.flush()

    # Each published demo article is approved by an editor of its own section.
    editors_of: dict[int, list[int]] = {}
    for row in EditorCategory.query.order_by(EditorCategory.editor_id):
        editors_of.setdefault(row.category_id, []).append(row.editor_id)
    for article in Article.query.filter(Article.status == ArticleStatus.PUBLISHED,
                                        Article.republication.is_(None)):
        editors = editors_of.get(article.category_id)
        if editors and article.reviewed_by_id not in editors and not article.awaiting_review:
            article.reviewed_by_id = editors[article.id % len(editors)]

    for article in touched:
        db.session.expire(article, ["sources"])
        rate_sources(article)
        index_article(article)
    db.session.flush()
    for writer in User.query.filter(User.role.in_([Role.VERIFIED_CONTRIBUTOR, Role.EDITOR,
                                                    Role.SYSTEM_ADMIN])):
        rescore_contributor_articles(writer)
    db.session.commit()
    seed_daily_views()
    print(f"Expansion: {len(more.NEW_EDITORS)} editors and {len(more.NEW_WRITERS)} writers ready; "
          f"moved {moved} article(s) to their right section; added {added} article(s).")


def seed_more() -> None:
    """Ten more published articles for every country (demo_more/).

    Safe to run again and on the live database: an article whose title already
    exists is skipped. Each new article is approved by an editor of its own
    section, its sources are rated (this needs internet access), and its
    writer's scores are recalculated.
    """
    from demo_bodies import render
    from demo_more import ARTICLES
    from app.originality_service import index_article
    from app.source_service import rate_sources

    sections = {c.name: c for c in Category.query.filter_by(deleted_at=None)}
    editors_of: dict[int, list[int]] = {}
    for row in EditorCategory.query.order_by(EditorCategory.editor_id):
        editors_of.setdefault(row.category_id, []).append(row.editor_id)
    admin = User.query.filter_by(email="admin@newsrelease.test").one()
    now = utcnow()

    added, writers = [], set()
    for n, (code, section_name, email, title, standfirst, paragraphs) in enumerate(ARTICLES):
        if Article.query.filter_by(title=title).first():
            continue
        writer = User.query.filter_by(email=email).one()
        category = sections[section_name]
        # Spread over the last eight weeks so every page mixes old and new.
        published_at = now - timedelta(days=1 + (n * 23) % 56, hours=(n * 7) % 18)
        editors = editors_of.get(category.id) or [admin.id]
        article = Article(
            contributor_id=writer.id, category_id=category.id, country_code=code,
            title=title, slug=slugify(title), summary=standfirst, body=render(paragraphs),
            tags="regional,analysis", status=ArticleStatus.PUBLISHED,
            published_at=published_at, submitted_at=published_at - timedelta(hours=5),
            reviewed_by_id=editors[n % len(editors)],
            view_count=120 + (n * 149) % 1700,
        )
        db.session.add(article)
        db.session.flush()
        article.slug = slugify(title, article.id)
        for url, label in sources_for(title, code, section_name, email):
            db.session.add(ArticleSource(article_id=article.id, url=url, label=label))
        added.append(article)
        writers.add(writer)
    db.session.flush()

    for article in added:
        db.session.expire(article, ["sources"])
        rate_sources(article)
        index_article(article)
    db.session.flush()
    for writer in writers:
        rescore_contributor_articles(writer)
    db.session.commit()
    seed_daily_views()
    print(f"More: added {len(added)} of {len(ARTICLES)} article(s).")


def translation_problems(article, tr: dict) -> list[str]:
    """Why a stored translation does not line up with its English, if it does not."""
    from app.insights import paragraphs
    from app.translation_service import english_points

    english = paragraphs(article.body)
    problems = []
    if len(tr["paragraphs"]) != len(english):
        problems.append(f"{len(tr['paragraphs'])} paragraphs for {len(english)} in English")
    else:
        for i, (para, mine) in enumerate(zip(english, tr["paragraphs"])):
            if para.heading != mine.startswith("## "):
                problems.append(f"paragraph {i + 1}: subheading in one language only")
    wanted = len(english_points(article))
    if len(tr.get("points") or []) != wanted:
        problems.append(f"{len(tr.get('points') or [])} key points for {wanted} in English")
    return problems


def seed_translations() -> None:
    """Store the demo articles' Mandarin and Malay translations (demo_translations/).

    Each is checked against the article's current English first, and stored
    with a fingerprint of that English, so a later edit marks it stale. Safe to
    run again: existing translations are replaced.
    """
    import json
    import demo_translations
    from demo_bodies import render
    from app.models import ArticleTranslation
    from app.translation_service import source_hash

    stored, skipped = 0, []
    for lang in ("zh", "ms"):
        for title, tr in demo_translations.load(lang).items():
            article = Article.query.filter_by(title=title).first()
            if article is None:
                skipped.append(f"{lang}: no article '{title[:50]}'")
                continue
            problems = translation_problems(article, tr)
            if problems:
                skipped.append(f"{lang}: '{title[:50]}': {'; '.join(problems)}")
                continue
            ArticleTranslation.query.filter_by(article_id=article.id, lang=lang).delete()
            db.session.add(ArticleTranslation(
                article_id=article.id, lang=lang, title=tr["title"], summary=tr["summary"],
                body=render(tr["paragraphs"]), points=json.dumps(tr.get("points") or [], ensure_ascii=False),
                provider="ai", source_hash=source_hash(article.title, article.summary, article.body),
            ))
            stored += 1
    db.session.commit()
    print(f"Translations: stored {stored}.")
    for line in skipped:
        print("  skipped", line)


def seed_daily_views() -> None:
    """Give each demo article a history of daily views behind its total.

    Demo data only. The seeded view counts are themselves made up, so this
    spreads each article's existing total over the days since it was published
    (at most six weeks), most of it early and tailing off, as reading usually
    does, with a little day-to-day variation. Real views are recorded day by
    day from now on. Articles that already have a history are left alone, so
    it is safe to run again.
    """
    import math
    from datetime import timedelta
    from app.models import ArticleDailyView

    today = utcnow().date()
    filled = 0
    for article in Article.query.filter(Article.status == ArticleStatus.PUBLISHED):
        if ArticleDailyView.query.filter_by(article_id=article.id).first():
            continue
        if not article.published_at or not article.view_count:
            continue
        start = max(article.published_at.date(), today - timedelta(days=41))
        days = (today - start).days + 1
        rng = random.Random(article.id)
        weights = [math.exp(-d / 6) * (0.75 + rng.random() * 0.5) for d in range(days)]
        total = sum(weights)
        counts = [int(article.view_count * w / total) for w in weights]
        counts[0] += article.view_count - sum(counts)
        for d, n in enumerate(counts):
            if n:
                db.session.add(ArticleDailyView(article_id=article.id, day=start + timedelta(d), views=n))
        filled += 1
    db.session.commit()
    print(f"Daily views: gave {filled} article(s) a history.")


def seed_long_bodies() -> None:
    """Swap the short demo bodies on an existing database for the long ones.

    Safe to run more than once and on the live database: only demo articles
    whose body differs from the long version change, republished articles are
    never touched, and the originality index and pending checks are refreshed.
    """
    import re
    from demo_bodies import LONG
    from app.originality_service import check, index_article
    from app.scoring_service import load_settings

    changed = []
    summaries = 0
    for article in Article.query.filter(Article.republication.is_(None)):
        title = re.sub(r" \(\d+\)$", "", article.title)
        # The first demo headlines were seeded with a placeholder summary that
        # only repeated the headline; give them their real standfirst.
        if title in STANDFIRSTS and "What the change means" in (article.summary or ""):
            article.summary = STANDFIRSTS[title]
            summaries += 1
        if title in LONG:
            body = body_for(title)
            if article.body != body:
                article.body = body
                changed.append(article)
    db.session.flush()
    for article in changed:
        index_article(article)
    db.session.flush()

    settings = load_settings()
    for article in Article.query.filter_by(status=ArticleStatus.PENDING):
        report = check(article, settings=settings)
        print(f"  checked {report['percent']:5.1f}% {report['level']:<10} {article.title[:60]}")
    db.session.commit()
    print(f"Long bodies: rewrote {len(changed)} article(s) and {summaries} summaries.")


# ---- originality ------------------------------------------------------------ #
#
# One pending submission that copies an existing article and part of a real
# cited page, so the review queue has a genuine case to show. It also quotes the
# same page correctly, which the check reports as a verified quote rather than
# copying.
PLANTED_COPY = {
    "title": "New privacy rules give Australians the right to erase their data",
    "summary": "What the revised privacy framework means for households.",
    "source": ("https://en.wikipedia.org/wiki/Privacy_Act_1988", "Privacy Act 1988, Wikipedia"),
    "paragraphs": [
        # Copied from "Parliament passes revised data protection framework".
        "Federal parliament has passed a revised privacy framework that gives individuals a "
        "statutory right to ask organisations to delete personal information they no longer "
        "need. Businesses with annual turnover above the small business threshold will have "
        "eighteen months to update their handling practices.",
        # Copied from the cited page without quotation marks.
        "The principles govern when and how personal information can be collected by these "
        "entities. Information can only be collected if it is relevant to the agencies' "
        "functions.",
        # Quoted from the cited page, correctly.
        "As the legislation already provides, “Australians have the right to know why "
        "information about them is being acquired and who will see the information.”",
        "Consumer advocates in the Illawarra said they would run sessions at local libraries "
        "to explain the new rights to older residents.",
    ],
}


def seed_originality() -> None:
    """Give demo articles distinct text, build the index, and plant one copy.

    Safe to run more than once and on the live database: only bodies still
    carrying the old shared template are rewritten, and the planted article is
    added once. Pending articles are checked so the review queue shows results.
    """
    from app.originality_service import check, index_article
    from app.scoring_service import load_settings

    rewritten = 0
    for article in Article.query.all():
        if "The change follows a period of consultation" in (article.body or ""):
            if article.title in dict.fromkeys(HEADLINES):
                article.body = body_for(article.title)
                rewritten += 1

    if not Article.query.filter_by(title=PLANTED_COPY["title"]).first():
        writer = User.query.filter_by(email="newcontributor@newsrelease.test").one()
        politics = Category.query.filter_by(name="Politics").one()
        now = utcnow()
        copy = Article(
            contributor_id=writer.id,
            category_id=politics.id,
            country_code="AU",
            title=PLANTED_COPY["title"],
            slug=slugify(PLANTED_COPY["title"]),
            summary=PLANTED_COPY["summary"],
            body="".join(f"<p>{p}</p>" for p in PLANTED_COPY["paragraphs"]),
            tags="privacy,policy",
            status=ArticleStatus.PENDING,
            submitted_at=now - timedelta(hours=3),
        )
        db.session.add(copy)
        db.session.flush()
        copy.slug = slugify(copy.title, copy.id)
        url, label = PLANTED_COPY["source"]
        db.session.add(ArticleSource(article_id=copy.id, url=url, label=label))

    db.session.flush()
    articles = Article.query.all()
    for article in articles:
        index_article(article)
    db.session.flush()

    settings = load_settings()
    checked = []
    for article in Article.query.filter_by(status=ArticleStatus.PENDING):
        report = check(article, settings=settings)
        checked.append((article.title, report["percent"], report["level"]))
    db.session.commit()

    print(f"Originality: rewrote {rewritten} template bodies, indexed {len(articles)} articles.")
    for title, percent, level in checked:
        print(f"  pending {percent:5.1f}% {level:<12} {title}")


def reset() -> None:
    """Empty every table, keeping the schema and the Alembic revision intact.

    Deliberately not drop_all()/create_all(): that rebuilds tables from the
    models and leaves the alembic_version row pointing at a revision that was
    never applied to what is actually there. Migrations own the schema.
    """
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()


def seed() -> None:
    if User.query.first():
        print("Database already contains data. Re-run with --reset to rebuild.")
        return

    random.seed(20260903)  # deterministic demo -- the same data every run
    now = utcnow()

    # ---- categories ------------------------------------------------------- #
    categories = []
    for name, description, is_system in CATEGORIES:
        category = Category(
            name=name, slug=slugify(name), description=description, is_system=is_system
        )
        db.session.add(category)
        categories.append(category)
    db.session.flush()

    real_categories = [c for c in categories if not c.is_system]

    # ---- accounts --------------------------------------------------------- #
    def make_user(email, name, role, bio=None):
        user = User(
            email=email,
            display_name=name,
            password_hash=hash_password(DEMO_PASSWORD),
            role=role,
            bio=bio,
            email_verified_at=now,
        )
        db.session.add(user)
        return user

    admin = make_user("admin@newsrelease.test", "Platform Administrator", Role.SYSTEM_ADMIN)
    editor_a = make_user("editor.tech@newsrelease.test", "Priya Raman", Role.EDITOR)
    editor_b = make_user("editor.politics@newsrelease.test", "Daniel Ong", Role.EDITOR)
    # Placeholder panel details for the demo. Fictional people, generic
    # experience, no real publication named.
    editor_a.editor_title = "Technology and Science Editor"
    editor_a.editor_credentials = (
        "Nine years on a regional daily's science desk. Degree in computer science."
    )
    editor_b.editor_title = "Politics and Business Editor"
    editor_b.editor_credentials = (
        "Former parliamentary reporter. Eleven years covering state and federal politics."
    )

    veteran = make_user(
        "veteran@newsrelease.test", "Marcus Lim", Role.VERIFIED_CONTRIBUTOR,
        "Twelve years covering regional policy.",
    )
    mixed = make_user(
        "contributor@newsrelease.test", "Aisha Rahman", Role.VERIFIED_CONTRIBUTOR,
        "Technology and business reporting.",
    )
    newcomer = make_user(
        "newcontributor@newsrelease.test", "Sam Tan", Role.VERIFIED_CONTRIBUTOR,
        "Recently approved contributor.",
    )

    reader = make_user("reader@newsrelease.test", "Free Reader", Role.FREE_REGISTERED)
    premium = make_user("premium@newsrelease.test", "Premium Reader", Role.PREMIUM_REGISTERED)
    db.session.flush()

    # Editors are scoped to categories (PRD 1.3.2).
    by_name = {c.name: c for c in categories}
    db.session.add(EditorCategory(editor_id=editor_a.id, category_id=by_name["Technology"].id))
    db.session.add(EditorCategory(editor_id=editor_a.id, category_id=by_name["Science"].id))
    db.session.add(EditorCategory(editor_id=editor_b.id, category_id=by_name["Politics"].id))
    db.session.add(EditorCategory(editor_id=editor_b.id, category_id=by_name["Business"].id))

    for category in real_categories[:3]:
        db.session.add(
            UserCategoryPreference(user_id=reader.id, category_id=category.id)
        )
    db.session.add(Follow(follower_id=reader.id, contributor_id=veteran.id))
    db.session.add(Follow(follower_id=premium.id, contributor_id=mixed.id))

    db.session.add(
        Subscription(
            subscriber_id=premium.id,
            contributor_id=mixed.id,
            price_cents=500,
            period_start=now - timedelta(days=3),
            period_end=now + timedelta(days=27),
            status=SubscriptionStatus.ACTIVE,
            gateway_ref="stub_seed",
        )
    )
    db.session.flush()

    # ---- articles --------------------------------------------------------- #
    contributors = [veteran, mixed, newcomer]
    articles: list[Article] = []

    for index in range(ARTICLE_COUNT):
        contributor = contributors[index % 3]
        headline = f"{HEADLINES[index % len(HEADLINES)]}"
        if index >= len(HEADLINES):
            headline = f"{headline} ({index // len(HEADLINES) + 1})"

        category = real_categories[index % len(real_categories)]
        published_at = now - timedelta(days=index, hours=random.randint(0, 20))

        # A few drafts and pending submissions so the dashboards and review queue
        # are not empty either.
        if index >= 46:
            status = ArticleStatus.PENDING
            published_at = None
        elif index == 45:
            status = ArticleStatus.DRAFT
            published_at = None
        else:
            status = ArticleStatus.PUBLISHED

        article = Article(
            contributor_id=contributor.id,
            category_id=category.id,
            title=headline,
            slug=slugify(headline, index + 1),
            summary=STANDFIRSTS.get(headline, f"{headline}. What the change means and who it affects."),
            body=body_for(headline),
            tags=",".join(random.sample(
                ["policy", "analysis", "explainer", "data", "regional", "industry"], 3
            )),
            status=status,
            published_at=published_at,
            submitted_at=published_at or now,
            # Approved by the editor who covers the section, so the "Approved
            # by" line agrees with the assignments above.
            reviewed_by_id=(
                {"Technology": editor_a, "Science": editor_a,
                 "Politics": editor_b, "Business": editor_b}.get(category.name, admin).id
                if status == ArticleStatus.PUBLISHED else None
            ),
            is_premium=(index % 7 == 0),
            view_count=random.randint(40, 4000),
        )
        db.session.add(article)
        articles.append(article)
    db.session.flush()

    # ---- scoring inputs --------------------------------------------------- #
    for index, article in enumerate(articles):
        # Marcus sources heavily, Sam barely at all, so their scores differ for
        # a reason a reader can inspect. Real institutions and outlets
        # (demo_sources.py); `flask rate-sources` grades them after seeding.
        email = {veteran.id: veteran.email, mixed.id: mixed.email,
                 newcomer.id: newcomer.email}[article.contributor_id]
        section = next(c.name for c in categories if c.id == article.category_id)
        for url, label in sources_for(article.title, COUNTRY_OF_HEADLINE.get(article.title),
                                      section, email):
            db.session.add(ArticleSource(article_id=article.id, url=url, label=label))

    published = [a for a in articles if a.status == ArticleStatus.PUBLISHED]

    # Two corrections and one retraction against Aisha, so accuracy is not 100%.
    for article in [a for a in published if a.contributor_id == mixed.id][:2]:
        db.session.add(
            Correction(
                article_id=article.id,
                issued_by_id=editor_a.id,
                correction_type=CorrectionType.CORRECTION,
                reason="Figure in paragraph four corrected after publisher clarification.",
            )
        )

    retracted = [a for a in published if a.contributor_id == newcomer.id][0]
    retracted.status = ArticleStatus.RETRACTED
    db.session.add(
        Correction(
            article_id=retracted.id,
            issued_by_id=editor_b.id,
            correction_type=CorrectionType.RETRACTION,
            reason="Central claim could not be substantiated by the cited sources.",
        )
    )

    # Engagement, and enough reports on one article to reach the moderation queue.
    flagged = published[3]
    for n in range(12):
        filler = make_user(
            f"reporter{n}@newsrelease.test", f"Reader {n + 1}", Role.FREE_REGISTERED
        )
        db.session.flush()
        db.session.add(
            Report(
                article_id=flagged.id,
                reporter_id=filler.id,
                reason="The quoted figure does not match the linked source.",
                status=ReportStatus.OPEN,
            )
        )

    for article in published[:20]:
        for liker in (reader, premium):
            db.session.add(Like(article_id=article.id, user_id=liker.id))
            article.like_count += 1
        db.session.add(
            Comment(
                article_id=article.id,
                user_id=reader.id,
                body="Useful summary. Are the underlying figures published anywhere?",
            )
        )

    db.session.flush()

    # ---- scores ----------------------------------------------------------- #
    for contributor in contributors:
        rescore_contributor_articles(contributor)

    db.session.commit()
    seed_countries()
    seed_originality()
    seed_daily_views()

    print("Seeded.")
    print(f"  categories   {len(categories)}")
    print(f"  users        {User.query.count()}")
    print(f"  articles     {Article.query.count()} ({len(published)} published)")
    print()
    print(f"  All accounts use the password: {DEMO_PASSWORD}")
    for user in (admin, editor_a, veteran, mixed, newcomer, reader, premium):
        accuracy = "New Contributor" if user.accuracy_rate is None else f"{user.accuracy_rate}%"
        print(f"  {user.role.value:<22} {user.email:<38} accuracy={accuracy}")


def require_schema() -> None:
    """Refuse to run before migrations have been applied.

    An earlier version called db.create_all() here, which builds tables straight
    from the models without stamping a revision. The database then looks correct
    while Alembic believes it is empty, and the first real migration fails trying
    to create tables that already exist.
    """
    from sqlalchemy import inspect

    if "alembic_version" not in inspect(db.engine).get_table_names():
        raise SystemExit(
            "No schema found in this database.\n\n"
            "Apply the migrations first:\n"
            "    flask db upgrade\n\n"
            "then run this script again."
        )


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        require_schema()
        if "--countries" in sys.argv:
            seed_countries()
            sys.exit(0)
        if "--originality" in sys.argv:
            seed_originality()
            sys.exit(0)
        if "--long-bodies" in sys.argv:
            seed_long_bodies()
            sys.exit(0)
        if "--daily-views" in sys.argv:
            seed_daily_views()
            sys.exit(0)
        if "--expansion" in sys.argv:
            seed_expansion()
            sys.exit(0)
        if "--more" in sys.argv:
            seed_more()
            sys.exit(0)
        if "--translations" in sys.argv:
            seed_translations()
            sys.exit(0)
        if "--reset" in sys.argv:
            reset()
        seed()
