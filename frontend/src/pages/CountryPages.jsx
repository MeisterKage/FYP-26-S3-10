/**
 * Country-based news: every country with published articles, and one
 * country's articles narrowed by section.
 *
 * A country is what the article is about, set by the writer from a fixed list.
 * Country plus section ("Politics in Australia") is the view the monthly digest
 * compiles, so the section chips are a filter here rather than links away.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { EntryThumb } from "../components/CoverImage";
import { CredibilityInline } from "../components/Credibility";
import { Empty, EntrySkeleton, Notice, SectionHead, formatDate } from "../components/UI";
import { usePageTitle } from "../usePageTitle";
import { useI18n } from "../i18n";

const SORTS = [
  ["recent", "Most recent"],
  ["credibility", "Highest credibility"],
];

export function CountryIndex() {
  const [countries, setCountries] = useState(null);
  const { t, country } = useI18n();
  usePageTitle(t("countries.title"));
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/countries")
      .then((d) => setCountries(d.countries))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="wide">
      <header className="read">
        <h1 className="display">{t("countries.title")}</h1>
        <p className="lead mt-6">{t("countries.lead")}</p>
      </header>

      <section className="section mt-8">
        {error && <Notice>{error}</Notice>}
        {!countries && !error && <EntrySkeleton rows={3} />}
        {countries?.length === 0 && (
          <Empty title="No country-tagged articles yet">
            Articles appear here once a writer tags one with a country.
          </Empty>
        )}
        {countries?.length > 0 && (
          <ul className="country-grid">
            {countries.map((c) => (
              <li key={c.code}>
                <Link className="country-card" to={`/countries/${c.code.toLowerCase()}`}>
                  <span className="country-name">{country(c.code, c.name)}</span>
                  <span className="meta">{t("topics.articles", { n: c.articleCount })}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export function CountryPage() {
  const { code } = useParams();
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") || "recent";
  const section = params.get("category") || "";

  const [data, setData] = useState(null);
  const { t, country, section: sectionName } = useI18n();
  const countryName = data?.country ? country(data.country.code, data.country.name) : null;
  usePageTitle(countryName);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    const query = new URLSearchParams({ sort });
    if (section) query.set("category", section);
    api
      .get(`/countries/${code}/articles?${query}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [code, sort, section]);

  useEffect(load, [load]);

  function update(next) {
    const merged = { sort, category: section, ...next };
    setParams(Object.fromEntries(Object.entries(merged).filter(([, v]) => v)));
  }

  if (error) {
    return (
      <Empty
        level={1}
        title="No news for that country"
        action={
          <Link className="link-quiet mt-4" to="/countries">
            See all countries
          </Link>
        }
      >
        {error}
      </Empty>
    );
  }

  const selectedName = data?.sections.find((s) => s.slug === section)?.name;

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <p className="label">
            <Link className="link-quiet" to="/countries">
              {t("countries.title")}
            </Link>
          </p>
          <h1 className="title mt-3">{countryName || t("list.loading")}</h1>
          <p className="meta mt-3">
            {data
              ? `${data.articles.length} published${selectedName ? ` in ${selectedName}` : ""}`
              : "Loading"}
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
            onChange={(e) => update({ sort: e.target.value })}
          >
            {SORTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </header>

      {data?.sections.length > 0 && (
        <nav className="chips mt-6" aria-label="Filter by section">
          <button
            type="button"
            className="chip"
            aria-pressed={!section}
            onClick={() => update({ category: "" })}
          >
            {t("list.allSections")}
          </button>
          {data.sections.map((s) => (
            <button
              type="button"
              className="chip"
              key={s.slug}
              aria-pressed={section === s.slug}
              onClick={() => update({ category: s.slug })}
            >
              {sectionName(s.slug, s.name)}
              <span className="chip-count">{s.articleCount}</span>
            </button>
          ))}
        </nav>
      )}

      <section className="section mt-7">
        <SectionHead title={t("list.articles")} />
        {!data && <EntrySkeleton rows={4} />}
        {data && data.articles.length === 0 && (
          <Empty title="Nothing published here yet">
            Try another section, or another country.
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
