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
import { useI18n } from "../i18n";

export default function TopicsIndex() {
  const { t, section } = useI18n();
  usePageTitle(t("topics.title"));
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
        <h1 className="display">{t("topics.title")}</h1>
        <p className="lead mt-6">{t("topics.lead")}</p>
      </header>

      <section className="section mt-8">
        {error && <Notice>{error}</Notice>}
        {!topics && !error && <EntrySkeleton rows={3} />}
        {topics && (
          <ul className="country-grid topic-grid">
            {topics.map((x) => (
              <li key={x.id}>
                <Link className="country-card topic-card" to={`/categories/${x.slug}`}>
                  <span className="country-name">{section(x.slug, x.name)}</span>
                  {x.description && <span className="topic-description">{x.description}</span>}
                  <span className="meta">{t("topics.articles", { n: x.articleCount })}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="meta mt-7">
          {t("topics.byCountry")} <Link className="link" to="/countries">{t("topics.browseCountry")}</Link>.
        </p>
      </section>
    </div>
  );
}
