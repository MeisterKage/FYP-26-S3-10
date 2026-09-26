/**
 * How scoring works (PDD Figure 5.2).
 *
 * What a credibility score is built from.
 *
 * Team decision: the inputs are published, the weights are not. A reader learns
 * that sourcing raises a score and a correction lowers it, and can open any
 * article's ledger to see what each input contributed to that article. The
 * tuning constants stay internal.
 *
 * Everything here is fetched rather than hard-coded, so the page cannot drift
 * from what the engine actually does.
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

  const v = formula;

  return (
    <div className="about">
      <header className="read">
        <h1 className="display">Every score is arithmetic you can check.</h1>
        <p className="lead mt-6">
          Most platforms rank what you read and never say what moves the ranking.
          This one does. Every score comes from the same fixed rules applied the
          same way to every article: nothing is predicted, learned, or personalised
          to you.
        </p>
      </header>

      {error && (
        <div className="read mt-7">
          <Notice>
            This explanation could not be loaded. The scores themselves are
            unaffected.
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
            a minimum number of articles; before that their profile reads{" "}
            <em>new contributor</em>, which is not a low score. It is no score at
            all.
          </Term>

          <Term name="Credibility Score">
            A single article, rated out of 100. It combines the writer&rsquo;s
            track record with what that specific article did: how well sourced it
            is, whether it was later corrected, and whether enough
            readers reported it to trigger review.
          </Term>
        </dl>
      </section>

      {v && (
        <section className="section read mt-9">
          <h2 className="title">What moves a score</h2>
          <p className="lead mt-5">
            An article starts from its writer&rsquo;s track record, gains for
            sourcing, and loses for anything an editor later has to correct. The
            result is held between 0 and 100.
          </p>

          <dl className="terms mt-7">
            {v.inputs.map((input) => (
              <div className="term" key={input.name}>
                <dt className="sub">
                  {input.name}{" "}
                  {/* The direction is a word, never an arrow or a colour: this
                      system encodes nothing by colour alone. */}
                  <span className="tag">{input.effect} the score</span>
                </dt>
                <dd className="lead">{input.description}</dd>
              </div>
            ))}
          </dl>

          <p className="meta mt-6">
            {v.newContributor}
          </p>

          <p className="meta mt-5">
            The exact weight given to each input is set by an administrator and is
            not published. Every article carries its own ledger showing what each
            of these contributed to that article&rsquo;s score, so you can always
            see why a particular number is what it is.
          </p>
        </section>
      )}

      {v?.sourceTiers && (
        <section className="section read mt-9" id="sources">
          <h2 className="title">How sources are graded</h2>
          <p className="lead mt-5">
            Not every link is evidence. Each source an article cites is graded by what
            kind of source it is, and the grade decides what it adds to the score.
            Every grade comes from a rule or a public list, never from this site&rsquo;s
            opinion, and an editor who has read the source has the final word.
          </p>
          <div className="table-scroll mt-6">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Grade</th>
                  <th scope="col">What it means</th>
                  <th scope="col" className="tabular">Adds</th>
                </tr>
              </thead>
              <tbody>
                {v.sourceTiers.map((t) => (
                  <tr key={t.tier}>
                    <td><strong>{t.label}</strong></td>
                    <td>{t.description}</td>
                    <td className="tabular">{t.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta mt-5">
            Outlet ratings come from{" "}
            <a className="link-quiet" href={v.sourceLists.perennial.url} target="_blank"
              rel="noreferrer noopener">{v.sourceLists.perennial.name}</a>
            , used under {v.sourceLists.perennial.license} (copy of{" "}
            {v.sourceLists.perennial.retrieved}). Retractions come from{" "}
            <a className="link-quiet" href={v.sourceLists.retractions.url} target="_blank"
              rel="noreferrer noopener">{v.sourceLists.retractions.name}</a>
            . Many smaller sites are on neither list and show as unrated.
          </p>
        </section>
      )}

      {formula && (
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
            Every article names the editor who approved it, and{" "}
            <Link className="link-quiet" to="/editors">
              each editor&rsquo;s record is public
            </Link>
            .
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
