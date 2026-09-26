/**
 * The editorial review queue (PDD Figures 5.48 to 5.49).
 *
 * Operate mode, and the screen with the most riding on it: approving here
 * publishes, and publishing is when a credibility score first becomes visible to
 * readers. So the queue shows the score an article would carry before the editor
 * commits, alongside the sourcing that produced it.
 *
 * An editor sees only their assigned categories. The server decides that, so an
 * empty queue is a legitimate state, and the page says which kind of empty it is.
 *
 * The server orders the queue by review priority, riskiest first, and each item
 * says why it sits where it does. Editors can approve several at once, and any
 * article the system published during a backlog waits at the top for an editor
 * to confirm it.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import {
  AccuracyRate,
  CredibilityLedger,
  CredibilityMeter,
} from "../components/Credibility";
import { CoverFigure } from "../components/CoverImage";
import { StoredOriginality } from "../components/Originality";
import { SourceList } from "../components/Sources";
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

const PRIORITY_LABELS = {
  newContributor: "New writer with no record yet",
  accuracy: "Writer accuracy below the baseline",
  sources: "Fewer sources than expected",
  duplicate: "Title matches another article",
  similarity: "Text matches another article or a cited source",
  waiting: "Time spent waiting",
};

/** Why this article sits where it does in the queue. The same arithmetic, shown. */
function PriorityNote({ priority }) {
  if (!priority) return null;
  const parts = Object.entries(priority.breakdown).filter(([, value]) => value > 0);

  return (
    <div className="priority-note mt-5">
      <p className="label">Review priority {Math.round(priority.priority)}</p>
      {parts.length === 0 ? (
        <p className="meta mt-2">Trusted writer, well sourced, nothing flagged.</p>
      ) : (
        <ul className="priority-list mt-2">
          {parts.map(([key, value]) => (
            <li key={key}>
              <span>{PRIORITY_LABELS[key] ?? key}</span>
              <span className="priority-value">+{value.toFixed(1)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Articles the system published during a backlog, waiting for a human. */
function AwaitingConfirmation({ articles, onDone, onError }) {
  const [busyId, setBusyId] = useState(null);

  async function confirm(article) {
    setBusyId(article.id);
    try {
      await api.post(`/review/${article.id}/confirm`);
      onDone(`Confirmed “${article.title}”. Readers no longer see it as unreviewed.`);
    } catch (e) {
      onError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="section mt-7">
      <SectionHead title="Published before review">
        <p className="label">{articles.length} to confirm</p>
      </SectionHead>
      <p className="meta">
        These went live automatically while the queue was backed up, before an
        editor read them. Readers see each one marked as not yet reviewed until you
        confirm it. If one is wrong, open it and log a correction instead.
      </p>
      <ul className="confirm-list mt-5">
        {articles.map((article) => (
          <li key={article.id} className="confirm-row">
            <div>
              <Link className="link" to={`/articles/${article.slug}`}>
                <span className="entry-title">{article.title}</span>
              </Link>
              <p className="entry-meta mt-2">
                <span>{article.contributor.name}</span>
                {article.review?.autoPublishedAt && (
                  <span className="dot">
                    Published {formatDate(article.review.autoPublishedAt)}
                  </span>
                )}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              busy={busyId === article.id}
              onClick={() => confirm(article)}
            >
              Confirm reviewed
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Submission({ article, selected, onToggle, onDone, onError }) {
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  // A verdict on a source changes the projected score, so both are local.
  const [sources, setSources] = useState(article.sources);
  const [credibility, setCredibility] = useState(article.credibility);

  function onVerdict({ source, credibility: next }) {
    setSources((list) => list.map((s) => (s.id === source.id ? source : s)));
    setCredibility((c) => ({ ...c, ...next, prospective: true }));
  }

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

  const validSources = sources.filter((s) => s.isValid).length;
  const flagged = sources.filter((s) => s.rating?.flagged && !s.rating?.editorVerdict).length;

  return (
    <article className={selected ? "submission submission--selected" : "submission"}>
      <div className="submission-main">
        <label className="batch-pick">
          <input type="checkbox" checked={selected} onChange={onToggle} />
          <span>Include in batch approval</span>
        </label>

        <h3 className="entry-title mt-3">{article.title}</h3>

        <p className="entry-meta mt-3">
          <span>{article.contributor.name}</span>
          <span className="dot" aria-hidden="true" />
          <AccuracyRate rate={article.contributor.accuracyRate} />
          {article.submittedAt && (
            <span className="dot">Submitted {formatDate(article.submittedAt)}</span>
          )}
        </p>

        {article.summary && <p className="entry-summary mt-4">{article.summary}</p>}

        <PriorityNote priority={article.priority} />

        {/* The image is part of what is being approved: an editor checks it
            shows what the credit says, and that the credit is plausible. */}
        {article.coverImage && (
          <div className="review-cover mt-5">
            <p className="label">Cover image</p>
            <CoverFigure image={article.coverImage} className="mt-3" />
            <p className="meta mt-2">Described as: {article.coverImage.alt || "no description"}</p>
          </div>
        )}

        <StoredOriginality articleId={article.id} summary={article.originality} />

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
            {validSources} source{validSources === 1 ? "" : "s"} counting towards the score
          </p>
          {flagged > 0 && (
            <p className="source-flag-note mt-2">
              {flagged} flagged source{flagged === 1 ? "" : "s"}: check {flagged === 1 ? "it" : "them"} before approving.
            </p>
          )}
          {sources.length > 0 ? (
            <div className="mt-3">
              <SourceList sources={sources} articleId={article.id} reviewable onChange={onVerdict} />
            </div>
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
          <CredibilityMeter credibility={credibility} />
        </div>
        {/* The editor sees the same ledger the reader will, before deciding. */}
        <CredibilityLedger credibility={credibility} />
        <p className="meta mt-4">
          Provisional until you approve. It becomes visible to readers the moment
          you do.
        </p>
      </aside>
    </article>
  );
}

/**
 * Approve several articles in one decision.
 *
 * The ids sent are exactly the ones ticked on screen. The server re-checks each
 * one as a single approval would, and reports any it could not publish rather
 * than failing the whole batch.
 */
function BatchBar({ articles, selected, setSelected, onDone, onError }) {
  const [busy, setBusy] = useState(false);
  const count = selected.size;

  async function approveSelected() {
    setBusy(true);
    try {
      const result = await api.post("/review/batch-approve", {
        articleIds: [...selected],
      });
      const published = result.approved.length;
      const failed = result.failed.length;
      onDone(
        `Published ${published} article${published === 1 ? "" : "s"}.` +
          (failed
            ? ` ${failed} could not be published: ${result.failed
                .map((f) => f.reason)
                .join(" ")}`
            : ""),
      );
      setSelected(new Set());
    } catch (e) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="batch-bar">
      <p className="meta">
        {count === 0
          ? "Tick articles to approve several at once. The lowest-risk ones sit at the bottom."
          : `${count} selected`}
      </p>
      <div className="row gap-3">
        {count < articles.length && (
          <Button
            variant="quiet"
            size="sm"
            onClick={() => setSelected(new Set(articles.map((a) => a.id)))}
          >
            Select all
          </Button>
        )}
        {count > 0 && (
          <Button variant="quiet" size="sm" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        )}
        <Button
          variant="primary"
          size="sm"
          busy={busy}
          disabled={count === 0}
          onClick={approveSelected}
        >
          Approve {count > 0 ? count : ""} selected
        </Button>
      </div>
    </div>
  );
}

export default function ReviewQueue() {
  const [queue, setQueue] = useState(null);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => new Set());

  const load = useCallback(() => {
    api
      .get("/review/queue")
      .then((data) => {
        setQueue(data);
        // Drop any selection that is no longer in the queue, so a batch can
        // never include an article that has already been dealt with.
        const present = new Set(data.articles.map((a) => a.id));
        setSelected((prev) => new Set([...prev].filter((id) => present.has(id))));
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  function handleDone(message) {
    setNotice(message);
    setError(null);
    load();
  }

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (error && !queue) {
    return <Notice>{error}</Notice>;
  }

  if (!queue) {
    return <div className="skeleton" style={{ height: "16rem" }} />;
  }

  const awaiting = queue.awaitingConfirmation ?? [];

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">Review queue</h1>
          <p className="meta mt-3">
            Riskiest first. New writers, thin sourcing and repeated titles rise to
            the top, and anything that has waited long enough rises with them. You
            review articles in the categories assigned to you.
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

      {awaiting.length > 0 && (
        <AwaitingConfirmation articles={awaiting} onDone={handleDone} onError={setError} />
      )}

      <section className="section mt-7">
        <SectionHead title="Awaiting review">
          <p className="label">{queue.articles.length} waiting</p>
        </SectionHead>

        {queue.note && (
          <Empty title="No categories are assigned to you yet">
            An administrator assigns editors to categories. Until then this
            queue stays empty, which is not a fault.
          </Empty>
        )}

        {!queue.note && queue.articles.length === 0 && (
          <Empty title="Nothing is waiting">
            Everything submitted in your categories has been reviewed.
          </Empty>
        )}

        {queue.articles.length > 1 && (
          <BatchBar
            articles={queue.articles}
            selected={selected}
            setSelected={setSelected}
            onDone={handleDone}
            onError={setError}
          />
        )}

        <div className="stack">
          {queue.articles.map((article) => (
            <Submission
              key={article.id}
              article={article}
              selected={selected.has(article.id)}
              onToggle={() => toggle(article.id)}
              onDone={handleDone}
              onError={setError}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
