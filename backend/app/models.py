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

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, Float, ForeignKey,
    Index, Integer, LargeBinary, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .enums import (
    ApplicationStatus, ArticleStatus, CorrectionType, DisputeStatus, ReportStatus,
    Role, SubscriptionStatus,
)
from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Treat a stored time without a zone as UTC. PostgreSQL keeps the zone;
    SQLite, which the tests use, drops it, and comparing the two raises."""
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


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
            s.status == SubscriptionStatus.ACTIVE and _aware(s.period_end) > now
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


class UserCountryPreference(db.Model):
    """A country whose news a reader follows, beside the sections they follow."""

    __tablename__ = "user_country_preferences"
    __table_args__ = (UniqueConstraint("user_id", "country_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: ISO 3166-1 alpha-2, as on Article.country_code.
    country_code: Mapped[str] = mapped_column(String(2))


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
    #: ISO 3166-1 alpha-2 code of the country the article is about (app.countries).
    #: NULL means international, or not about any single country.
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)

    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(String(500))
    #: Sanitised HTML from the rich-text editor. Cleaned on write, never on read.
    body: Mapped[str] = mapped_column(Text)
    cover_image_url: Mapped[str | None] = mapped_column(String(500))
    #: An uploaded cover image (ArticleImage). Alt text and a credit are
    #: required before submission: every image states where it came from.
    cover_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("article_images.id", ondelete="SET NULL")
    )
    cover_image_alt: Mapped[str | None] = mapped_column(String(300))
    cover_image_credit: Mapped[str | None] = mapped_column(String(300))
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

    #: Set when the article is republished from another publisher under a
    #: licence that allows it (JSON: publisher, authors, url, publishedAt,
    #: licence, licenceUrl, counterUrl). NULL for original reporting.
    republication: Mapped[str | None] = mapped_column(Text)

    #: Latest originality check (app/originality_service.py). The percentage is
    #: kept as a column because review ordering and auto-publish read it; the
    #: full report with matched passages is JSON, read only by the report view.
    originality_percent: Mapped[float | None] = mapped_column(Float)
    originality_report: Mapped[str | None] = mapped_column(Text, deferred=True)
    originality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contributor: Mapped[User] = relationship(
        back_populates="articles", foreign_keys=[contributor_id]
    )
    #: Whoever approved it, or confirmed it after auto-publish.
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    cover_image: Mapped["ArticleImage | None"] = relationship(foreign_keys=[cover_image_id])
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
    translations: Mapped[list["ArticleTranslation"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )

    @property
    def is_retracted(self) -> bool:
        return self.status == ArticleStatus.RETRACTED

    @property
    def awaiting_review(self) -> bool:
        """Published by the system, and no editor has confirmed it yet."""
        return self.auto_published_at is not None and self.review_confirmed_at is None


class DigestEdition(db.Model):
    """One monthly digest: a topic, optionally narrowed to a country.

    Fixed once compiled, like a printed issue. The ranked article list is kept
    in DigestEntry rows and never re-ranked; what later happens to an article
    (a correction, a retraction) is shown against it when the edition is read.
    """

    __tablename__ = "digest_editions"
    __table_args__ = (UniqueConstraint("month", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: "2026-09"
    month: Mapped[str] = mapped_column(String(7), index=True)
    #: "technology" or "politics-au": the section slug, plus the country if any.
    key: Mapped[str] = mapped_column(String(100))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    #: ISO code, or "" for every country. Not NULL, so the uniqueness of
    #: (month, key) and subscription matching need no NULL special cases.
    country_code: Mapped[str] = mapped_column(String(2), default="")
    #: Month statistics and the corrections logged that month, as compiled.
    data: Mapped[str] = mapped_column(Text)
    compiled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entries: Mapped[list["DigestEntry"]] = relationship(
        cascade="all, delete-orphan", order_by="DigestEntry.rank"
    )


class DigestEntry(db.Model):
    __tablename__ = "digest_entries"
    __table_args__ = (UniqueConstraint("edition_id", "article_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("digest_editions.id", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    #: The score the ranking used, kept so a reader can see it moved since.
    score_at_compile: Mapped[float] = mapped_column(Float)

    article: Mapped["Article"] = relationship()


class DigestSubscription(db.Model):
    __tablename__ = "digest_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "category_id", "country_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    country_code: Mapped[str] = mapped_column(String(2), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArticleTranslation(db.Model):
    """An article in another language (see translation_service).

    `source_hash` fingerprints the English it was translated from, so an edit
    to the article marks the translation stale instead of showing readers a
    translation of text that has changed.
    """

    __tablename__ = "article_translations"
    __table_args__ = (UniqueConstraint("article_id", "lang"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    lang: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String(400))
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    #: The In brief points, translated, as a JSON list.
    points: Mapped[str | None] = mapped_column(Text)
    #: Who translated it: "ai" for the demo articles, or a provider's name.
    provider: Mapped[str] = mapped_column(String(20))
    source_hash: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    article: Mapped["Article"] = relationship(back_populates="translations")


class ArticleDailyView(db.Model):
    """How many times an article was opened on one day (UTC).

    The running total stays on Article.view_count; this is the history behind
    it, for the trend on the article's analysis panel. One row per article per
    day that had any views.
    """

    __tablename__ = "article_daily_views"
    __table_args__ = (UniqueConstraint("article_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    views: Mapped[int] = mapped_column(Integer, default=0)


class ArticleFingerprint(db.Model):
    """One winnowed fingerprint of an article's text (app/originality.py).

    The index a submission is looked up against: one query for the submission's
    hashes returns every article sharing a passage with it, without reading any
    article body. Rewritten whenever an article's text changes.
    """

    __tablename__ = "article_fingerprints"
    __table_args__ = (Index("ix_article_fingerprints_hash", "hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    hash: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer)


class SourceDomainRule(db.Model):
    """An administrator's grade for a domain, overriding the automatic rules.

    For the cases no rule or list gets right: an official body on a plain
    .com address, a reputable local outlet no list covers, or a site the lists
    rate more kindly than this platform should. Every change is logged, and
    articles citing the domain are re-graded when it changes.
    """

    __tablename__ = "source_domain_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: A bare domain, e.g. "bankofengland.co.uk". Covers its subdomains.
    domain: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    tier: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(400))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DomainLookup(db.Model):
    """Who owns a domain, according to Wikidata. A cache: one lookup per domain.

    `status` is "official" (owned by a government body that is not a media
    organisation), "none" (no such owner found) or "error" (Wikidata could not
    be asked; retried sooner).
    """

    __tablename__ = "domain_lookups"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20))
    owner: Mapped[str | None] = mapped_column(String(300))
    wikidata_id: Mapped[str | None] = mapped_column(String(20))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceSnapshot(db.Model):
    """The text of a cited page as it was when last checked.

    A cache, so re-checking an article does not re-fetch every source, and a
    record: if a page later changes, what it said when the article was checked
    is still here.
    """

    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(1000))
    #: "ok", or "unavailable" with the reason in `error`.
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str | None] = mapped_column(Text, deferred=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArticleImage(db.Model):
    """An uploaded image, stored already processed (app/images.py).

    Held in the database rather than a storage bucket so it works with nothing
    extra to provision. Only modules/images.py reads or writes these rows, so
    moving to object storage later changes that one module.

    `key` is the public identifier: random, so an image attached to an
    unpublished draft cannot be found by counting upward through ids.
    """

    __tablename__ = "article_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    large: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    thumb: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    #: True when the source currently earns points. Kept in step with the
    #: rating below; the review queue and auto-publish rules read it.
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)

    #: The source's rating (app/source_rating.py). NULL tier means it has not
    #: been rated yet; every submission rates its sources before review.
    tier: Mapped[str | None] = mapped_column(String(20))
    points: Mapped[float | None] = mapped_column(Float)
    rating_reason: Mapped[str | None] = mapped_column(String(400))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: An editor's final word: "accepted" or "rejected", with the reason.
    editor_verdict: Mapped[str | None] = mapped_column(String(20))
    editor_reason: Mapped[str | None] = mapped_column(String(500))
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verdict_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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


class Payment(db.Model):
    """One order, from checkout to outcome (app/payments.py).

    The amount is set here by the server when the order is created. A webhook
    only moves the status on, and only if its amount and currency match.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: What was bought. "subscription" is the only purpose so far.
    purpose: Mapped[str] = mapped_column(String(40))
    contributor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    #: pending -> succeeded | failed; succeeded -> refunded
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(20))
    #: The provider's checkout id: how its webhook refers back to this row.
    provider_ref: Mapped[str | None] = mapped_column(String(255), unique=True)
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentWebhookEvent(db.Model):
    """Every provider event acted on, so a resent event is recognised and ignored.

    Providers deliver webhooks at least once, and resend on any timeout. Without
    this, one payment delivered twice would grant two months for one charge.
    """

    __tablename__ = "payment_webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(40))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
