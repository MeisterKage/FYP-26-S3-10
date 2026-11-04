# Payments: how they work, and connecting a real provider

Wollongong News takes payments through a provider interface (`backend/app/payments.py`). The live site uses the **sandbox provider**, which runs the whole flow with no real money. Going live means completing the **Stripe adapter** and setting three environment variables. Nothing else in the application changes.

## How a payment works

1. **A reader clicks Subscribe.** The server creates an order (`payments` table) and sets the price itself (US$5.00 a month). The browser is never trusted to say how much something costs.
2. **The reader is sent to the provider's checkout page.** Card details go to the provider and never reach this server. That keeps the platform out of scope for most of the card industry's security standard (PCI DSS).
3. **The provider reports the outcome by webhook** to `POST /api/payments/webhook/<provider>`. The server:
   - checks the signature (HMAC-SHA256, the scheme Stripe uses) and rejects anything unsigned, altered, or more than five minutes old;
   - checks the amount and currency against the order it created;
   - records the event id, so a webhook the provider sends twice is applied once.
4. **Only then is the subscription switched on.** The page the reader returns to (`/checkout/result`) asks the server what happened. It never grants access itself, because anyone can visit a "success" address.

A declined payment grants nothing. A refund ends access immediately. If the provider can't be reached, the reader is told they haven't been charged.

## The sandbox provider

`PAYMENT_PROVIDER=sandbox` (the default). The checkout page is part of the site (`/checkout/test/<ref>`), is labelled as a test, and has no card fields. Its **Pay** and **Decline** buttons create the event the provider would send, sign it, and pass it through the same webhook verification as a real provider's request. The sandbox routes return "not found" whenever a real provider is configured.

## Connecting Stripe

`StripeProvider` in `backend/app/payments.py` is a skeleton. Each method names the Stripe call it needs, and until it is completed it refuses to run and tells the reader card payments aren't switched on yet.

1. **Complete the four methods**, using the official `stripe` Python package (add it to `requirements.txt`):
   - `create_checkout`: create a Checkout Session (`mode=payment`) with one line item for the order amount. Set `client_reference_id` to the payment id, and use the success and cancel URLs passed in. Return the session id and its URL.
   - `verify_webhook`: the signature check is already written. Map `checkout.session.completed` to `payment.succeeded`; `checkout.session.async_payment_failed` and `checkout.session.expired` to `payment.failed`; `charge.refunded` to `refund.succeeded`.
   - `refund`: create a Refund for the session's payment intent.
   - `payout`: needs **Stripe Connect**. Each writer onboards a connected account, then a Transfer pays them their share.
2. **In the Stripe dashboard**, add a webhook endpoint pointing at `https://fyp-26-s3-10-api.onrender.com/api/payments/webhook/stripe`, subscribed to the events above.
3. **In the Render dashboard** (fyp-26-s3-10-api, Environment), set:
   - `PAYMENT_PROVIDER=stripe`
   - `STRIPE_SECRET_KEY`: the secret key (`sk_test_...` while testing)
   - `STRIPE_WEBHOOK_SECRET`: the endpoint's signing secret (`whsec_...`)

   Never commit these to the repository.
4. **Test with Stripe's test mode** and its test card numbers before switching to live keys.

## Adding another provider

Write a class implementing `PaymentProvider` (`create_checkout`, `verify_webhook`, `refund`, `payout`) and add it to `provider()` in `backend/app/payments.py`. Subscriptions, access checks and payment history all work through the interface.

## What is not built

- Automatic monthly renewal. Each payment currently buys 30 days, and a reader pays again to continue. A real provider's subscription billing (Stripe Billing, for example) would send a `payment.succeeded` webhook each month, which the existing handler already turns into an extended subscription.
- An administrator refund button. The provider interface and the webhook handle refunds; nothing in the admin console calls them yet.
- Writer payouts through the provider. Earnings are calculated and shown; transferring money requires Stripe Connect.
