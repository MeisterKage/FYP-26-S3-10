"""The editor panel: who checks the articles, and how well they check them.

A credibility score says an article is well sourced and its writer is accurate.
It does not say who read it before it went out. This makes that public: every
editor, the sections they cover, the credentials an administrator has vouched
for, and a track record.

The track record includes how many of an editor's corrections were overturned
on appeal. That is the editor's own accuracy figure, the answer to "who checks
the checkers", and it is shown because an editor panel that only lists
achievements is marketing, not accountability.

Deliberately not shown: which articles an editor rejected, or why. Those are
writers' unpublished drafts, and exposing them would punish a writer for being
edited. Rejections appear as a count only. Email addresses never appear.
"""
from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import func

from ..enums import ArticleStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import Article, Category, Correction, EditorCategory, User
from ..security import current_user
from .articles import serialize

bp = Blueprint("editors", __name__)

#: Published or later withdrawn: both went out under the editor's approval.
APPROVED = (ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED)
RECENT_LIMIT = 20


def _panel():
    return User.query.filter(User.role == Role.EDITOR, User.deleted_at.is_(None))


def _sections(editor_ids: list[int]) -> dict[int, list[dict]]:
    rows = (
        db.session.query(EditorCategory.editor_id, Category)
        .join(Category, Category.id == EditorCategory.category_id)
        .filter(
            EditorCategory.editor_id.in_(editor_ids or [-1]),
            Category.deleted_at.is_(None),
        )
        .order_by(Category.name)
        .all()
    )
    sections: dict[int, list[dict]] = {}
    for editor_id, category in rows:
        sections.setdefault(editor_id, []).append(
            {"id": category.id, "name": category.name, "slug": category.slug}
        )
    return sections


def _counts(column, editor_ids: list[int], *criteria) -> dict[int, int]:
    rows = (
        db.session.query(column, func.count())
        .filter(column.in_(editor_ids or [-1]), *criteria)
        .group_by(column)
        .all()
    )
    return dict(rows)


def _records(editors: list[User]) -> list[dict]:
    """Public records for a list of editors, in a fixed number of queries."""
    ids = [e.id for e in editors]
    sections = _sections(ids)
    approved = _counts(Article.reviewed_by_id, ids, Article.status.in_(APPROVED))
    rejected = _counts(Article.reviewed_by_id, ids, Article.status == ArticleStatus.REJECTED)
    issued = _counts(Correction.issued_by_id, ids)
    overturned = _counts(Correction.issued_by_id, ids, Correction.overturned_at.isnot(None))

    records = []
    for e in editors:
        n_issued = issued.get(e.id, 0)
        n_overturned = overturned.get(e.id, 0)
        records.append(
            {
                "id": e.id,
                "name": e.byline,
                "title": e.editor_title,
                "credentials": e.editor_credentials,
                "bio": e.bio,
                "since": e.created_at.isoformat() if e.created_at else None,
                "sections": sections.get(e.id, []),
                "record": {
                    "articlesApproved": approved.get(e.id, 0),
                    "articlesReturned": rejected.get(e.id, 0),
                    "correctionsIssued": n_issued,
                    "correctionsOverturned": n_overturned,
                    # Withheld rather than shown as 100% when there is nothing
                    # to measure, the same rule as a new writer's accuracy rate.
                    "correctionsUpheldRate": (
                        round(100 * (n_issued - n_overturned) / n_issued, 1)
                        if n_issued else None
                    ),
                },
            }
        )
    return records


@bp.get("/editors")
def editor_panel():
    """Everyone on the panel. Public: readers are the audience."""
    editors = _panel().order_by(User.display_name).all()
    return jsonify({"editors": _records(editors)})


@bp.get("/editors/<int:editor_id>")
def editor_profile(editor_id: int):
    """One editor's record, plus the articles they most recently approved."""
    editor = _panel().filter(User.id == editor_id).first()
    if editor is None:
        raise ApiError("Editor not found.", status=404)

    recent = (
        Article.query.filter(
            Article.reviewed_by_id == editor.id,
            Article.status == ArticleStatus.PUBLISHED,
        )
        .order_by(Article.published_at.desc())
        .limit(RECENT_LIMIT)
        .all()
    )
    viewer = current_user()
    return jsonify(
        {
            "editor": _records([editor])[0],
            "articles": [serialize(a, include_body=False, viewer=viewer) for a in recent],
        }
    )
