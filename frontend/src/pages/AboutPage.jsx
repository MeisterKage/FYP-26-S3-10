/**
 * How scoring works (PDD Figure 5.2).
 *
 * PRD 1.3.3 promises "a disclosed formula rather than a hidden or predictive
 * model", and this is the page where that promise is kept.
 *
 * The constants are fetched rather than hard-coded. Administrators can change
 * every threshold at runtime (PRD 1.3.2), so a page printing last month's
 * numbers would be worse than printing none.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { CredibilityMeter } from "../components/Credibility";
import { Notice } from "../components/UI";

function Term({ name, children }) {
  return (
    <div className="term">
      <dt className="sub">{name}</dt>
      <dd className="lead">{children}</dd>
    </div>
  );
}

export default function AboutPage() {
  const [formula, setFormula] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/scoring/formula")
      .then(setFormula)
      .catch((e) => setError(e.message));
  }, []);

  const v = formula?.constants;

  return (
    <div className="about">
      <header className="read">
        <h1 className="display">Every score is arithmetic you can check.</h1>
        <p className="lead mt-6">
          Most platforms rank what you read and never say how. This one publishes
          the formula, the inputs, and the thresholds. The same inputs always
          produce the same number, and nothing here is predicted, learned, or
          weighted behind a curtain.
        </p>
      </header>

      {error && (
        <div className="read mt-7">
          <Notice>
            The live figures could not be loaded, so the numbers below are not
            shown. The method itself is unchanged.
          </Notice>
        </div>
      )}

      <section className="section read mt-9">
        <h2 className="title">The two numbers</h2>

        <dl className="terms mt-6">
          <Term name="Accuracy Rate">
            A writer&rsquo;s published articles that were never corrected or
            retracted, as a share of everything they have published. It appears
            only once they have published{" "}
            {v ? <strong>{v.min_articles_for_accuracy} articles</strong> : "a set minimum"};
            before that their profile reads <em>new contributor</em>, which is not
            a low score. It is no score at all.
          </Term>

          <Term name="Credibility Score">
            A single article, rated out of 100. It combines the writer&rsquo;s
            track record with what that specific article did: how many verifiable
            sources it cited, whether it was later corrected, and whether enough
            readers reported it to trigger review.
          </Term>
        </dl>
      </section>

      {v && (
        <section className="section read mt-9">
          <h2 className="title">The formula</h2>
          <p className="lead mt-5">
            An article starts from its writer&rsquo;s accuracy, earns points for
            sourcing, and loses them for corrections. The result is held between
            0 and 100.
          </p>

          <div className="formula mt-6">
            <dl>
              <div className="ledger-row">
                <dt>Writer&rsquo;s accuracy rate, weighted</dt>
                <dd>&times; {v.accuracy_weight}</dd>
              </div>
              <div className="ledger-row">
                <dt>Each verifiable source cited</dt>
                <dd>+{v.source_points}</dd>
              </div>
              <div className="ledger-row">
                <dt>Most sourcing can contribute</dt>
                <dd>+{v.source_cap}</dd>
              </div>
              <div className="ledger-row">
                <dt>Each logged correction</dt>
                <dd>&minus;{v.correction_penalty}</dd>
              </div>
              <div className="ledger-row">
                <dt>A retraction</dt>
                <dd>&minus;{v.retraction_penalty}</dd>
              </div>
              <div className="ledger-row">
                <dt>
                  Once {v.report_threshold} reader reports are upheld
                </dt>
                <dd>&minus;{v.report_penalty}</dd>
              </div>
            </dl>
          </div>

          <p className="meta mt-5">
            These figures are live. An administrator can change any of them, and
            when they do, every published score is recalculated and this page
            shows the new numbers immediately.
          </p>
        </section>
      )}

      {v && (
        <section className="section read mt-9">
          <h2 className="title">A worked example</h2>
          <p className="lead mt-5">
            A writer with a {v.example.accuracy}% accuracy rate publishes an
            article citing {v.example.sources} verifiable sources, with no
            corrections against it.
          </p>

          <div className="formula mt-6">
            <dl>
              <div className="ledger-row">
                <dt>
                  {v.example.accuracy}% accuracy &times; {v.accuracy_weight}
                </dt>
                <dd>{v.example.accuracy_component}</dd>
              </div>
              <div className="ledger-row">
                <dt>
                  {v.example.sources} sources &times; {v.source_points}
                </dt>
                <dd>+{v.example.source_component}</dd>
              </div>
              <div className="ledger-row ledger-total">
                <dt>Credibility score</dt>
                <dd>{v.example.score}</dd>
              </div>
            </dl>
          </div>

          <div className="mt-6" style={{ maxWidth: "20rem" }}>
            <CredibilityMeter
              credibility={{ score: v.example.score, band: v.example.band }}
            />
          </div>
        </section>
      )}

      {formula?.bands && (
        <section className="section read mt-9">
          <h2 className="title">What the bands mean</h2>
          <p className="lead mt-5">
            The band is a label on the number, not a separate judgement. We
            deliberately do not colour it green or red: a score is a measurement,
            and dressing it as a warning light would overstate what it knows.
          </p>

          <div className="bands mt-6">
            {formula.bands.map((band) => (
              <div className="band-row" key={band.label}>
                <div className="band-meter">
                  <CredibilityMeter
                    credibility={{ score: band.sample, band: band.label }}
                    animate={false}
                  />
                </div>
                <p className="meta">{band.description}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="section read mt-9">
        <h2 className="title">What we do not do</h2>
        <dl className="terms mt-6">
          <Term name="No automated judgement">
            Nothing here reads your article and decides whether it is true. The
            score counts sourcing and corrections; a human editor makes every
            call about accuracy, and an administrator can overturn that editor.
          </Term>
          <Term name="No ranking you cannot see">
            Search matches keywords against titles, tags, and categories. There
            is no semantic matching and no personalised re-ranking of results.
          </Term>
          <Term name="No score without a record">
            Every correction and retraction is logged in an article&rsquo;s
            revision history and stays there. A score that improved because
            something was quietly deleted would be worthless.
          </Term>
        </dl>

        <p className="lead mt-7">
          Every article carries its own working.{" "}
          <Link className="link-quiet" to="/">
            Read something and check it
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
