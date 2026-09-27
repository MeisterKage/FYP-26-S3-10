"""Payment providers, behind one interface.

Every real provider (Stripe, PayPal, Square, Adyen) follows the same shape, and
this module is built to it so that swapping providers means writing one class:

  1. Our server creates the order and sets the price. The browser never says
     how much something costs.
  2. The buyer is sent to the provider's hosted checkout page. Card details
     go to the provider and never touch this server, which keeps the platform
     out of scope for most of the card industry's security standard (PCI DSS).
  3. The provider tells our server the outcome by webhook, a signed request we
     verify. Only then is anything switched on. The page the buyer returns to
     afterwards is never trusted on its own: anyone can visit a "success" URL.

Two providers are here:

  * SandboxProvider works end to end with no real money. Its checkout page is
    part of this site and is labelled as a test. Its webhooks are signed and
    verified exactly as a real provider's would be.
  * StripeProvider is the framework for going live: the interface implemented
    as a documented skeleton. It refuses to run until it is completed and
    configured, and says so, rather than pretending.

Which one is used is configuration (PAYMENT_PROVIDER), not code.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from flask import current_app

log = logging.getLogger(__name__)

#: A webhook older than this is refused even with a valid signature, so a
#: captured request cannot be replayed later.
WEBHOOK_TOLERANCE_SECONDS = 300


class ProviderError(Exception):
    """The provider could not be reached or refused the request. Nothing was charged."""


class ProviderNotConfigured(ProviderError):
    """The configured provider is not set up on this deployment."""


class WebhookRejected(Exception):
    """A webhook failed verification. Never acted on."""


@dataclass(frozen=True)
class CheckoutRequest:
    payment_id: int
    amount_cents: int
    currency: str
    description: str
    customer_email: str
    success_url: str
    cancel_url: str


@dataclass(frozen=True)
class Checkout:
    #: The provider's id for this checkout; how its webhook refers back to it.
    provider_ref: str
    #: Where to send the buyer to pay.
    redirect_url: str


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    #: "payment.succeeded", "payment.failed" or "refund.succeeded"
    kind: str
    provider_ref: str
    amount_cents: int
    currency: str
    failure_reason: str | None = None


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def create_checkout(self, request: CheckoutRequest) -> Checkout:
        """Start a hosted checkout. Raises ProviderError."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers) -> PaymentEvent:
        """Check a webhook's signature and freshness and parse it. Raises WebhookRejected."""

    @abstractmethod
    def refund(self, provider_ref: str, amount_cents: int) -> str:
        """Refund a completed payment. Returns the refund reference. Raises ProviderError."""

    @abstractmethod
    def payout(self, contributor_id: int, amount_cents: int) -> str:
        """Pay a writer their share. Returns the transfer reference. Raises ProviderError."""


# --------------------------------------------------------------------------- #
#  Signatures: the same scheme real providers use
# --------------------------------------------------------------------------- #

def sign(body: bytes, secret: str, timestamp: int) -> str:
    """HMAC-SHA256 over "timestamp.body", in the header format Stripe uses."""
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def check_signature(body: bytes, header: str | None, secret: str, now: float | None = None) -> None:
    if not header:
        raise WebhookRejected("Missing signature.")
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        given = parts["v1"]
    except (ValueError, KeyError):
        raise WebhookRejected("Malformed signature.")
    now = time.time() if now is None else now
    if abs(now - timestamp) > WEBHOOK_TOLERANCE_SECONDS:
        raise WebhookRejected("Signature too old.")
    expected = sign(body, secret, timestamp).split("v1=")[1]
    # Constant-time: comparing byte by byte would leak how much was right.
    if not hmac.compare_digest(expected, given):
        raise WebhookRejected("Signature does not match.")


# --------------------------------------------------------------------------- #
#  Sandbox
# --------------------------------------------------------------------------- #

SIGNATURE_HEADER = "Payment-Signature"


