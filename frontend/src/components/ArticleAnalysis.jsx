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

const DIRECTION = {
  rising: "Rising",
  steady: "Steady",
  falling: "Falling",
  quiet: "No recent views",
};

function shortDay(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "short", timeZone: "UTC" });
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
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {data.map((d, i) => (
            <tr key={i}><td>{describe(d)}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export function ArticleAnalysis({ slug }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

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
      <h2 className="label" id="analysis-title">Tone and trend</h2>

      <div className="analysis-grid">
        {tone && (
          <div className="analysis-block">
            <p className="analysis-kicker">Tone of the writing</p>
            <p className="analysis-figure">{tone.label}</p>
            <p className="meta">
              {signed(tone.score)} on a scale from −1 (negative) to +1 (positive) ·{" "}
              {Math.round(tone.share.positive * 100)}% of sentences positive,{" "}
              {Math.round(tone.share.negative * 100)}% negative
            </p>
            {tone.paragraphs.length > 1 && (
              <Bars
                diverging
                label="Tone of each paragraph, in reading order"
                data={tone.paragraphs.map((v, i) => ({ value: v, i }))}
                describe={(d) => `Paragraph ${d.i + 1}: ${signed(d.value)}`}
              />
            )}
            <p className="analysis-caption">Each bar is a paragraph, in order: above the line reads positive, below it negative.</p>
            {tone.mostPositive && (
              <blockquote className="analysis-quote">
                <span className="analysis-quote-label">Most positive line</span>
                {tone.mostPositive.text}
              </blockquote>
            )}
            {tone.mostNegative && (
              <blockquote className="analysis-quote">
                <span className="analysis-quote-label">Most negative line</span>
                {tone.mostNegative.text}
              </blockquote>
            )}
            {topic.tone != null && (
              <p className="meta mt-4">
                Other {topic.name} articles from the last eight weeks: {topic.toneLabel}{" "}
                ({signed(topic.tone)}).
              </p>
            )}
          </div>
        )}

        <div className="analysis-block">
          <p className="analysis-kicker">Reader interest</p>
          <p className="analysis-figure">{DIRECTION[trend.direction]}</p>
          <p className="meta">
            {trend.viewsInPeriod.toLocaleString()} views in the last 14 days ·{" "}
            {trend.viewsTotal.toLocaleString()} in total
            {likes + comments > 0 && ` · ${likes} like${likes === 1 ? "" : "s"} and ${comments} comment${comments === 1 ? "" : "s"} in that time`}
          </p>
          <Bars
            label="Views per day over the last 14 days"
            data={trend.views.map((d) => ({ value: d.count, day: d.day }))}
            describe={(d) => `${shortDay(d.day)}: ${d.value.toLocaleString()} view${d.value === 1 ? "" : "s"}`}
          />
          <p className="analysis-caption">
            Views per day, {shortDay(trend.views[0].day)} to {shortDay(trend.views[trend.views.length - 1].day)}.
            Rising or falling compares the last seven days with the seven before.
          </p>

          {topic.name && (
            <>
              <p className="analysis-kicker mt-6">
                Coverage of <Link className="link-quiet" to={`/categories/${topic.slug}`}>{topic.name}</Link>
              </p>
              <Bars
                label={`${topic.name} articles published per week, last eight weeks`}
                data={topic.weekly.map((w) => ({ value: w.count, week: w.weekEnding }))}
                describe={(d) => `Week to ${shortDay(d.week)}: ${d.value} article${d.value === 1 ? "" : "s"}`}
              />
              <p className="analysis-caption">
                Articles published per week in this section, about {perWeek.toFixed(1)} a week on average.
              </p>
            </>
          )}
        </div>
      </div>

      <p className="analysis-note">
        Tone describes the wording, not whether the article is accurate: careful reporting of bad
        news reads negative. Scored automatically with VADER, a standard sentiment model.
      </p>
    </section>
  );
}
