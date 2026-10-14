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
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import {
  AccuracyRate,
  CredibilityLedger,
  CredibilityMeter,
} from "../components/Credibility";
import ArticleExtras from "../components/ArticleExtras";
import { CoverFigure } from "../components/CoverImage";
import { ArticleAudio } from "../components/ArticleAudio";
import Corrections from "../components/Corrections";
import { SourceList } from "../components/Sources";
import { WriterCard } from "../components/WriterCard";
import { SimilarArticles } from "../components/SimilarArticles";
import { ArticleAnalysis } from "../components/ArticleAnalysis";
import ReportPanel from "../components/ReportPanel";
import Discussion from "../components/Discussion";
import { FlagIcon, SourceIcon } from "../components/Icon";
import { Button, Empty, Notice, formatDate } from "../components/UI";
import { startSubscription } from "./Checkout";
import { usePageTitle } from "../usePageTitle";
import { useI18n } from "../i18n";

/**
 * Who vouched for this article. Absent while it awaits review: the meter
 * already says so, and no editor has vouched for it yet.
 */
function ApprovedBy({ review }) {
  const { t } = useI18n();
  const reviewer = review?.reviewer;
  if (!reviewer) return null;
  return (
    <span>
      {t("article.approvedBy")}{" "}
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

/**
 * Where a republished article came from, above it. The licence requires the
 * link to the original (preferably at the top) and The Conversation asks for
 * its invisible page-view counter, loaded here rather than stored in the body.
 */
function Republished({ info }) {
  return (
    <p className="republished-note">
      Republished from{" "}
      <a className="link-quiet" href={info.url} target="_blank" rel="noopener">
        {info.publisher}
      </a>{" "}
      under a{" "}
      <a className="link-quiet" href={info.licenceUrl} target="_blank" rel="noopener license">
        Creative Commons licence ({info.licence})
      </a>
      .{" "}
      <a className="link-quiet" href={info.url} target="_blank" rel="noopener">
        Read the original
      </a>
      {info.counterUrl && (
        <img src={info.counterUrl} alt="" width="1" height="1" className="republished-counter"
          referrerPolicy="no-referrer-when-downgrade" />
      )}
    </p>
  );
}

/** The credit line republishers are asked to place at the end. */
function RepublishedFooter({ info }) {
  return (
    <p className="republished-footer">
      This article is republished from{" "}
      <a className="link-quiet" href={info.url} target="_blank" rel="noopener">{info.publisher}</a>{" "}
      under a Creative Commons license.{" "}
      <a className="link-quiet" href={info.url} target="_blank" rel="noopener">
        Read the original article
      </a>
      .
    </p>
  );
}

const VOICE_LANGS = { en: "en-AU", zh: "zh-CN", ms: "ms-MY" };

export default function ArticlePage() {
  const { slug } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  // Separate from `error`, which replaces the whole article with a not-found state.
  const [subscribeError, setSubscribeError] = useState(null);

  const [article, setArticle] = useState(null);
  const proseRef = useRef(null);
  const { t, lang, country } = useI18n();
  usePageTitle(article?.title);
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

  // A translation still being made: check now and then, and swap it in when it
  // is ready. The reload is not counted as another view (?seen=1).
  const preparing = Boolean(article?.translation?.preparing);
  useEffect(() => {
    if (!preparing) return undefined;
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (tries > 12) {
        clearInterval(timer);
        return;
      }
      api
        .get(`/articles/${slug}/translation`)
        .then((data) => {
          if (!data.translation?.available) return undefined;
          clearInterval(timer);
          return api.get(`/articles/${slug}?seen=1`).then((fresh) => setArticle(fresh.article));
        })
        .catch(() => {});
    }, 15000);
    return () => clearInterval(timer);
  }, [preparing, slug]);

  if (error) {
    return (
      <Empty
        level={1}
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

        {article.republication && <Republished info={article.republication} />}

        {/* Which language this is: AI translated, or English because no
            translation exists yet. */}
        {article.translation && (
          <p className={`translation-note${article.translation.available ? "" : " translation-note--missing"}`}>
            {article.translation.note}
          </p>
        )}

        <div className="article-byline">
          {article.republication ? (
            // The authors, with their institutions, as the licence asks.
            <span className="republished-authors">
              By {article.republication.authors.join("; ")}
            </span>
          ) : (
            <>
              <Link
                className="link-quiet"
                style={{ color: "var(--ink)" }}
                to={`/contributors/${article.contributor.id}`}
              >
                {article.contributor.name}
              </Link>
              <AccuracyRate rate={article.contributor.accuracyRate} />
            </>
          )}
          {date && <span>{date}</span>}
          {article.country && (
            <Link className="link-quiet" to={`/countries/${article.country.code.toLowerCase()}`}>
              {country(article.country.code, article.country.name)}
            </Link>
          )}
          <ApprovedBy review={article.review} />
        </div>
      </header>

      <div className="article-grid">
        <div className="article-body">
          <CoverFigure image={article.coverImage} priority />
          {!article.paywalled && (
            <ArticleAudio title={article.title} brief={article.inBrief} proseRef={proseRef}
              bodyKey={`${article.id}-${lang}`}
              voiceLang={article.translation?.available ? VOICE_LANGS[lang] : "en-AU"} />
          )}
          {article.paywalled ? (
            <>
              <div className="prose">
                <p>{article.bodyPreview}</p>
              </div>
              <div className="paywall">
                <h2 className="heading">{t("article.continueReading")}</h2>
                <p className="lead mt-4">
                  {t("article.forSubscribers", { name: article.contributor.name })}
                </p>
                <div className="row gap-4 mt-5">
                  {user ? (
                    <Button
                      variant="primary"
                      onClick={() =>
                        startSubscription(article.contributor.id, navigate).catch((e) =>
                          setSubscribeError(e.message),
                        )
                      }
                    >
                      {t("article.subscribeToRead")}
                    </Button>
                  ) : (
                    <>
                      <Button variant="primary" as={Link} to="/register">
                        {t("article.createAccount")}
                      </Button>
                      <Link className="link-quiet" to="/login">
                        {t("article.haveAccount")}
                      </Link>
                      <Link className="link-quiet" to="/pricing">
                        {t("article.whatCosts")}
                      </Link>
                    </>
                  )}
                </div>
                {subscribeError && (
                  <div className="mt-4">
                    <Notice>{subscribeError}</Notice>
                  </div>
                )}
              </div>
            </>
          ) : (
            // Safe: the server sanitises against an allowlist on write, so
            // nothing reaches here that was not already filtered.
            <div
              ref={proseRef}
              className="prose"
              dangerouslySetInnerHTML={{ __html: article.body }}
            />
          )}

          {/* Where a reader who liked it decides to follow or subscribe. Left out
              behind a paywall, which has its own subscribe button in place. */}
          {!article.paywalled && article.writer && !article.republication && (
            <WriterCard writer={article.writer} />
          )}
          {article.republication && <RepublishedFooter info={article.republication} />}

          {article.sources?.length > 0 && (
            <section className="sources">
              <h2 className="label">
                {t("article.sources")}
                <span className="sources-count">{article.sources.length}</span>
              </h2>
              <SourceList sources={article.sources} />
              <p className="meta mt-4">
                <SourceIcon size={14} style={{ display: "inline", verticalAlign: "-2px" }} />{" "}
                {t("article.sourcesNote")}{" "}
                <Link className="link-quiet" to="/about#sources">{t("article.howGraded")}</Link>
              </p>
            </section>
          )}

          {article.status === "published" && <ArticleAnalysis slug={article.slug} />}

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
            <p className="label">{t("home.credibility")}</p>
            <div className="mt-4">
              <CredibilityMeter credibility={article.credibility} review={article.review} />
            </div>
            <CredibilityLedger credibility={article.credibility} />
            <p className="meta mt-5">
              {t("cred.arithmetic")}{" "}
              <Link className="link-quiet" to="/about">
                {t("cred.howCalculated")}
              </Link>
            </p>
          </div>
        </aside>
      </div>

      <SimilarArticles articles={article.similar} />
    </article>
  );
}
