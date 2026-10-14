/**
 * Page furniture: masthead, footer, and the error boundary that keeps one bad
 * render from blanking the whole application.
 */
import { Component, useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { api } from "../api";
import { CAN_ADMIN, CAN_AUTHOR, CAN_REVIEW, useAuth } from "../auth";
import { AccountMenu } from "./AccountMenu";
import { BrowseMenu } from "./BrowseMenu";
import { LanguageSwitcher } from "./LanguageSwitcher";
import Notifications from "./Notifications";
import { Button, Notice } from "./UI";
import { useI18n } from "../i18n";

export function Masthead() {
  const { user, has } = useAuth();
  const { t } = useI18n();

  return (
    <header className="masthead">
      <div className="shell masthead-inner">
        {/* First on the left, beside the wordmark: the panel it opens slides in
            from this side. */}
        <div className="masthead-browse">
          <BrowseMenu />
        </div>
        <Link className="wordmark" to="/">
          Wollongong News
        </Link>

        <nav className="nav" aria-label="Main">
          <NavLink className="nav-link" to="/search">
            {t("nav.search")}
          </NavLink>

          {has(...CAN_AUTHOR) && (
            <NavLink className="nav-link" to="/dashboard">
              {t("nav.yourWriting")}
            </NavLink>
          )}
          {has(...CAN_REVIEW) && (
            <NavLink className="nav-link" to="/review">
              {t("nav.reviewQueue")}
            </NavLink>
          )}
          {has(...CAN_REVIEW) && (
            <NavLink className="nav-link" to="/moderation">
              {t("nav.flagged")}
            </NavLink>
          )}
          {has(...CAN_ADMIN) && (
            <NavLink className="nav-link" to="/admin">
              {t("nav.admin")}
            </NavLink>
          )}

          {user && <Notifications />}
          {!user && (
            <NavLink className="nav-link" to="/pricing">
              {t("nav.pricing")}
            </NavLink>
          )}
        </nav>

        {/* Outside the nav, which scrolls sideways on narrow screens: the way
            to your account or to sign in must never be scrolled out of view. */}
        <div className="masthead-account">
          <LanguageSwitcher />
          {user ? (
            <AccountMenu />
          ) : (
            <>
              <NavLink className="nav-link" to="/login">
                {t("nav.signIn")}
              </NavLink>
              <Button variant="primary" size="sm" as={Link} to="/register">
                {t("nav.createAccount")}
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  // Sections are fetched rather than hard-coded: an administrator can add or
  // remove one at runtime, and a footer listing last month's sections would be
  // worse than listing none.
  const [categories, setCategories] = useState([]);
  const { t, section } = useI18n();

  useEffect(() => {
    api
      .get("/categories")
      .then((d) => setCategories(d.categories || []))
      .catch(() => setCategories([]));
  }, []);

  return (
    <footer className="footer">
      <div className="shell footer-inner">
        <p>
          {t("footer.tagline")}
        </p>
        {categories.length > 0 && (
          <nav className="footer-sections" aria-label="Sections">
            {categories.map((c) => (
              <Link className="link-quiet" key={c.id} to={`/categories/${c.slug}`}>
                {section(c.slug, c.name)}
              </Link>
            ))}
          </nav>
        )}
        <nav aria-label="Footer">
          <Link className="link-quiet" to="/about-us">{t("footer.aboutUs")}</Link>
          <Link className="link-quiet" to="/about">{t("footer.howScoring")}</Link>
          <Link className="link-quiet" to="/topics">{t("footer.allTopics")}</Link>
          <Link className="link-quiet" to="/digests">{t("footer.digests")}</Link>
          <Link className="link-quiet" to="/countries">{t("footer.countries")}</Link>
          <Link className="link-quiet" to="/editors">{t("footer.editors")}</Link>
          <Link className="link-quiet" to="/pricing">{t("footer.subscriptions")}</Link>
          <Link className="link-quiet" to="/search">{t("footer.search")}</Link>
          <Link className="link-quiet" to="/privacy">{t("footer.privacy")}</Link>
          <Link className="link-quiet" to="/terms">{t("footer.terms")}</Link>
        </nav>
      </div>
    </footer>
  );
}

/**
 * Error boundary.
 *
 * Without one, a single render error unmounts the whole tree and the reader
 * gets a white page with no explanation and no way back. This keeps the
 * masthead, says what happened in the product's own voice, and offers the two
 * recoveries that actually work.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Left in place deliberately: in development this is the only record of
    // what broke, and in production it is where a reporter would be wired in.
    console.error("Render failed:", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="shell main" id="main">
        <div className="read">
          <h1 className="title">This page didn&rsquo;t load</h1>
          <p className="lead mt-4">
            Something went wrong while rendering it. Your work has not been sent
            anywhere, and reloading usually clears it.
          </p>
          <div className="row gap-4 mt-6">
            <Button variant="primary" onClick={() => window.location.reload()}>
              Reload the page
            </Button>
            <Button variant="outline" onClick={() => (window.location.href = "/")}>
              Back to the front page
            </Button>
          </div>
          <div className="mt-7">
            <Notice tone="quiet">
              If this keeps happening, the details are in the browser console.
            </Notice>
          </div>
        </div>
      </main>
    );
  }
}
