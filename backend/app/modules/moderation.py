"""Moderation and rule-based checks (PDD Section 2.2, Figures 5.50, 5.58).

This is where corrections and retractions are logged, and therefore where the
scoring engine is triggered on the moderation side (PDD Section 3).
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..credibility import DEFAULTS
from ..enums import REVIEW_ROLES, ArticleStatus, CorrectionType, ReportStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import Article, AuditLog, Comment, Correction, Notification, Report, utcnow
from ..sanitize import clean_plain_text
from ..scoring_service import load_settings, rescore_contributor_articles
from ..security import editor_owns_category, roles_required
from ..validation import json_body, require_choice, require_str

bp = Blueprint("moderation", __name__)


@bp.get("/moderation/reports")
@roles_required(*REVIEW_ROLES)
def flagged_content():
    """PDD Figure 5.50.

    Articles are surfaced once their open report count crosses the admin-set
    threshold, which is the escalation rule in PRD 1.3.3 point 2.
    """
    threshold = int(load_settings().get("report_threshold", DEFAULTS["report_threshold"]))

    rows = (
        db.session.query(Article, func.count(Report.id).label("open_reports"))
        .join(Report, Report.article_id == Article.id)
        .filter(Report.status == ReportStatus.OPEN)
        .group_by(Article.id)
        .having(func.count(Report.id) >= threshold)
        .all()
    )

    visible = [
        {
            "articleId": article.id,
            "title": article.title,
            "openReports": count,
            "credibilityScore": article.credibility_score,
        }
        for article, count in rows
        if editor_owns_category(article.category_id)
    ]
    return jsonify({"threshold": threshold, "flagged": visible})


@bp.post("/moderation/reports/<int:report_id>/resolve")
@roles_required(*REVIEW_ROLES)
def resolve_report(report_id: int):
    """Uphold or dismiss one reader report.

    Upholding is a scoring input, so the article and its author are rescored.
    """
    report = Report.query.get(report_id)
    if report is None:
        raise ApiError("Report not found.", status=404)
    if report.status != ReportStatus.OPEN:
        raise ApiError("This report is already resolved.", status=409)

    article = Article.query.get(report.article_id)
    if not editor_owns_category(article.category_id):
        raise ApiError("This article is outside your assigned categories.", status=403)

    outcome = json_body().get("outcome")
    if outcome not in {"upheld", "dismissed"}:
        raise ApiError("Outcome must be 'upheld' or 'dismissed'.", status=422, field="outcome")

    report.status = ReportStatus.UPHELD if outcome == "upheld" else ReportStatus.DISMISSED
    report.resolved_by_id = g.current_user.id

    if outcome == "upheld":
        rescore_contributor_articles(article.contributor)

    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action=f"report.{outcome}",
            entity_type="report",
            entity_id=report.id,
        )
    )
    db.session.commit()

    return jsonify({"status": report.status.value, "credibilityScore": article.credibility_score})


@bp.post("/moderation/articles/<int:article_id>/correction")
@roles_required(*REVIEW_ROLES)
def log_correction(article_id: int):
    """PRD 1.3.3 point 3: a confirmed inaccuracy becomes a correction or retraction.

    Both are logged in the revision history and immediately lower the article's
    score and the contributor's accuracy rate.
    """
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)
    if article.status not in {ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED}:
        raise ApiError("Only a published article can be corrected.", status=409)
    if not editor_owns_category(article.category_id):
        raise ApiError("This article is outside your assigned categories.", status=403)

    data = json_body()
    raw_type = data.get("type", "correction")
    reason = clean_plain_text(data.get("reason") or "")

    if raw_type not in {t.value for t in CorrectionType}:
        raise ApiError("Type must be 'correction' or 'retraction'.", status=422, field="type")
    if not reason:
        raise ApiError("Record why the article is being corrected.", status=422, field="reason")

    correction_type = CorrectionType(raw_type)
    db.session.add(
        Correction(
            article_id=article.id,
            issued_by_id=g.current_user.id,
            correction_type=correction_type,
            reason=reason,
        )
    )

    if correction_type == CorrectionType.RETRACTION:
        article.status = ArticleStatus.RETRACTED

    db.session.flush()
    rescore_contributor_articles(article.contributor)

    db.session.add(
        Notification(
            user_id=article.contributor_id,
            event_type="article.corrected",
            title=f"Your article has been {raw_type}ed",
            body=reason,
            link=f"/articles/{article.slug}",
        )
    )
    db.session.commit()

    return jsonify(
        {
            "articleScore": article.credibility_score,
            "contributorAccuracy": article.contributor.accuracy_rate,
        }
    )


@bp.post("/moderation/corrections/<int:correction_id>/overturn")
@roles_required(Role.SYSTEM_ADMIN)
def overturn_correction(correction_id: int):
    """PRD 1.3.2, administrator power 4: overturn an editor's earlier call.

    Administrator-only. An editor cannot reverse a correction against an article
    they themselves review.
    """
    correction = Correction.query.get(correction_id)
    if correction is None:
        raise ApiError("Correction not found.", status=404)
    if correction.overturned_at is not None:
        raise ApiError("This correction has already been overturned.", status=409)

    correction.overturned_at = utcnow()
    correction.overturned_by_id = g.current_user.id

    article = Article.query.get(correction.article_id)
    if correction.correction_type == CorrectionType.RETRACTION:
        article.status = ArticleStatus.PUBLISHED

    db.session.flush()
    rescore_contributor_articles(article.contributor)

    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action="correction.overturn",
            entity_type="correction",
            entity_id=correction.id,
        )
    )
    db.session.commit()

    return jsonify({"articleScore": article.credibility_score})


@bp.post("/moderation/comments/<int:comment_id>/hide")
@roles_required(*REVIEW_ROLES)
def hide_comment(comment_id: int):
    """Moderate a discussion thread (PRD 1.3.2, editor power 6)."""
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise ApiError("Comment not found.", status=404)

    comment.is_hidden = True
    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action="comment.hide",
            entity_type="comment",
            entity_id=comment.id,
        )
    )
    db.session.commit()
    return jsonify({"hidden": True})


# --------------------------------------------------------------------------- #
#  Rule-based submission checks (PDD Section 2.2)
# --------------------------------------------------------------------------- #

def duplicate_titles(title: str, exclude_article_id: int | None = None) -> list[int]:
    """Rule-based duplicate check. Exact normalised title match -- no fuzzy logic."""
    normalised = " ".join(title.lower().split())
    query = Article.query.filter(func.lower(Article.title) == normalised)
    if exclude_article_id:
        query = query.filter(Article.id != exclude_article_id)
    return [a.id for a in query]
