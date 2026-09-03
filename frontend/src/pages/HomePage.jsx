/**
 * The front page (PDD Figures 5.4 and 5.16).
 *
 * Laid out as a newspaper front: one lead article at display scale, then a ruled
 * index beneath it. Equal-sized cards would flatten the hierarchy the
 * credibility scores exist to create.
 *
 * Signed out, this is trending. Signed in with interests or follows, it becomes
 * the two personalised rows, falling back to trending rather than an empty page,
 * which Figure 5.16 requires explicitly.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { AccuracyRate, CredibilityInline, CredibilityMeter } from "../components/Credibility";
import { ArrowIcon } from "../components/Icon";
import {
  ArticleEntry,
  Empty,
  EntrySkeleton,
  Notice,
  SectionHead,
  formatDate,
} from "../components/UI";

function Lead({ article }) {
  const date = formatDate(article.publishedAt);

  return (
    <article className="lead-article">
      <div className="lead-body">
        <h1 className="display">
          <Link className="link" to={`/articles/${article.slug}`}>
            {article.title}
          </Link>
        </h1>

        {article.summary && <p className="lead mt-5">{article.summary}</p>}

        <p className="entry-meta mt-5">
          <span>{article.contributor.name}</span>
          <span className="dot" aria-hidden="true" />
          <AccuracyRate rate={article.contributor.accuracyRate} />
          {date && <span className="dot">{date}</span>}
        </p>
      </div>

      <aside className="lead-aside">
        <p className="label">Credibility</p>
        <div className="mt-4">
          <CredibilityMeter credibility={article.credibility} />
        </div>
        <Link className="link-quiet lead-trace" to={`/articles/${article.slug}`}>
          Trace this score
          <ArrowIcon size={15} />
        </Link>
      </aside>
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
          aside={<CredibilityInline credibility={article.credibility} />}
        />
      ))}
    </div>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);

    api
      .get(user ? "/feed/personalised" : "/feed/trending")
      .then((payload) => !cancelled && setData(payload))
      .catch((e) => !cancelled && setError(e.message));

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
        <div className="skeleton" style={{ height: "12rem", marginBottom: "3rem" }} />
        <EntrySkeleton rows={4} />
      </>
    );
  }

  // Trending shape: a flat list. Lead with the first, index the rest.
  if (data.articles) {
    if (data.articles.length === 0) {
      return (
        <Empty title="Nothing published yet">
          The first article appears here the moment an editor approves it.
        </Empty>
      );
    }

    const [lead, ...rest] = data.articles;

    return (
      <>
        <Lead article={lead} />
        {rest.length > 0 && (
          <section className="section mt-7">
            <SectionHead title="Also today">
              <p className="label">{rest.length} articles</p>
            </SectionHead>
            <Index articles={rest} />
          </section>
        )}
      </>
    );
  }

  // Personalised shape: two named rows.
  const { forYou = [], fromFollowed = [] } = data;

  return (
    <>
      {forYou.length > 0 ? (
        <>
          <Lead article={forYou[0]} />
          {forYou.length > 1 && (
            <section className="section mt-7">
              <SectionHead title="In your categories" />
              <Index articles={forYou.slice(1)} />
            </section>
          )}
        </>
      ) : (
        <Empty title="Nothing in your categories yet">
          Choose a few more interests and this page fills up.
        </Empty>
      )}

      {fromFollowed.length > 0 && (
        <section className="section">
          <SectionHead title="From writers you follow" />
          <Index articles={fromFollowed} />
        </section>
      )}
    </>
  );
}
