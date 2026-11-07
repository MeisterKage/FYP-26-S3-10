"""Notification Service (PDD Section 2.2).

Notifications are written to the database by whichever module triggers them, so
the bell always has them. Email delivery is a separate step: PRD 5.1 requires
queueing within 60 seconds of the trigger, which `dispatch_pending` performs.

v1 runs `dispatch_pending` from the CLI (`flask dispatch-notifications`). Moving
it to a scheduler is a deployment change, not a code change.
"""
from __future__ import annotations

import logging

from flask import Blueprint, g, jsonify
from sqlalchemy.exc import SQLAlchemyError

from ..errors import ApiError
from ..extensions import db
from ..integrations import email_service
from ..models import Notification, NotificationPreference, User, utcnow
from ..security import login_required

bp = Blueprint("notifications", __name__)

log = logging.getLogger(__name__)


@bp.get("/notifications")
@login_required
def list_notifications():
    rows = (
        Notification.query.filter_by(user_id=g.current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(
        {
            "unreadCount": sum(1 for n in rows if n.read_at is None),
            "notifications": [
                {
                    "id": n.id,
                    "type": n.event_type,
                    "title": n.title,
                    "body": n.body,
                    "link": n.link,
                    "read": n.read_at is not None,
                    "createdAt": n.created_at.isoformat(),
                }
                for n in rows
            ],
        }
    )


@bp.post("/notifications/<int:notification_id>/read")
@login_required
def mark_read(notification_id: int):
    notification = Notification.query.filter_by(
        id=notification_id, user_id=g.current_user.id
    ).first()
    if notification is None:
        raise ApiError("Notification not found.", status=404)

    notification.read_at = notification.read_at or utcnow()
    db.session.commit()
    return jsonify({"read": True})


@bp.post("/notifications/read-all")
@login_required
def mark_all_read():
    now = utcnow()
    Notification.query.filter_by(user_id=g.current_user.id, read_at=None).update(
        {"read_at": now}
    )
    db.session.commit()
    return jsonify({"read": True})


def dispatch_pending(limit: int = 200) -> int:
    """Email every notification not yet dispatched, honouring per-user toggles.

    Returns the number sent. A user who has switched an event type off gets the
    in-app notification but no email; the toggle governs delivery, not the record.
    """
    pending = (
        Notification.query.filter_by(emailed_at=None)
        .order_by(Notification.created_at.asc())
        .limit(limit)
        .all()
    )

    sent = 0
    failed = 0

    for notification in pending:
        #One bad address must not abort the batch. Without this, a single
        #provider error leaves every later notification unsent, and the whole
        #run is lost because the commit below never happens.
        try:
            user = User.query.get(notification.user_id)
            if user is None or not user.is_active:
                notification.emailed_at = utcnow()  #do not retry forever
                continue

            preference = NotificationPreference.query.filter_by(
                user_id=user.id, event_type=notification.event_type
            ).first()
            if preference is not None and not preference.enabled:
                notification.emailed_at = utcnow()
                continue

            if email_service.send(
                to=user.email, subject=notification.title, body=notification.body or ""
            ):
                notification.emailed_at = utcnow()
                sent += 1
        except Exception:  # noqa: BLE001 - one failure must not stop the queue
            failed += 1
            #emailed_at is left unset, so the next run retries this one.
            log.exception("Could not dispatch notification %s", notification.id)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Could not record notification dispatch results")
        return 0

    if failed:
        log.warning("%s notification(s) failed and will be retried", failed)
    return sent
