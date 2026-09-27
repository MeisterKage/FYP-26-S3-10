/**
 * Moderation (PDD Figures 5.50, 5.58).
 *
 * An article reaches this queue once its open reports cross the threshold an
 * administrator sets. The threshold is shown rather than hidden, because a
 * moderator seeing an empty queue should be able to tell "nothing is disputed"
 * from "the bar is set high".
 *
 * Upholding a report and logging a correction both move scores. The screen says
 * so at the point of decision and shows the score before and after, so a
 * moderator is never guessing at the consequence of a click.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { ROLES, useAuth } from "../auth";
import { Button, Empty, Notice, SectionHead, formatDate } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

function CorrectionForm({ article, onDone, onCancel }) {
  const [type, setType] = useState("correction");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.post(
        `/moderation/articles/${article.articleId}/correction`,
        { type, reason },
      );
      onDone(
        `Logged a ${type} against “${article.title}”.` +
          (typeof result?.credibilityScore === "number"
            ? ` Its score is now ${Math.round(result.credibilityScore)}.`
            : ""),
      );
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <form className="well mt-5" onSubmit={submit}>
      <fieldset className="fieldset">
        <legend className="field-label">What is being recorded?</legend>
        <div className="checkbox-grid mt-3">
          <label className="checkbox">
            <input
              type="radio"
              name={`type-${article.articleId}`}
              value="correction"
              checked={type === "correction"}
              onChange={() => setType("correction")}
            />
            <span>Correction — the article stays published</span>
          </label>
          <label className="checkbox">
            <input
              type="radio"
              name={`type-${article.articleId}`}
              value="retraction"
              checked={type === "retraction"}
              onChange={() => setType("retraction")}
            />
            <span>Retraction — the article is withdrawn</span>
          </label>
        </div>
      </fieldset>

      <label className="field-label mt-5" htmlFor={`reason-${article.articleId}`}>
        Why?
      </label>
      <p className="field-hint">
        This is permanent. It appears in the article&rsquo;s revision history and
        lowers both its score and the writer&rsquo;s accuracy rate.
      </p>
      <textarea
        id={`reason-${article.articleId}`}
        className="textarea mt-3"
        rows={3}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        required
      />

      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}

      <div className="row gap-4 mt-5">
        <Button variant="primary" type="submit" busy={busy} disabled={!reason.trim()}>
          Log {type}
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Flagged({ article, onDone, onError, isAdmin }) {
  const [correcting, setCorrecting] = useState(false);
  const [busy, setBusy] = useState(null);

  async function resolve(report, outcome) {
    setBusy(report.id);
    try {
      const result = await api.post(`/moderation/reports/${report.id}/resolve`, {
        outcome,
      });
      onDone(
        outcome === "upheld"
          ? `Report upheld. “${article.title}” now scores ${Math.round(
              result.credibilityScore,
            )}.`
          : "Report dismissed. Nothing about the article changed.",
      );
    } catch (e) {
      onError(e.message);
      setBusy(null);
    }
  }

  async function overturn(correction) {
    if (
      !window.confirm(
        "Overturn this correction? The article and its writer are rescored as if it had never been issued.",
      )
    )
      return;
    setBusy(`c${correction.id}`);
    try {
      await api.post(`/moderation/corrections/${correction.id}/overturn`);
      onDone("Correction overturned and scores restored.");
    } catch (e) {
      onError(e.message);
      setBusy(null);
    }
  }

  return (
    <article className="submission">
      <div className="submission-main">
        <h3 className="entry-title">
          <Link className="link-quiet" to={`/articles/${article.slug}`}>
            {article.title}
          </Link>
        </h3>
        <p className="entry-meta mt-3">
          <span className="status" data-status={article.status}>
            {article.status}
          </span>
          <span className="dot" aria-hidden="true" />
          <span>
            {article.openReports} open report{article.openReports === 1 ? "" : "s"}
          </span>
          <span className="dot" aria-hidden="true" />
          <span className="tabular">
            Score {Math.round(article.credibilityScore ?? 0)}
          </span>
        </p>

        <p className="label mt-6">What readers said</p>
        <ul className="report-list mt-3">
          {article.reports.map((report) => (
            <li className="report" key={report.id}>
              <div>
                <p className="comment-body">{report.reason}</p>
                <p className="meta mt-2">Reported {formatDate(report.reportedAt)}</p>
              </div>
              <div className="row gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  busy={busy === report.id}
                  onClick={() => resolve(report, "upheld")}
                >
                  Uphold
                </Button>
                <Button
                  size="sm"
                  variant="quiet"
                  busy={busy === report.id}
                  onClick={() => resolve(report, "dismissed")}
                >
                  Dismiss
                </Button>
              </div>
            </li>
          ))}
        </ul>

        {article.corrections.length > 0 && (
          <>
            <p className="label mt-6">Already recorded</p>
            <ul className="report-list mt-3">
              {article.corrections.map((c) => (
                <li className="report" key={c.id}>
                  <div>
                    <p className="comment-body">
                      <span className="tag">{c.type}</span> {c.reason}
                    </p>
                    <p className="meta mt-2">
                      {formatDate(c.issuedAt)}
                      {c.overturned && " · overturned"}
                    </p>
                  </div>
                  {/* PRD 1.3.2 administrator power 4: only an administrator may
                      reverse an editor's call, and never an editor their own. */}
                  {isAdmin && !c.overturned && (
                    <Button
                      size="sm"
                      variant="quiet"
                      busy={busy === `c${c.id}`}
                      onClick={() => overturn(c)}
                    >
                      Overturn
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}

        {correcting ? (
          <CorrectionForm
            article={article}
            onDone={onDone}
            onCancel={() => setCorrecting(false)}
          />
        ) : (
          <div className="row gap-4 mt-6">
            <Button variant="outline" onClick={() => setCorrecting(true)}>
              Log a correction or retraction
            </Button>
          </div>
        )}
      </div>
    </article>
  );
}

export default function Moderation() {
  const { user } = useAuth();
  const isAdmin = user?.role === ROLES.ADMIN;

  const [data, setData] = useState(null);
  usePageTitle("Moderation");
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api
      .get("/moderation/reports")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  function done(message) {
    setNotice(message);
    setError(null);
    load();
  }

  if (error && !data) return <Notice>{error}</Notice>;
  if (!data) return <div className="skeleton" style={{ height: "16rem" }} />;

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">Flagged content</h1>
          <p className="meta mt-3">
            An article appears here once{" "}
            <strong>{data.threshold} readers</strong> have reported it, a threshold
            an administrator sets. You see only your assigned sections.
          </p>
        </div>
      </header>

      {notice && (
        <div className="mt-6">
          <Notice tone="quiet">{notice}</Notice>
        </div>
      )}
      {error && (
        <div className="mt-6">
          <Notice>{error}</Notice>
        </div>
      )}

      <section className="section mt-7">
        <SectionHead title="Awaiting a decision">
          <p className="label">{data.flagged.length} article{data.flagged.length === 1 ? "" : "s"}</p>
        </SectionHead>

        {data.flagged.length === 0 ? (
          <Empty title="Nothing has crossed the threshold">
            Readers can report any published article. One appears here once{" "}
            {data.threshold} separate reports are open against it.
          </Empty>
        ) : (
          <div className="stack">
            {data.flagged.map((article) => (
              <Flagged
                key={article.articleId}
                article={article}
                onDone={done}
                onError={setError}
                isAdmin={isAdmin}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
