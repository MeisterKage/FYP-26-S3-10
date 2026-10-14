/**
 * Writing and editing an article (PDD Figures 5.41 to 5.44).
 *
 * Operate mode. The writer is composing, so the column is narrow enough to read
 * comfortably and everything that is not the body sits out of the way.
 *
 * Sources get their own repeatable list rather than a comma-separated box,
 * because the count feeds the Credibility Score directly. A writer should see
 * what each one is worth while they add it, which is what the running note
 * under the list does.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../api";
import { CoverImageField } from "../components/CoverImage";
import { OriginalityCheck } from "../components/Originality";
import { SourceIcon } from "../components/Icon";
import RichText from "../components/RichText";
import { Button, Field, Notice, SectionHead, formatDate } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

const MAX_SOURCES = 20;
const MAX_TAGS = 10;

/** Statuses the server will accept an edit for (articles.py EDITABLE). */
const EDITABLE = new Set(["draft", "rejected", "unpublished", "published"]);

const BLANK = {
  title: "",
  summary: "",
  body: "",
  categoryId: "",
  // What the article is about. Starts on Australia; "" means international.
  countryCode: "AU",
  tags: "",
  isPremium: false,
};

function SourceRows({ sources, onChange, disabled }) {
  function update(index, key, value) {
    const next = sources.map((s, i) => (i === index ? { ...s, [key]: value } : s));
    onChange(next);
  }

  return (
    <div className="sources-editor">
      {sources.map((source, i) => (
        <div className="source-row" key={i}>
          <span className="sources-num" aria-hidden="true">
            {i + 1}
          </span>
          <div className="source-row-fields">
            <input
              className="input"
              type="url"
              inputMode="url"
              placeholder="https://example.com/report"
              aria-label={`Source ${i + 1} link`}
              value={source.url}
              onChange={(e) => update(i, "url", e.target.value)}
              disabled={disabled}
            />
            <input
              className="input"
              placeholder="What it is (optional)"
              aria-label={`Source ${i + 1} description`}
              value={source.label}
              onChange={(e) => update(i, "label", e.target.value)}
              disabled={disabled}
            />
          </div>
          <Button
            variant="quiet"
            size="sm"
            type="button"
            onClick={() => onChange(sources.filter((_, j) => j !== i))}
            disabled={disabled}
            aria-label={`Remove source ${i + 1}`}
          >
            Remove
          </Button>
        </div>
      ))}

      {sources.length < MAX_SOURCES && (
        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={() => onChange([...sources, { url: "", label: "" }])}
          disabled={disabled}
        >
          Add a source
        </Button>
      )}
    </div>
  );
}

