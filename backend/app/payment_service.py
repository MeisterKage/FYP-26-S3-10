"""The checkout flow and webhook processing, independent of which provider is used.

Access is granted in exactly one place, `_apply`, and only for a verified
webhook whose amount and currency match an order this server created. The page
a buyer returns to after checkout grants nothing.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from .enums import Role, SubscriptionStatus
from .extensions import db
from .models import (
    AuditLog, Notification, Payment, PaymentWebhookEvent, Subscription, User, utcnow,
)
from .payments import (
    CheckoutRequest, PaymentEvent, ProviderError, WebhookRejected, provider,
)

#: Flat monthly price for a writer's premium tier. Per-writer pricing is a later step.
SUBSCRIPTION_PRICE_CENTS = 500
CURRENCY = "AUD"
SUBSCRIPTION_DAYS = 30


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def start_subscription_checkout(user: User, contributor: User) -> tuple[Payment, str]:
    """Create the order and the provider checkout. Returns (payment, where to send the buyer).

    Raises ProviderError if the provider cannot be reached; the order is then
    recorded as failed and nothing has been charged.
    """
    gateway = provider()
    payment = Payment(
        user_id=user.id,
        purpose="subscription",
        contributor_id=contributor.id,
        amount_cents=SUBSCRIPTION_PRICE_CENTS,
        currency=CURRENCY,
        status="pending",
        provider=gateway.name,
    )
    db.session.add(payment)
    db.session.flush()

    try:
        checkout = gateway.create_checkout(CheckoutRequest(
            payment_id=payment.id,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            description=f"Monthly subscription to {contributor.byline}",
            customer_email=user.email,
            success_url=f"/checkout/result?payment={payment.id}",
            cancel_url=f"/contributors/{contributor.id}",
        ))
    except ProviderError as e:
        payment.status = "failed"
        payment.failure_reason = str(e)[:300]
        db.session.commit()
        raise

    payment.provider_ref = checkout.provider_ref
    db.session.commit()
    return payment, checkout.redirect_url


def process_webhook(provider_name: str, body: bytes, headers) -> dict:
    """Verify and apply one provider event. Commits. Raises WebhookRejected.

    Safe to call any number of times with the same event: the event id is
    recorded under a unique constraint, and a repeat is acknowledged without
    being applied again.
    """
    gateway = provider()
    if gateway.name != provider_name:
        raise WebhookRejected("Webhook for a provider this site does not use.")
    event = gateway.verify_webhook(body, headers)

    if PaymentWebhookEvent.query.filter_by(provider=gateway.name, event_id=event.event_id).first():
        return {"status": "duplicate"}

    payment = Payment.query.filter_by(provider=gateway.name, provider_ref=event.provider_ref).first()
    if payment is None:
        raise WebhookRejected("No order matches this event.")
    if event.amount_cents != payment.amount_cents or event.currency.upper() != payment.currency:
        # Never trust the amount in the event: check it against what we charged.
        current_app.logger.critical(
            "Payment webhook amount mismatch: payment=%s expected=%s %s got=%s %s",
            payment.id, payment.amount_cents, payment.currency,
            event.amount_cents, event.currency,
        )
        raise WebhookRejected("Amount does not match the order.")

    db.session.add(PaymentWebhookEvent(
        provider=gateway.name, event_id=event.event_id, kind=event.kind, payment_id=payment.id,
    ))
    try:
        # Claim the event before acting on it. Two deliveries racing each
        # other cannot both pass the unique constraint.
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return {"status": "duplicate"}

    result = _apply(payment, event, utcnow())
    db.session.commit()
    return result


def _apply(payment: Payment, event: PaymentEvent, now: datetime) -> dict:
    if event.kind == "payment.succeeded":
        if payment.status != "pending":
            return {"status": "ignored", "reason": f"payment already {payment.status}"}
        payment.status = "succeeded"
        payment.completed_at = now
        subscription = _activate_subscription(payment, now)
        payment.subscription_id = subscription.id
        db.session.add(Notification(
            user_id=payment.user_id,
            event_type="payment_receipt",
            title="Payment received",
            body=f"A${payment.amount_cents / 100:.2f} for a monthly subscription. "
                 f"Access runs until {_aware(subscription.period_end):%d %B %Y}.",
            link="/account",
        ))
        db.session.add(AuditLog(
            actor_id=payment.user_id, action="payment.succeeded", entity_type="payment",
            entity_id=payment.id, detail=payment.provider_ref,
        ))
        return {"status": "succeeded", "subscriptionId": subscription.id}

    if event.kind == "payment.failed":
        if payment.status != "pending":
            return {"status": "ignored", "reason": f"payment already {payment.status}"}
        payment.status = "failed"
        payment.completed_at = now
        payment.failure_reason = (event.failure_reason or "The payment was not completed.")[:300]
        return {"status": "failed"}

    if event.kind == "refund.succeeded":
        if payment.status != "succeeded":
            return {"status": "ignored", "reason": f"payment is {payment.status}"}
        payment.status = "refunded"
        if payment.subscription_id:
            sub = db.session.get(Subscription, payment.subscription_id)
            if sub is not None:
                sub.status = SubscriptionStatus.CANCELLED
                sub.cancelled_at = now
                sub.period_end = min(_aware(sub.period_end), now)
        return {"status": "refunded"}

    return {"status": "ignored", "reason": f"unhandled event {event.kind}"}


def _activate_subscription(payment: Payment, now: datetime) -> Subscription:
    """Start a subscription, or extend the current one if the buyer already has it."""
    existing = Subscription.query.filter_by(
        subscriber_id=payment.user_id,
        contributor_id=payment.contributor_id,
        status=SubscriptionStatus.ACTIVE,
    ).first()
    if existing is not None and _aware(existing.period_end) > now:
        # Paid twice (two tabs, say): the second payment buys the next period
        # rather than vanishing.
        existing.period_end = _aware(existing.period_end) + timedelta(days=SUBSCRIPTION_DAYS)
        existing.gateway_ref = payment.provider_ref
        return existing

    subscription = Subscription(
        subscriber_id=payment.user_id,
        contributor_id=payment.contributor_id,
        price_cents=payment.amount_cents,
        period_start=now,
        period_end=now + timedelta(days=SUBSCRIPTION_DAYS),
        gateway_ref=payment.provider_ref,
    )
    db.session.add(subscription)
    db.session.flush()

    # The role label follows payment; access itself is always checked against
    # the live subscription (security.premium_required).
    user = db.session.get(User, payment.user_id)
    if user.role == Role.FREE_REGISTERED:
        user.role = Role.PREMIUM_REGISTERED
    return subscription


def serialize(payment: Payment) -> dict:
    contributor = db.session.get(User, payment.contributor_id) if payment.contributor_id else None
    return {
        "id": payment.id,
        "purpose": payment.purpose,
        "description": (
            f"Monthly subscription to {contributor.byline}" if contributor else payment.purpose
        ),
        "contributorId": payment.contributor_id,
        "amountCents": payment.amount_cents,
        "currency": payment.currency,
        "status": payment.status,
        "provider": payment.provider,
        "reference": payment.provider_ref,
        "failureReason": payment.failure_reason,
        "createdAt": payment.created_at.isoformat(),
        "completedAt": payment.completed_at.isoformat() if payment.completed_at else None,
    }
