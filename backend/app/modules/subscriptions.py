"""Subscription and Revenue-Share (PDD Section 2.2).

Covers PDD Figures 5.14, 5.24, 5.37-5.39, 5.47.

Billing goes through the PaymentGateway stub in `integrations.py`. Nothing here
touches a real payment provider, and the seam is deliberate -- swapping in Stripe
later replaces one class.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from ..enums import AUTHORING_ROLES, Role, SubscriptionStatus
from ..errors import ApiError
from ..extensions import db
from ..integrations import payment_gateway, revenue_tier_for
from ..models import Payout, Subscription, User, utcnow
from ..security import login_required, roles_required
from ..validation import json_body

bp = Blueprint("subscriptions", __name__)

#: Flat monthly price in cents for v1. Per-contributor pricing is a later step.
DEFAULT_PRICE_CENTS = 500


@bp.get("/me/subscription")
@login_required
def my_subscription():
    """PDD Figures 5.14 / 5.38."""
    now = utcnow()
    active = [
        s for s in g.current_user.subscriptions
        if s.status == SubscriptionStatus.ACTIVE and s.period_end > now
    ]
    return jsonify(
        {
            "hasPremiumAccess": bool(active),
            "subscriptions": [
                {
                    "id": s.id,
                    "contributorId": s.contributor_id,
                    "status": s.status.value,
                    "periodEnd": s.period_end.isoformat(),
                    "priceCents": s.price_cents,
                }
                for s in active
            ],
        }
    )


@bp.post("/contributors/<int:contributor_id>/subscribe")
@login_required
def subscribe(contributor_id: int):
    """PDD Figure 5.37."""
    contributor = User.query.filter_by(id=contributor_id, deleted_at=None).first()
    if contributor is None or contributor.role not in AUTHORING_ROLES:
        raise ApiError("That contributor does not offer a premium tier.", status=404)
    if contributor_id == g.current_user.id:
        raise ApiError("You cannot subscribe to yourself.", status=422)

    now = utcnow()
    existing = Subscription.query.filter_by(
        subscriber_id=g.current_user.id,
        contributor_id=contributor_id,
        status=SubscriptionStatus.ACTIVE,
    ).first()
    if existing and existing.period_end > now:
        raise ApiError("You are already subscribed to this contributor.", status=409)

    try:
        charge = payment_gateway.charge(
            user_id=g.current_user.id,
            amount_cents=DEFAULT_PRICE_CENTS,
            description=f"Premium subscription to contributor {contributor_id}",
        )
    except Exception:  # noqa: BLE001 - a provider outage is not a bug in our code
        current_app.logger.exception("Payment gateway unreachable")
        raise ApiError(
            "We could not reach the payment provider. You have not been charged.",
            status=503,
        ) from None

    if not charge.ok:
        raise ApiError(charge.message or "Payment could not be completed.", status=402)

    db.session.add(
        Subscription(
            subscriber_id=g.current_user.id,
            contributor_id=contributor_id,
            price_cents=DEFAULT_PRICE_CENTS,
            period_start=now,
            period_end=now + timedelta(days=30),
            gateway_ref=charge.reference,
        )
    )

    # PDD lists PREMIUM_REGISTERED as a tier, but access itself is always checked
    # against the live subscription -- see security.premium_required.
    if g.current_user.role == Role.FREE_REGISTERED:
        g.current_user.role = Role.PREMIUM_REGISTERED

    try:
        db.session.commit()
    except SQLAlchemyError:
        # The charge succeeded but the record did not save. Letting the generic
        # handler turn this into "Something went wrong." would strand a real
        # payment with nothing pointing at it, so the gateway reference goes to
        # the log at CRITICAL and into the user's hands.
        db.session.rollback()
        current_app.logger.critical(
            "PAYMENT TAKEN BUT SUBSCRIPTION NOT SAVED. user=%s contributor=%s ref=%s",
            g.current_user.id, contributor_id, charge.reference,
        )
        raise ApiError(
            "Your payment went through but we could not activate the subscription. "
            f"Please contact support quoting reference {charge.reference}.",
            status=500,
        ) from None

    return jsonify({"message": "Subscription active.", "reference": charge.reference}), 201


@bp.delete("/subscriptions/<int:subscription_id>")
@login_required
def unsubscribe(subscription_id: int):
    """PDD Figure 5.39. Access continues until the paid period ends."""
    subscription = Subscription.query.filter_by(
        id=subscription_id, subscriber_id=g.current_user.id
    ).first()
    if subscription is None:
        raise ApiError("Subscription not found.", status=404)
    if subscription.status != SubscriptionStatus.ACTIVE:
        raise ApiError("This subscription is not active.", status=409)

    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = utcnow()
    db.session.commit()

    return jsonify(
        {
            "message": "Subscription cancelled.",
            "accessUntil": subscription.period_end.isoformat(),
        }
    )


@bp.get("/me/earnings")
@roles_required(*AUTHORING_ROLES)
def earnings_dashboard():
    """PDD Figure 5.47: payouts, current revenue-share tier, time remaining on it."""
    now = utcnow()

    subscriber_count = (
        db.session.query(func.count(Subscription.id))
        .filter(
            Subscription.contributor_id == g.current_user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.period_end > now,
        )
        .scalar()
        or 0
    )
    tier_name, platform_share = revenue_tier_for(subscriber_count)

    gross_cents = (
        db.session.query(func.coalesce(func.sum(Subscription.price_cents), 0))
        .filter(
            Subscription.contributor_id == g.current_user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.period_end > now,
        )
        .scalar()
        or 0
    )

    payouts = (
        Payout.query.filter_by(contributor_id=g.current_user.id)
        .order_by(Payout.period_end.desc())
        .limit(12)
        .all()
    )

    return jsonify(
        {
            "subscriberCount": subscriber_count,
            "revenueTier": tier_name,
            "platformSharePercent": round(platform_share * 100),
            "currentPeriod": {
                "grossCents": gross_cents,
                "estimatedNetCents": round(gross_cents * (1 - platform_share)),
            },
            "payouts": [
                {
                    "periodEnd": p.period_end.isoformat(),
                    "grossCents": p.gross_cents,
                    "netCents": p.net_cents,
                    "tier": p.revenue_tier,
                    "paid": p.paid_at is not None,
                }
                for p in payouts
            ],
        }
    )