class SandboxProvider(PaymentProvider):
    """Works end to end with no money. For development, tests and demonstrations."""

    name = "sandbox"

    def __init__(self, secret: str):
        self.secret = secret

    def create_checkout(self, request: CheckoutRequest) -> Checkout:
        ref = f"sbx_cs_{secrets.token_hex(12)}"
        log.info("[payment:sandbox] checkout %s for payment %s, %s %s",
                 ref, request.payment_id, request.amount_cents, request.currency)
        return Checkout(provider_ref=ref, redirect_url=f"/checkout/test/{ref}")

    def event_for(self, provider_ref: str, *, succeeded: bool, amount_cents: int,
                  currency: str) -> tuple[bytes, dict]:
        """What the sandbox 'provider' sends back when the buyer clicks pay or decline.

        Returns a signed body and headers, which go through verify_webhook like
        any real provider's request would.
        """
        body = json.dumps({
            "id": f"sbx_evt_{secrets.token_hex(12)}",
            "type": "payment.succeeded" if succeeded else "payment.failed",
            "checkout": provider_ref,
            "amount": amount_cents,
            "currency": currency,
            "failure_reason": None if succeeded else "Card declined.",
        }).encode()
        return body, {SIGNATURE_HEADER: sign(body, self.secret, int(time.time()))}

    def verify_webhook(self, body: bytes, headers) -> PaymentEvent:
        check_signature(body, headers.get(SIGNATURE_HEADER), self.secret)
        try:
            data = json.loads(body)
            return PaymentEvent(
                event_id=str(data["id"]),
                kind=str(data["type"]),
                provider_ref=str(data["checkout"]),
                amount_cents=int(data["amount"]),
                currency=str(data["currency"]),
                failure_reason=data.get("failure_reason"),
            )
        except (ValueError, KeyError, TypeError):
            raise WebhookRejected("Malformed event.")

    def refund(self, provider_ref: str, amount_cents: int) -> str:
        log.info("[payment:sandbox] refund %s of %s", provider_ref, amount_cents)
        return f"sbx_re_{secrets.token_hex(8)}"

    def payout(self, contributor_id: int, amount_cents: int) -> str:
        log.info("[payment:sandbox] payout to %s of %s", contributor_id, amount_cents)
        return f"sbx_tr_{secrets.token_hex(8)}"


# --------------------------------------------------------------------------- #
#  Stripe: the framework for going live
# --------------------------------------------------------------------------- #

class StripeProvider(PaymentProvider):
    """Skeleton for Stripe. Not functional until completed; see docs/payments.md.

    Each method names the Stripe call it needs. Completing it means making
    those calls (the official `stripe` package, or HTTPS to api.stripe.com with
    the secret key) and mapping the responses to this module's types. Nothing
    else in the application changes: subscriptions, access checks and payment
    history all work through the interface above.

    Configuration (Render environment, never committed):
        PAYMENT_PROVIDER=stripe
        STRIPE_SECRET_KEY=sk_live_... or sk_test_...
        STRIPE_WEBHOOK_SECRET=whsec_...   (from the webhook endpoint in Stripe)
    """

    name = "stripe"

    def __init__(self, secret_key: str | None, webhook_secret: str | None):
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret

    def _not_ready(self):
        raise ProviderNotConfigured(
            "Card payments are not switched on for this site yet."
        )

    def create_checkout(self, request: CheckoutRequest) -> Checkout:
        # POST /v1/checkout/sessions with mode=payment, one line item of
        # request.amount_cents in request.currency, client_reference_id =
        # request.payment_id, customer_email, success_url and cancel_url.
        # Return Checkout(provider_ref=session.id, redirect_url=session.url).
        self._not_ready()

    def verify_webhook(self, body: bytes, headers) -> PaymentEvent:
        # Stripe signs with the same "t=...,v1=..." scheme as check_signature
        # above, in the Stripe-Signature header, using STRIPE_WEBHOOK_SECRET.
        # Map checkout.session.completed to payment.succeeded,
        # checkout.session.async_payment_failed and checkout.session.expired to
        # payment.failed, and charge.refunded to refund.succeeded.
        if not self.webhook_secret:
            raise WebhookRejected("Stripe webhooks are not configured.")
        check_signature(body, headers.get("Stripe-Signature"), self.webhook_secret)
        raise WebhookRejected("Stripe event mapping is not implemented yet.")

    def refund(self, provider_ref: str, amount_cents: int) -> str:
        # POST /v1/refunds with the session's payment_intent and amount.
        self._not_ready()

    def payout(self, contributor_id: int, amount_cents: int) -> str:
        # Requires Stripe Connect: each writer onboards a connected account,
        # then POST /v1/transfers with amount and destination=that account.
        self._not_ready()


def provider() -> PaymentProvider:
    """The provider this deployment is configured for."""
    cfg = current_app.config
    name = cfg.get("PAYMENT_PROVIDER", "sandbox")
    if name == "sandbox":
        return SandboxProvider(cfg["PAYMENT_WEBHOOK_SECRET"])
    if name == "stripe":
        return StripeProvider(cfg.get("STRIPE_SECRET_KEY"), cfg.get("STRIPE_WEBHOOK_SECRET"))
    raise ProviderNotConfigured(f"Unknown payment provider '{name}'.")
