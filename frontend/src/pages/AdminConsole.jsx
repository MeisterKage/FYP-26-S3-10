/**
 * Administration (PDD Figures 5.51 to 5.62).
 *
 * Operate mode, and the densest screen in the product. Seven jobs live here, so
 * they are tabs rather than one long page: an administrator arrives with one
 * task in mind and should not scroll past six others to reach it.
 *
 * Two things are surfaced rather than left to be discovered:
 *
 *   - An editor with no assigned categories has a permanently empty review
 *     queue. That looks like a broken queue and is actually an unset field, so
 *     the editors tab calls it out.
 *   - Changing a scoring threshold rewrites every published score. The scoring
 *     tab says so before the button, not after.
 */
import { useCallback, useEffect, useState } from "react";

import { Link } from "react-router-dom";

import { api } from "../api";
import { ROLES, useAuth } from "../auth";
import { Button, Empty, Notice, SectionHead, formatDate } from "../components/UI";

const TABS = [
  ["overview", "Overview"],
  ["users", "Accounts"],
  ["applications", "Applications"],
  ["editors", "Editors"],
  ["articles", "Articles"],
  ["disputes", "Disputes"],
  ["categories", "Categories"],
  ["scoring", "Scoring"],
  ["logs", "Logs"],
];

const ROLE_LABELS = {
  [ROLES.FREE]: "Free reader",
  [ROLES.PREMIUM]: "Premium reader",
  [ROLES.CONTRIBUTOR]: "Contributor",
  [ROLES.EDITOR]: "Editor",
  [ROLES.ADMIN]: "Administrator",
};

/** Shared loading/error/empty handling, so seven panels do not repeat it. */
function Panel({ state, empty, children }) {
  if (state.error) return <Notice>{state.error}</Notice>;
  if (!state.data) return <div className="skeleton" style={{ height: "14rem" }} />;
  if (empty && empty(state.data)) return empty.render ? empty.render() : null;
  return children(state.data);
}

