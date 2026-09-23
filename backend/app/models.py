"""Data model. Every entity in PDD Section 4, plus three the diagram omits.

The PDD states its field lists are "illustrative rather than exhaustive" and
leaves two things to implementation. Both are decided here and flagged:

  1. Cascade on account deletion vs suspension. A suspended user keeps every row.
     A deleted user is soft-deleted (deleted_at set, credentials scrubbed); their
     articles survive under an "Account Removed" byline, their comments and likes
     are hard-deleted. So Article.contributor_id is NOT NULL and points at a
     retained tombstone row, rather than being nullable.
  2. Category deletion. Categories are soft-deleted; articles are reassigned to
     the "Uncategorised" system category rather than cascading away.

Added beyond the diagram: PlatformSetting (admin thresholds, PRD 1.3.2 admin
power 5), EditorCategory (editors work "within a specific assigned content
category", PRD 1.3.2), and AuditLog (system logs, PDD Figure 5.62).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .enums import (
    ApplicationStatus, ArticleStatus, CorrectionType, DisputeStatus, ReportStatus,
    Role, SubscriptionStatus,
)
from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --------------------------------------------------------------------------- #
#  Users and access
# --------------------------------------------------------------------------- #

class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    bio: Mapped[str | None] = mapped_column(Text)

    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role"), default=Role.FREE_REGISTERED, index=True
    )

    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_reason: Mapped[str | None] = mapped_column(String(500))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Soft delete. Set => credentials scrubbed, byline reads "Account Removed".
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Denormalised, maintained by the scoring engine. NULL => "New Contributor".
    accuracy_rate: Mapped[float | None] = mapped_column(Float)
    #: Set when a correction lands on one of this writer's auto-published
    #: articles. Until it passes, nothing of theirs skips review.
    autopublish_suspended_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    #: Shown on the public editor panel. Set by an administrator, never by the
    #: editor, so a credential there is one the platform vouches for.
    editor_title: Mapped[str | None] = mapped_column(String(120))
    editor_credentials: Mapped[str | None] = mapped_column(String(500))

    articles: Mapped[list["Article"]] = relationship(
        back_populates="contributor", foreign_keys="Article.contributor_id"
    )
    application: Mapped["ContributorApplication | None"] = relationship(
        back_populates="user", uselist=False,
        foreign_keys="ContributorApplication.user_id",
    )

    @property
    def byline(self) -> str:
        return "Account Removed" if self.deleted_at else self.display_name

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None and not self.is_suspended

    def has_premium_access(self, now: datetime | None = None) -> bool:
        """Live paywall check. Never trust `role` alone; it does not expire."""
        now = now or utcnow()
        return any(
            s.status == SubscriptionStatus.ACTIVE and s.period_end > now
            for s in self.subscriptions
        )


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    #: The "Uncategorised" fallback cannot be deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EditorCategory(db.Model):
    """Editors "work within a specific assigned content category" (PRD 1.3.2)."""

    __tablename__ = "editor_categories"
    __table_args__ = (UniqueConstraint("editor_id", "category_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    editor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))


class UserCategoryPreference(db.Model):
    __tablename__ = "user_category_preferences"
    __table_args__ = (UniqueConstraint("user_id", "category_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    notify: Mapped[bool] = mapped_column(Boolean, default=True)


class ContributorApplication(TimestampMixin, db.Model):
    __tablename__ = "contributor_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    writing_sample: Mapped[str] = mapped_column(Text)
    background: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.PENDING,
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    #: PDD Figure 5.15: a declined applicant is told when they may reapply.
    reapply_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="application", foreign_keys=[user_id])


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    #: Only the hash is stored; the raw token exists solely in the emailed link.
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- #
#  Articles
# --------------------------------------------------------------------------- #

class Article(TimestampMixin, db.Model):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_feed", "status", "published_at", "credibility_score"),
        CheckConstraint(
            "credibility_score >= 0 AND credibility_score <= 100",
            name="ck_articles_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contributor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)

    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(String(500))
    #: Sanitised HTML from the rich-text editor. Cleaned on write, never on read.
    body: Mapped[str] = mapped_column(Text)
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    #: Comma-separated. Rule-based search only, no semantic matching (PDD Fig 5.7).
    tags: Mapped[str | None] = mapped_column(String(500))

    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status"),
        default=ArticleStatus.DRAFT, index=True,
    )
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)

    #: Denormalised per PDD Section 4, read on nearly every fetch, so not a join.
    credibility_score: Mapped[float] = mapped_column(Float, default=0.0)
    credibility_band: Mapped[str | None] = mapped_column(String(20))

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Future value + SCHEDULED status drives scheduled publication (PDD Fig 5.44).
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    #: Auto-publish marks an article with timestamps rather than a new status.
    #: A PROVISIONAL status would have to be added to every query that filters
    #: on PUBLISHED (feeds, search, categories, scoring, the accuracy counts),
    #: and missing one would silently drop the article out of a feed. As columns,
    #: nothing that already works has to change. The reader sees "Not yet
    #: reviewed" while the first is set and the second is not.
    auto_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    view_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)

    contributor: Mapped[User] = relationship(
        back_populates="articles", foreign_keys=[contributor_id]
    )
    #: Whoever approved it, or confirmed it after auto-publish.
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    sources: Mapped[list["ArticleSource"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["ArticleRevision"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    corrections: Mapped[list["Correction"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )

    @property
    def is_retracted(self) -> bool:
        return self.status == ArticleStatus.RETRACTED

    @property
    def awaiting_review(self) -> bool:
        """Published by the system, and no editor has confirmed it yet."""
        return self.auto_published_at is not None and self.review_confirmed_at is None


class ArticleRevision(db.Model):
    __tablename__ = "article_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    article: Mapped[Article] = relationship(back_populates="revisions")


class ArticleSource(db.Model):
    """A verifiable source link tagged at submission. Feeds the score directly."""

    __tablename__ = "article_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(1000))
    label: Mapped[str | None] = mapped_column(String(255))
    #: Set by the rule-based source-validity check (PDD Section 2.2, Moderation).
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    article: Mapped[Article] = relationship(back_populates="sources")


class Correction(TimestampMixin, db.Model):
    """A logged correction or retraction, the direct trigger for rescoring."""

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    issued_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    correction_type: Mapped[CorrectionType] = mapped_column(
        SAEnum(CorrectionType, name="correction_type")
    )
    reason: Mapped[str] = mapped_column(Text)
    #: An admin may overturn an editor's call (PRD 1.3.2 admin power 4).
    overturned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overturned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    article: Mapped[Article] = relationship(back_populates="corrections")


class CorrectionDispute(TimestampMixin, db.Model):
    """A contributor's challenge to a correction against their work.

    PDD Figure 5.94. A correction lowers both the article's score and the
    writer's accuracy rate, and until now the only route to reversing one was an
    administrator noticing. This gives the writer a way to put their case, and
    an administrator a queue to answer it, with the original correction and its
    effect on the score attached.

    One open dispute per correction: a second filing is the same argument again,
    not new information.
    """

    __tablename__ = "correction_disputes"
    __table_args__ = (UniqueConstraint("correction_id", "contributor_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    correction_id: Mapped[int] = mapped_column(
        ForeignKey("corrections.id", ondelete="CASCADE"), index=True
    )
    contributor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    argument: Mapped[str] = mapped_column(Text)
    status: Mapped[DisputeStatus] = mapped_column(
        SAEnum(DisputeStatus, name="dispute_status"),
        default=DisputeStatus.OPEN, index=True,
    )
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class Report(TimestampMixin, db.Model):
    """Reader-submitted inaccuracy flag. Accumulates toward the review threshold."""

    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("article_id", "reporter_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status"),
        default=ReportStatus.OPEN, index=True,
    )
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    article: Mapped[Article] = relationship(back_populates="reports")


# --------------------------------------------------------------------------- #
#  Engagement
# --------------------------------------------------------------------------- #

class Comment(TimestampMixin, db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # moderated


class Like(db.Model):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("article_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Follow(db.Model):
    """Self-referential on User: a follower following a contributor (PDD Section 4)."""

    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "contributor_id"),
        CheckConstraint("follower_id <> contributor_id", name="ck_follows_not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    contributor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SavedArticle(db.Model):
    __tablename__ = "saved_articles"
    __table_args__ = (UniqueConstraint("user_id", "article_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- #
#  Notifications, money, ops
# --------------------------------------------------------------------------- #

class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: PRD 5.1 Performance: queued for delivery within 60s of the trigger.
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "event_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(60))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(TimestampMixin, db.Model):
    """Links a reader to a contributor's premium tier (PDD Section 4)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.ACTIVE,
    )
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Opaque reference from the payment gateway. Stubbed in v1.
    gateway_ref: Mapped[str | None] = mapped_column(String(255))

    subscriber: Mapped[User] = relationship(
        foreign_keys=[subscriber_id], backref="subscriptions"
    )


class Payout(TimestampMixin, db.Model):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gross_cents: Mapped[int] = mapped_column(Integer, default=0)
    platform_cut_cents: Mapped[int] = mapped_column(Integer, default=0)
    net_cents: Mapped[int] = mapped_column(Integer, default=0)
    #: Revenue-share tier applied for this period, e.g. "tier_2".
    revenue_tier: Mapped[str] = mapped_column(String(40))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformSetting(TimestampMixin, db.Model):
    """Admin-configurable thresholds (PRD 1.3.2, administrator power 5).

    Keys match app.credibility.DEFAULTS. An absent row means "use the default",
    so the table starts empty and the engine still works.
    """

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AuditLog(db.Model):
    """System logs (PDD Figure 5.62). Append-only; never updated or deleted."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
