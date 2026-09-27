/**
 * Writing signals: patterns common in machine-generated text, for the editor.
 *
 * Deliberately not a percentage. No checker can tell reliably who wrote a
 * piece, so this shows what it observed and what is typical, and leaves the
 * judgement with the editor. It never affects the score or the queue.
 */
import { useState } from "react";

import { api } from "../api";
import { Notice } from "./UI";

const LEVELS = {
  few: "Few signals",
  some: "Some signals",
  many: "Many signals",
  too_short: "Too short to judge",
};

export function WritingSignals({ articleId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  function load(event) {
    if (!event.currentTarget.open || result) return;
    api
      .get(`/articles/${articleId}/writing-signals`)
      .then((d) => setResult(d.signals))
      .catch((e) => setError(e.message));
  }

  return (
    <details className="review-originality mt-5" onToggle={load}>
      <summary>
        AI-writing signals
        {result && (
          <span className={`signals-badge signals-badge--${result.level}`}>
            {LEVELS[result.level]}
          </span>
        )}
      </summary>
      <div className="mt-4">
        {error && <Notice>{error}</Notice>}
        {!result && !error && <p className="meta">Checking the writing.</p>}
        {result && (
          <>
            {result.level === "too_short" ? (
              <p className="meta">Under 150 words: too little text to say anything useful.</p>
            ) : (
              <p className="meta">
                {result.flagged} of {result.signals.length} signals outside the range typical of
                edited reporting.
              </p>
            )}
            {result.signals.length > 0 && (
              <ul className="signals-list mt-4">
                {result.signals.map((s) => (
                  <li key={s.key} className={s.flagged ? "is-flagged" : undefined}>
                    <div className="signals-row">
                      <span className="signals-label">{s.label}</span>
                      <span className="signals-value">{s.display}</span>
                      <span className="signals-flag">{s.flagged ? "Look closer" : "Typical"}</span>
                    </div>
                    <p className="meta mt-1">
                      {s.explain} Typical: {s.typical}.
                    </p>
                  </li>
                ))}
              </ul>
            )}
            <p className="signals-disclaimer mt-4">{result.disclaimer}</p>
          </>
        )}
      </div>
    </details>
  );
}
