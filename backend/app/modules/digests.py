"""Monthly digests: the public archive, editions, subscriptions, and compiling."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import digest
from ..countries import normalise as normalise_country
from ..digest_service import compile_month, full, summary, topic_label
from ..enums import Role
from ..errors import ApiError
from ..extensions import db
from ..models import AuditLog, Category, DigestEdition, DigestSubscription, utcnow
from ..security import current_user, login_required, roles_required
from ..validation import json_body, require_int

bp = Blueprint("digests", __name__)

#: The archive page shows this many editions at most. Months of editions for
#: every topic add up; older ones are reached by filtering on a month.
ARCHIVE_LIMIT = 200


@bp.get("/digests")
def archive():
    """Editions, newest month first. Filters: ?month=2026-09&category=technology."""
    query = db.session.query(DigestEdition, Category).join(
        Category, Category.id == DigestEdition.category_id
    )
    month = request.args.get("month")
    if month:
        try:
            digest.parse_month(month)
        except ValueError:
            raise ApiError("Month must look like 2026-09.", status=422, field="month")
        query = query.filter(DigestEdition.month == month)
    slug = request.args.get("category")
    if slug:
        query = query.filter(Category.slug == slug)

    rows = query.order_by(
        DigestEdition.month.desc(), Category.name, DigestEdition.country_code
    ).limit(ARCHIVE_LIMIT).all()
    months = [m for (m,) in db.session.query(DigestEdition.month).distinct()
              .order_by(DigestEdition.month.desc())]
    return jsonify({
        "editions": [summary(e, c) for e, c in rows],
        "months": months,
    })


@bp.get("/digests/<month>/<key>")
def edition(month: str, key: str):
    row = DigestEdition.query.filter_by(month=month, key=key).first()
    if row is None:
        raise ApiError("That digest does not exist.", status=404)
    category = db.session.get(Category, row.category_id)
    return jsonify({"edition": full(row, category, viewer=current_user())})


# --------------------------------------------------------------------------- #
#  Subscriptions
# --------------------------------------------------------------------------- #

def _subscription_view(sub: DigestSubscription, category: Category) -> dict:
    return {
        "id": sub.id,
        "category": {"id": category.id, "name": category.name, "slug": category.slug},
        "countryCode": sub.country_code or None,
        "topic": topic_label(category.name, sub.country_code),
    }


@bp.get("/digests/subscriptions")
@login_required
def my_subscriptions():
    rows = (
        db.session.query(DigestSubscription, Category)
        .join(Category, Category.id == DigestSubscription.category_id)
        .filter(DigestSubscription.user_id == g.current_user.id)
        .order_by(Category.name, DigestSubscription.country_code)
        .all()
    )
    return jsonify({"subscriptions": [_subscription_view(s, c) for s, c in rows]})


@bp.post("/digests/subscriptions")
@login_required
def subscribe():
    """Subscribe to a topic's digest, optionally for one country. Idempotent."""
    data = json_body()
    category_id = require_int(data, "categoryId", minimum=1)
    category = Category.query.filter_by(id=category_id, deleted_at=None, is_system=False).first()
    if category is None:
        raise ApiError("Choose a section.", status=422, field="categoryId")
    try:
        country = normalise_country(data.get("countryCode")) or ""
    except ValueError:
        raise ApiError("Choose a country from the list.", status=422, field="countryCode")

    sub = DigestSubscription.query.filter_by(
        user_id=g.current_user.id, category_id=category.id, country_code=country
    ).first()
    created = sub is None
    if created:
        sub = DigestSubscription(user_id=g.current_user.id, category_id=category.id,
                                 country_code=country)
        db.session.add(sub)
        db.session.commit()
    return jsonify({"subscription": _subscription_view(sub, category)}), 201 if created else 200


@bp.delete("/digests/subscriptions/<int:subscription_id>")
@login_required
def unsubscribe(subscription_id: int):
    sub = DigestSubscription.query.filter_by(
        id=subscription_id, user_id=g.current_user.id
    ).first()
    if sub is None:
        raise ApiError("Subscription not found.", status=404)
    db.session.delete(sub)
    db.session.commit()
    return "", 204


# --------------------------------------------------------------------------- #
#  Compiling (administrators; normally the monthly CLI job)
# --------------------------------------------------------------------------- #

@bp.post("/admin/digests/compile")
@roles_required(Role.SYSTEM_ADMIN)
def compile_now():
    """Compile a month on demand. Defaults to last month. `force` recompiles final editions.

    The current month may be compiled: its editions are marked in progress and
    completed by the first run after the month ends.
    """
    data = json_body()
    month = data.get("month") or digest.previous_month(utcnow())
    try:
        digest.parse_month(month)
    except ValueError:
        raise ApiError("Month must look like 2026-09.", status=422, field="month")
    if month > utcnow().strftime("%Y-%m"):
        raise ApiError("That month has not happened yet.", status=422, field="month")

    result = compile_month(month, force=bool(data.get("force")))
    db.session.add(AuditLog(
        actor_id=g.current_user.id, action="digest.compile", entity_type="digest",
        entity_id=None, detail=f"{month}: {len(result['created'])} new, "
                            f"{len(result['recompiled'])} recompiled",
        ip_address=request.remote_addr,
    ))
    db.session.commit()
    return jsonify(result)
