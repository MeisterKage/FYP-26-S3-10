/**
 * The editorial review queue (PDD Figures 5.48–5.49).
 *
 * Operate mode, and the highest-stakes screen in the product: approving here
 * publishes, and publishing is when a credibility score first becomes visible to
 * readers. So the queue shows the score an article *would* carry before the
 * editor commits, alongside the sourcing that produced it.
 *
 * An editor sees only their assigned categories. The server decides that, so an
 * empty queue is a legitimate state — and it says which, rather than sitting
 * blank and looking broken.
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import {
  AccuracyRate,
  CredibilityLedger,
  CredibilityMeter,
} from "../components/Credibility";
import { SourceIcon } from "../components/Icon";
import { Button, Empty, Notice, SectionHead, formatDate } from "../components/UI";

function RejectForm({ article, onCancel, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/review/${article.id}/reject`, { reason });
      onDone(`Returned “${article.title}” to its writer.`);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <form className="reject well mt-5" onSubmit={submit}>
      <label className="field-label" htmlFor={`reason-${article.id}`}>
        Why is this being returned?
      </label>
      <p className="field-hint">
        The writer sees exactly this text, so name what needs to change.
      </p>
      <textarea
        id={`reason-${article.id}`}
        className="textarea mt-3"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={3}
        required
        autoFocus
      />
      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}
      <div className="row gap-4 mt-4">
        <Button variant="primary" type="submit" busy={busy} disabled={!reason.trim()}>
          Return to writer
        </Button>
        <Button variant="quiet" type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Submission({ article, onDone, onError }) {
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);

  async function approve() {
    setBusy(true);
    try {
      const result = await api.post(`/review/${article.id}/approve`);
      onDone(
        `Published “${article.title}” with a credibility score of ${Math.round(
          result.credibility.score,
        )}.`,
      );
    } catch (e) {
      onError(e.message);
      setBusy(false);
    }
  }

  const validSources = article.sources.filter((s) => s.isValid).length;

  return (
    <article className="submission">
      <div className="submission-main">
        <h3 className="entry-title">{article.title}</h3>

        <p className="entry-meta mt-3">
          <span>{article.contributor.name}</span>
          <span className="dot" aria-hidden="true" />
          <AccuracyRate rate={article.contributor.accuracyRate} />
          {article.submittedAt && (
            <span className="dot">Submitted {formatDate(article.submittedAt)}</span>
          )}
        </p>

        {article.summary && <p className="entry-summary mt-4">{article.summary}</p>}

        <details className="review-body mt-5">
          <summary>Read the full submission</summary>
          <div
            className="prose mt-5"
            dangerouslySetInnerHTML={{ __html: article.body }}
          />
        </details>

        <div className="review-sources mt-5">
          <p className="label">
            <SourceIcon size={14} style={{ display: "inline", verticalAlign: "-2px" }} />{" "}
            {validSources} verified source{validSources === 1 ? "" : "s"}
          </p>
          {article.sources.length > 0 ? (
            <ol className="sources-list mt-3">
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
          ) : (
            <p className="meta mt-3">
              No sources were tagged. This article will score lower for it.
            </p>
          )}
        </div>

        {rejecting ? (
          <RejectForm
            article={article}
            onCancel={() => setRejecting(false)}
            onDone={onDone}
          />
        ) : (
          <div className="row gap-4 mt-6">
            <Button variant="primary" onClick={approve} busy={busy}>
              Approve and publish
            </Button>
            <Button variant="outline" onClick={() => setRejecting(true)}>
              Return to writer
            </Button>
          </div>
        )}
      </div>

      <aside className="submission-aside">
        <p className="label">Score on publication</p>
        <div className="mt-4">
          <CredibilityMeter credibility={article.credibility} />
        </div>
        {/* The editor sees the same ledger the reader will, before deciding. */}
        <CredibilityLedger credibility={article.credibility} />
        <p className="meta mt-4">
          Provisional until you approve. It becomes visible to readers the moment
          you do.
        </p>
      </aside>
    </article>
  );
}

export default function ReviewQueue() {
  const [queue, setQueue] = useState(null);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api
      .get("/review/queue")
      .then(setQueue)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  function handleDone(message) {
    setNotice(message);
    setError(null);
    load();
  }

  if (error && !queue) {
    return <Notice>{error}</Notice>;
  }

  if (!queue) {
    return <div className="skeleton" style={{ height: "16rem" }} />;
  }

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">Review queue</h1>
          <p className="meta mt-3">
            Oldest submission first. You review articles in the categories
            assigned to you.
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
        <SectionHead title="Awaiting review">
          <p className="label">{queue.articles.length} waiting</p>
        </SectionHead>

        {queue.note && (
          <Empty title="No categories are assigned to you yet">
            An administrator assigns editors to categories. Until then this queue
            stays empty — it is not a fault.
          </Empty>
        )}

        {!queue.note && queue.articles.length === 0 && (
          <Empty title="Nothing is waiting">
            Everything submitted in your categories has been reviewed.
          </Empty>
        )}

        <div className="stack">
          {queue.articles.map((article) => (
            <Submission
              key={article.id}
              article={article}
              onDone={handleDone}
              onError={setError}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
