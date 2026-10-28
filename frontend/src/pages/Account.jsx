/**
 * Your account (PDD Figures 5.12, 5.13, 5.15, 5.24, 5.47).
 *
 * Five jobs, tabbed like the administration console. Which tabs exist depends
 * on the role: only a writer has earnings, and only a reader who is not already
 * a contributor can apply to become one.
 *
 * The application tab is the one that needs care. It is a request an
 * administrator decides later, never an upgrade, and a decline carries a date
 * before which reapplying is refused. Both are stated on the form rather than
 * discovered after submitting.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { EntryThumb } from "../components/CoverImage";
import { CAN_AUTHOR, ROLES, useAuth } from "../auth";
import { CredibilityInline } from "../components/Credibility";
import { Button, Empty, Field, Notice, SectionHead, formatDate } from "../components/UI";
import { PaymentHistory } from "./Checkout";
import { DigestSubscriptions } from "./Digests";
import { usePageTitle } from "../usePageTitle";

const EVENT_LABELS = {
  breaking_news: "Breaking news",
  comment_reply: "Replies to my comments",
  followed_contributor_article: "New articles from writers I follow",
  monthly_digest: "Monthly digests I subscribe to",
  account_security: "Account and security",
};

const MIN_SAMPLE = 200;

function money(cents) {
  return `$${((cents ?? 0) / 100).toFixed(2)}`;
}

/* ------------------------------------------------------------------ */

