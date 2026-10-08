/**
 * Subscription tiers and pricing (PDD Figure 5.3).
 *
 * Persuade mode, and public. A visitor deciding whether to subscribe needs the
 * context for why one writer's price differs from another's: the platform's cut
 * falls as a writer gains subscribers, so more of a subscription reaches them
 * over time.
 *
 * The bands are fetched rather than written into the page. They are a
 * commercial term, and a page quoting last quarter's split would be worse than
 * a page quoting none.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { Notice } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

function money(cents) {
  return `$${((cents ?? 0) / 100).toFixed(2)}`;
}

export default function PricingPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  usePageTitle("Pricing");

  useEffect(() => {
    api
      .get("/subscription-tiers")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="about doc">
      <header className="read">
        <h1 className="display">What a subscription pays for.</h1>
        <p className="lead mt-6">
          You subscribe to a writer, not to the platform. That subscription
          unlocks their subscriber-only articles and nothing else, and most of
          it goes to them.
        </p>
      </header>

      {error && (
        <div className="read mt-7">
          <Notice>{error}</Notice>
        </div>
      )}

      {data && (
        <>
          <section className="section read mt-9">
            <h2 className="title">The price</h2>
            <p className="lead mt-5">
              <strong>{money(data.monthlyPriceCents)} a month</strong> per writer.
              Cancelling stops the next renewal; access runs to the end of the
              period you have already paid for.
            </p>
          </section>

          <section className="section read mt-9">
            <h2 className="title">How the split changes</h2>
            <p className="lead mt-5">
              The platform&rsquo;s share falls as a writer&rsquo;s readership grows, so a
              writer keeps more of each subscription the more people back them.
            </p>

            <div className="table-scroll mt-6">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Subscribers</th>
                    <th scope="col">Writer keeps</th>
                    <th scope="col">Platform takes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tiers.map((t) => (
                    <tr key={t.name}>
                      <td style={{ color: "var(--ink)" }}>
                        {t.fromSubscribers === 0
                          ? "From the first"
                          : `${t.fromSubscribers.toLocaleString()} and above`}
                      </td>
                      <td className="tabular">{t.contributorSharePercent}%</td>
                      <td className="meta tabular">{t.platformSharePercent}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="meta mt-5">
              A writer&rsquo;s current band is shown on their earnings page, alongside
              what they have been paid.
            </p>
          </section>

          <section className="section read mt-9">
            <h2 className="title">What it does not buy</h2>
            <dl className="terms mt-6">
              <div className="term">
                <dt className="sub">Not a better score</dt>
                <dd className="lead">
                  A credibility score counts sourcing and corrections. Paying a
                  writer does not move it, and neither does the platform.
                </dd>
              </div>
              <div className="term">
                <dt className="sub">Not the whole site</dt>
                <dd className="lead">
                  Subscribing to one writer never unlocks another&rsquo;s
                  subscriber-only work. Every writer is a separate subscription.
                </dd>
              </div>
            </dl>
          </section>

          <p className="read mt-9">
            <Link className="link-quiet" to="/">
              Read something first
            </Link>
            .
          </p>
        </>
      )}
    </div>
  );
}
