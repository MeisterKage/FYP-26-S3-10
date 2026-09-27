"""Payments: checkout, webhooks, and the rules that stop access being granted wrongly.

Everything that grants access runs through a verified webhook. These tests
drive the sandbox provider end to end, then attack the webhook directly:
forged signatures, replays, stale timestamps, wrong amounts, duplicates.
"""
import json
import time

import pytest

from app import payments
from app.enums import Role, SubscriptionStatus
from app.extensions import db as _db
from app.models import Notification, Payment, Subscription, User
from app.payments import SIGNATURE_HEADER, WebhookRejected, check_signature, sign
from app.security import hash_password

PASSWORD = "PaymentsTest1234!"


@pytest.fixture()
def people(app):
    writer = User(email="writer@example.com", display_name="Writer",
                  password_hash=hash_password(PASSWORD), role=Role.VERIFIED_CONTRIBUTOR)
    reader = User(email="reader@example.com", display_name="Reader",
                  password_hash=hash_password(PASSWORD), role=Role.FREE_REGISTERED)
    other = User(email="other@example.com", display_name="Other",
                 password_hash=hash_password(PASSWORD), role=Role.FREE_REGISTERED)
    _db.session.add_all([writer, reader, other])
    _db.session.commit()
    return {"writer": writer, "reader": reader, "other": other}


def auth(client, email="reader@example.com"):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def start(client, people, headers=None):
    response = client.post(f"/api/contributors/{people['writer'].id}/subscribe",
                           headers=headers or auth(client))
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def ref_of(started):
    return started["checkoutUrl"].rsplit("/", 1)[1]


def secret(app):
    return app.config["PAYMENT_WEBHOOK_SECRET"]


def event(ref, *, kind="payment.succeeded", amount=500, currency="AUD", event_id="evt_1"):
    return json.dumps({"id": event_id, "type": kind, "checkout": ref,
                       "amount": amount, "currency": currency}).encode()


def post_webhook(client, body, signature):
    return client.post("/api/payments/webhook/sandbox", data=body,
                       headers={SIGNATURE_HEADER: signature, "Content-Type": "application/json"})


def signed(app, body, ts=None):
    return sign(body, secret(app), int(ts if ts is not None else time.time()))


# =========================================================================== #
#  The happy path, through the test checkout
# =========================================================================== #

def test_subscribing_starts_a_checkout_and_grants_nothing_yet(client, people):
    started = start(client, people)
    assert started["checkoutUrl"].startswith("/checkout/test/sbx_cs_")
    payment = _db.session.get(Payment, started["paymentId"])
    assert payment.status == "pending"
    assert payment.amount_cents == 500 and payment.currency == "AUD"
    assert Subscription.query.count() == 0


def test_paying_on_the_test_checkout_activates_the_subscription(client, people):
    headers = auth(client)
    started = start(client, people, headers)
    done = client.post(f"/api/payments/sandbox/{ref_of(started)}/complete",
                       json={"outcome": "pay"}, headers=headers).get_json()

    assert done["payment"]["status"] == "succeeded"
    sub = Subscription.query.one()
    assert sub.subscriber_id == people["reader"].id
    assert sub.status == SubscriptionStatus.ACTIVE
    assert _db.session.get(User, people["reader"].id).role == Role.PREMIUM_REGISTERED
    assert Notification.query.filter_by(event_type="payment_receipt").count() == 1

    history = client.get("/api/me/payments", headers=headers).get_json()["payments"]
    assert history[0]["status"] == "succeeded"
    assert history[0]["description"] == "Monthly subscription to Writer"


def test_declining_grants_nothing_and_records_why(client, people):
    headers = auth(client)
    started = start(client, people, headers)
    done = client.post(f"/api/payments/sandbox/{ref_of(started)}/complete",
                       json={"outcome": "decline"}, headers=headers).get_json()
    assert done["payment"]["status"] == "failed"
    assert done["payment"]["failureReason"] == "Card declined."
    assert Subscription.query.count() == 0
    assert _db.session.get(User, people["reader"].id).role == Role.FREE_REGISTERED


def test_a_checkout_cannot_be_completed_twice(client, people):
    headers = auth(client)
    ref = ref_of(start(client, people, headers))
    client.post(f"/api/payments/sandbox/{ref}/complete", json={"outcome": "pay"}, headers=headers)
    again = client.post(f"/api/payments/sandbox/{ref}/complete", json={"outcome": "pay"},
                        headers=headers)
    assert again.status_code == 409
    assert Subscription.query.count() == 1


def test_someone_elses_checkout_is_not_found(client, people):
    ref = ref_of(start(client, people))
    other = auth(client, "other@example.com")
    assert client.get(f"/api/payments/sandbox/{ref}", headers=other).status_code == 404
    assert client.post(f"/api/payments/sandbox/{ref}/complete", json={"outcome": "pay"},
                       headers=other).status_code == 404


def test_the_return_page_status_is_owner_only(client, people):
    started = start(client, people)
    assert client.get(f"/api/payments/{started['paymentId']}",
                      headers=auth(client, "other@example.com")).status_code == 404


