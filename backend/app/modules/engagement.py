"""Engagement: comments, likes, follows, saved reading lists, shares, reports.

Covers PDD Figures 5.8, 5.17-5.20, 5.29-5.36.

Per PDD Section 3, this service forwards reader-submitted reports to Moderation
rather than acting on them itself -- the decision to escalate stays with a human.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..enums import ArticleStatus, ReportStatus
from ..errors import ApiError
from ..extensions import db
from ..integrations import social_share
from ..models import (
    Article, Comment, Follow, Like, Notification, Report, SavedArticle, User,
)
from ..sanitize import clean_plain_text
from ..security import login_required
from ..validation import json_body, require_int, require_str

bp = Blueprint("engagement", __name__)


def _published_article(article_id: int) -> Article:
    article = Article.query.filter_by(id=article_id, status=ArticleStatus.PUBLISHED).first()
    if article is None:
        raise ApiError("Article not found.", status=404)
    return article


# --------------------------------------------------------------------------- #
#  Likes  (PDD Figures 5.17, 5.18)
# --------------------------------------------------------------------------- #

@bp.post("/articles/<int:article_id>/like")
@login_required
def like(article_id: int):
    article = _published_article(article_id)

    existing = Like.query.filter_by(article_id=article.id, user_id=g.current_user.id).first()
    if existing:
        return jsonify({"liked": True, "likeCount": article.like_count})

    db.session.add(Like(article_id=article.id, user_id=g.current_user.id))
    article.like_count += 1
    db.session.commit()
    return jsonify({"liked": True, "likeCount": article.like_count})


@bp.delete("/articles/<int:article_id>/like")
@login_required
def unlike(article_id: int):
    article = _published_article(article_id)

    deleted = Like.query.filter_by(
        article_id=article.id, user_id=g.current_user.id
    ).delete()
    if deleted:
        # Guard against drift if the counter and rows ever disagree.
        article.like_count = max(0, article.like_count - 1)
    db.session.commit()
    return jsonify({"liked": False, "likeCount": article.like_count})


# --------------------------------------------------------------------------- #
#  Comments  (PDD Figures 5.29, 5.30)
# --------------------------------------------------------------------------- #

@bp.get("/articles/<int:article_id>/comments")
def list_comments(article_id: int):
    article = _published_article(article_id)
    comments = (
        Comment.query.filter_by(article_id=article.id, is_hidden=False)
        .order_by(Comment.created_at.asc())
        .all()
    )
    authors = {u.id: u for u in User.query.filter(
        User.id.in_([c.user_id for c in comments] or [-1])
    )}
    return jsonify(
        {
            "comments": [
                {
                    "id": c.id,
                    "body": c.body,
                    "parentId": c.parent_id,
                    "createdAt": c.created_at.isoformat(),
                    "author": {
                        "id": c.user_id,
                        "name": authors[c.user_id].byline if c.user_id in authors else "Unknown",
                    },
                }
                for c in comments
            ]
        }
    )


@bp.post("/articles/<int:article_id>/comments")
@login_required
def add_comment(article_id: int):
    article = _published_article(article_id)
    data = json_body()

    body = clean_plain_text(require_str(data, "body", max_length=5000))
    if not body:
        raise ApiError("Write something first.", status=422, field="body")

    # A parent id is a foreign key arriving straight from the client. Left
    # unvalidated, a nonexistent id becomes a database error on Postgres (SQLite
    # silently accepts it), and an id belonging to a *different* article would
    # graft this reply onto someone else's discussion.
    parent_id = require_int(data, "parentId", default=None, minimum=1)
    if parent_id is not None:
        parent = Comment.query.filter_by(id=parent_id, article_id=article.id).first()
        if parent is None:
            raise ApiError(
                "The comment you are replying to no longer exists.",
                status=422, field="parentId",
            )
        if parent.parent_id is not None:
            raise ApiError(
                "Replies cannot be nested further.", status=422, field="parentId"
            )

    comment = Comment(
        article_id=article.id,
        user_id=g.current_user.id,
        parent_id=parent_id,
        body=body,
    )
    db.session.add(comment)

    if article.contributor_id != g.current_user.id:
        db.session.add(
            Notification(
                user_id=article.contributor_id,
                event_type="comment.new",
                title="New comment on your article",
                body=body[:200],
                link=f"/articles/{article.slug}",
            )
        )

    db.session.commit()
    return jsonify({"id": comment.id, "body": comment.body}), 201


@bp.delete("/comments/<int:comment_id>")
@login_required
def remove_own_comment(comment_id: int):
    """PDD Figure 5.30. Authors remove their own; moderators use the moderation queue."""
    comment = Comment.query.get(comment_id)
    if comment is None:
        raise ApiError("Comment not found.", status=404)
    if comment.user_id != g.current_user.id:
        raise ApiError("You can only remove your own comments.", status=403)

    db.session.delete(comment)
    db.session.commit()
    return jsonify({"message": "Comment removed."})


# --------------------------------------------------------------------------- #
#  Follows and saved articles  (PDD Figures 5.32-5.35)
# --------------------------------------------------------------------------- #

@bp.post("/contributors/<int:contributor_id>/follow")
@login_required
def follow(contributor_id: int):
    if contributor_id == g.current_user.id:
        raise ApiError("You cannot follow yourself.", status=422)

    contributor = User.query.filter_by(id=contributor_id, deleted_at=None).first()
    if contributor is None:
        raise ApiError("Contributor not found.", status=404)

    if not Follow.query.filter_by(
        follower_id=g.current_user.id, contributor_id=contributor_id
    ).first():
        db.session.add(Follow(follower_id=g.current_user.id, contributor_id=contributor_id))
        db.session.commit()

    return jsonify({"following": True})


@bp.delete("/contributors/<int:contributor_id>/follow")
@login_required
def unfollow(contributor_id: int):
    Follow.query.filter_by(
        follower_id=g.current_user.id, contributor_id=contributor_id
    ).delete()
    db.session.commit()
    return jsonify({"following": False})


@bp.post("/articles/<int:article_id>/save")
@login_required
def save_article(article_id: int):
    article = _published_article(article_id)
    if not SavedArticle.query.filter_by(
        user_id=g.current_user.id, article_id=article.id
    ).first():
        db.session.add(SavedArticle(user_id=g.current_user.id, article_id=article.id))
        db.session.commit()
    return jsonify({"saved": True})


@bp.delete("/articles/<int:article_id>/save")
@login_required
def unsave_article(article_id: int):
    SavedArticle.query.filter_by(user_id=g.current_user.id, article_id=article_id).delete()
    db.session.commit()
    return jsonify({"saved": False})


@bp.get("/me/reading-list")
@login_required
def reading_list():
    from .articles import serialize

    saved = (
        db.session.query(Article)
        .join(SavedArticle, SavedArticle.article_id == Article.id)
        .filter(SavedArticle.user_id == g.current_user.id)
        .order_by(SavedArticle.created_at.desc())
        .all()
    )
    return jsonify(
        {"articles": [serialize(a, include_body=False, viewer=g.current_user) for a in saved]}
    )


# --------------------------------------------------------------------------- #
#  Share and report  (PDD Figures 5.8, 5.36)
# --------------------------------------------------------------------------- #

@bp.get("/articles/<int:article_id>/share")
def share(article_id: int):
    article = _published_article(article_id)
    base = request.host_url.rstrip("/")
    article_url = f"{base}/articles/{article.slug}"

    return jsonify(
        {
            "url": article_url,
            "targets": social_share.share_urls(
                article_url=article_url, title=article.title, score=article.credibility_score
            ),
            "previewCard": social_share.preview_card(
                title=article.title,
                summary=article.summary or "",
                score=article.credibility_score,
                band=article.credibility_band or "",
            ),
        }
    )


@bp.post("/articles/<int:article_id>/report")
@login_required
def report_article(article_id: int):
    """PDD Figure 5.36. Forwarded to Moderation; never acted on here."""
    article = _published_article(article_id)
    data = json_body()

    reason = clean_plain_text(data.get("reason") or "")
    if not reason:
        raise ApiError("Tell us what is inaccurate.", status=422, field="reason")

    if Report.query.filter_by(article_id=article.id, reporter_id=g.current_user.id).first():
        raise ApiError("You have already reported this article.", status=409)

    db.session.add(
        Report(
            article_id=article.id,
            reporter_id=g.current_user.id,
            reason=reason,
            status=ReportStatus.OPEN,
        )
    )
    db.session.commit()

    return jsonify({"message": "Thanks. An editor will review this article."}), 201
