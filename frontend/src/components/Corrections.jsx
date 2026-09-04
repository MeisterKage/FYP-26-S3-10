/**
 * Corrections logged against an article, and the writer's route to disputing
 * one (PDD Figures 5.94, and the permanent record the PDD requires).
 *
 * Shown to everyone, not just the writer. A correction is the reason a score
 * fell, and the product's claim is that a reader can trace why a number is what
 * it is. Hiding the correction would leave the drop unexplained.
 *
 * The dispute button appears only for the article's own writer, because it is
 * the only person who can file one.
 */
import { useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Button, Notice, formatDate } from "./UI";

function DisputeForm({ correction, onDone, onCancel }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/corrections/${correction.id}/dispute`, { case: text });
      onDone();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <form className="well mt-4" onSubmit={submit}>
      <label className="field-label" htmlFor={`case-${correction.id}`}>
        Why is this correction wrong?
      </label>
      <p className="field-hint">
        An administrator reads this alongside the correction itself. If they
        agree, the correction is reversed and your accuracy rate is restored
        across everything you have published.
      </p>
      <textarea
        id={`case-${correction.id}`}
        className="textarea mt-3"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        required
        autoFocus
      />

      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}

      <div className="row gap-4 mt-4">
        <Button variant="primary" size="sm" type="submit" busy={busy} disabled={!text.trim()}>
          File dispute
        </Button>
        <Button variant="quiet" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export default function Corrections({ article }) {
  const { user } = useAuth();
  const [disputing, setDisputing] = useState(null);
  const [filed, setFiled] = useState([]);

  const corrections = article.corrections || [];
  if (corrections.length === 0) return null;

  const isAuthor = user && user.id === article.contributor.id;

  return (
    <section className="corrections">
      <p className="label">
        {corrections.length} correction{corrections.length === 1 ? "" : "s"} on this
        article
      </p>

      <ol className="report-list mt-3">
        {corrections.map((c) => (
          <li className="report" key={c.id}>
            <div>
              <p className="comment-body">
                <span className="tag">{c.type}</span> {c.reason}
              </p>
              <p className="meta mt-2">
                {formatDate(c.issuedAt)}
                {c.overturned && " · overturned, no longer counted"}
              </p>

              {disputing === c.id && (
                <DisputeForm
                  correction={c}
                  onDone={() => {
                    setDisputing(null);
                    setFiled((f) => [...f, c.id]);
                  }}
                  onCancel={() => setDisputing(null)}
                />
              )}
            </div>

            {isAuthor && !c.overturned && disputing !== c.id && (
              filed.includes(c.id) ? (
                <span className="meta">Dispute filed</span>
              ) : (
                <Button variant="quiet" size="sm" onClick={() => setDisputing(c.id)}>
                  Dispute
                </Button>
              )
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
