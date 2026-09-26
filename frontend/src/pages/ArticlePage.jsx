/**
 * The reading view (PDD Figure 5.6).
 *
 * Byline, date, credibility, and accuracy all sit above the body. The score's
 * arithmetic sits beside the article in a margin column on wide screens and
 * folds under the headline on narrow ones. The reference calls its supporting
 * material marginalia, and a score the reader has to hunt for is not disclosed.
 *
 * A paywalled article arrives from the server without a body at all, so this
 * renders whatever it was given.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import {
  AccuracyRate,
  CredibilityLedger,
  CredibilityMeter,
} from "../components/Credibility";
import ArticleExtras from "../components/ArticleExtras";
import { CoverFigure } from "../components/CoverImage";
import Corrections from "../components/Corrections";
import ReportPanel from "../components/ReportPanel";
import Discussion from "../components/Discussion";
import { FlagIcon, SourceIcon } from "../components/Icon";
import { Button, Empty, Notice, formatDate } from "../components/UI";

/**
 * Who vouched for this article. Absent while it awaits review: the meter
 * already says so, and no editor has vouched for it yet.
 */
function ApprovedBy({ review }) {
  const reviewer = review?.reviewer;
  if (!reviewer) return null;
  return (
    <span>
      Approved by{" "}
      {reviewer.onPanel ? (
        <Link className="link-quiet" to={`/editors/${reviewer.id}`}>
          {reviewer.name}
        </Link>
      ) : (
        reviewer.name
      )}
      {reviewer.title && `, ${reviewer.title}`}
    </span>
  );
}

export default function ArticlePage() {
  const { slug } = useParams();
  const { user } = useAuth();

  const [article, setArticle] = useState(null);
  const [error, setError] = useState(null);
  const [reported, setReported] = useState(false);
  const [reporting, setReporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setArticle(null);
    setError(null);
    setReported(false);
    window.scrollTo(0, 0);

    api
      .get(`/articles/${slug}`)
      .then((data) => !cancelled && setArticle(data.article))
      .catch((e) => !cancelled && setError(e.message));

    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (error) {
    return (
      <Empty
        title="This article isn't here"
        action={
          <Button variant="outline" as={Link} to="/" className="mt-4">
            Back to the front page
          </Button>
        }
      >
        {error}
      </Empty>
    );
  }

  if (!article) {
    return (
      <div className="read">
        <div className="skeleton skeleton-line" style={{ width: "80%", height: "3rem" }} />
        <div className="skeleton skeleton-line" style={{ width: "45%", height: "1.5rem" }} />
        <div className="skeleton" style={{ height: "18rem", marginTop: "2rem" }} />
        <span className="sr-only">Loading article</span>
      </div>
    );
  }

  const date = formatDate(article.publishedAt);

  return (
    <article className="article">
      <header className="article-head">
        <h1 className="title">{article.title}</h1>

        {article.summary && <p className="lead mt-5">{article.summary}</p>}

        <div className="article-byline">
          <Link
            className="link-quiet"
            style={{ color: "var(--ink)" }}
            to={`/contributors/${article.contributor.id}`}
          >
            {article.contributor.name}
          </Link>
          <AccuracyRate rate={article.contributor.accuracyRate} />
          {date && <span>{date}</span>}
          {article.country && (
            <Link className="link-quiet" to={`/countries/${article.country.code.toLowerCase()}`}>
              {article.country.name}
            </Link>
          )}
          <ApprovedBy review={article.review} />
        </div>
      </header>

      <div className="article-grid">
        <div className="article-body">
          <CoverFigure image={article.coverImage} priority />
          {article.paywalled ? (
            <>
              <div className="prose">
                <p>{article.bodyPreview}</p>
              </div>
              <div className="paywall">
                <h2 className="heading">Continue reading</h2>
                <p className="lead mt-4">
                  This article is published for {article.contributor.name}&rsquo;s
                  subscribers.
                </p>
                <div className="row gap-4 mt-5">
                  {user ? (
                    <Button variant="primary">Subscribe to read</Button>
                  ) : (
                    <>
                      <Button variant="primary" as={Link} to="/register">
                        Create an account
                      </Button>
                      <Link className="link-quiet" to="/login">
                        Already have one? Sign in
                      </Link>
                    </>
                  )}
                </div>
              </div>
            </>
          ) : (
            // Safe: the server sanitises against an allowlist on write, so
            // nothing reaches here that was not already filtered.
            <div
              className="prose"
              dangerouslySetInnerHTML={{ __html: article.body }}
            />
          )}

          {article.sources?.length > 0 && (
            <section className="sources">
              <h2 className="label">
                Sources
                <span className="sources-count">{article.sources.length}</span>
              </h2>
              <ol className="sources-list">
                {article.sources.map((source, i) => (
                  <li key={source.url}>
                    <span className="sources-num">{i + 1}</span>
                    <a
                      className="link-quiet"
                      href={source.url}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      {source.label || source.url}
                    </a>
                  </li>
                ))}
              </ol>
              <p className="meta mt-4">
                <SourceIcon size={14} style={{ display: "inline", verticalAlign: "-2px" }} />{" "}
                Each verified source raises this article&rsquo;s score.
              </p>
            </section>
          )}

          <Corrections article={article} />

          <footer className="article-foot">
            {reported ? (
              <Notice tone="quiet">
                Thank you. An editor will review this article.
              </Notice>
            ) : (
              user &&
              (reporting ? (
                <ReportPanel
                  article={article}
                  onDone={() => {
                    setReporting(false);
                    setReported(true);
                  }}
                  onCancel={() => setReporting(false)}
                />
              ) : (
                <Button variant="quiet" size="sm" onClick={() => setReporting(true)}>
                  <FlagIcon size={16} />
                  Report an inaccuracy
                </Button>
              ))
            )}
            <ArticleExtras article={article} />
          </footer>

          {/* Only a published article has a discussion: the server rejects
              comments on anything else, so an author previewing their own draft
              should not be shown a form that cannot work. */}
          {article.status === "published" && <Discussion article={article} />}
        </div>

        <aside className="article-margin">
          <div className="margin-card">
            <p className="label">Credibility</p>
            <div className="mt-4">
              <CredibilityMeter credibility={article.credibility} review={article.review} />
            </div>
            <CredibilityLedger credibility={article.credibility} />
            <p className="meta mt-5">
              Arithmetic, not prediction.{" "}
              <Link className="link-quiet" to="/about">
                How this is calculated
              </Link>
            </p>
          </div>
        </aside>
      </div>
    </article>
  );
}
