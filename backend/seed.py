"""Demo data.

Every wireframe in the PDD shows a populated platform. An empty demo reads as
broken, so this script builds a plausible one: six accounts covering every role,
eight categories, and ~50 articles with a realistic spread of credibility scores,
corrections, and reports.

    flask db upgrade     # schema first -- migrations own it
    py seed.py           # then load demo data
    py seed.py --reset   # empty the tables and reload

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

BODY = (
    "<p>{lede}</p>"
    "<p>The change follows a period of consultation with affected parties, "
    "including industry representatives, academic reviewers, and members of the "
    "public who submitted feedback during the review window.</p>"
    "<h3>What changes</h3>"
    "<p>Officials confirmed the measures take effect at the start of the next "
    "quarter. Existing arrangements remain valid until then, and no immediate "
    "action is required from those already compliant.</p>"
    "<p>Analysts noted the practical impact will depend on enforcement, which has "
    "historically varied between jurisdictions.</p>"
    "<h3>Reaction</h3>"
    "<p>Responses have been mixed. Supporters point to clearer obligations, while "
    "critics argue the timeline is short for smaller organisations.</p>"
)


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
            summary=f"{headline}. What the change means and who it affects.",
            body=BODY.format(lede=f"{headline}, according to a statement issued this week."),
            tags=",".join(random.sample(
                ["policy", "analysis", "explainer", "data", "regional", "industry"], 3
            )),
            status=status,
            published_at=published_at,
            submitted_at=published_at or now,
            reviewed_by_id=editor_a.id if status == ArticleStatus.PUBLISHED else None,
            is_premium=(index % 7 == 0),
            view_count=random.randint(40, 4000),
        )
        db.session.add(article)
        articles.append(article)
    db.session.flush()

    # ---- scoring inputs --------------------------------------------------- #
    for index, article in enumerate(articles):
        # Marcus sources heavily, Sam barely at all -- so their scores differ for
        # a reason a reader can inspect.
        source_count = {veteran.id: 5, mixed.id: 3, newcomer.id: 1}[article.contributor_id]
        for n in range(source_count):
            db.session.add(
                ArticleSource(
                    article_id=article.id,
                    url=f"https://example.org/source/{article.id}/{n}",
                    label=f"Primary source {n + 1}",
                )
            )

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
        if "--reset" in sys.argv:
            reset()
        seed()
