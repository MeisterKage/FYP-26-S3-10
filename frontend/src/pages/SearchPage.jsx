/**
 * Search (PDD Figure 5.7).
 *
 * Rule-based keyword matching against title, tags, and category. The page says
 * so plainly: the absence of clever ranking is a feature of this product, not an
 * omission to hide.
 */
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api";
import { CredibilityInline } from "../components/Credibility";
import { SearchIcon } from "../components/Icon";
import { ArticleEntry, Button, Empty, EntrySkeleton, Notice } from "../components/UI";

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") || "";

  const [draft, setDraft] = useState(query);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!query) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);

    api
      .get(`/search?q=${encodeURIComponent(query)}`)
      .then((data) => !cancelled && setResult(data))
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setBusy(false));

    return () => {
      cancelled = true;
    };
  }, [query]);

  function submit(event) {
    event.preventDefault();
    const next = draft.trim();
    setParams(next ? { q: next } : {});
  }

  return (
    <div className="wide">
      <h1 className="title">Search</h1>

      <form className="search-form mt-6" onSubmit={submit} role="search">
        <label className="sr-only" htmlFor="q">
          Search articles by title, tag, or category
        </label>
        <span className="search-icon" aria-hidden="true">
          <SearchIcon size={18} />
        </span>
        <input
          ref={inputRef}
          id="q"
          className="input search-input"
          type="search"
          value={draft}
          placeholder="Title, tag, or category"
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button variant="primary" type="submit" busy={busy}>
          Search
        </Button>
      </form>

      <p className="meta mt-4">
        Keyword matching only — no semantic search, no personalised ranking.
        Results are ordered by credibility, then recency.
      </p>

      <div className="mt-7">
        {error && <Notice>{error}</Notice>}

        {busy && !result && <EntrySkeleton rows={3} />}

        {result && result.articles.length === 0 && (
          <Empty title="No results found">
            Nothing matched &ldquo;{result.query}&rdquo;. Try a broader word, or a
            category name.
          </Empty>
        )}

        {result && result.articles.length > 0 && (
          <>
            <p className="label">
              {result.articles.length} result{result.articles.length === 1 ? "" : "s"}
            </p>
            <div className="stack mt-5">
              {result.articles.map((article) => (
                <ArticleEntry
                  key={article.id}
                  article={article}
                  aside={<CredibilityInline credibility={article.credibility} />}
                />
              ))}
            </div>
          </>
        )}

        {!query && !busy && (
          <Empty title="What are you looking for?">
            Search matches article titles, their tags, and category names.
          </Empty>
        )}
      </div>
    </div>
  );
}