function useResource(path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(() => {
    setError(null);
    api
      .get(path)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [path]);

  useEffect(reload, [reload]);
  return { data, error, reload, setError };
}

/* ------------------------------------------------------------------ */
/*  Overview (PDD Figure 5.51)                                         */
/* ------------------------------------------------------------------ */

function Overview({ onGo }) {
  const state = useResource("/admin/dashboard");

  const CARDS = [
    ["users", "Accounts"],
    ["published", "Published"],
    ["pendingReview", "Awaiting review"],
    ["openReports", "Open reports"],
    ["averageCredibility", "Mean credibility"],
  ];

  return (
    <Panel state={state}>
      {(d) => (
        <>
          <div className="stat-grid">
            {CARDS.map(([key, label]) => (
              <div className="stat" key={key}>
                <p className="label">{label}</p>
                <p className="stat-figure">{d[key] ?? 0}</p>
              </div>
            ))}
          </div>

          {/* Read-only, per PDD Figure 5.97: each line goes to the tab where
              the work is done rather than being actionable from here. */}
          <div className="mt-7">
            <SectionHead title="Needs attention" />
            {(d.attention || []).length === 0 ? (
              <p className="meta">Nothing is waiting.</p>
            ) : (
              <ul className="attention-list">
                {d.attention.map((item) => (
                  <li key={item.tab}>
                    <button type="button" className="attention-row" onClick={() => onGo(item.tab)}>
                      <span>{item.label}</span>
                      <span className="tabular">{item.count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ */
/*  Accounts (PDD Figures 5.52, 5.56)                                  */
/* ------------------------------------------------------------------ */

function Accounts({ onNotice }) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const path = `/admin/users?q=${encodeURIComponent(query)}&role=${role}`;
  const state = useResource(path);
  const [busy, setBusy] = useState(null);

  async function act(user, fn, message) {
    setBusy(user.id);
    try {
      await fn();
      onNotice(message);
      state.reload();
    } catch (e) {
      state.setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="filter-bar">
        <input
          className="input"
          type="search"
          placeholder="Search name or email"
          aria-label="Search accounts"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="input"
          aria-label="Filter by role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option value="">Every role</option>
          {Object.entries(ROLE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <Panel state={state}>
        {(d) =>
          d.users.length === 0 ? (
            <Empty title="No accounts match">Try a different search or role.</Empty>
          ) : (
            <div className="table-scroll mt-5">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Account</th>
                    <th scope="col">Role</th>
                    <th scope="col">Joined</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {d.users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <span style={{ color: "var(--ink)", fontWeight: 500 }}>{u.name}</span>
                        <br />
                        <span className="meta">{u.email}</span>
                        {u.suspended && (
                          <>
                            {" "}
                            <span className="tag">Suspended</span>
                          </>
                        )}
                      </td>
                      <td>
                        <select
                          className="input input-sm"
                          aria-label={`Role for ${u.name}`}
                          value={u.role}
                          disabled={busy === u.id}
                          onChange={(e) =>
                            act(
                              u,
                              () =>
                                api.post(`/admin/users/${u.id}/role`, {
                                  role: e.target.value,
                                }),
                              `${u.name} is now a ${ROLE_LABELS[e.target.value]?.toLowerCase()}.`,
                            )
                          }
                        >
                          {Object.entries(ROLE_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="meta">{formatDate(u.joinedAt)}</td>
                      <td>
                        <div className="row gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            busy={busy === u.id}
                            onClick={() =>
                              act(
                                u,
                                () =>
                                  api.post(`/admin/users/${u.id}/suspend`, {
                                    suspend: !u.suspended,
                                    reason: u.suspended
                                      ? undefined
                                      : window.prompt("Reason for suspension?") || "",
                                  }),
                                u.suspended
                                  ? `${u.name} can sign in again.`
                                  : `${u.name} is suspended.`,
                              )
                            }
                          >
                            {u.suspended ? "Reinstate" : "Suspend"}
                          </Button>
                          <Button
                            size="sm"
                            variant="quiet"
                            busy={busy === u.id}
                            onClick={() => {
                              // PDD Figure 5.87: what happens to anything they
                              // published is the administrator's decision, not
                              // a side effect of removing the account.
                              if (
                                !window.confirm(
                                  `Remove ${u.name}? This cannot be undone.`,
                                )
                              )
                                return;
                              const keep = window.confirm(
                                `Keep ${u.name}'s published articles on the site under an "Account Removed" byline?

OK  keeps them published
Cancel  takes them off the site`,
                              );
                              act(
                                u,
                                () =>
                                  api.del(`/admin/users/${u.id}`, {
                                    articles: keep ? "keep" : "remove",
                                  }),
                                keep
                                  ? `${u.name} removed. Their articles stay up under "Account Removed".`
                                  : `${u.name} removed, and their articles are off the site.`,
                              );
                            }}
                          >
                            Remove
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Contributor applications (PDD Figure 5.55)                         */
/* ------------------------------------------------------------------ */

function Applications({ onNotice }) {
  const state = useResource("/admin/applications");
  const [busy, setBusy] = useState(null);

  async function decide(application, decision) {
    const reason =
      decision === "reject"
        ? window.prompt("Tell the applicant why. They see this text.")
        : window.prompt("Any note for the applicant? (optional)") || "";
    if (decision === "reject" && !reason) return;

    setBusy(application.id);
    try {
      await api.post(`/admin/applications/${application.id}/decide`, { decision, reason });
      onNotice(
        decision === "approve"
          ? `${application.applicant} can now write.`
          : `${application.applicant}'s application was declined.`,
      );
      state.reload();
    } catch (e) {
      state.setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel state={state}>
      {(d) =>
        d.applications.length === 0 ? (
          <Empty title="No applications waiting">
            Readers apply from their own account page. Approving one upgrades it to a
            contributor.
          </Empty>
        ) : (
          <div className="stack">
            {d.applications.map((a) => (
              <article className="submission" key={a.id}>
                <div className="submission-main">
                  <h3 className="entry-title">{a.applicant}</h3>
                  <p className="entry-meta mt-3">
                    <span>Applied {formatDate(a.submittedAt)}</span>
                    {a.history && (
                      <>
                        <span className="dot" aria-hidden="true" />
                        <span>Member since {formatDate(a.history.memberSince)}</span>
                        <span className="dot" aria-hidden="true" />
                        <span>
                          {a.history.comments} comment
                          {a.history.comments === 1 ? "" : "s"}
                        </span>
                        {a.history.suspended && (
                          <>
                            <span className="dot" aria-hidden="true" />
                            <span className="tag">Suspended</span>
                          </>
                        )}
                      </>
                    )}
                  </p>
                  {a.background && (
                    <>
                      <p className="label mt-5">Background</p>
                      <p className="entry-summary mt-2">{a.background}</p>
                    </>
                  )}
                  {a.writingSample && (
                    <>
                      <p className="label mt-5">Writing sample</p>
                      <p className="entry-summary mt-2">{a.writingSample}</p>
                    </>
                  )}
                  <div className="row gap-4 mt-6">
                    <Button
                      variant="primary"
                      busy={busy === a.id}
                      onClick={() => decide(a, "approve")}
                    >
                      Approve
                    </Button>
                    <Button
                      variant="outline"
                      busy={busy === a.id}
                      onClick={() => decide(a, "reject")}
                    >
                      Decline
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )
      }
    </Panel>
  );
}

/* ------------------------------------------------------------------ */
/*  Editor assignments                                                 */
/* ------------------------------------------------------------------ */

function Editors({ onNotice }) {
  const state = useResource("/admin/editors");
  const [categories, setCategories] = useState([]);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    api
      .get("/categories")
      .then((d) => setCategories(d.categories || []))
      .catch(() => setCategories([]));
  }, []);

  async function toggle(editor, categoryId) {
    const current = editor.categories.map((c) => c.id);
    const next = current.includes(categoryId)
      ? current.filter((id) => id !== categoryId)
      : [...current, categoryId];

    setBusy(editor.id);
    try {
      // PUT replaces the whole set, so two admins editing at once cannot lose
      // each other's change silently.
      await api.put(`/admin/editors/${editor.id}/categories`, { categoryIds: next });
      onNotice(`Updated the sections ${editor.name} reviews.`);
      state.reload();
    } catch (e) {
      state.setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel state={state}>
      {(d) =>
        d.editors.length === 0 ? (
          <Empty title="There are no editors yet">
            Promote an account to Editor on the Accounts tab, then assign its sections
            here.
          </Empty>
        ) : (
          <div className="stack">
            {d.editors.map((e) => (
              <section className="well" key={e.id}>
                <div className="section-head">
                  <div>
                    <h3 className="sub">{e.name}</h3>
                    <p className="meta mt-2">{e.email}</p>
                  </div>
                </div>

                {e.hasNoCategories && (
                  <div className="mt-4">
                    <Notice>
                      No sections assigned, so this editor&rsquo;s review queue is empty.
                      That is this setting, not a fault in the queue.
                    </Notice>
                  </div>
                )}

                <div className="checkbox-grid mt-5">
                  {categories.map((c) => (
                    <label className="checkbox" key={c.id}>
                      <input
                        type="checkbox"
                        checked={e.categories.some((x) => x.id === c.id)}
                        disabled={busy === e.id}
                        onChange={() => toggle(e, c.id)}
                      />
                      <span>{c.name}</span>
                    </label>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )
      }
    </Panel>
  );
}

/* ------------------------------------------------------------------ */
/*  Categories (PDD Figure 5.57)                                       */
/* ------------------------------------------------------------------ */

function Categories({ onNotice }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState(null);

  const reload = useCallback(() => {
    api
      .get("/categories")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(reload, [reload]);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setFieldError(null);
    try {
      await api.post("/admin/categories", { name, description });
      onNotice(`Added ${name}.`);
      setName("");
      setDescription("");
      reload();
    } catch (e) {
      setFieldError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function rename(category, name) {
    const next = name.trim();
    if (!next || next === category.name) return;
    try {
      await api.patch(`/admin/categories/${category.id}`, { name: next });
      // The address is deliberately unchanged, so existing links keep working.
      onNotice(`Renamed to ${next}. Its web address is unchanged.`);
      reload();
    } catch (e) {
      setError(e.message);
      reload();
    }
  }

  async function remove(category) {
    if (
      !window.confirm(
        `Delete ${category.name}? Its articles move to Uncategorised rather than being deleted.`,
      )
    )
      return;
    try {
      await api.del(`/admin/categories/${category.id}`);
      onNotice(`${category.name} removed. Its articles moved to Uncategorised.`);
      reload();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <form className="filter-bar" onSubmit={create}>
        <input
          className="input"
          placeholder="New section name"
          aria-label="New section name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="input"
          placeholder="Description (optional)"
          aria-label="Section description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <Button variant="primary" type="submit" busy={busy} disabled={!name.trim()}>
          Add
        </Button>
      </form>

      {fieldError && (
        <div className="mt-4">
          <Notice>{fieldError}</Notice>
        </div>
      )}
      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}

      {!data ? (
        <div className="skeleton mt-5" style={{ height: "12rem" }} />
      ) : (
        <div className="table-scroll mt-5">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Section</th>
                <th scope="col">Slug</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.categories.map((c) => (
                <tr key={c.id}>
                  <td>
                    {/* Renaming happens in the row. A separate edit screen for
                        one text field is more navigation than the change is
                        worth. */}
                    <input
                      className="input input-sm"
                      aria-label={`Name for ${c.name}`}
                      defaultValue={c.name}
                      onBlur={(e) => rename(c, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") e.target.blur();
                      }}
                    />
                  </td>
                  <td className="meta">{c.slug}</td>
                  <td>
                    <Button size="sm" variant="quiet" onClick={() => remove(c)}>
                      Delete
                    </Button>
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
/*  Scoring thresholds (PRD 1.3.2, administrator power 5)              */
/* ------------------------------------------------------------------ */

function SettingsTable({ settings, draft, setDraft, label }) {
  return (
    <div className="table-scroll mt-5">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{label}</th>
            <th scope="col">Value</th>
            <th scope="col">Shipped default</th>
          </tr>
        </thead>
        <tbody>
          {settings.map((s) => (
            <tr key={s.key}>
              <td>
                <span style={{ color: "var(--ink)" }}>{s.key.replace(/_/g, " ")}</span>
                {s.isOverridden && (
                  <>
                    {" "}
                    <span className="tag">Changed</span>
                  </>
                )}
              </td>
              <td>
                <input
                  className="input input-sm"
                  type="number"
                  step="any"
                  aria-label={s.key}
                  value={draft[s.key] ?? s.value}
                  onChange={(e) => setDraft((p) => ({ ...p, [s.key]: e.target.value }))}
                />
              </td>
              <td className="meta">{s.default}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Scoring({ onNotice }) {
  const state = useResource("/admin/settings");
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(false);

  const changed = Object.keys(draft).length > 0;

  async function save() {
    setBusy(true);
    try {
      const result = await api.put("/admin/settings", {
        settings: Object.fromEntries(
          Object.entries(draft).map(([k, v]) => [k, Number(v)]),
        ),
      });
      // The server says whether scores moved: review settings do not touch them.
      onNotice(result.message);
      setDraft({});
      state.reload();
    } catch (e) {
      state.setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel state={state}>
      {(d) => (
        <>
          <Notice tone="quiet">
            Scoring thresholds are published on the How scoring works page. Changing
            one recalculates every article&rsquo;s credibility score immediately.
          </Notice>

          <SettingsTable
            label="Scoring threshold"
            settings={d.settings.filter((s) => (s.group ?? "scoring") === "scoring")}
            draft={draft}
            setDraft={setDraft}
          />

          <h3 className="sub mt-7">Review automation</h3>
          <p className="meta mt-3">
            The triage weights decide the order of every editor&rsquo;s queue. The
            auto-publish valve is off while <strong>autopublish enabled</strong> is 0.
            When it is 1, a scheduled sweep may publish articles from trusted writers
            once the queue is past the depth or wait threshold. Readers see those
            marked as not yet reviewed until an editor confirms them, and a correction
            on one suspends the writer from auto-publish. None of these change any
            score.
          </p>

          <SettingsTable
            label="Review setting"
            settings={d.settings.filter((s) => s.group === "review")}
            draft={draft}
            setDraft={setDraft}
          />

          <div className="row gap-4 mt-6">
            <Button variant="primary" onClick={save} busy={busy} disabled={!changed}>
              Save changes
            </Button>
            {changed && (
              <Button variant="quiet" onClick={() => setDraft({})}>
                Discard changes
              </Button>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ */
/*  Audit log (PDD Figure 5.62)                                        */
/* ------------------------------------------------------------------ */

function Logs() {
  const [action, setAction] = useState("");
  const state = useResource(`/admin/logs?action=${encodeURIComponent(action)}`);

  return (
    <>
      <div className="filter-bar">
        <input
          className="input"
          type="search"
          placeholder="Filter by action, e.g. user.suspend"
          aria-label="Filter by action"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        />
      </div>

      <Panel state={state}>
        {(d) =>
          d.logs.length === 0 ? (
            <Empty title="Nothing logged yet">
              Administrative actions are recorded here as they happen.
            </Empty>
          ) : (
            <div className="table-scroll mt-5">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Action</th>
                    <th scope="col">Subject</th>
                    <th scope="col">Detail</th>
                    <th scope="col">When</th>
                  </tr>
                </thead>
                <tbody>
                  {d.logs.map((l) => (
                    <tr key={l.id}>
                      <td style={{ color: "var(--ink)" }}>{l.action}</td>
                      <td className="meta">
                        {l.entityType} #{l.entityId}
                      </td>
                      <td className="meta" data-blank={!l.detail || undefined}>
                        {l.detail || "—"}
                      </td>
                      <td className="meta">{formatDate(l.at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Article moderation (PDD Figure 5.93)                               */
/* ------------------------------------------------------------------ */

const ARTICLE_STATUSES = [
  "", "published", "pending", "scheduled", "unpublished", "retracted", "rejected", "draft",
];

const ACTION_LABELS = {
  suspend: "Take off the site",
  reinstate: "Put back up",
  reject: "Reject",
};

function Articles({ onNotice }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const state = useResource(
    `/admin/articles?q=${encodeURIComponent(query)}&status=${status}`,
  );
  const [busy, setBusy] = useState(null);

  async function moderate(article, action) {
    if (
      action === "suspend" &&
      !window.confirm(
        `Take “${article.title}” off the site? It is not deleted and can go back up.`,
      )
    )
      return;

    setBusy(article.id);
    try {
      await api.post(`/admin/articles/${article.id}/moderate`, { action });
      onNotice(
        `“${article.title}” is now ${action === "reinstate" ? "live" : "off the site"}.`,
      );
      state.reload();
    } catch (e) {
      state.setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="filter-bar">
        <input
          className="input"
          type="search"
          placeholder="Search headlines"
          aria-label="Search articles"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="input"
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {ARTICLE_STATUSES.map((s) => (
            <option key={s || "any"} value={s}>
              {s ? s[0].toUpperCase() + s.slice(1) : "Any status"}
            </option>
          ))}
        </select>
      </div>

      <Panel state={state}>
        {(d) =>
          d.articles.length === 0 ? (
            <Empty title="No articles match">Try a different search or status.</Empty>
          ) : (
            <div className="table-scroll mt-5">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Article</th>
                    <th scope="col">Status</th>
                    <th scope="col">Score</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {d.articles.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link className="link-quiet" to={`/articles/${a.slug}`}>
                          {a.title}
                        </Link>
                        <br />
                        <span className="meta">{a.contributor}</span>
                      </td>
                      <td>
                        <span className="status" data-status={a.status}>
                          {a.status}
                        </span>
                      </td>
                      <td
                        className="meta tabular"
                        data-blank={!a.credibilityScore || undefined}
                      >
                        {a.credibilityScore ? Math.round(a.credibilityScore) : "—"}
                      </td>
                      <td>
                        {/* Only the actions that apply to this status. The
                            server enforces the same table. */}
                        <div className="row gap-2">
                          {a.actions.map((action) => (
                            <Button
                              key={action}
                              size="sm"
                              variant={action === "reinstate" ? "outline" : "quiet"}
                              busy={busy === a.id}
                              onClick={() => moderate(a, action)}
                            >
                              {ACTION_LABELS[action] || action}
                            </Button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Panel>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Credibility disputes (PDD Figure 5.94)                             */
/* ------------------------------------------------------------------ */

function Disputes({ onNotice }) {
  const state = useResource("/moderation/disputes");
  const [busy, setBusy] = useState(null);

  async function resolve(dispute, outcome) {
    const note = window.prompt(
      outcome === "reverse"
        ? "Note for the writer (optional)"
        : "Tell the writer why the correction stands (optional)",
    );
    if (note === null) return;

    setBusy(dispute.id);
    try {
      await api.post(`/moderation/disputes/${dispute.id}/resolve`, { outcome, note });
      onNotice(
        outcome === "reverse"
          ? "Correction reversed and scores restored."
          : "Correction stands. The writer has been told.",
      );
      state.reload();
    } catch (e) {
      state.setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel state={state}>
      {(d) =>
        d.disputes.length === 0 ? (
          <Empty title="No disputes waiting">
            A writer can challenge a correction logged against their article. It
            arrives here with the correction and its effect on the score attached.
          </Empty>
        ) : (
          <div className="stack">
            {d.disputes.map((x) => (
              <article className="submission" key={x.id}>
                <div className="submission-main">
                  <h3 className="entry-title">
                    <Link className="link-quiet" to={`/articles/${x.article.slug}`}>
                      {x.article.title}
                    </Link>
                  </h3>
                  <p className="entry-meta mt-3">
                    <span>{x.contributor.name}</span>
                    <span className="dot" aria-hidden="true" />
                    <span className="tabular">
                      Score {Math.round(x.article.credibilityScore ?? 0)}
                    </span>
                    <span className="dot" aria-hidden="true" />
                    <span>Filed {formatDate(x.filedAt)}</span>
                  </p>

                  <p className="label mt-6">The correction being challenged</p>
                  <p className="entry-summary mt-2">
                    <span className="tag">{x.correction.type}</span> {x.correction.reason}
                  </p>

                  <p className="label mt-5">The writer&rsquo;s case</p>
                  <p className="entry-summary mt-2">{x.case}</p>

                  <div className="row gap-4 mt-6">
                    <Button
                      variant="primary"
                      busy={busy === x.id}
                      onClick={() => resolve(x, "reverse")}
                    >
                      Reverse the correction
                    </Button>
                    <Button
                      variant="outline"
                      busy={busy === x.id}
                      onClick={() => resolve(x, "uphold")}
                    >
                      It stands
                    </Button>
                  </div>
                  <p className="meta mt-4">
                    Reversing restores this article&rsquo;s score and the writer&rsquo;s
                    accuracy rate across everything they have published.
                  </p>
                </div>
              </article>
            ))}
          </div>
        )
      }
    </Panel>
  );
}

/* ------------------------------------------------------------------ */

export default function AdminConsole() {
  const { user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [notice, setNotice] = useState(null);

  function onNotice(message) {
    setNotice(message);
  }

  const PANELS = {
    overview: <Overview onGo={setTab} />,
    users: <Accounts onNotice={onNotice} />,
    applications: <Applications onNotice={onNotice} />,
    editors: <Editors onNotice={onNotice} />,
    articles: <Articles onNotice={onNotice} />,
    disputes: <Disputes onNotice={onNotice} />,
    categories: <Categories onNotice={onNotice} />,
    scoring: <Scoring onNotice={onNotice} />,
    logs: <Logs />,
  };

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">Administration</h1>
          <p className="meta mt-3">
            Signed in as {user.displayName}. Every action on this screen is recorded in the log.
          </p>
        </div>
      </header>

      {notice && (
        <div className="mt-6">
          <Notice tone="quiet">{notice}</Notice>
        </div>
      )}

      <nav className="tabs mt-6" aria-label="Administration sections">
        {TABS.map(([key, label]) => (
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

      <section className="section mt-6">{PANELS[tab]}</section>
    </div>
  );
}
