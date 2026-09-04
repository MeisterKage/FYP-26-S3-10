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

import { api } from "../api";
import { ROLES, useAuth } from "../auth";
import { Button, Empty, Notice, formatDate } from "../components/UI";

const TABS = [
  ["overview", "Overview"],
  ["users", "Accounts"],
  ["applications", "Applications"],
  ["editors", "Editors"],
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

function Overview() {
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
        <div className="stat-grid">
          {CARDS.map(([key, label]) => (
            <div className="stat" key={key}>
              <p className="label">{label}</p>
              <p className="stat-figure">{d[key] ?? 0}</p>
            </div>
          ))}
        </div>
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
                              if (
                                !window.confirm(
                                  `Remove ${u.name}? Their articles stay published under "Account Removed". This cannot be undone.`,
                                )
                              )
                                return;
                              act(
                                u,
                                () => api.del(`/admin/users/${u.id}`),
                                `${u.name} has been removed.`,
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
                  <td style={{ color: "var(--ink)", fontWeight: 500 }}>{c.name}</td>
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

function Scoring({ onNotice }) {
  const state = useResource("/admin/settings");
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState(false);

  const changed = Object.keys(draft).length > 0;

  async function save() {
    setBusy(true);
    try {
      await api.put("/admin/settings", {
        settings: Object.fromEntries(
          Object.entries(draft).map(([k, v]) => [k, Number(v)]),
        ),
      });
      onNotice("Thresholds saved. Every published score has been recalculated.");
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
            These constants are published on the How scoring works page. Changing one
            recalculates every article&rsquo;s credibility score immediately.
          </Notice>

          <div className="table-scroll mt-5">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Threshold</th>
                  <th scope="col">Value</th>
                  <th scope="col">Shipped default</th>
                </tr>
              </thead>
              <tbody>
                {d.settings.map((s) => (
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
                        onChange={(e) =>
                          setDraft((p) => ({ ...p, [s.key]: e.target.value }))
                        }
                      />
                    </td>
                    <td className="meta">{s.default}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="row gap-4 mt-6">
            <Button variant="primary" onClick={save} busy={busy} disabled={!changed}>
              Save and rescore
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

export default function AdminConsole() {
  const { user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [notice, setNotice] = useState(null);

  function onNotice(message) {
    setNotice(message);
  }

  const PANELS = {
    overview: <Overview />,
    users: <Accounts onNotice={onNotice} />,
    applications: <Applications onNotice={onNotice} />,
    editors: <Editors onNotice={onNotice} />,
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
