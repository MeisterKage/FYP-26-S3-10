/**
 * The credibility instruments.
 *
 * The reference style forbids chromatic colour in UI, which rules out the
 * green/amber/red badge this data invites. That suits the product: a publication
 * that colour-codes its own trustworthiness ends up looking like a browser
 * security warning.
 *
 * Every reading carries independent encodings, none of them colour alone:
 *   1. the arc's length round the ring, the quantity
 *   2. the numeral, the exact score
 *   3. the band word, always rendered and always the authority
 *
 * "Disputed" also dashes the ring's track, so the state that matters most
 * survives grayscale printing and colour-blind vision.
 */
import { InfoIcon, ScaleIcon } from "./Icon";
import { useI18n } from "../i18n";

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
  const { t } = useI18n();
  if (!review?.awaitingReview) return null;
  return (
    <span
      className={compact ? "review-flag review-flag--compact" : "review-flag"}
      title="Published automatically while the review queue was backed up. An editor has not read it yet."
    >
      <InfoIcon size={compact ? 12 : 14} />
      {compact ? t("cred.notReviewed") : t("cred.notReviewedLong")}
    </span>
  );
}

/**
 * The ring: Sterling Wire's mark. A fine track with the score drawn round it,
 * like the gauge on an instrument. Strokes stay hairline at every size
 * (non-scaling), and "Disputed" dashes the track as well, so the state that
 * matters most survives grayscale and colour-blind vision.
 */
function Ring({ score, band, size, numeral = false }) {
  const value = Math.max(0, Math.min(100, score));
  return (
    <svg className="ring" data-band={band} width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      <circle className="ring-track" cx="50" cy="50" r="46" />
      <circle
        className="ring-arc"
        cx="50"
        cy="50"
        r="46"
        pathLength="100"
        strokeDasharray={`${value} 100`}
        transform="rotate(-90 50 50)"
      />
      {numeral && (
        <text className="ring-num" x="50" y="51" textAnchor="middle" dominantBaseline="central">
          {Math.round(score)}
        </text>
      )}
    </svg>
  );
}

/** Full readout: the ring with its score, the band word. Where the score is the subject. */
export function CredibilityMeter({ credibility, review, size = 88 }) {
  const { t } = useI18n();
  if (!credibility || credibility.score == null) return null;
  const { score, band } = credibility;
  const rounded = Math.round(score);

  return (
    <div
      className="cred"
      role="meter"
      aria-valuenow={rounded}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Credibility score ${rounded} out of 100, rated ${band}`}
    >
      <Ring score={score} band={band} size={size} numeral />
      <div className="cred-words">
        <span className="cred-band">{t(`band.${band}`)}</span>
        <span className="cred-outof">{t("cred.score")}: {rounded} / 100</span>
        <ReviewFlag review={review} />
      </div>
    </div>
  );
}

/** Compact reading for listings: a small ring, the number, the band word. */
export function CredibilityInline({ credibility, review }) {
  const { t } = useI18n();
  if (!credibility || credibility.score == null) return null;
  const { score, band } = credibility;
  const rounded = Math.round(score);

  return (
    <span className="cred-inline">
      <Ring score={score} band={band} size={20} />
      <span className="cred-inline-num">{rounded}</span>
      <span>{t(`band.${band}`)}</span>
      <span className="sr-only">
        Credibility {rounded} out of 100, rated {band}
      </span>
      <ReviewFlag review={review} compact />
    </span>
  );
}

const LEDGER_ROWS = [
  ["ledger.accuracy", "accuracy"],
  ["ledger.sources", "sources"],
  ["ledger.corrections", "corrections"],
  ["ledger.retraction", "retraction"],
  ["ledger.reports", "reports"],
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
  const { t } = useI18n();
  const breakdown = credibility?.breakdown;
  if (!breakdown) return null;

  const fmt = (n) => (n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1));

  return (
    <div className="ledger">
      <dl>
        {LEDGER_ROWS.map(([label, key]) => {
          const value = breakdown[key];
          if (value == null || value === 0) return null;
          const sourcing = key === "sources" ? credibility.sourcing : null;
          return (
            <div className="ledger-row" key={key}>
              <dt>
                {t(label)}
                {sourcing && sourcing.cited > 0 && (
                  <span className="ledger-note">
                    {sourcing.cited > sourcing.counted
                      ? t("ledger.bestOf", { counted: sourcing.counted, cited: sourcing.cited })
                      : sourcing.cited === 1 ? t("ledger.source1") : t("ledger.sourcesN", { n: sourcing.cited })}
                  </span>
                )}
              </dt>
              <dd>{fmt(value)}</dd>
            </div>
          );
        })}
        <div className="ledger-row ledger-total">
          <dt>{t("cred.score")}</dt>
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
  const { t } = useI18n();
  const isNew = rate == null;
  return (
    <span className="accuracy" data-new={isNew}>
      {isNew ? t("cred.new") : `${prefix}${t("cred.accuracy", { rate })}`}
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
