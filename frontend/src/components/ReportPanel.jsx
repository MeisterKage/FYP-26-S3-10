/**
 * Reporting an article (PDD Figure 5.26).
 *
 * A fixed list of reasons with optional detail, not a free-text box. Free text
 * made every report a small essay for a moderator to interpret, and the same
 * complaint arrived worded five different ways.
 *
 * The list comes from the server so a copy here cannot drift from what the API
 * will accept. The confirmation says the report was received and nothing about
 * what happens next, because the reader is not entitled to the outcome of an
 * editorial decision about someone else's work.
 */
import { useEffect, useState } from "react";

import { api } from "../api";
import { Button, Notice } from "./UI";

export default function ReportPanel({ article, onDone, onCancel }) {
  const [reasons, setReasons] = useState([]);
  const [category, setCategory] = useState("");
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/report-reasons")
      .then((d) => setReasons(d.reasons || []))
      .catch((e) => setError(e.message));
  }, []);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/articles/${article.id}/report`, { category, detail });
      onDone();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <form className="well mt-4" onSubmit={submit}>
      <fieldset className="fieldset">
        <legend className="field-label">Why are you reporting this?</legend>
        <div className="mt-3">
          {reasons.map((r) => (
            <label className="checkbox" key={r.value}>
              <input
                type="radio"
                name={`report-${article.id}`}
                value={r.value}
                checked={category === r.value}
                onChange={() => setCategory(r.value)}
              />
              <span>{r.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="field-label mt-5" htmlFor={`detail-${article.id}`}>
        Anything else? (optional)
      </label>
      <textarea
        id={`detail-${article.id}`}
        className="textarea mt-2"
        rows={3}
        maxLength={1000}
        value={detail}
        onChange={(e) => setDetail(e.target.value)}
      />

      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}

      <div className="row gap-4 mt-5">
        <Button variant="primary" size="sm" type="submit" busy={busy} disabled={!category}>
          Send report
        </Button>
        <Button variant="quiet" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
