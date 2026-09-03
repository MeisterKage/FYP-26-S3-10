"""Scheduled jobs, exposed as Flask CLI commands.

Two things in the PDD happen on a clock rather than on a request:

  * scheduled publication (Figure 5.44)
  * email dispatch within 60 seconds of a trigger (PRD 5.1 Performance)

v1 runs both from the CLI, which is enough to demonstrate the behaviour:

    flask publish-due
    flask dispatch-notifications

For the deployed system, point cron (or the host's scheduler) at these every
minute. Nothing in the application code needs to change to do that.
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
