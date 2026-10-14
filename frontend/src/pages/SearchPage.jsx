/**
 * Search (PDD Figure 5.7).
 *
 * Rule-based keyword matching against title, tags, and category. The page says
 * so plainly, because the absence of clever ranking is deliberate here.
 */
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api";
import { CredibilityInline } from "../components/Credibility";
import { SearchIcon } from "../components/Icon";
import { ArticleEntry, Button, Empty, EntrySkeleton, Notice } from "../components/UI";
import { useI18n } from "../i18n";
import { usePageTitle } from "../usePageTitle";

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") || "";
  const { t } = useI18n();
  usePageTitle(query ? `${t("nav.search")}: ${query}` : t("nav.search"));

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
      <h1 className="title">{t("nav.search")}</h1>

      <form className="search-form mt-6" onSubmit={submit} role="search">
        <label className="sr-only" htmlFor="q">
          {t("search.label")}
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
          placeholder={t("search.placeholder")}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button variant="primary" type="submit" busy={busy}>
          {t("nav.search")}
        </Button>
      </form>

      <p className="meta mt-4">{t("search.how")}</p>

      <div className="mt-7">
        {error && <Notice>{error}</Notice>}

        {busy && !result && <EntrySkeleton rows={3} />}

        {result && result.articles.length === 0 && (
          <Empty title={t("search.none")}>{t("search.noneText", { q: result.query })}</Empty>
        )}

        {result && result.articles.length > 0 && (
          <>
            <p className="label">
              {result.articles.length === 1
                ? t("search.countOne")
                : t("search.count", { n: result.articles.length })}
            </p>
            <div className="stack mt-5">
              {result.articles.map((article) => (
                <ArticleEntry
                  key={article.id}
                  article={article}
                  aside={<CredibilityInline credibility={article.credibility} review={article.review} />}
                />
              ))}
            </div>
          </>
        )}

        {!query && !busy && (
          <Empty title={t("search.prompt")}>{t("search.promptText")}</Empty>
        )}
      </div>
    </div>
  );
}
