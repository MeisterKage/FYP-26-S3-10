/**
 * Monthly digests: the archive, one edition, and a reader's subscriptions.
 *
 * An edition ranks a month's articles in one topic by credibility, not by
 * views, and ends with every correction logged in that topic that month. It is
 * fixed once compiled; if an article is corrected or retracted afterwards, the
 * edition says so against it rather than quietly re-ranking.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { CredibilityInline } from "../components/Credibility";
import { EntryThumb } from "../components/CoverImage";
import { Button, Empty, EntrySkeleton, Notice, SectionHead, formatDate } from "../components/UI";

function monthName(month) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(undefined, {
    month: "long", year: "numeric", timeZone: "UTC",
  });
}

function Stats({ stats }) {
  return (
    <dl className="digest-stats">
      <div>
        <dt className="label">Articles</dt>
        <dd>{stats.articleCount}</dd>
      </div>
      <div>
        <dt className="label">Average credibility</dt>
        <dd>{stats.averageCredibility}</dd>
      </div>
      <div>
        <dt className="label">Writers</dt>
        <dd>{stats.writerCount}</dd>
      </div>
      <div>
        <dt className="label">Corrections</dt>
        <dd>{stats.correctionCount}</dd>
      </div>
    </dl>
  );
}

/* ------------------------------------------------------------------ */
/*  Archive                                                            */
/* ------------------------------------------------------------------ */

