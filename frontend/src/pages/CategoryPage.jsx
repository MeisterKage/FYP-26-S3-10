/**
 * Articles in one section (PDD Figure 5.5).
 *
 * Sorting is offered by credibility as well as recency, because a section is
 * where a reader browses without a specific article in mind, and that is
 * exactly where the score is most useful as a way in.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { EntryThumb } from "../components/CoverImage";
import { CredibilityInline } from "../components/Credibility";
import { Empty, EntrySkeleton, Notice, SectionHead, formatDate } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

const SORTS = [
  ["recent", "Most recent"],
  ["credibility", "Highest credibility"],
];

export default function CategoryPage() {
  const { slug } = useParams();
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") || "recent";

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  usePageTitle(data?.category?.name);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    api
      .get(`/categories/${slug}/articles?sort=${sort}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [slug, sort]);

  useEffect(load, [load]);

  // Every topic, as quick links beside this one, so a reader can move between
  // them or go back to All topics without the menu.
  const [topics, setTopics] = useState([]);
  useEffect(() => {
    api
      .get("/categories")
      .then((d) => setTopics((d.categories || []).filter((c) => c.slug !== "uncategorised")))
      .catch(() => setTopics([]));
  }, []);

  if (error) return <Notice>{error}</Notice>;

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <p className="label">
            <Link className="link-quiet" to="/topics">All topics</Link>
          </p>
          <h1 className="title mt-3">{data?.category?.name || "Section"}</h1>
          <p className="meta mt-3">
            {data ? `${data.articles.length} published` : "Loading"}
          </p>
        </div>

        <div className="row gap-4">
          <label className="sr-only" htmlFor="sort">
            Sort by
          </label>
          <select
            id="sort"
            className="input input-sm"
            value={sort}
            onChange={(e) => setParams({ sort: e.target.value })}
          >
            {SORTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {topics.length > 0 && (
        <nav className="chips mt-6" aria-label="Topics">
          <Link className="chip" to="/topics">All topics</Link>
          {topics.map((t) => (
            <Link className="chip" key={t.id} to={`/categories/${t.slug}`}
              aria-current={t.slug === slug ? "page" : undefined}>
              {t.name}
            </Link>
          ))}
        </nav>
      )}

      <section className="section mt-7">
        <SectionHead title="Articles" />
        {!data && <EntrySkeleton rows={4} />}
        {data && data.articles.length === 0 && (
          <Empty title="Nothing published in this section yet">
            Try another section, or the front page.
          </Empty>
        )}
        {data && data.articles.length > 0 && (
          <div className="index">
            {data.articles.map((a) => (
              <article className={`entry${a.coverImage ? " entry--media" : ""}`} key={a.id}>
                <EntryThumb image={a.coverImage} />
                <div className="entry-main">
                  <h3 className="entry-title">
                    <Link className="link-quiet" to={`/articles/${a.slug}`}>
                      {a.title}
                    </Link>
                  </h3>
                  {a.summary && <p className="entry-summary mt-2">{a.summary}</p>}
                  <p className="entry-meta mt-3">
                    <Link className="link-quiet" to={`/contributors/${a.contributor.id}`}>
                      {a.contributor.name}
                    </Link>
                    <span className="dot" aria-hidden="true" />
                    <span>{formatDate(a.publishedAt)}</span>
                  </p>
                </div>
                <div className="entry-aside">
                  <CredibilityInline credibility={a.credibility} review={a.review} />
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
