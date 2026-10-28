/**
 * About us: what the platform is, how it works, and what a visitor can do here.
 *
 * Public, and the first page a curious visitor should find. The figures are
 * live (GET /platform), so the page never quotes stale numbers. How the score
 * is calculated has its own page; this one explains why it exists.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { usePageTitle } from "../usePageTitle";

const FIGURES = [
  ["articles", "published articles"],
  ["writers", "writers"],
  ["editors", "editors"],
  ["sections", "topics"],
  ["countries", "countries covered"],
  ["corrections", "corrections on the public record"],
];

export default function AboutUsPage() {
  usePageTitle("About us");
  const [figures, setFigures] = useState(null);

  useEffect(() => {
    api.get("/platform").then(setFigures).catch(() => setFigures(null));
  }, []);

  return (
    <div className="about doc">
      <header className="read">
        <p className="label">About us</p>
        <h1 className="display mt-3">News you can check.</h1>
        <p className="lead mt-6">
          Sterling Wire publishes reporting from independent writers, reviewed by editors,
          and gives every article a credibility score worked out in the open. You can see who
          wrote a story, what it is based on, and every correction made to it.
        </p>
      </header>

      {figures && (
        <section className="section read mt-8" aria-label="The platform in numbers">
          <dl className="about-figures">
            {FIGURES.map(([key, label]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>{figures[key]}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="section read prose mt-9">
        <h2>How it works</h2>
        <p>
          <strong>Writers</strong> submit articles with the sources they rely on. Anyone with an
          account can apply to become one.
        </p>
        <p>
          <strong>Editors</strong>, each responsible for their own topics, read every submission
          before it is published. The editor who approved an article is named on it.{" "}
          <Link className="link" to="/editors">Meet our editors</Link>.
        </p>
        <p>
          <strong>The credibility score</strong> on every article comes from fixed rules: the
          writer&rsquo;s track record, how well-graded the article&rsquo;s sources are, and any
          corrections. Nobody can buy or hand-pick a score.{" "}
          <Link className="link" to="/about">How scoring works</Link>.
        </p>
        <p>
          <strong>Corrections are public.</strong> When an article is corrected or retracted, the
          note stays on it, the score changes, and the writer&rsquo;s accuracy rate reflects it.
        </p>

        <h2>What you can do here</h2>
        <ul>
          <li>Read every free article, browse by <Link className="link" to="/topics">topic</Link> or{" "}
            <Link className="link" to="/countries">country</Link>, and search.</li>
          <li>Listen to an article&rsquo;s key points or the whole article, read aloud.</li>
          <li>With a free account: follow writers, like and save articles, comment, and get the{" "}
            <Link className="link" to="/digests">monthly digest</Link> of the most credible reporting
            in the topics you choose.</li>
          <li>Subscribe to a writer to read their subscriber-only articles.{" "}
            <Link className="link" to="/pricing">See pricing</Link>.</li>
          <li>Report an article you believe is wrong. Editors review every report.</li>
        </ul>

        <h2>Your data</h2>
        <p>
          No advertising and no tracking. The <Link className="link" to="/privacy">privacy page</Link>{" "}
          sets out exactly what we keep, and the <Link className="link" to="/terms">terms of use</Link>{" "}
          the rules for writers, readers and subscribers.
        </p>
      </section>
    </div>
  );
}