function Profile({ onNotice }) {
  const { user, refresh } = useAuth();
  const [form, setForm] = useState({ displayName: "", bio: "" });
  const [categories, setCategories] = useState([]);
  const [selected, setSelected] = useState([]);
  const [countries, setCountries] = useState([]);
  const [selectedCountries, setSelectedCountries] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setForm({ displayName: user?.displayName || "", bio: user?.bio || "" });
    // Tick the sections already chosen, so a save visibly sticks.
    setSelected(user?.categoryIds || []);
    setSelectedCountries(user?.countryCodes || []);
    api
      .get("/categories")
      // Uncategorised only holds articles whose section was deleted: not a topic.
      .then((d) => setCategories((d.categories || []).filter((c) => c.slug !== "uncategorised")))
      .catch(() => setCategories([]));
    api
      .get("/countries")
      .then((d) => setCountries(d.countries || []))
      .catch(() => setCountries([]));
  }, [user]);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch("/me", { ...form, categoryIds: selected, countryCodes: selectedCountries });
      onNotice("Profile saved. Your personalised feed reflects it immediately.");
      refresh?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form profile-form" onSubmit={save}>
      {error && <Notice>{error}</Notice>}

      <div className="profile-main">
      <Field label="Display name" id="displayName">
        {(props) => (
          <input
            {...props}
            className="input"
            value={form.displayName}
            onChange={(e) => setForm((f) => ({ ...f, displayName: e.target.value }))}
            required
          />
        )}
      </Field>

      <Field label="Bio" id="bio" hint="Shown on your public profile.">
        {(props) => (
          <textarea
            {...props}
            className="textarea"
            rows={4}
            maxLength={2000}
            value={form.bio}
            onChange={(e) => setForm((f) => ({ ...f, bio: e.target.value }))}
          />
        )}
      </Field>

      </div>

      <fieldset className="fieldset profile-side">
        <legend className="field-label">Sections you follow</legend>
        <p className="field-hint">
          These shape your front page, with the countries below. Leaving both empty falls back to trending.
        </p>
        <div className="checkbox-grid mt-4">
          {categories.map((c) => (
            <label className="checkbox" key={c.id}>
              <input
                type="checkbox"
                checked={selected.includes(c.id)}
                onChange={() =>
                  setSelected((s) =>
                    s.includes(c.id) ? s.filter((x) => x !== c.id) : [...s, c.id],
                  )
                }
              />
              <span>{c.name}</span>
            </label>
          ))}
        </div>

        <p className="field-label mt-6">Countries you follow</p>
        <p className="field-hint">
          Their news joins your front page too. You can also follow a country
          from its page.
        </p>
        <div className="checkbox-grid mt-4">
          {countries.map((c) => (
            <label className="checkbox" key={c.code}>
              <input
                type="checkbox"
                checked={selectedCountries.includes(c.code)}
                onChange={() =>
                  setSelectedCountries((s) =>
                    s.includes(c.code) ? s.filter((x) => x !== c.code) : [...s, c.code],
                  )
                }
              />
              <span>{c.name}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="row gap-4 profile-actions">
        <Button variant="primary" type="submit" busy={busy}>
          Save profile
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */

/** A list of the reader's articles: saved for later, or liked. */
function ArticleList({ endpoint, empty }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    api
      .get(endpoint)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [endpoint]);

  if (error) return <Notice>{error}</Notice>;
  if (!data) return <div className="skeleton" style={{ height: "12rem" }} />;
  if (data.articles.length === 0) return empty;

  return (
    <div className="index">
      {data.articles.map((a) => (
        <article className={`entry${a.coverImage ? " entry--media" : ""}`} key={a.id}>
          <EntryThumb image={a.coverImage} />
          <div className="entry-main">
            <h3 className="entry-title">
              <Link className="link-quiet" to={`/articles/${a.slug}`}>
                {a.title}
              </Link>
            </h3>
            {a.summary && <p className="entry-summary mt-2">{a.summary}</p>}
            <p className="entry-meta mt-3">
              <span>{a.contributor.name}</span>
              <span className="dot" aria-hidden="true" />
              <span>{formatDate(a.publishedAt)}</span>
            </p>
          </div>
          <div className="entry-aside">
            <CredibilityInline credibility={a.credibility} review={a.review} />
          </div>
        </article>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function NotificationSettings({ onNotice }) {
  const [prefs, setPrefs] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/me/notification-preferences")
      .then((d) => setPrefs(d.preferences))
      .catch((e) => setError(e.message));
  }, []);

  async function save() {
    setBusy(true);
    try {
      await api.put("/me/notification-preferences", { preferences: prefs });
      onNotice("Notification settings saved. This applies to future alerts only.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <Notice>{error}</Notice>;
  if (!prefs) return <div className="skeleton" style={{ height: "10rem" }} />;

  return (
    <>
      <p className="meta">
        These govern email delivery. The bell always shows everything, so turning
        one off never hides a notification from you inside the site.
      </p>
      <div className="checkbox-grid mt-5">
        {Object.entries(prefs).map(([event, enabled]) => (
          <label className="checkbox" key={event}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={() => setPrefs((p) => ({ ...p, [event]: !p[event] }))}
            />
            <span>{EVENT_LABELS[event] || event.replace(/_/g, " ")}</span>
          </label>
        ))}
      </div>
      <div className="row gap-4 mt-6">
        <Button variant="primary" onClick={save} busy={busy}>
          Save settings
        </Button>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */

function Application({ onNotice }) {
  const [existing, setExisting] = useState(undefined);
  const [form, setForm] = useState({ writingSample: "", background: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [fieldError, setFieldError] = useState({});

  const load = useCallback(() => {
    api
      .get("/me/contributor-application")
      .then((d) => setExisting(d.application))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setFieldError({});
    setError(null);
    try {
      await api.post("/me/contributor-application", form);
      onNotice("Application sent. An administrator will review it.");
      load();
    } catch (e) {
      if (e.field) setFieldError({ [e.field]: e.message });
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (existing === undefined) return <div className="skeleton" style={{ height: "12rem" }} />;

  if (existing) {
    return (
      <div className="well">
        <p className="label">Your application</p>
        <p className="mt-3">
          <span className="status" data-status={existing.status}>
            {existing.status}
          </span>{" "}
          <span className="meta">· submitted {formatDate(existing.submittedAt)}</span>
        </p>
        {existing.reason && <p className="entry-summary mt-4">{existing.reason}</p>}
        {existing.reapplyAfter && (
          <p className="meta mt-4">
            You can apply again after {formatDate(existing.reapplyAfter)}.
          </p>
        )}
        {existing.status === "pending" && (
          <p className="meta mt-4">
            Nothing is granted automatically. An administrator decides, and you will
            be notified either way.
          </p>
        )}
      </div>
    );
  }

  const short = form.writingSample.length > 0 && form.writingSample.length < MIN_SAMPLE;

  return (
    <form className="form" onSubmit={submit}>
      <p className="meta">
        Contributors write articles that carry a credibility score. Applications go
        to an administrator; approval is never automatic.
      </p>

      {error && <Notice>{error}</Notice>}

      <Field
        label="Writing sample"
        id="writingSample"
        hint={`At least ${MIN_SAMPLE} characters.`}
        error={
          fieldError.writingSample ||
          (short ? `${MIN_SAMPLE - form.writingSample.length} more characters needed.` : null)
        }
      >
        {(props) => (
          <textarea
            {...props}
            className="textarea"
            rows={8}
            value={form.writingSample}
            onChange={(e) => setForm((f) => ({ ...f, writingSample: e.target.value }))}
            required
          />
        )}
      </Field>

      <Field label="Background" id="background" error={fieldError.background}>
        {(props) => (
          <textarea
            {...props}
            className="textarea"
            rows={4}
            value={form.background}
            onChange={(e) => setForm((f) => ({ ...f, background: e.target.value }))}
          />
        )}
      </Field>

      <div className="row gap-4 mt-6">
        <Button
          variant="primary"
          type="submit"
          busy={busy}
          disabled={form.writingSample.length < MIN_SAMPLE}
        >
          Apply to contribute
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */

function Subscriptions({ onNotice }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    api
      .get("/me/subscription")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  async function cancel(sub) {
    if (!window.confirm("Cancel this subscription? Access continues to the end of the paid period."))
      return;
    setBusy(sub.id);
    try {
      await api.del(`/subscriptions/${sub.id}`);
      onNotice("Subscription cancelled. Access runs to the end of the period you paid for.");
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  if (error) return <Notice>{error}</Notice>;
  if (!data) return <div className="skeleton" style={{ height: "10rem" }} />;

  return (
    <>
      <p className="meta">
        Premium access is checked against a live subscription, never against your
        role, so it ends exactly when the period does.
      </p>

      {data.subscriptions.length === 0 ? (
        <div className="mt-5">
          <Empty title="No subscriptions">
            Subscribing to a writer unlocks their subscriber-only articles.
          </Empty>
        </div>
      ) : (
        <div className="table-scroll mt-5">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Writer</th>
                <th scope="col">Status</th>
                <th scope="col">Runs until</th>
                <th scope="col">Price</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.subscriptions.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link className="link-quiet" to={`/contributors/${s.contributorId}`}>
                      {s.contributorName || `Writer #${s.contributorId}`}
                    </Link>
                  </td>
                  <td>
                    <span className="status" data-status={s.status}>
                      {s.status}
                    </span>
                  </td>
                  <td className="meta">{formatDate(s.periodEnd)}</td>
                  <td className="meta tabular">{money(s.priceCents)}</td>
                  <td>
                    {s.status === "active" && (
                      <Button
                        size="sm"
                        variant="quiet"
                        busy={busy === s.id}
                        onClick={() => cancel(s)}
                      >
                        Cancel
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-7">
        <SectionHead title="Payments" />
        <PaymentHistory />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */

function Earnings() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/me/earnings")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <Notice>{error}</Notice>;
  if (!data) return <div className="skeleton" style={{ height: "12rem" }} />;

  return (
    <>
      <div className="stat-grid">
        <div className="stat">
          <p className="label">Subscribers</p>
          <p className="stat-figure">{data.subscriberCount}</p>
        </div>
        <div className="stat">
          <p className="label">Revenue tier</p>
          <p className="stat-figure">{data.revenueTier}</p>
        </div>
        <div className="stat">
          <p className="label">Platform share</p>
          <p className="stat-figure">{data.platformSharePercent}%</p>
        </div>
        <div className="stat">
          <p className="label">This period, net</p>
          <p className="stat-figure">{money(data.currentPeriod?.estimatedNetCents)}</p>
        </div>
      </div>

      {data.nextTier && (
        <div className="well mt-6">
          <p className="label">Next revenue band</p>
          <p className="meta mt-2">
            {data.nextTier.remaining} more subscriber
            {data.nextTier.remaining === 1 ? "" : "s"} and the platform&rsquo;s share
            falls to {data.nextTier.platformSharePercent}%, so you keep{" "}
            {data.nextTier.contributorSharePercent}%.
          </p>
          {/* A measure, not a progress bar toward a task: the meter component is
              reserved for credibility, so this is a plain ruled track. */}
          <div
            className="tier-track mt-4"
            role="img"
            aria-label={`${data.nextTier.progressPercent}% of the way to the next band`}
          >
            <span style={{ width: `${data.nextTier.progressPercent}%` }} />
          </div>
        </div>
      )}

      <SectionHead title="Payouts" />
      {data.payouts.length === 0 ? (
        <Empty title="No payouts yet">
          A payout appears here once a subscription period closes.
        </Empty>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Period ending</th>
                <th scope="col">Gross</th>
                <th scope="col">Net</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.payouts.map((p, i) => (
                <tr key={i}>
                  <td className="meta">{formatDate(p.periodEnd)}</td>
                  <td className="meta tabular">{money(p.grossCents)}</td>
                  <td className="meta tabular">{money(p.netCents)}</td>
                  <td>
                    <span className="status" data-status={p.status}>
                      {p.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */

export default function Account() {
  usePageTitle("Your account");
  const { user, has } = useAuth();
  const [notice, setNotice] = useState(null);

  const canWrite = has(...CAN_AUTHOR);
  const canApply = user?.role === ROLES.FREE || user?.role === ROLES.PREMIUM;

  const tabs = [
    ["profile", "Profile"],
    ["reading", "Reading list"],
    ["liked", "Liked"],
    ["alerts", "Email alerts"],
    ["digests", "Digests"],
    ...(canApply ? [["apply", "Become a contributor"]] : []),
    ["subs", "Subscriptions"],
    ...(canWrite ? [["earnings", "Earnings"]] : []),
  ];

  // The tab is in the address (?tab=liked) so the account menu can link to it.
  const [params, setParams] = useSearchParams();
  const tab = tabs.some(([key]) => key === params.get("tab")) ? params.get("tab") : "profile";
  const setTab = (key) => setParams(key === "profile" ? {} : { tab: key });

  const panels = {
    profile: <Profile onNotice={setNotice} />,
    reading: (
      <ArticleList
        endpoint="/me/reading-list"
        empty={
          <Empty title="Nothing saved yet">
            Use <em>Save for later</em> on any article and it appears here.
          </Empty>
        }
      />
    ),
    liked: (
      <ArticleList
        endpoint="/me/liked"
        empty={
          <Empty title="No liked articles yet">
            Like an article and it appears here, newest first.
          </Empty>
        }
      />
    ),
    alerts: <NotificationSettings onNotice={setNotice} />,
    digests: <DigestSubscriptions onNotice={setNotice} />,
    apply: <Application onNotice={setNotice} />,
    subs: <Subscriptions onNotice={setNotice} />,
    earnings: <Earnings />,
  };

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">Your account</h1>
          <p className="meta mt-3">{user?.email}</p>
        </div>
      </header>

      {notice && (
        <div className="mt-6">
          <Notice tone="quiet">{notice}</Notice>
        </div>
      )}

      <nav className="tabs mt-6" aria-label="Account sections">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className="tab"
            aria-current={tab === key ? "page" : undefined}
            onClick={() => {
              setTab(key);
              setNotice(null);
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      <section className="section mt-6">{panels[tab]}</section>
    </div>
  );
}