export function DigestArchive() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || "";
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    api
      .get(`/digests${month ? `?month=${month}` : ""}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [month]);

  const byMonth = {};
  for (const e of data?.editions ?? []) (byMonth[e.month] ??= []).push(e);

  return (
    <div className="wide">
      <header className="read">
        <h1 className="display">Monthly digests</h1>
        <p className="lead mt-6">
          Each month, every section&rsquo;s most credible reporting, ranked by score
          rather than by how many people clicked. Each digest ends with every
          correction we logged in that section that month.
        </p>
      </header>

      {data?.months?.length > 1 && (
        <nav className="chips mt-7" aria-label="Filter by month">
          <button type="button" className="chip" aria-pressed={!month}
            onClick={() => setParams({})}>
            All months
          </button>
          {data.months.map((m) => (
            <button type="button" className="chip" key={m} aria-pressed={month === m}
              onClick={() => setParams({ month: m })}>
              {monthName(m)}
            </button>
          ))}
        </nav>
      )}

      <section className="section mt-7">
        {error && <Notice>{error}</Notice>}
        {!data && !error && <EntrySkeleton rows={3} />}
        {data?.editions.length === 0 && (
          <Empty title="No digests yet">
            The first editions are compiled at the start of next month.
          </Empty>
        )}
        {Object.entries(byMonth).map(([m, editions]) => (
          <div key={m} className="digest-month">
            <SectionHead title={monthName(m)}>
              {editions.some((e) => e.provisional) && <p className="label">In progress</p>}
            </SectionHead>
            <ul className="digest-grid">
              {editions.map((e) => (
                <li key={e.key}>
                  <Link className="digest-card" to={`/digests/${e.month}/${e.key}`}>
                    <span className="digest-card-topic">{e.topic}</span>
                    <span className="meta">
                      {e.stats.articleCount} articles · average credibility{" "}
                      {e.stats.averageCredibility}
                      {e.stats.correctionCount > 0 &&
                        ` · ${e.stats.correctionCount} correction${e.stats.correctionCount === 1 ? "" : "s"}`}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  One edition                                                        */
/* ------------------------------------------------------------------ */

function SubscribeButton({ edition, onChange }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!user) {
    return (
      <p className="meta">
        <Link className="link-quiet" to="/login">Sign in</Link> to get this digest every month.
      </p>
    );
  }

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      if (edition.subscribed) {
        const { subscriptions } = await api.get("/digests/subscriptions");
        const mine = subscriptions.find(
          (s) => s.category.id === edition.category.id &&
            (s.countryCode || null) === (edition.country?.code || null),
        );
        if (mine) await api.del(`/digests/subscriptions/${mine.id}`);
      } else {
        await api.post("/digests/subscriptions", {
          categoryId: edition.category.id,
          countryCode: edition.country?.code || null,
        });
      }
      onChange();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Button variant={edition.subscribed ? "outline" : "primary"} size="sm" busy={busy}
        onClick={toggle}>
        {edition.subscribed ? "Subscribed. Unsubscribe" : `Get ${edition.topic} every month`}
      </Button>
      {error && <p className="field-error mt-2">{error}</p>}
    </div>
  );
}

export function DigestEdition() {
  const { month, key } = useParams();
  const [edition, setEdition] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api
      .get(`/digests/${month}/${key}`)
      .then((d) => setEdition(d.edition))
      .catch((e) => setError(e.message));
  }, [month, key]);

  useEffect(load, [load]);

  if (error) {
    return (
      <Empty title="This digest isn't here"
        action={<Link className="link-quiet mt-4" to="/digests">See all digests</Link>}>
        {error}
      </Empty>
    );
  }
  if (!edition) return <div className="skeleton" style={{ height: "18rem" }} />;

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <p className="label">
            <Link className="link-quiet" to="/digests">Monthly digests</Link> · {edition.monthLabel}
          </p>
          <h1 className="title mt-3">{edition.topic}</h1>
          <p className="meta mt-3">
            {edition.provisional
              ? `In progress: compiled on ${formatDate(edition.compiledAt)}. The final edition follows when the month ends.`
              : `Compiled on ${formatDate(edition.compiledAt)}. Ranked by credibility score.`}
          </p>
        </div>
        <SubscribeButton edition={edition} onChange={load} />
      </header>

      <section className="section mt-7">
        <Stats stats={edition.stats} />
      </section>

      <section className="section mt-7">
        <SectionHead title="The month's most credible reporting" />
        <ol className="digest-list">
          {edition.entries.map((e) => (
            <li key={e.article.id}
              className={`entry digest-entry${e.available && e.article.coverImage ? " entry--media" : ""}`}>
              <span className="digest-rank" aria-label={`Rank ${e.rank}`}>{e.rank}</span>
              {e.available && <EntryThumb image={e.article.coverImage} />}
              <div className="entry-main">
                <h3 className="entry-title">
                  {e.available ? (
                    <Link className="link-quiet" to={`/articles/${e.article.slug}`}>{e.article.title}</Link>
                  ) : (
                    e.article.title
                  )}
                </h3>
                {e.available && e.article.summary && (
                  <p className="entry-summary mt-2">{e.article.summary}</p>
                )}
                {e.available && (
                  <p className="entry-meta mt-3">
                    <Link className="link-quiet" to={`/contributors/${e.article.contributor.id}`}>
                      {e.article.contributor.name}
                    </Link>
                    <span className="dot" aria-hidden="true" />
                    <span>{formatDate(e.article.publishedAt)}</span>
                  </p>
                )}
                {e.since && <p className="digest-since mt-3">{e.since}</p>}
              </div>
              {e.available && (
                <div className="entry-aside">
                  <CredibilityInline credibility={e.article.credibility} review={e.article.review} />
                  {Math.round(e.article.credibility.score) !== Math.round(e.scoreAtCompile) && (
                    <p className="meta mt-2">{Math.round(e.scoreAtCompile)} when compiled</p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section className="section mt-7">
        <SectionHead title="What we corrected this month" />
        {edition.corrections.length === 0 ? (
          <p className="meta">
            No corrections were logged in {edition.topic} in {edition.monthLabel}.
          </p>
        ) : (
          <ul className="digest-corrections">
            {edition.corrections.map((c, i) => (
              <li key={i}>
                <p className="sub">
                  {c.type === "retraction" ? "Retracted" : "Corrected"}: {c.title}
                  {c.overturned && <span className="tag digest-overturned">Overturned on appeal</span>}
                </p>
                <p className="meta mt-1">
                  {formatDate(c.issuedAt)}. {c.reason}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Account: a reader's digest subscriptions                           */
/* ------------------------------------------------------------------ */

export function DigestSubscriptions({ onNotice }) {
  const [subs, setSubs] = useState(null);
  const [categories, setCategories] = useState([]);
  const [countries, setCountries] = useState([]);
  const [categoryId, setCategoryId] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.get("/digests/subscriptions").then((d) => setSubs(d.subscriptions))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
    api.get("/categories").then((d) =>
      setCategories((d.categories || []).filter((c) => c.slug !== "uncategorised")));
    api.get("/countries/all").then((d) => setCountries(d.countries || []));
  }, [load]);

  async function add(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/digests/subscriptions", {
        categoryId: Number(categoryId), countryCode: countryCode || null,
      });
      onNotice("Subscribed. You'll be notified when each month's edition is out.");
      setCategoryId("");
      setCountryCode("");
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(sub) {
    await api.del(`/digests/subscriptions/${sub.id}`);
    onNotice(`Unsubscribed from ${sub.topic}.`);
    load();
  }

  if (!subs) return <div className="skeleton" style={{ height: "10rem" }} />;

  return (
    <>
      <p className="meta">
        A monthly digest collects a section&rsquo;s most credible articles and the month&rsquo;s
        corrections. You get a notification when each edition is out.{" "}
        <Link className="link-quiet" to="/digests">Browse past digests</Link>.
      </p>

      {subs.length > 0 && (
        <ul className="digest-subs mt-5">
          {subs.map((s) => (
            <li key={s.id}>
              <span>{s.topic}</span>
              <Button variant="quiet" size="sm" onClick={() => remove(s)}>Unsubscribe</Button>
            </li>
          ))}
        </ul>
      )}

      <form className="row gap-4 mt-6 digest-add" onSubmit={add}>
        <label className="sr-only" htmlFor="digest-section">Section</label>
        <select id="digest-section" className="input input-sm" value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)} required>
          <option value="">Choose a section</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <label className="sr-only" htmlFor="digest-country">Country</label>
        <select id="digest-country" className="input input-sm" value={countryCode}
          onChange={(e) => setCountryCode(e.target.value)}>
          <option value="">Every country</option>
          {countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
        </select>
        <Button type="submit" variant="primary" size="sm" busy={busy} disabled={!categoryId}>
          Subscribe
        </Button>
      </form>
      {error && <div className="mt-4"><Notice>{error}</Notice></div>}
    </>
  );
}
