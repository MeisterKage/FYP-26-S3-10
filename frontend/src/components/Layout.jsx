/**
 * Page furniture: masthead, footer, and the error boundary that keeps one bad
 * render from blanking the whole application.
 */
import { Component, useEffect, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { api } from "../api";
import { CAN_ADMIN, CAN_AUTHOR, CAN_REVIEW, useAuth } from "../auth";
import { BrowseMenu } from "./BrowseMenu";
import Notifications from "./Notifications";
import { Button, Notice } from "./UI";

export function Masthead() {
  const { user, signOut, has } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="masthead">
      <div className="shell masthead-inner">
        <Link className="wordmark" to="/">
          Wollongong News
        </Link>

        <nav className="nav" aria-label="Main">
          <BrowseMenu />
          <NavLink className="nav-link" to="/search">
            Search
          </NavLink>
          <NavLink className="nav-link" to="/about">
            How scoring works
          </NavLink>

          {has(...CAN_AUTHOR) && (
            <NavLink className="nav-link" to="/dashboard">
              Your writing
            </NavLink>
          )}
          {has(...CAN_REVIEW) && (
            <NavLink className="nav-link" to="/review">
              Review queue
            </NavLink>
          )}
          {has(...CAN_REVIEW) && (
            <NavLink className="nav-link" to="/moderation">
              Flagged
            </NavLink>
          )}
          {has(...CAN_ADMIN) && (
            <NavLink className="nav-link" to="/admin">
              Administration
            </NavLink>
          )}

          {user && <Notifications />}

          <span className="nav-divider" aria-hidden="true" />

          {user ? (
            <>
              <NavLink className="nav-link nav-name" to="/account">
                {user.displayName}
              </NavLink>
              <Button
                variant="quiet"
                size="sm"
                onClick={async () => {
                  await signOut();
                  navigate("/");
                }}
              >
                Sign out
              </Button>
            </>
          ) : (
            <>
              <NavLink className="nav-link" to="/login">
                Sign in
              </NavLink>
              <Button variant="primary" size="sm" as={Link} to="/register">
                Create account
              </Button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  // Sections are fetched rather than hard-coded: an administrator can add or
  // remove one at runtime, and a footer listing last month's sections would be
  // worse than listing none.
  const [categories, setCategories] = useState([]);

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
          Wollongong News. Every article scored by the same fixed rules.
        </p>
        {categories.length > 0 && (
          <nav className="footer-sections" aria-label="Sections">
            {categories.map((c) => (
              <Link className="link-quiet" key={c.id} to={`/categories/${c.slug}`}>
                {c.name}
              </Link>
            ))}
          </nav>
        )}
        <nav aria-label="Footer">
          <Link className="link-quiet" to="/about">
            How scoring works
          </Link>
          <Link className="link-quiet" to="/digests">
            Monthly digests
          </Link>
          <Link className="link-quiet" to="/countries">
            Countries
          </Link>
          <Link className="link-quiet" to="/editors">
            Our editors
          </Link>
          <Link className="link-quiet" to="/pricing">
            Subscriptions
          </Link>
          <Link className="link-quiet" to="/search">
            Search
          </Link>
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
