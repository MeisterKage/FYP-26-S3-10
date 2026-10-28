/**
 * The front page (PDD Figures 5.4 and 5.16).
 *
 * Set as a quality paper sets its front: one lead story with a large photograph
 * and its credibility ring, three top stories with photographs beneath, then the
 * latest as a ruled list beside a short note on what the rings mean.
 *
 * Signed out, this is trending. Signed in with interests or follows, it becomes
 * the personalised rows, falling back to trending rather than an empty page,
 * which Figure 5.16 requires explicitly.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, imageUrl } from "../api";
import { useAuth } from "../auth";
import { CredibilityInline, CredibilityMeter } from "../components/Credibility";
import {
  ArticleEntry,
  Empty,
  EntrySkeleton,
  Notice,
  SectionHead,
} from "../components/UI";
import { usePageTitle } from "../usePageTitle";
import { useI18n } from "../i18n";

/** "Environment, New Zealand": where a story sits, in the reader's language. */
function Kicker({ article, sections }) {
  const { section, country } = useI18n();
  const cat = sections[article.categoryId];
  const parts = [
    cat && section(cat.slug, cat.name),
    article.country && country(article.country.code, article.country.name),
  ].filter(Boolean);
  if (!parts.length) return null;
  return <p className="front-kicker">{parts.join(", ")}</p>;
}

function Photo({ image, ratio, priority = false }) {
  if (!image) return null;
  return (
    <img
      className="front-photo"
      src={imageUrl(image.url)}
      alt={image.alt || ""}
      width={image.width}
      height={image.height}
      style={{ aspectRatio: ratio }}
      loading={priority ? "eager" : "lazy"}
      fetchpriority={priority ? "high" : undefined}
      decoding="async"
    />
  );
}

function Lead({ article, sections }) {
  const { t } = useI18n();
  const href = `/articles/${article.slug}`;
  const reviewer = article.review?.reviewer;

  return (
    <article className="front-lead">
      <Link className="front-lead-photo" to={href} tabIndex={-1} aria-hidden="true">
        <Photo image={article.coverImage} ratio="4 / 3" priority />
      </Link>
      <div className="front-lead-text">
        <Kicker article={article} sections={sections} />
        <h1 className="front-lead-title">
          <Link to={href}>{article.title}</Link>
        </h1>
        {article.summary && <p className="front-standfirst">{article.summary}</p>}
        <p className="front-byline">
          {t("home.by", { name: article.contributor.name })}
          {reviewer && (
            <>
              <br />
              {t("home.reviewedBy", { name: reviewer.name, title: reviewer.title || "" })}
            </>
          )}
        </p>
        <div className="front-lead-score">
          <CredibilityMeter credibility={article.credibility} review={article.review} size={64} />
          <Link className="front-trace" to={href}>{t("home.trace")}</Link>
        </div>
      </div>
    </article>
  );
}

function Feature({ article, sections }) {
  const href = `/articles/${article.slug}`;
  return (
    <article className="front-feature">
      <Link to={href} tabIndex={-1} aria-hidden="true">
        <Photo image={article.coverImage} ratio="3 / 2" />
      </Link>
      <Kicker article={article} sections={sections} />
      <h2 className="front-feature-title">
        <Link to={href}>{article.title}</Link>
      </h2>
      {article.summary && <p className="front-feature-summary">{article.summary}</p>}
      <CredibilityInline credibility={article.credibility} review={article.review} />
    </article>
  );
}

function Index({ articles }) {
  return (
    <div className="stack">
      {articles.map((article) => (
        <ArticleEntry
          key={article.id}
          article={article}
          aside={<CredibilityInline credibility={article.credibility} review={article.review} />}
        />
      ))}
    </div>
  );
}

function ScoreNote() {
  const { t } = useI18n();
  return (
    <aside className="front-note" aria-labelledby="front-note-title">
      <h2 className="front-note-title" id="front-note-title">{t("home.scoreTitle")}</h2>
      <p>{t("home.scoreNote")}</p>
      <Link className="front-note-link" to="/about">{t("home.scoreLink")}</Link>
    </aside>
  );
}

/** Lead, three top stories, then the rest beside the note on scoring. */
function Front({ articles, sections, latestTitle }) {
  const [lead, ...rest] = articles;
  const features = rest.slice(0, 3);
  const latest = rest.slice(3);
  return (
    <>
      <Lead article={lead} sections={sections} />
      {features.length > 0 && (
        <section className="front-features" aria-label={latestTitle}>
          {features.map((a) => <Feature key={a.id} article={a} sections={sections} />)}
        </section>
      )}
      <div className="front-latest">
        <section className="front-latest-list">
          {latest.length > 0 && (
            <>
              <SectionHead title={latestTitle} />
              <Index articles={latest} />
            </>
          )}
        </section>
        <ScoreNote />
      </div>
    </>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [sections, setSections] = useState({});
  const [error, setError] = useState(null);
  const { t } = useI18n();
  usePageTitle(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);

    api
      .get(user ? "/feed/personalised" : "/feed/trending")
      .then((payload) => !cancelled && setData(payload))
      .catch((e) => !cancelled && setError(e.message));
    api
      .get("/categories")
      .then((d) => !cancelled && setSections(Object.fromEntries((d.categories || []).map((c) => [c.id, c]))))
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [user]);

  if (error) {
    return (
      <div className="read">
        <Notice>{error}</Notice>
      </div>
    );
  }

  if (!data) {
    return (
      <>
        <div className="skeleton" style={{ height: "24rem", marginBottom: "3rem" }} />
        <EntrySkeleton rows={4} />
      </>
    );
  }

  // Trending shape: a flat list.
  if (data.articles) {
    if (data.articles.length === 0) {
      return <Empty title={t("home.nothing")}>{t("home.nothingNote")}</Empty>;
    }
    return <Front articles={data.articles} sections={sections} latestTitle={t("home.latest")} />;
  }

  // Personalised shape: your categories, then writers you follow.
  const { forYou = [], fromFollowed = [] } = data;

  return (
    <>
      {forYou.length > 0 ? (
        <Front articles={forYou} sections={sections} latestTitle={t("home.inYourCategories")} />
      ) : (
        <Empty
          title={t("home.nothingCats")}
          action={
            <div className="row gap-4 mt-5">
              <Link className="btn btn-primary btn-sm" to="/topics">{t("home.browseTopics")}</Link>
              <Link className="btn btn-outline btn-sm" to="/countries">{t("home.browseCountries")}</Link>
            </div>
          }
        >
          {t("home.nothingCatsNote")}
        </Empty>
      )}

      {fromFollowed.length > 0 && (
        <section className="section">
          <SectionHead title={t("home.fromFollowed")} />
          <Index articles={fromFollowed} />
        </section>
      )}
    </>
  );
}
