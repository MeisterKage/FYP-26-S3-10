/**
 * All topics: every section with its description and how many articles it has.
 *
 * The way back from any one topic page, which links here, and the counterpart
 * of the countries page.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { EntrySkeleton, Notice } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

export default function TopicsIndex() {
  usePageTitle("All topics");
  const [topics, setTopics] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/categories")
      .then((d) => setTopics((d.categories || []).filter((c) => c.slug !== "uncategorised")))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="wide">
      <header className="read">
        <h1 className="display">All topics</h1>
        <p className="lead mt-6">
          Every section of Wollongong News. Each article is scored by the same rules,
          whichever section it is in.
        </p>
      </header>

      <section className="section mt-8">
        {error && <Notice>{error}</Notice>}
        {!topics && !error && <EntrySkeleton rows={3} />}
        {topics && (
          <ul className="country-grid topic-grid">
            {topics.map((t) => (
              <li key={t.id}>
                <Link className="country-card topic-card" to={`/categories/${t.slug}`}>
                  <span className="country-name">{t.name}</span>
                  {t.description && <span className="topic-description">{t.description}</span>}
                  <span className="meta">
                    {t.articleCount} article{t.articleCount === 1 ? "" : "s"}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="meta mt-7">
          Looking for a place instead? <Link className="link" to="/countries">Browse by country</Link>.
        </p>
      </section>
    </div>
  );
}
