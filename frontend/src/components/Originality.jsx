/**
 * The originality report: how much of an article's text also appears elsewhere,
 * with the evidence side by side.
 *
 * The number is arithmetic (the share of the article's own words that sit in a
 * passage found elsewhere) and every match shows the passages that produced it,
 * so an editor judges the evidence rather than trusting a figure. Quotations
 * are never counted; they are checked against the cited sources instead.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { Button, Notice } from "./UI";

const LEVELS = {
  original: { label: "Original", note: "Nothing beyond common phrasing matches." },
  partial: { label: "Partial match", note: "Part of this text also appears elsewhere. Read the passages." },
  substantial: { label: "Substantial match", note: "Much of this text also appears elsewhere." },
};

/** One-line summary for lists: the percentage and what it means. */
export function OriginalityBadge({ summary }) {
  if (!summary) return <span className="orig-badge">Not checked</span>;
  const level = LEVELS[summary.level] ?? LEVELS.original;
  return (
    <span className={`orig-badge orig-badge--${summary.level}`}>
      {Math.round(summary.percent)}% matched · {level.label}
    </span>
  );
}

function MatchTitle({ match }) {
  if (match.kind === "source") {
    return (
      <>
        Cited source:{" "}
        <a className="link-quiet" href={match.url} target="_blank" rel="noreferrer noopener">
          {match.label || match.url}
        </a>
      </>
    );
  }
  if (!match.title) return "Another writer's submission, not yet published";
  const label = match.sameWriter ? `Your own article: ${match.title}` : match.title;
  return match.public ? (
    <Link className="link-quiet" to={`/articles/${match.slug}`}>
      {label}
    </Link>
  ) : (
    `${label} (${match.status})`
  );
}

function Match({ match }) {
  const [open, setOpen] = useState(false);
  const note =
    match.kind === "source"
      ? "Copied from a page this article cites, without quotation marks."
      : match.sameWriter
        ? "Reused from an earlier article by the same writer."
        : null;

  return (
    <li className="orig-match">
      <div className="orig-match-head">
        <span className="orig-match-percent">{Math.round(match.percent)}%</span>
        <span className="orig-match-title">
          <MatchTitle match={match} />
        </span>
      </div>
      {note && <p className="meta mt-2">{note}</p>}
      <button type="button" className="link-quiet orig-toggle mt-2" onClick={() => setOpen(!open)}
        aria-expanded={open}>
        {open ? "Hide" : "Show"} {match.passages.length} matching passage
        {match.passages.length === 1 ? "" : "s"}
      </button>
      {open && (
        <ol className="orig-passages mt-3">
          {match.passages.map((p, i) => (
            <li key={i} className={p.otherText ? "orig-pair" : ""}>
              <blockquote>
                <p className="label">This article</p>
                <mark>{p.text}</mark>
              </blockquote>
              {p.otherText && (
                <blockquote>
                  <p className="label">{match.kind === "source" ? "The source" : "The other article"}</p>
                  <mark>{p.otherText}</mark>
                </blockquote>
              )}
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}

export function OriginalityReport({ report }) {
  if (!report) return null;
  const level = LEVELS[report.level] ?? LEVELS.original;
  const checked = report.sources.filter((s) => s.status === "checked").length;
  const unverified = report.quotes.filter((q) => !q.verified);

  return (
    <div className="orig-report">
      <div className="orig-head">
        <p className={`orig-percent orig-percent--${report.level}`}>
          {Math.round(report.percent)}%
        </p>
        <div>
          <p className="sub">{level.label}</p>
          <p className="meta mt-1">
            {level.note} {Math.round(report.percent)}% of this article&rsquo;s own words
            (quotations excluded) also appear in the text below.
          </p>
        </div>
      </div>

      {report.matches.length > 0 && (
        <ul className="orig-matches mt-5">
          {report.matches.map((m, i) => (
            <Match key={`${m.kind}-${m.articleId ?? m.url}-${i}`} match={m} />
          ))}
        </ul>
      )}

      {report.sources.length > 0 && (
        <div className="mt-5">
          <p className="label">
            Cited sources checked: {checked} of {report.sources.length}
          </p>
          <ul className="orig-sources mt-2">
            {report.sources
              .filter((s) => s.status !== "checked")
              .map((s) => (
                <li key={s.url} className="meta">
                  {s.label || s.url}: {s.reason}
                </li>
              ))}
          </ul>
        </div>
      )}

      {report.quotes.length > 0 && (
        <div className="mt-5">
          <p className="label">
            Quotations: {report.quotes.length - unverified.length} of {report.quotes.length} found
            in a cited source
          </p>
          {unverified.length > 0 && (
            <ul className="orig-quotes mt-2">
              {unverified.map((q, i) => (
                <li key={i} className="meta">
                  &ldquo;{q.text}&rdquo; was not found in any cited source. That is normal
                  for an interview; otherwise, cite where it came from.
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="meta mt-5">{report.scope}</p>
    </div>
  );
}

/**
 * A check a writer or editor runs on demand. `articleId` must exist (saved);
 * `beforeCheck` lets the editor save pending changes first.
 */
export function OriginalityCheck({ articleId, initial = null, beforeCheck, label = "Check originality" }) {
  const [report, setReport] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const id = beforeCheck ? await beforeCheck() : articleId;
      const result = await api.post(`/articles/${id}/originality`);
      setReport(result.report);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="orig-check">
      <div className="row gap-4">
        <Button type="button" variant="outline" size="sm" busy={busy} onClick={run}>
          {report ? "Check again" : label}
        </Button>
        <p className="meta">
          Compares with every article on Wollongong News and the pages you cite. Takes a few
          seconds.
        </p>
      </div>
      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}
      {report && (
        <div className="mt-5">
          <OriginalityReport report={report} />
        </div>
      )}
    </section>
  );
}

/** For the review queue: load the stored report when the editor opens it. */
export function StoredOriginality({ articleId, summary }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  function load(event) {
    if (!event.currentTarget.open || report) return;
    api
      .get(`/articles/${articleId}/originality`)
      .then((d) => setReport(d.report))
      .catch((e) => setError(e.message));
  }

  return (
    <details className="review-originality mt-5" onToggle={load}>
      <summary>
        Originality <OriginalityBadge summary={summary} />
      </summary>
      <div className="mt-4">
        {error && <Notice>{error}</Notice>}
        {!report && !error && <p className="meta">Loading the report.</p>}
        {report && <OriginalityReport report={report} />}
      </div>
    </details>
  );
}
