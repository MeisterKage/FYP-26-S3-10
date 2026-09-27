/**
 * Checkout: the test provider's checkout page, the page a buyer returns to,
 * and a reader's payment history.
 *
 * With a real provider the checkout page is the provider's own site, and card
 * details never reach this application. The test page stands in for it, so it
 * has no card fields at all, and says plainly that it is a test.
 *
 * The result page reports; it never grants. Access starts when the provider's
 * webhook reaches the server, so this page asks the server what happened
 * rather than assuming success from having been reached.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { Button, Empty, Notice, formatDate } from "../components/UI";

export function money(cents, currency = "AUD") {
  return new Intl.NumberFormat("en-AU", { style: "currency", currency }).format(cents / 100);
}

/** Start a subscription checkout and go to it. Shared by the profile and the paywall. */
export async function startSubscription(contributorId, navigate) {
  const { checkoutUrl } = await api.post(`/contributors/${contributorId}/subscribe`);
  if (checkoutUrl.startsWith("/")) navigate(checkoutUrl);
  else window.location.assign(checkoutUrl); // a real provider's hosted page
}

export function CheckoutTest() {
  const { ref } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    api.get(`/payments/sandbox/${ref}`).then(setOrder).catch((e) => setError(e.message));
  }, [ref]);

  async function complete(outcome) {
    setBusy(outcome);
    setError(null);
    try {
      const result = await api.post(`/payments/sandbox/${ref}/complete`, { outcome });
      navigate(result.returnUrl, { replace: true });
    } catch (e) {
      setError(e.message);
      setBusy(null);
    }
  }

  if (error && !order) return <Notice>{error}</Notice>;
  if (!order) return <div className="skeleton" style={{ height: "16rem" }} />;

  const p = order.payment;
  const done = p.status !== "pending";

  return (
    <div className="checkout">
      <p className="checkout-banner" role="note">
        Test checkout. No real payment is taken and no card details are asked for.
        A live site sends you to the payment provider&rsquo;s own page instead.
      </p>

      <div className="checkout-card">
        <p className="label">{order.merchant}</p>
        <h1 className="heading mt-3">{order.item}</h1>
        <p className="checkout-amount mt-5">{money(p.amountCents, p.currency)}</p>
        <p className="meta mt-3">Billed monthly. Cancel any time from your account.</p>

        {done ? (
          <div className="mt-6">
            <Notice tone="quiet">This checkout is already {p.status}.</Notice>
          </div>
        ) : (
          <div className="row gap-4 mt-6">
            <Button variant="primary" busy={busy === "pay"} disabled={!!busy}
              onClick={() => complete("pay")}>
              Pay {money(p.amountCents, p.currency)}
            </Button>
            <Button variant="outline" busy={busy === "decline"} disabled={!!busy}
              onClick={() => complete("decline")}>
              Decline
            </Button>
            <Link className="link-quiet meta" to={`/contributors/${p.contributorId}`}>
              Cancel
            </Link>
          </div>
        )}
        {error && <div className="mt-4"><Notice>{error}</Notice></div>}
      </div>
    </div>
  );
}

export function CheckoutResult() {
  const [params] = useSearchParams();
  const id = params.get("payment");
  const [payment, setPayment] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!id) return undefined;
    let tries = 0;
    let timer;
    // A real provider's webhook can arrive a few seconds after the buyer does.
    const poll = () =>
      api.get(`/payments/${id}`)
        .then(({ payment: p }) => {
          setPayment(p);
          if (p.status === "pending" && tries++ < 10) timer = setTimeout(poll, 1500);
        })
        .catch((e) => setError(e.message));
    poll();
    return () => clearTimeout(timer);
  }, [id]);

  if (!id || error) return <Notice>{error || "No payment to show."}</Notice>;
  if (!payment) return <div className="skeleton" style={{ height: "12rem" }} />;

  const back = (
    <Link className="link-quiet" to={`/contributors/${payment.contributorId}`}>
      Back to the writer
    </Link>
  );

  if (payment.status === "succeeded") {
    return (
      <Empty title="You're subscribed" action={<div className="row gap-4 mt-4">{back}
        <Link className="link-quiet" to="/account">Your subscriptions</Link></div>}>
        {money(payment.amountCents, payment.currency)} paid. Their subscriber-only articles
        are open to you now. Reference {payment.reference}.
      </Empty>
    );
  }
  if (payment.status === "failed") {
    return (
      <Empty title="The payment didn't go through" action={<div className="mt-4">{back}</div>}>
        {payment.failureReason || "The payment was not completed."} You have not been charged.
      </Empty>
    );
  }
  return (
    <Empty title="Waiting for the payment provider" action={<div className="mt-4">{back}</div>}>
      Your payment has not been confirmed yet. If you completed it, this usually takes a few
      seconds; your account updates as soon as it arrives.
    </Empty>
  );
}

const STATUS_LABELS = {
  succeeded: "Paid", failed: "Failed", pending: "Not completed", refunded: "Refunded",
};

export function PaymentHistory() {
  const [payments, setPayments] = useState(null);

  useEffect(() => {
    api.get("/me/payments").then((d) => setPayments(d.payments)).catch(() => setPayments([]));
  }, []);

  if (!payments) return null;
  if (payments.length === 0) {
    return <p className="meta">No payments yet.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">For</th>
            <th scope="col">Amount</th>
            <th scope="col">Status</th>
            <th scope="col">Reference</th>
          </tr>
        </thead>
        <tbody>
          {payments.map((p) => (
            <tr key={p.id}>
              <td className="meta">{formatDate(p.createdAt)}</td>
              <td>{p.description}</td>
              <td className="meta tabular">{money(p.amountCents, p.currency)}</td>
              <td><span className="status" data-status={p.status}>{STATUS_LABELS[p.status] ?? p.status}</span></td>
              <td className="meta"><code>{p.reference || "none"}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
