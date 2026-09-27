/**
 * A writer's own work (PDD Figures 5.41 to 5.46).
 *
 * Operate mode. This is a workbench, so scanability and status outrank
 * expression: the display serif appears once at the top and the rest is a ruled
 * table with tabular figures.
 *
 * The writer's own accuracy rate leads, because it is the number that moves
 * every score below it.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { CredibilityInline } from "../components/Credibility";
import { Button, Empty, Notice, SectionHead, formatDate } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

const EDITABLE = new Set(["draft", "rejected"]);

export default function ContributorDashboard() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [articles, setArticles] = useState(null);
  usePageTitle("Your articles");
  const [notice, setNotice] = useState(location.state?.notice || null);
  const [error, setError] = useState(null);
  const [pendingId, setPendingId] = useState(null);

  useEffect(() => {
    if (location.state?.notice) navigate(location.pathname, { replace: true });
  }, [location.pathname, location.state, navigate]);

  const load = useCallback(() => {
    api
      .get("/articles/mine")
      .then((data) => setArticles(data.articles))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  async function submitForReview(article) {
    setNotice(null);
    setError(null);
    setPendingId(article.id);
    try {
      await api.post(`/articles/${article.id}/submit`);
      setNotice(`“${article.title}” is with an editor.`);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setPendingId(null);
    }
  }

  const counts = articles
    ? articles.reduce((acc, a) => ({ ...acc, [a.status]: (acc[a.status] || 0) + 1 }), {})
    : {};

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">Your writing</h1>
          <p className="meta mt-3">
            {user.accuracyRate == null ? (
              <>
                You are a <strong>new contributor</strong>, so your accuracy
                rate appears once you have published enough articles.
              </>
            ) : (
              <>
                Your accuracy rate is <strong>{user.accuracyRate}%</strong>. It
                feeds the credibility score of every article you publish.
              </>
            )}
          </p>
        </div>
        <div className="row gap-4">
          <Link className="link-quiet" to="/about">
            How scoring works
          </Link>
          <Link className="btn btn-primary" to="/dashboard/articles/new">
            New article
          </Link>
        </div>
      </header>

      {notice && (
        <div className="mt-6">
          <Notice tone="quiet">{notice}</Notice>
        </div>
      )}
      {error && (
        <div className="mt-6">
          <Notice>{error}</Notice>
        </div>
      )}

      <section className="section mt-7">
        <SectionHead title="Articles">
          {articles && (
            <p className="label">
              {counts.published || 0} published · {counts.pending || 0} in review ·{" "}
              {counts.draft || 0} draft
            </p>
          )}
        </SectionHead>

        {!articles && <div className="skeleton" style={{ height: "12rem" }} />}

        {articles?.length === 0 && (
          <Empty
            title="You haven't written anything yet"
            action={
              <Link className="btn btn-primary" to="/dashboard/articles/new">
                Write your first article
              </Link>
            }
          >
            Drafts stay private until you submit them. An editor for the
            article&rsquo;s category reviews it before it goes live.
          </Empty>
        )}

        {articles?.length > 0 && (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Status</th>
                  <th scope="col">Credibility</th>
                  <th scope="col">Updated</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {articles.map((article) => (
                  <tr key={article.id}>
                    <td>
                      <span style={{ color: "var(--ink)", fontWeight: 500 }}>
                        {article.title}
                      </span>
                      {article.isPremium && (
                        <>
                          {" "}
                          <span className="tag">Subscriber</span>
                        </>
                      )}
                    </td>
                    <td>
                      <span className="status" data-status={article.status}>
                        {article.status}
                      </span>
                    </td>
                    {/* data-blank: a placeholder dash reads correctly in a
                        desktop column but stacks as a stray line on mobile,
                        where the CSS drops it entirely. */}
                    <td data-blank={article.status !== "published" || undefined}>
                      {article.status === "published" ? (
                        <CredibilityInline credibility={article.credibility} review={article.review} />
                      ) : (
                        <span className="meta">—</span>
                      )}
                    </td>
                    <td className="meta" data-blank={!article.publishedAt || undefined}>
                      {formatDate(article.publishedAt) || "—"}
                    </td>
                    <td>
                      <div className="row gap-2">
                        <Link
                          className="btn btn-quiet btn-sm"
                          to={`/dashboard/articles/${article.id}`}
                        >
                          {EDITABLE.has(article.status) ? "Edit" : "View"}
                        </Link>
                        {EDITABLE.has(article.status) && (
                          <Button
                            size="sm"
                            variant="outline"
                            busy={pendingId === article.id}
                            onClick={() => submitForReview(article)}
                          >
                            Submit for review
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