def test_paying_again_extends_rather_than_duplicates(client, people):
    headers = auth(client)
    ref = ref_of(start(client, people, headers))
    client.post(f"/api/payments/sandbox/{ref}/complete", json={"outcome": "pay"}, headers=headers)
    first_end = Subscription.query.one().period_end

    # A second checkout started before the first completed (another tab).
    second = Payment(user_id=people["reader"].id, purpose="subscription",
                     contributor_id=people["writer"].id, amount_cents=500, currency="AUD",
                     status="pending", provider="sandbox", provider_ref="sbx_cs_second")
    _db.session.add(second)
    _db.session.commit()
    client.post("/api/payments/sandbox/sbx_cs_second/complete", json={"outcome": "pay"},
                headers=headers)
    subs = Subscription.query.all()
    assert len(subs) == 1
    assert (subs[0].period_end - first_end).days == 30


# =========================================================================== #
#  Attacks on the webhook
# =========================================================================== #

def test_a_forged_signature_is_rejected(client, app, people):
    ref = ref_of(start(client, people))
    response = post_webhook(client, event(ref), sign(event(ref), "not-the-secret", int(time.time())))
    assert response.status_code == 400
    assert Subscription.query.count() == 0


def test_an_unsigned_webhook_is_rejected(client, people):
    ref = ref_of(start(client, people))
    response = client.post("/api/payments/webhook/sandbox", data=event(ref))
    assert response.status_code == 400


def test_a_tampered_body_is_rejected(client, app, people):
    ref = ref_of(start(client, people))
    signature = signed(app, event(ref, amount=500))
    response = post_webhook(client, event(ref, amount=1), signature)
    assert response.status_code == 400


def test_a_replayed_old_webhook_is_rejected(client, app, people):
    ref = ref_of(start(client, people))
    body = event(ref)
    response = post_webhook(client, body, signed(app, body, ts=time.time() - 3600))
    assert response.status_code == 400
    assert Subscription.query.count() == 0


def test_a_correctly_signed_event_for_the_wrong_amount_is_rejected(client, app, people):
    """Even a genuine provider event must match what this server charged."""
    ref = ref_of(start(client, people))
    body = event(ref, amount=1)
    assert post_webhook(client, body, signed(app, body)).status_code == 400
    assert Subscription.query.count() == 0


def test_a_duplicate_delivery_is_applied_once(client, app, people):
    ref = ref_of(start(client, people))
    body = event(ref, event_id="evt_same")
    assert post_webhook(client, body, signed(app, body)).get_json()["status"] == "succeeded"
    assert post_webhook(client, body, signed(app, body)).get_json()["status"] == "duplicate"
    assert Subscription.query.count() == 1


def test_an_event_for_an_unknown_order_is_rejected(client, app, people):
    body = event("sbx_cs_nobody")
    assert post_webhook(client, body, signed(app, body)).status_code == 400


def test_a_refund_ends_access(client, app, people):
    headers = auth(client)
    ref = ref_of(start(client, people, headers))
    client.post(f"/api/payments/sandbox/{ref}/complete", json={"outcome": "pay"}, headers=headers)
    body = event(ref, kind="refund.succeeded", event_id="evt_refund")
    assert post_webhook(client, body, signed(app, body)).get_json()["status"] == "refunded"
    assert Subscription.query.one().status == SubscriptionStatus.CANCELLED
    assert _db.session.get(User, people["reader"].id).has_premium_access() is False


# =========================================================================== #
#  Signatures and providers
# =========================================================================== #

def test_signature_check_is_exact():
    body = b'{"x":1}'
    now = 1_700_000_000
    check_signature(body, sign(body, "s", now), "s", now=now)
    for bad in (None, "", "t=abc,v1=00", "v1=00", sign(body, "s", now).replace("v1=", "v1=0")):
        with pytest.raises(WebhookRejected):
            check_signature(body, bad, "s", now=now)


def test_stripe_is_a_framework_that_refuses_to_run_unfinished(client, app, people):
    app.config["PAYMENT_PROVIDER"] = "stripe"
    response = client.post(f"/api/contributors/{people['writer'].id}/subscribe",
                           headers=auth(client))
    assert response.status_code == 503
    assert "not been charged" in response.get_json()["error"]["message"]
    assert Payment.query.one().status == "failed"


def test_the_test_checkout_disappears_when_a_real_provider_is_configured(client, app, people):
    ref = ref_of(start(client, people))
    app.config["PAYMENT_PROVIDER"] = "stripe"
    assert client.get(f"/api/payments/sandbox/{ref}", headers=auth(client)).status_code == 404


def test_the_price_comes_from_the_server_not_the_request(client, people):
    response = client.post(f"/api/contributors/{people['writer'].id}/subscribe",
                           json={"amountCents": 1}, headers=auth(client))
    assert _db.session.get(Payment, response.get_json()["paymentId"]).amount_cents == 500
