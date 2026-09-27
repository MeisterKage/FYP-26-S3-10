/**
 * Browse: a side panel listing every topic and country.
 *
 * Modelled on a retail menu (Kith's "Mens"): the tab opens a panel from the
 * left; choosing Topics or Countries slides that list into the same panel,
 * with a way back. It sits in the masthead as one tab rather than as eight
 * section links, which the administrator's crowded navigation could not take.
 *
 * It behaves as a modal dialog: focus moves into it and stays there, Escape
 * or the backdrop closes it, the page behind does not scroll, and focus
 * returns to the tab afterwards. Following a link closes it.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";

import { api } from "../api";
import { BackIcon, ChevronIcon, CloseIcon, MenuIcon } from "./Icon";

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

function useBrowseData(open) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!open || data) return;
    Promise.all([api.get("/categories"), api.get("/countries")])
      .then(([c, k]) => setData({
        topics: (c.categories || []).filter((x) => x.slug !== "uncategorised"),
        countries: k.countries || [],
      }))
      .catch((e) => setError(e.message));
  }, [open, data]);
  return { data, error };
}

function Row({ children, onClick, to, count }) {
  const content = (
    <>
      <span className="browse-row-label">{children}</span>
      {count != null && <span className="browse-row-count">{count}</span>}
      {onClick && <ChevronIcon size={18} className="browse-row-chevron" />}
    </>
  );
  return (
    <li>
      {to ? (
        <Link className="browse-row" to={to}>{content}</Link>
      ) : (
        <button type="button" className="browse-row" onClick={onClick}>{content}</button>
      )}
    </li>
  );
}

function Loading() {
  return (
    <ul className="browse-list" aria-hidden="true">
      {[0, 1, 2, 3, 4].map((i) => (
        <li key={i}><div className="skeleton skeleton-line browse-skeleton" /></li>
      ))}
    </ul>
  );
}

export function BrowseMenu() {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState("main");
  const trigger = useRef(null);
  const drawer = useRef(null);
  const location = useLocation();
  const { data, error } = useBrowseData(open);

  const close = useCallback(() => {
    setOpen(false);
    setPanel("main");
    // Back to where the reader was, so a keyboard user is not stranded at the top.
    requestAnimationFrame(() => trigger.current?.focus());
  }, []);

  // Following a link inside the panel changes the route: close then.
  useEffect(() => {
    setOpen(false);
    setPanel("main");
  }, [location.pathname, location.search]);

  // While open: stop the page scrolling behind, and move focus in.
  useEffect(() => {
    if (!open) return undefined;
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = previous;
    };
  }, [open]);

  // Each time the panel changes, focus its first control.
  useEffect(() => {
    if (!open) return;
    requestAnimationFrame(() => drawer.current?.querySelector(FOCUSABLE)?.focus());
  }, [open, panel]);

  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (panel !== "main") setPanel("main");
      else close();
      return;
    }
    if (event.key !== "Tab") return;
    // Keep focus inside the dialog.
    const items = [...drawer.current.querySelectorAll(FOCUSABLE)];
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  const title = { main: "Browse", topics: "Topics", countries: "Countries" }[panel];

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="nav-link browse-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="browse-drawer"
        onClick={() => setOpen(true)}
      >
        <MenuIcon size={18} />
        Browse
      </button>

      {open && createPortal(
        <div className="browse-layer" onKeyDown={onKeyDown}>
          <div className="browse-backdrop" onClick={close} aria-hidden="true" />
          <div
            ref={drawer}
            id="browse-drawer"
            className="browse-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={title}
          >
            <div className="browse-head">
              {panel === "main" ? (
                <p className="browse-title">Browse</p>
              ) : (
                <button type="button" className="browse-back" onClick={() => setPanel("main")}>
                  <BackIcon size={18} />
                  <span className="browse-title">{title}</span>
                </button>
              )}
              <button type="button" className="browse-close" onClick={close}
                aria-label="Close the menu">
                <CloseIcon size={20} />
              </button>
            </div>

            <div className="browse-body" key={panel} data-panel={panel}>
              {panel === "main" && (
                <>
                  <ul className="browse-list">
                    <Row onClick={() => setPanel("topics")} count={data?.topics.length}>
                      Topics
                    </Row>
                    <Row onClick={() => setPanel("countries")} count={data?.countries.length}>
                      Countries
                    </Row>
                  </ul>
                  <ul className="browse-list browse-list--secondary">
                    <Row to="/">Front page</Row>
                    <Row to="/digests">Monthly digests</Row>
                    <Row to="/editors">Our editors</Row>
                    <Row to="/about">How scoring works</Row>
                  </ul>
                  <Link className="browse-feature" to="/digests">
                    <span className="browse-feature-label">Featured</span>
                    <span className="browse-feature-title">This month&rsquo;s most credible reporting</span>
                    <span className="browse-feature-note">
                      Every section&rsquo;s best-verified articles, and what we corrected.
                    </span>
                  </Link>
                </>
              )}

              {panel === "topics" && (
                error ? <p className="browse-error">{error}</p>
                  : !data ? <Loading />
                  : (
                    <ul className="browse-list">
                      {data.topics.map((t) => (
                        <Row key={t.id} to={`/categories/${t.slug}`}>{t.name}</Row>
                      ))}
                    </ul>
                  )
              )}

              {panel === "countries" && (
                error ? <p className="browse-error">{error}</p>
                  : !data ? <Loading />
                  : (
                    <>
                      <ul className="browse-list">
                        <Row to="/countries">All countries</Row>
                      </ul>
                      <ul className="browse-list browse-list--secondary">
                        {data.countries.map((c) => (
                          <Row key={c.code} to={`/countries/${c.code.toLowerCase()}`}
                            count={c.articleCount}>
                            {c.name}
                          </Row>
                        ))}
                      </ul>
                    </>
                  )
              )}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
