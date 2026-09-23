/**
 * The credibility instruments.
 *
 * The reference style forbids chromatic colour in UI, which rules out the
 * green/amber/red badge this data invites. That suits the product: a publication
 * that colour-codes its own trustworthiness ends up looking like a browser
 * security warning.
 *
 * Every reading carries three independent encodings, none of them colour:
 *   1. fill length, the quantity
 *   2. ink value, the band, expressed as weight within one hue
 *   3. the band word, always rendered and always the authority
 *
 * "Disputed" also switches to a hatched fill, so the state that matters most
 * survives grayscale printing and colour-blind vision.
 */
import { InfoIcon, ScaleIcon } from "./Icon";

/**
 * Whether an editor has read this article yet.
 *
 * During a review backlog the system may publish an article before an editor
 * reads it. A reader must never mistake that for an article a human approved,
 * so the flag travels with every credibility reading rather than living on one
 * page. It is words, not a colour, like every other state on the platform, and
 * it sits beside the score rather than changing it: the score is the arithmetic,
 * this is who has checked it.
 */
function ReviewFlag({ review, compact = false }) {
  if (!review?.awaitingReview) return null;
  return (
    <span
      className={compact ? "review-flag review-flag--compact" : "review-flag"}
      title="Published automatically while the review queue was backed up. An editor has not read it yet."
    >
      <InfoIcon size={compact ? 12 : 14} />
      {compact ? "Not yet reviewed" : "Not yet reviewed by an editor"}
    </span>
  );
}

/** Full readout: score, band, meter. Used where the score is the subject. */
export function CredibilityMeter({ credibility, review, animate = true }) {
  if (!credibility || credibility.score == null) return null;
  const { score, band } = credibility;

  return (
    <div className="cred">
      <div className="cred-readout">
        <span className="cred-score">{Math.round(score)}</span>
        <span className="cred-outof">/ 100</span>
        <span className="cred-band">{band}</span>
      </div>
      <div
        className="cred-track"
        role="meter"
        aria-valuenow={Math.round(score)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Credibility score ${Math.round(score)} out of 100, rated ${band}`}
      >
        <div
          className="cred-fill"
          data-band={band}
          style={{
            width: `${Math.max(0, Math.min(100, score))}%`,
            animation: animate ? undefined : "none",
          }}
        />
      </div>
      <ReviewFlag review={review} />
    </div>
  );
}

/** Compact reading for listings, where the score is a column, not the subject. */
export function CredibilityInline({ credibility, review }) {
  if (!credibility || credibility.score == null) return null;
  const { score, band } = credibility;
  const rounded = Math.round(score);

  return (
    <span className="cred-inline">
      <span className="cred-inline-num">{rounded}</span>
      <span className="cred-inline-bar" aria-hidden="true">
        <i data-band={band} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </span>
      <span>{band}</span>
      <span className="sr-only">
        Credibility {rounded} out of 100, rated {band}
      </span>
      <ReviewFlag review={review} compact />
    </span>
  );
}

const LEDGER_ROWS = [
  ["Contributor accuracy", "accuracy"],
  ["Verified sources", "sources"],
  ["Corrections", "corrections"],
  ["Retraction", "retraction"],
  ["Reader reports", "reports"],
];

/**
 * The disclosure.
 *
 * PRD 1.3.3 promises a reader can "trace exactly why an article's score is what
 * it is". That promise is only kept if the arithmetic is on the page, so it is
 * a ledger with dotted leaders and a ruled total, rather than a tooltip the
 * reader has to hunt for and cannot print.
 */
export function CredibilityLedger({ credibility }) {
  const breakdown = credibility?.breakdown;
  if (!breakdown) return null;

  const fmt = (n) => (n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1));

  return (
    <div className="ledger">
      <dl>
        {LEDGER_ROWS.map(([label, key]) => {
          const value = breakdown[key];
          if (value == null || value === 0) return null;
          return (
            <div className="ledger-row" key={key}>
              <dt>{label}</dt>
              <dd>{fmt(value)}</dd>
            </div>
          );
        })}
        <div className="ledger-row ledger-total">
          <dt>Credibility score</dt>
          <dd>{Math.round(credibility.score)}</dd>
        </div>
      </dl>
      {credibility.provisional && (
        <p className="meta mt-4">
          This contributor has not yet published enough articles for an accuracy
          rate, so the score uses the platform's starting figure in its place.
        </p>
      )}
    </div>
  );
}

/**
 * A contributor's accuracy rate.
 *
 * A withheld rate is a legitimate state, not a bad score, so it renders as a
 * word. Rendering it as 0%, or with a meter at zero, would say the opposite
 * of what it means.
 */
export function AccuracyRate({ rate, prefix = "" }) {
  const isNew = rate == null;
  return (
    <span className="accuracy" data-new={isNew}>
      {isNew ? "New contributor" : `${prefix}${rate}% accuracy`}
    </span>
  );
}

/** Standing explanation of the formula, for the article page and About. */
export function FormulaNote({ compact = false }) {
  if (compact) {
    return (
      <p className="meta">
        Every score comes from the same fixed rules: contributor accuracy,
        verified sources, and logged corrections. Nothing is predicted.
      </p>
    );
  }
  return (
    <div className="row gap-4">
      <ScaleIcon size={20} />
      <p className="meta" style={{ maxWidth: "46ch" }}>
        Scores are arithmetic, not prediction. Every input is published, and the
        same inputs always produce the same number.
      </p>
    </div>
  );
}
