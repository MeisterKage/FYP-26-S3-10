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
import { FollowButton } from "../components/FollowButton";
import { usePageTitle } from "../usePageTitle";
import { useI18n } from "../i18n";

const SORTS = [
  ["recent", "list.mostRecent"],
  ["credibility", "list.highest"],
];

export default function CategoryPage() {
  const { slug } = useParams();
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") || "recent";

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { t, section } = useI18n();
  const name = data?.category ? section(data.category.slug, data.category.name) : null;
  usePageTitle(name);

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
            <Link className="link-quiet" to="/topics">{t("topics.title")}</Link>
          </p>
          <h1 className="title mt-3">{name || t("list.loading")}</h1>
          <p className="meta mt-3">
            {data ? t("list.published", { n: data.articles.length }) : t("list.loading")}
          </p>
        </div>

        <div className="row gap-4">
          <FollowButton kind="category" id={data?.category?.id} name={name} />
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
                {t(label)}
              </option>
            ))}
          </select>
        </div>
      </header>

      {topics.length > 0 && (
        <nav className="chips mt-6" aria-label="Topics">
          <Link className="chip" to="/topics">{t("topics.title")}</Link>
          {topics.map((x) => (
            <Link className="chip" key={x.id} to={`/categories/${x.slug}`}
              aria-current={x.slug === slug ? "page" : undefined}>
              {section(x.slug, x.name)}
            </Link>
          ))}
        </nav>
      )}

      <section className="section mt-7">
        <SectionHead title={t("list.articles")} />
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
