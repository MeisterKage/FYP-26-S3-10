/**
 * Tone and trend for one article, below its sources.
 *
 * Tone: how the article's wording reads, from VADER sentence scores (backend
 * app/analysis.py), overall and paragraph by paragraph. Trend: views per day
 * over the last two weeks and whether interest is rising, and how much the
 * article's section has published each week.
 *
 * Charts are single-series and drawn in the one ink the site uses; polarity is
 * shown by direction (above or below the line), never by colour alone. Every
 * bar can be hovered or focused for its exact value, and each chart has a
 * table for screen readers.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useI18n } from "../i18n";

const LOCALES = { en: "en-AU", zh: "zh-CN", ms: "ms-MY" };

function shortDay(iso, lang = "en") {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(LOCALES[lang], { day: "numeric", month: "short", timeZone: "UTC" });
}

/** The band for a tone score: the same cut-offs as the server (app/analysis.py). */
function toneBand(score) {
  if (score >= 0.25) return "positive";
  if (score >= 0.1) return "leans_positive";
  if (score >= -0.05) return "neutral";
  if (score >= -0.2) return "leans_negative";
  return "negative";
}

function signed(n) {
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(2)}`;
}

/** Thin vertical bars with a hover/focus readout. `diverging` centres a zero line. */
function Bars({ data, label, diverging = false, describe }) {
  const [active, setActive] = useState(null);
  const max = Math.max(...data.map((d) => Math.abs(d.value)), diverging ? 0.5 : 1);
  const shown = active ?? null;

  return (
    <figure className="bars-figure">
      <p className="bars-readout" aria-hidden="true">
        {shown != null ? describe(data[shown]) : " "}
      </p>
      <div className={`bars${diverging ? " bars--diverging" : ""}`} role="img" aria-label={label}
        onMouseLeave={() => setActive(null)}>
        {data.map((d, i) => {
          const size = `${(Math.abs(d.value) / max) * 100}%`;
          const up = d.value >= 0;
          return (
            <button
              key={i}
              type="button"
              className={`bar-slot${active === i ? " is-active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              aria-label={describe(d)}
            >
              <span className={`bar ${diverging ? (up ? "bar--up" : "bar--down") : "bar--up"}`}
                style={{ "--size": size }} />
            </button>
          );
        })}
      </div>
      <div className="sr-only">
        <table>
          <caption>{label}</caption>
          <tbody>
            {data.map((d, i) => (
              <tr key={i}><td>{describe(d)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

export function ArticleAnalysis({ slug }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { t, lang, section } = useI18n();
  const day = (iso) => shortDay(iso, lang);

  useEffect(() => {
    setData(null);
    api.get(`/articles/${slug}/analysis`).then(setData).catch((e) => setError(e.message));
  }, [slug]);

  if (error || !data) return null;
  const { tone, trend, topic } = data;
  const likes = trend.likes.reduce((n, d) => n + d.count, 0);
  const comments = trend.comments.reduce((n, d) => n + d.count, 0);
  const perWeek = topic.weekly.length
    ? topic.weekly.reduce((n, w) => n + w.count, 0) / topic.weekly.length : 0;

  return (
    <section className="analysis" aria-labelledby="analysis-title">
      <h2 className="label" id="analysis-title">{t("analysis.title")}</h2>

      <div className="analysis-grid">
        {tone && (
          <div className="analysis-block">
            <p className="analysis-kicker">{t("analysis.tone")}</p>
            <p className="analysis-figure">{t(`tone.${tone.band}`)}</p>
            <p className="meta">
              {t("analysis.scale", { score: signed(tone.score) })} ·{" "}
              {t("analysis.share", { p: Math.round(tone.share.positive * 100), n: Math.round(tone.share.negative * 100) })}
            </p>
            {tone.paragraphs.length > 1 && (
              <Bars
                diverging
                label={t("analysis.paragraphs")}
                data={tone.paragraphs.map((v, i) => ({ value: v, i }))}
                describe={(d) => t("analysis.paragraph", { i: d.i + 1, v: signed(d.value) })}
              />
            )}
            <p className="analysis-caption">{t("analysis.paragraphCaption")}</p>
            {tone.mostPositive && (
              <blockquote className="analysis-quote">
                <span className="analysis-quote-label">{t("analysis.mostPositive")}</span>
                {tone.mostPositive.text}
              </blockquote>
            )}
            {tone.mostNegative && (
              <blockquote className="analysis-quote">
                <span className="analysis-quote-label">{t("analysis.mostNegative")}</span>
                {tone.mostNegative.text}
              </blockquote>
            )}
            {topic.tone != null && (
              <p className="meta mt-4">
                {t("analysis.topicTone", {
                  topic: section(topic.slug, topic.name),
                  label: t(`tone.${toneBand(topic.tone)}`),
                  score: signed(topic.tone),
                })}
              </p>
            )}
          </div>
        )}

        <div className="analysis-block">
          <p className="analysis-kicker">{t("analysis.interest")}</p>
          <p className="analysis-figure">{t(`direction.${trend.direction}`)}</p>
          <p className="meta">
            {t("analysis.views", { n: trend.viewsInPeriod.toLocaleString(), total: trend.viewsTotal.toLocaleString() })}
            {likes + comments > 0 && t("analysis.engagement", { likes, comments })}
          </p>
          <Bars
            label={t("analysis.viewsChart")}
            data={trend.views.map((d) => ({ value: d.count, day: d.day }))}
            describe={(d) => t("analysis.viewsDay", { day: day(d.day), n: d.value.toLocaleString() })}
          />
          <p className="analysis-caption">
            {t("analysis.viewsCaption", { from: day(trend.views[0].day), to: day(trend.views[trend.views.length - 1].day) })}
          </p>

          {topic.name && (
            <>
              <p className="analysis-kicker mt-6">
                {t("analysis.coverage")} <Link className="link-quiet" to={`/categories/${topic.slug}`}>{section(topic.slug, topic.name)}</Link>
              </p>
              <Bars
                label={t("analysis.weekChart", { topic: section(topic.slug, topic.name) })}
                data={topic.weekly.map((w) => ({ value: w.count, week: w.weekEnding }))}
                describe={(d) => t("analysis.week", { day: day(d.week), n: d.value })}
              />
              <p className="analysis-caption">
                {t("analysis.coverageCaption", { avg: perWeek.toFixed(1) })}
              </p>
            </>
          )}
        </div>
      </div>

      <p className="analysis-note">
        {t("analysis.note")}
      </p>
    </section>
  );
}
