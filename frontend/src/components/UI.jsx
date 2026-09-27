/**
 * Shared primitives: buttons, fields, notices, empty states, layout furniture.
 */
import { Link } from "react-router-dom";

import { EntryThumb } from "./CoverImage";

import { AlertIcon, InfoIcon } from "./Icon";

export function Button({
  variant = "outline",
  size,
  busy = false,
  as: As = "button",
  className = "",
  children,
  ...rest
}) {
  const classes = [
    "btn",
    `btn-${variant}`,
    size === "sm" ? "btn-sm" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  // Default to type="button". A <button> with no type inside a form is a
  // submit button, so an action button next to a form silently submits it.
  // Every real submit in this codebase passes type="submit" explicitly.
  const typeProp = As === "button" && rest.type === undefined ? { type: "button" } : {};

  return (
    <As
      className={classes}
      data-busy={busy || undefined}
      aria-busy={busy || undefined}
      {...typeProp}
      {...rest}
    >
      {children}
    </As>
  );
}

export function Field({ label, id, hint, error, children }) {
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {children({
        id,
        "aria-invalid": error ? "true" : undefined,
        "aria-describedby": describedBy || undefined,
      })}
      {hint && !error && (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field-error" id={`${id}-error`}>
          <AlertIcon size={15} />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

/**
 * A notice.
 *
 * There is no red in this world, so an error is marked by a full-weight rule
 * and an icon rather than by turning a colour. `role="alert"` carries the
 * urgency to a screen reader, which a colour never did.
 */
export function Notice({ tone = "loud", children, ...rest }) {
  const Icon = tone === "loud" ? AlertIcon : InfoIcon;
  return (
    <div
      className={`notice${tone === "quiet" ? " notice-quiet" : ""}`}
      role={tone === "loud" ? "alert" : "status"}
      {...rest}
    >
      <Icon size={18} />
      <div>{children}</div>
    </div>
  );
}

export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <h2 className="sub">{title}</h2>
      {children && <p className="meta">{children}</p>}
      {action}
    </div>
  );
}

export function SectionHead({ title, children }) {
  return (
    <div className="section-head">
      <h2 className="heading">{title}</h2>
      {children}
    </div>
  );
}

/** Loading placeholder shaped like the content it replaces, not a spinner. */
export function EntrySkeleton({ rows = 3 }) {
  return (
    <div className="stack" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div className="entry" key={i}>
          <div style={{ width: "100%" }}>
            <div className="skeleton skeleton-line" style={{ width: "62%", height: "1.6em" }} />
            <div className="skeleton skeleton-line" style={{ width: "88%" }} />
            <div className="skeleton skeleton-line" style={{ width: "34%" }} />
          </div>
        </div>
      ))}
      <span className="sr-only">Loading</span>
    </div>
  );
}

export function formatDate(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** One listing row. Rules between entries, not a grid of identical cards. */
export function ArticleEntry({ article, aside }) {
  const date = formatDate(article.publishedAt);

  return (
    <article className={`entry${article.coverImage ? " entry--media" : ""}`}>
      <EntryThumb image={article.coverImage} />
      <h3 className="entry-title">
        <Link to={`/articles/${article.slug}`}>{article.title}</Link>
      </h3>

      {article.summary && <p className="entry-summary">{article.summary}</p>}

      <p className="entry-meta">
        {/* Not a link: contributor profiles are a later surface, and a dead
            link is worse than a plain byline. */}
        <span>
          {article.republication
            ? `${article.republication.authors[0].split(",")[0]}${article.republication.authors.length > 1 ? " and others" : ""}, ${article.republication.publisher}`
            : article.contributor.name}
        </span>
        {date && <span className="dot">{date}</span>}
        {article.isPremium && (
          <>
            <span className="dot" aria-hidden="true" />
            <span className="tag">Subscriber</span>
          </>
        )}
      </p>

      {aside && <div className="entry-aside">{aside}</div>}
    </article>
  );
}
