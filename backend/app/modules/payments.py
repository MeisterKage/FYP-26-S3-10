"""Payments: the provider webhook, order status, history, and the sandbox checkout.

The webhook is the only route that grants anything, and it acts only on a
signed event matching an order this server created. The sandbox checkout
routes stand in for a provider's hosted checkout page: they exist only while
the sandbox provider is configured, and they feed the same webhook path.
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError
from ..extensions import db
from ..models import Payment, User
from ..payment_service import process_webhook, serialize
from ..payments import SandboxProvider, WebhookRejected, provider
from ..ratelimit import client_address, limiter
from ..security import login_required
from ..validation import json_body, require_choice

bp = Blueprint("payments", __name__)


@bp.post("/payments/webhook/<provider_name>")
@limiter.limit("120 per minute", key_func=client_address)
def webhook(provider_name: str):
    """Where the provider reports outcomes. Public: the signature is the authentication."""
    try:
        result = process_webhook(provider_name, request.get_data(), request.headers)
    except WebhookRejected as e:
        current_app.logger.warning("Rejected payment webhook from %s: %s",
                                   client_address(), e)
        # 400 tells a real provider to stop retrying a request that will never
        # verify; it gives an attacker nothing they did not send.
        raise ApiError("Webhook rejected.", status=400)
    return jsonify({"received": True, **result})


def _own_payment(payment_id: int) -> Payment:
    payment = Payment.query.filter_by(id=payment_id, user_id=g.current_user.id).first()
    if payment is None:
        raise ApiError("Payment not found.", status=404)
    return payment


@bp.get("/payments/<int:payment_id>")
@login_required
def payment_status(payment_id: int):
    """Polled by the page a buyer returns to. Reports; never grants."""
    return jsonify({"payment": serialize(_own_payment(payment_id))})


@bp.get("/me/payments")
@login_required
def payment_history():
    rows = (
        Payment.query.filter_by(user_id=g.current_user.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"payments": [serialize(p) for p in rows]})


# --------------------------------------------------------------------------- #
#  Sandbox checkout: stands in for a provider's hosted page
# --------------------------------------------------------------------------- #

def _sandbox_payment(ref: str) -> Payment:
    if not isinstance(provider(), SandboxProvider):
        raise ApiError("Test checkout is not available on this site.", status=404)
    payment = Payment.query.filter_by(
        provider="sandbox", provider_ref=ref, user_id=g.current_user.id
    ).first()
    if payment is None:
        raise ApiError("Checkout not found.", status=404)
    return payment


@bp.get("/payments/sandbox/<ref>")
@login_required
def sandbox_checkout(ref: str):
    payment = _sandbox_payment(ref)
    contributor = db.session.get(User, payment.contributor_id)
    return jsonify({
        "payment": serialize(payment),
        "merchant": "Wollongong News",
        "item": f"Monthly subscription to {contributor.byline}",
    })


@bp.post("/payments/sandbox/<ref>/complete")
@login_required
def sandbox_complete(ref: str):
    """The buyer clicked Pay or Decline on the test checkout.

    Builds the event the sandbox provider would send, signs it, and passes it
    through the same verification and processing as any real webhook.
    """
    payment = _sandbox_payment(ref)
    if payment.status != "pending":
        raise ApiError(f"This payment is already {payment.status}.", status=409)
    outcome = require_choice(json_body(), "outcome", ("pay", "decline"))

    gateway = provider()
    body, headers = gateway.event_for(
        ref, succeeded=outcome == "pay",
        amount_cents=payment.amount_cents, currency=payment.currency,
    )
    process_webhook(gateway.name, body, headers)
    db.session.refresh(payment)
    return jsonify({"payment": serialize(payment),
                    "returnUrl": f"/checkout/result?payment={payment.id}"})
