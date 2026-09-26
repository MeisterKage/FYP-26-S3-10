"""Scheduled jobs, exposed as Flask CLI commands.

Three things happen on a clock rather than on a request:

  * scheduled publication (Figure 5.44)
  * email dispatch within 60 seconds of a trigger (PRD 5.1 Performance)
  * the auto-publish sweep, which only acts when the review queue is overloaded
  * monthly digests, compiled on the first of each month

They run from the CLI:

    flask publish-due
    flask dispatch-notifications
    flask autopublish-backlog
    flask compile-digests          # monthly, on the 1st

For the deployed system, point cron (or the host's scheduler) at these every
minute. Nothing in the application code needs to change to do that.

None of this may run inside a web request. Production serves every request from
a single gunicorn worker, so a sweep over the backlog in a request handler would
stall the whole site for its duration.
"""
from __future__ import annotations

import click
from flask import current_app

from .enums import ArticleStatus
from .extensions import db
from .models import Article, Notification, utcnow


def register_cli(app) -> None:
    @app.cli.command("publish-due")
    def publish_due():
        """Publish every scheduled article whose time has come."""
        now = utcnow()
        due = Article.query.filter(
            Article.status == ArticleStatus.SCHEDULED,
            Article.published_at <= now,
        ).all()

        from .scoring_service import rescore_article

        for article in due:
            article.status = ArticleStatus.PUBLISHED
            rescore_article(article)
            db.session.add(
                Notification(
                    user_id=article.contributor_id,
                    event_type="article.published",
                    title="Your scheduled article is live",
                    body=article.title,
                    link=f"/articles/{article.slug}",
                )
            )

        db.session.commit()
        click.echo(f"Published {len(due)} scheduled article(s).")

    @app.cli.command("dispatch-notifications")
    @click.option("--limit", default=200, help="Maximum notifications to send in one pass.")
    def dispatch_notifications(limit: int):
        """Email queued notifications, honouring each user's toggles."""
        from .modules.notifications import dispatch_pending

        sent = dispatch_pending(limit=limit)
        click.echo(f"Dispatched {sent} notification(s).")

    @app.cli.command("compile-digests")
    @click.option("--month", default=None, help="YYYY-MM. Defaults to last month.")
    @click.option("--force", is_flag=True, help="Recompile editions that already exist.")
    def compile_digests(month, force):
        """Compile the monthly digests and notify subscribers of new editions."""
        from .digest import previous_month
        from .digest_service import compile_month

        month = month or previous_month(utcnow())
        result = compile_month(month, force=force)
        click.echo(
            f"{month}: {len(result['created'])} new edition(s), "
            f"{len(result['recompiled'])} recompiled, {len(result['unchanged'])} unchanged, "
            f"{result['notified']} subscriber notification(s)."
        )
        for key in result["created"]:
            click.echo(f"  new  {key}")

    @app.cli.command("rate-sources")
    @click.option("--all-statuses", is_flag=True, help="Also rate drafts and rejected articles.")
    def rate_all_sources(all_statuses):
        """Rate every cited source (source_rating.py) and rescore the articles.

        Needed once after the source-ratings migration, and whenever the
        Perennial Sources list is refreshed. Fetches each cited page and asks
        Crossref about any DOI, so it takes a while and needs internet access.
        """
        from .source_service import rate_sources
        from .scoring_service import rescore_contributor_articles

        query = Article.query
        if not all_statuses:
            query = query.filter(Article.status.notin_([ArticleStatus.DRAFT,
                                                        ArticleStatus.REJECTED]))
        articles = query.all()
        writers = set()
        tiers: dict[str, int] = {}
        for article in articles:
            for source in rate_sources(article):
                tiers[source.tier] = tiers.get(source.tier, 0) + 1
            writers.add(article.contributor)
        db.session.flush()
        for writer in writers:
            rescore_contributor_articles(writer)
        db.session.commit()
        click.echo(f"Rated the sources of {len(articles)} article(s): "
                   + ", ".join(f"{k} {v}" for k, v in sorted(tiers.items())))

    @app.cli.command("index-originality")
    def index_originality():
        """Rebuild every article's originality fingerprints.

        Needed once after the originality migration, and after any change to
        how text is normalised in app/originality.py.
        """
        from .originality_service import reindex_all

        click.echo(f"Indexed {reindex_all()} article(s).")

    @app.cli.command("prune-images")
    def prune_images():
        """Delete uploaded images never attached to an article within a day."""
        from .modules.images import prune_orphans

        click.echo(f"Removed {prune_orphans()} unattached image(s).")

    @app.cli.command("autopublish-backlog")
    def autopublish_backlog():
        """Publish eligible articles while the review queue is overloaded.

        Does nothing unless an administrator has switched auto-publish on and the
        queue is past the depth or wait threshold. Everything it publishes is
        labelled for readers until an editor confirms it.
        """
        from .review_service import run_autopublish

        result = run_autopublish()
        if not result["open"]:
            click.echo(
                f"Valve closed: {result['queueDepth']} pending, oldest waiting "
                f"{result['oldestWaitHours']}h. Nothing published."
            )
            return

        click.echo(
            f"Valve open: {result['queueDepth']} pending, oldest waiting "
            f"{result['oldestWaitHours']}h. Published {len(result['published'])}, "
            f"held {len(result['held'])} for review."
        )
        for article_id, reasons in result["held"].items():
            click.echo(f"  held {article_id}: {'; '.join(reasons)}")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    def create_admin(email: str, password: str):
        """Create the first System Administrator.

        Needed once per environment: there is no self-service route to the admin
        tier, by design.
        """
        from .enums import Role
        from .models import User
        from .security import hash_password

        if User.query.filter_by(email=email.lower()).first():
            raise click.ClickException(f"{email} already exists.")
        if len(password) < current_app.config["MIN_PASSWORD_LENGTH"]:
            raise click.ClickException(
                f"Password must be at least {current_app.config['MIN_PASSWORD_LENGTH']} characters."
            )

        db.session.add(
            User(
                email=email.lower(),
                display_name="System Administrator",
                password_hash=hash_password(password),
                role=Role.SYSTEM_ADMIN,
                email_verified_at=utcnow(),
            )
        )
        db.session.commit()
        click.echo(f"Administrator created: {email}")