export default function ArticleEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  // "new" is a route param, not a separate route: see App.jsx.
  const isNew = id === "new" || id === undefined;
  usePageTitle(isNew ? "New article" : "Edit article");

  const [form, setForm] = useState(BLANK);
  const [sources, setSources] = useState([]);
  // { image: {key, url, thumbUrl, width, height} | null, alt, credit }
  const [cover, setCover] = useState({ image: null, alt: "", credit: "" });
  const [categories, setCategories] = useState([]);
  const [countries, setCountries] = useState([]);
  const [status, setStatus] = useState("draft");
  const [articleId, setArticleId] = useState(null);
  const [rejection, setRejection] = useState(null);

  const [loading, setLoading] = useState(!isNew);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [fieldError, setFieldError] = useState({});
  const [notice, setNotice] = useState(null);
  const [publishAt, setPublishAt] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);

  useEffect(() => {
    api
      .get("/categories")
      .then((d) => setCategories(d.categories || []))
      .catch(() => setCategories([]));
    api
      .get("/countries/all")
      .then((d) => setCountries(d.countries || []))
      .catch(() => setCountries([]));
  }, []);

  // The owner-scoped read, which includes the body. The public route is keyed
  // on slug and withholds premium bodies, so it cannot back an editing screen.
  useEffect(() => {
    if (isNew) return;
    let cancelled = false;

    api
      .get(`/articles/${id}`)
      .then((d) => {
        if (cancelled) return;
        const found = d.article;
        setArticleId(found.id);
        setStatus(found.status);
        setUpdatedAt(found.publishedAt || found.submittedAt || null);
        setRejection(found.rejectionReason || null);
        setForm({
          title: found.title || "",
          summary: found.summary || "",
          body: found.body || "",
          categoryId: found.categoryId ? String(found.categoryId) : "",
          countryCode: found.country?.code || "",
          tags: (found.tags || []).join(", "),
          isPremium: Boolean(found.isPremium),
        });
        setSources((found.sources || []).map((s) => ({ url: s.url, label: s.label || "" })));
        setCover({
          image: found.coverImage || null,
          alt: found.coverImage?.alt || "",
          credit: found.coverImage?.credit || "",
        });
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, isNew]);

  const set = useCallback(
    (key) => (event) => {
      const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
      setForm((f) => ({ ...f, [key]: value }));
      setFieldError((f) => ({ ...f, [key]: undefined }));
    },
    [],
  );

  const payload = useMemo(
    () => ({
      title: form.title,
      summary: form.summary,
      body: form.body,
      categoryId: Number(form.categoryId),
      countryCode: form.countryCode || null,
      coverImage: cover.image?.key || null,
      coverImageAlt: cover.alt,
      coverImageCredit: cover.credit,
      isPremium: form.isPremium,
      tags: form.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, MAX_TAGS),
      sources: sources.filter((s) => s.url.trim()),
    }),
    [form, sources, cover],
  );

  const validSources = payload.sources.filter((s) =>
    /^https?:\/\//i.test(s.url.trim()),
  ).length;

  const editable = isNew || EDITABLE.has(status);

  function handleError(e) {
    if (e instanceof ApiError && e.field) {
      setFieldError({ [e.field]: e.message });
      setError(null);
    } else {
      setError(e.message);
    }
  }

  /** Persist, and return the article id so a follow-on action can use it. */
  async function persist() {
    if (articleId) {
      await api.patch(`/articles/${articleId}`, payload);
      return articleId;
    }
    const created = await api.post("/articles", payload);
    const newId = created.article?.id ?? created.id;
    setArticleId(newId);
    // Move to the edit URL so a refresh does not create a second draft.
    navigate(`/dashboard/articles/${newId}`, { replace: true });
    return newId;
  }

  async function save(event) {
    event?.preventDefault();
    setBusy("save");
    setError(null);
    setFieldError({});
    try {
      await persist();
      setNotice("Saved.");
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(null);
    }
  }

  async function submit() {
    setBusy("submit");
    setError(null);
    setFieldError({});
    try {
      const target = await persist();
      await api.post(`/articles/${target}/submit`);
      navigate("/dashboard", {
        state: { notice: `“${form.title}” is with an editor for review.` },
      });
    } catch (e) {
      handleError(e);
      setBusy(null);
    }
  }

  /** PDD Figure 5.44. The server accepts this only on an approved article. */
  async function schedule() {
    setBusy("schedule");
    setError(null);
    try {
      // datetime-local has no timezone, and the server treats a naive value as
      // UTC. Send an explicit offset so "9am" means 9am where the writer is.
      const iso = new Date(publishAt).toISOString();
      await api.post(`/articles/${articleId}/schedule`, { publishAt: iso });
      setNotice(`Scheduled to publish on ${new Date(publishAt).toLocaleString()}.`);
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(null);
    }
  }

  // DELETE /articles/<id> does two different things depending on status: it
  // destroys a draft, and it unpublishes a live article without destroying it.
  // The button used to say "Delete" and warn "cannot be undone" for both, which
  // was wrong and alarming for the reversible case.
  const isLive = status === "published" || status === "scheduled";

  async function discard() {
    if (!articleId) {
      navigate("/dashboard");
      return;
    }
    const confirmation = isLive
      ? "Take this article off the site? Readers will no longer see it. You can publish it again later."
      : "Delete this draft? This cannot be undone.";
    if (!window.confirm(confirmation)) return;

    setBusy("delete");
    try {
      await api.del(`/articles/${articleId}`);
      navigate("/dashboard", {
        state: { notice: isLive ? "Article unpublished." : "Draft deleted." },
      });
    } catch (e) {
      handleError(e);
      setBusy(null);
    }
  }

  if (loading) return <div className="skeleton" style={{ height: "24rem" }} />;

  if (error && !editable && !articleId) {
    return <Notice>{error}</Notice>;
  }

  return (
    <div className="editor">
      <header className="dash-head">
        <div>
          <h1 className="title">{isNew ? "New article" : "Edit article"}</h1>
          <p className="entry-meta mt-3">
            {isNew ? (
              <span>Saved as a draft until you send it for review.</span>
            ) : (
              <>
                <span className="status" data-status={status}>
                  {status}
                </span>
                {updatedAt && (
                  <>
                    <span className="dot" aria-hidden="true" />
                    <span>Last edited {formatDate(updatedAt)}</span>
                  </>
                )}
              </>
            )}
          </p>
        </div>
      </header>

      {rejection && (
        <div className="mt-6">
          <Notice>
            <strong>Returned by an editor.</strong> {rejection}
          </Notice>
        </div>
      )}

      {!editable && (
        <div className="mt-6">
          <Notice tone="quiet">
            An article that is {status} cannot be edited. Nothing here will save.
          </Notice>
        </div>
      )}

      {error && (
        <div className="mt-6">
          <Notice>{error}</Notice>
        </div>
      )}
      {notice && (
        <div className="mt-6">
          <Notice tone="quiet">{notice}</Notice>
        </div>
      )}

      <form className="form editor-form mt-7" onSubmit={save} noValidate>
        {/* The writing on the left; what it is filed under, and the buttons
            that send it, beside it on a wide screen. */}
        <div className="editor-main">
        <Field label="Headline" id="title" error={fieldError.title}>
          {(props) => (
            <input
              {...props}
              className="input input-title"
              value={form.title}
              onChange={set("title")}
              disabled={!editable}
              maxLength={255}
              required
            />
          )}
        </Field>

        <Field
          label="Standfirst"
          id="summary"
          hint="One or two sentences. This is what readers see on the front page."
          error={fieldError.summary}
        >
          {(props) => (
            <textarea
              {...props}
              className="textarea"
              rows={2}
              maxLength={500}
              value={form.summary}
              onChange={set("summary")}
              disabled={!editable}
            />
          )}
        </Field>

        <Field
          label="Article"
          id="body"
          hint="Anything unsafe is stripped when you save, whatever you paste."
          error={fieldError.body}
        >
          {(props) => (
            <RichText
              {...props}
              value={form.body}
              onChange={(html) => {
                setForm((f) => ({ ...f, body: html }));
                setFieldError((f) => ({ ...f, body: undefined }));
              }}
              disabled={!editable}
            />
          )}
        </Field>

        <section className="section">
          <SectionHead title="Sources">
            <p className="label">
              <SourceIcon size={14} style={{ display: "inline", verticalAlign: "-2px" }} />{" "}
              {validSources} verified
            </p>
          </SectionHead>
          <p className="field-hint">
            Each source raises the credibility score by what kind of source it is: an
            official body, published research or an established outlet counts for most;
            placeholders, social media and deprecated sites count for nothing. Only
            your five best sources count, so a better source helps more than another
            link. Your editor sees the rating for each one.
          </p>
          <div className="mt-4">
            <SourceRows sources={sources} onChange={setSources} disabled={!editable} />
          </div>
        </section>

        {editable && (
          <section className="section">
            <SectionHead title="Originality" />
            <p className="field-hint">
              Runs automatically when you submit, and your editor sees the result. Check
              first so nothing surprises you. Quotations are never counted as copying.
            </p>
            <div className="mt-4">
              {/* Saves first: the check reads what is stored, not the form. */}
              <OriginalityCheck beforeCheck={persist} />
            </div>
          </section>
        )}

        </div>

        <aside className="editor-side" aria-label="Article settings">
        <Field label="Section" id="categoryId" error={fieldError.categoryId}
          hint="Required. An article cannot be submitted or published without a section.">
          {(props) => (
            <select
              {...props}
              className="input"
              value={form.categoryId}
              onChange={set("categoryId")}
              disabled={!editable}
              required
            >
              <option value="">Choose a section</option>
              {/* Uncategorised is never offered: every article needs a real section. */}
              {categories.filter((c) => c.slug !== "uncategorised").map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </Field>

        <Field
          label="Country"
          id="countryCode"
          hint="The country the article is about, not where you are."
          error={fieldError.countryCode}
        >
          {(props) => (
            <select
              {...props}
              className="input"
              value={form.countryCode}
              onChange={set("countryCode")}
              disabled={!editable}
            >
              <option value="">International / no single country</option>
              {/* Until the list arrives, keep the current value selectable so
                  the select does not silently show a different country. */}
              {countries.length === 0 && form.countryCode && (
                <option value={form.countryCode}>{form.countryCode}</option>
              )}
              {countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </Field>

        <CoverImageField
          value={cover.image}
          alt={cover.alt}
          credit={cover.credit}
          disabled={!editable}
          errors={fieldError}
          onChange={(change) => {
            setCover((c) => ({ ...c, ...change }));
            setFieldError((f) => ({ ...f, coverImageAlt: undefined, coverImageCredit: undefined }));
          }}
        />

        <Field
          label="Tags"
          id="tags"
          hint="Comma separated. Used by search, which matches on keywords only."
          error={fieldError.tags}
        >
          {(props) => (
            <input
              {...props}
              className="input"
              value={form.tags}
              onChange={set("tags")}
              disabled={!editable}
            />
          )}
        </Field>

        <div className="field">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.isPremium}
              onChange={set("isPremium")}
              disabled={!editable}
            />
            <span>Subscribers only</span>
          </label>
          <p className="field-hint">
            Readers without a subscription see the opening lines and nothing more.
          </p>
        </div>

        {(status === "published" || status === "scheduled") && (
          <section className="well">
            <p className="label">Schedule publication</p>
            <p className="field-hint mt-2">
              Only an approved article can be scheduled, and only for a time in the
              future.
            </p>
            <div className="row gap-4 mt-4">
              <input
                className="input"
                type="datetime-local"
                aria-label="Publication time"
                value={publishAt}
                onChange={(e) => setPublishAt(e.target.value)}
              />
              <Button
                variant="outline"
                type="button"
                busy={busy === "schedule"}
                disabled={!publishAt}
                onClick={schedule}
              >
                Schedule
              </Button>
            </div>
          </section>
        )}

        <div className="editor-actions">
          <Button
            variant="primary"
            type="button"
            onClick={submit}
            busy={busy === "submit"}
            disabled={!editable || !form.title.trim() || !form.categoryId}
          >
            Submit for review
          </Button>
          <Button
            variant="outline"
            type="submit"
            busy={busy === "save"}
            disabled={!editable}
          >
            Save draft
          </Button>
          <Button variant="quiet" type="button" onClick={() => navigate("/dashboard")}>
            Back
          </Button>
          {articleId && (
            <Button
              variant="quiet"
              type="button"
              onClick={discard}
              busy={busy === "delete"}
              style={{ marginLeft: "auto" }}
            >
              {isLive ? "Unpublish" : "Delete"}
            </Button>
          )}
        </div>
        </aside>
      </form>
    </div>
  );
}
