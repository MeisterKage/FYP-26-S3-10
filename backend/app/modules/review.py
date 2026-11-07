"""Editorial review (PDD Figures 5.48-5.49).

An editor sees only the queue for the categories they are assigned to
(PRD 1.3.2: editors "work within a specific assigned content category").
Administrators see everything, which PRD 1.3.2 grants them explicitly.

The queue is ordered by review priority rather than by arrival, so an editor's
attention goes where the risk is. Articles the system published during a backlog
appear in a second list until an editor confirms them.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..enums import REVIEW_ROLES, ArticleStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import Article, AuditLog, EditorCategory, Notification, utcnow
from ..review_service import confirm_article, duplicated_titles, priority_for, publish_article
from ..sanitize import clean_plain_text
from ..scoring_service import explain_article, load_settings, upheld_report_counts
from ..security import editor_owns_category, roles_required
from ..validation import json_body, require_choice, require_list, require_str
from ..source_service import apply_verdict, serialize as serialize_source
from .articles import list_loads, serialize

bp = Blueprint("review", __name__)

#: Upper bound on one batch approval. Large enough to clear a real backlog in a
#: few clicks, small enough that one request cannot publish the whole platform.
MAX_BATCH = 50


def _assigned_category_ids() -> list[int] | None:
    """None means 'every category' (administrators)."""
    if g.current_user.role == Role.SYSTEM_ADMIN:
        return None
    return [
        row.category_id
        for row in EditorCategory.query.filter_by(editor_id=g.current_user.id)
    ]


@bp.get("/review/queue")
@roles_required(*REVIEW_ROLES)
def review_queue():
    """PDD Figure 5.48, ordered by risk rather than by arrival.

    Oldest-first spends an editor's attention on whatever happened to arrive
    first, so a new writer with no sources waits behind a veteran who always
    cites properly. Ordering by review priority puts the articles that most need
    a human at the top. The priority includes a waiting term, so nothing starves.
    """
    category_ids = _assigned_category_ids()
    if category_ids is not None and not category_ids:
        #An editor with no assigned category has an empty queue, not an error.
        return jsonify(
            {
                "articles": [],
                "awaitingConfirmation": [],
                "note": "No categories are assigned to you yet.",
            }
        )

    pending = Article.query.options(*list_loads()).filter_by(status=ArticleStatus.PENDING)
    awaiting = Article.query.options(*list_loads()).filter(
        Article.status == ArticleStatus.PUBLISHED,
        Article.auto_published_at.isnot(None),
        Article.review_confirmed_at.is_(None),
    )
    if category_ids is not None:
        pending = pending.filter(Article.category_id.in_(category_ids))
        awaiting = awaiting.filter(Article.category_id.in_(category_ids))

    settings = load_settings()
    now = utcnow()

    #A pending article has never been scored, so its stored credibility_score is
    #still the 0.0 default. Serving that reads to an editor as "this article is
    #worthless" rather than "not yet scored". That is the opposite of true, on
    #the one screen where it would bias the decision. Compute the score the article
    #*would* carry on publication instead. Read-only: explain_article persists
    #nothing.
    payload = []
    articles = pending.order_by(Article.submitted_at.asc()).all()
    #What each article's score and priority need, counted for the whole queue
    #at once rather than once per article.
    record_counts: dict = {}
    upheld = upheld_report_counts([a.id for a in articles])
    duplicates = duplicated_titles(articles)
    for article in articles:
        data = serialize(article, viewer=g.current_user)
        data["credibility"] = {
            **data["credibility"],
            **explain_article(article, settings, record_counts, upheld).as_dict(),
            "prospective": True,
        }
        data["priority"] = priority_for(article, settings, now, article.id in duplicates).as_dict()
        payload.append(data)

    #Highest priority first. The sort is stable, so articles of equal priority
    #keep the oldest-first order the query produced.
    payload.sort(key=lambda d: d["priority"]["priority"], reverse=True)

    return jsonify(
        {
            "articles": payload,
            "awaitingConfirmation": [
                serialize(a, include_body=False, viewer=g.current_user)
                for a in awaiting.order_by(Article.auto_published_at.asc()).all()
            ],
        }
    )


@bp.post("/review/<int:article_id>/sources/<int:source_id>/verdict")
@roles_required(*REVIEW_ROLES)
def source_verdict(article_id: int, source_id: int):
    """An editor accepts a source, rejects it, or clears their earlier verdict.

    The automatic rating is where review starts. The editor, who can read the
    page, has the final word, and must say why: the reason is shown to the
    writer and kept in the log.
    """
    article = db.session.get(Article, article_id)
    if article is None or not editor_owns_category(article.category_id):
        raise ApiError("Article not found.", status=404)
    if article.status not in (ArticleStatus.PENDING, ArticleStatus.PUBLISHED,
                              ArticleStatus.SCHEDULED):
        raise ApiError(f"Sources on a {article.status.value} article cannot be reviewed.",
                       status=409)
    source = next((s for s in article.sources if s.id == source_id), None)
    if source is None:
        raise ApiError("Source not found.", status=404)

    data = json_body()
    verdict = data.get("verdict")
    if verdict not in ("accepted", "rejected", None):
        raise ApiError("'verdict' must be 'accepted', 'rejected' or null.", status=422,
                       field="verdict")
    reason = None
    if verdict:
        reason = clean_plain_text(require_str(data, "reason", max_length=500))
        if len(reason) < 5:
            raise ApiError("Say why, in a few words.", status=422, field="reason")

    apply_verdict(source, verdict=verdict, reason=reason, editor_id=g.current_user.id)
    if article.status == ArticleStatus.PUBLISHED:
        from ..scoring_service import rescore_article
        rescore_article(article)
    db.session.commit()
    return jsonify({"source": serialize_source(source),
                    "credibility": explain_article(article).as_dict()})


@bp.post("/review/<int:article_id>/approve")
@roles_required(*REVIEW_ROLES)
def approve(article_id: int):
    """PDD Figure 5.49."""
    article = _pending_article(article_id)
    breakdown = publish_article(article, reviewer_id=g.current_user.id, now=utcnow())
    db.session.commit()

    return jsonify(
        {"article": serialize(article, viewer=g.current_user), "credibility": breakdown.as_dict()}
    )


@bp.post("/review/batch-approve")
@roles_required(*REVIEW_ROLES)
def batch_approve():
    """Approve several articles in one decision.

    The client sends the explicit ids the editor saw on screen. The server does
    not re-derive "everything below some risk threshold", because the set the
    editor looked at and the set the server would compute can differ between
    render and click, and an editor must approve only what they actually saw.

    Each article is checked exactly as a single approval would check it, and
    each gets its own audit row: thirty approvals are thirty decisions, and the
    log must read that way. One that fails its checks is reported back rather
    than failing the others.
    """
    raw_ids = require_list(json_body(), "articleIds", max_items=MAX_BATCH)
    if not raw_ids:
        raise ApiError("Choose at least one article to approve.", status=422, field="articleIds")

    ids: list[int] = []
    for raw in raw_ids:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ApiError("Article ids must be whole numbers.", status=422, field="articleIds")
        if raw not in ids:
            ids.append(raw)

    now = utcnow()
    approved, failed = [], []
    for article_id in ids:
        try:
            article = _pending_article(article_id)
        except ApiError as error:
            failed.append({"id": article_id, "reason": error.message})
            continue
        try:
            publish_article(article, reviewer_id=g.current_user.id, now=now)
        except ApiError as error:
            failed.append({"id": article_id, "reason": error.message})
            continue
        approved.append(article_id)

    db.session.commit()
    return jsonify({"approved": approved, "failed": failed})


@bp.post("/review/<int:article_id>/confirm")
@roles_required(*REVIEW_ROLES)
def confirm(article_id: int):
    """An editor has now read an article the system published during a backlog.

    Clears the "Not yet reviewed" label readers see. Confirming is a review in
    its own right, so the same separation of duties applies: an editor cannot
    confirm an article they wrote.
    """
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)
    if not article.awaiting_review:
        raise ApiError("This article is not waiting for an editor to confirm it.", status=409)
    if not editor_owns_category(article.category_id):
        raise ApiError("This article is outside your assigned categories.", status=403)
    if article.contributor_id == g.current_user.id and g.current_user.role != Role.SYSTEM_ADMIN:
        raise ApiError(
            "You wrote this article, so another editor or an administrator has to "
            "confirm it.",
            status=403,
        )

    confirm_article(article, reviewer_id=g.current_user.id, now=utcnow())
    db.session.commit()
    return jsonify({"article": serialize(article, include_body=False, viewer=g.current_user)})


@bp.post("/review/<int:article_id>/reject")
@roles_required(*REVIEW_ROLES)
def reject(article_id: int):
    """PDD Figure 5.49. A rejected article returns to the author, editable."""
    article = _pending_article(article_id)
    data = json_body()

    reason = clean_plain_text(data.get("reason") or "")
    if not reason:
        raise ApiError(
            "Give the contributor a reason for the rejection.", status=422, field="reason"
        )

    article.status = ArticleStatus.REJECTED
    article.reviewed_by_id = g.current_user.id
    article.rejection_reason = reason

    db.session.add(
        Notification(
            user_id=article.contributor_id,
            event_type="article.rejected",
            title="Your article needs changes",
            body=reason,
            link=f"/dashboard/articles/{article.id}",
        )
    )
    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action="article.reject",
            entity_type="article",
            entity_id=article.id,
            detail=reason,
        )
    )
    db.session.commit()

    return jsonify({"article": serialize(article, viewer=g.current_user)})


def _pending_article(article_id: int) -> Article:
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)
    if article.status != ArticleStatus.PENDING:
        raise ApiError(
            f"This article is {article.status.value}, not awaiting review.", status=409
        )
    if not editor_owns_category(article.category_id):
        raise ApiError("This article is outside your assigned categories.", status=403)

    #Separation of duties. Editors may write (AUTHORING_ROLES includes them),
    #and without this an editor could write, submit, and approve their own
    #article inside their own section, skipping the only human check between a
    #claim and a published credibility score. PRD 7.4.2 commits to review
    #before publication, which a review by the author is not.
    #
    #Administrators are exempt: PRD 1.3.2 grants them oversight of everything,
    #and an administrator publishing their own piece is a deliberate act by the
    #one role that can already override any editorial decision.
    if (
        article.contributor_id == g.current_user.id
        and g.current_user.role != Role.SYSTEM_ADMIN
    ):
        raise ApiError(
            "You wrote this article, so another editor or an administrator has to "
            "review it.",
            status=403,
        )

    return article
