/**
 * AI detection for the editor: an estimate of how much of the text reads as
 * AI-generated, the passages that do, and the five signals behind it.
 *
 * An estimate, labelled as one. No checker can prove who wrote a piece, so
 * the editor sees what was observed and judges for themselves. It never
 * changes the score or blocks publication.
 */
import { useState } from "react";

import { api } from "../api";
import { Notice } from "./UI";

const LEVELS = {
  few: "Few signs",
  some: "Some signs",
  many: "Many signs",
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

  const flaggedPassages = result?.passages?.filter((p) => p.aiLike) ?? [];

  return (
    <details className="review-originality mt-5" onToggle={load}>
      <summary>
        AI detection
        {result && result.level !== "too_short" && (
          <span className={`signals-badge signals-badge--${result.level}`}>
            about {result.aiShare}% AI-like · {LEVELS[result.level]}
          </span>
        )}
        {result?.level === "too_short" && (
          <span className="signals-badge">{LEVELS.too_short}</span>
        )}
      </summary>
      <div className="mt-4">
        {error && <Notice>{error}</Notice>}
        {!result && !error && <p className="meta">Checking the writing.</p>}
        {result && result.level === "too_short" && (
          <p className="meta">Under 150 words: too little text to say anything useful.</p>
        )}
        {result && result.level !== "too_short" && (
          <>
            <div className="ai-share">
              <p className="ai-share-figure">{result.aiShare}%</p>
              <p className="meta">
                of the text is in passages that read as AI-generated (an estimate, by words).{" "}
                {result.flagged} of {result.signals.length} whole-article signals are outside the
                range typical of edited reporting.
              </p>
            </div>

            {flaggedPassages.length > 0 && (
              <>
                <p className="label mt-5">Passages that read as AI-generated</p>
                <ul className="ai-passages mt-3">
                  {flaggedPassages.map((p, i) => (
                    <li key={i}>
                      <p className="ai-passage-text">{p.excerpt}</p>
                      <p className="meta mt-1">{p.words} words · {p.reasons.join(", ")}</p>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <p className="label mt-5">Signals across the whole article</p>
            <ul className="signals-list mt-3">
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
            <p className="signals-disclaimer mt-4">{result.disclaimer}</p>
          </>
        )}
      </div>
    </details>
  );
}
