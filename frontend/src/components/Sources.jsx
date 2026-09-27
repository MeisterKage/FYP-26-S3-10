/**
 * An article's sources, each with its rating and the reason for it.
 *
 * A reader sees why one link counts for more than another: a government
 * statistics page and a deprecated tabloid are not the same evidence. In the
 * review queue the editor also gets the final word on each source, and has to
 * say why.
 */
import { useState } from "react";

import { api } from "../api";
import { Button } from "./UI";

const TONE = {
  official: "strong", research: "strong", institution: "strong", reliable: "strong",
  unrated: "neutral",
  unreliable: "weak", invalid: "weak", deprecated: "flag", retracted: "flag",
};

function Verdict({ articleId, source, onChange }) {
  const [mode, setMode] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function send(verdict) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post(
        `/review/${articleId}/sources/${source.id}/verdict`,
        verdict ? { verdict, reason } : { verdict: null },
      );
      onChange(result);
      setMode(null);
      setReason("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (mode) {
    return (
      <form className="source-verdict" onSubmit={(e) => { e.preventDefault(); send(mode); }}>
        <label className="sr-only" htmlFor={`reason-${source.id}`}>Reason</label>
        <input id={`reason-${source.id}`} className="input input-sm" value={reason}
          maxLength={500} autoFocus required
          placeholder={mode === "accepted" ? "Why this source is credible" : "Why it is not credible"}
          onChange={(e) => setReason(e.target.value)} />
        <Button type="submit" size="sm" variant="primary" busy={busy}>
          {mode === "accepted" ? "Accept" : "Mark not credible"}
        </Button>
        <Button type="button" size="sm" variant="quiet" onClick={() => setMode(null)}>Cancel</Button>
        {error && <p className="field-error">{error}</p>}
      </form>
    );
  }
  return (
    <div className="source-verdict">
      {source.rating?.editorVerdict ? (
        <Button size="sm" variant="quiet" busy={busy} onClick={() => send(null)}>
          Clear my verdict
        </Button>
      ) : (
        <>
          <Button size="sm" variant="outline" onClick={() => setMode("accepted")}>Accept</Button>
          <Button size="sm" variant="quiet" onClick={() => setMode("rejected")}>Not credible</Button>
        </>
      )}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

export function SourceList({ sources, articleId, reviewable = false, onChange }) {
  return (
    <ol className="sources-list">
      {sources.map((source, i) => {
        const r = source.rating;
        const verdict = r?.editorVerdict;
        return (
          <li key={source.id ?? source.url} className="source-item">
            <span className="sources-num">{i + 1}</span>
            <div className="source-body">
              <a className="link-quiet" href={source.url} target="_blank" rel="noreferrer noopener">
                {source.label || source.url}
              </a>
              {r && (
                <p className="source-rating">
                  <span className={`source-tier source-tier--${verdict === "rejected" ? "weak" : verdict === "accepted" ? "strong" : TONE[r.tier]}`}>
                    {r.label}
                  </span>
                  {/* Points are for editors weighing a source; a reader sees the grade and why. */}
                  {reviewable && <span className="source-points">+{r.points}</span>}
                  {verdict && (
                    <span className="source-editor">
                      {verdict === "accepted" ? "Accepted" : "Rejected"} by an editor: {r.editorReason}
                    </span>
                  )}
                </p>
              )}
              {r?.reason && <p className="source-reason">{r.reason}</p>}
              {reviewable && (
                <Verdict articleId={articleId} source={source} onChange={(result) => onChange?.(result)} />
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
