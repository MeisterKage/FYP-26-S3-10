/**
 * Sharing and revision history for a published article
 * (PDD Figures 5.8, 5.35, 5.43).
 *
 * Revision history is public rather than author-only, because corrections and
 * retractions are logged there permanently and the product's claim is that a
 * reader can trace why a score is what it is. A history a reader cannot open is
 * not a disclosure.
 *
 * Share links come from the server. The URLs are real and need no key, but
 * building them client-side would duplicate the encoding rules in two places.
 */
import { useState } from "react";

import { api, downloadFile } from "../api";
import { Button, Notice, formatDate } from "./UI";

export default function ArticleExtras({ article }) {
  const [share, setShare] = useState(null);
  const [downloading, setDownloading] = useState(null);
  const [revisions, setRevisions] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  async function openShare() {
    if (share) {
      setShare(null);
      return;
    }
    try {
      setShare(await api.get(`/articles/${article.id}/share`));
    } catch (e) {
      setError(e.message);
    }
  }

  async function openRevisions() {
    if (revisions) {
      setRevisions(null);
      return;
    }
    try {
      const d = await api.get(`/articles/${article.id}/revisions`);
      setRevisions(d.revisions || []);
    } catch (e) {
      setError(e.message);
    }
  }

  async function download(kind) {
    setDownloading(kind);
    setError(null);
    try {
      await downloadFile(`/articles/${article.slug}/download.${kind}`, `${article.slug}.${kind}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setDownloading(null);
    }
  }

  async function copy(url) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Clipboard access is refused in some contexts; the input beside this
      // button still holds the URL for a manual copy.
      setError("Copy the link from the box instead.");
    }
  }

  return (
    <div className="article-extras">
      <div className="row gap-4">
        <Button variant="quiet" size="sm" onClick={openShare}>
          {share ? "Hide sharing" : "Share"}
        </Button>
        <Button variant="quiet" size="sm" onClick={openRevisions}>
          {revisions ? "Hide history" : "Revision history"}
        </Button>
        {!article.paywalled && (
          <>
            <Button variant="quiet" size="sm" busy={downloading === "pdf"}
              onClick={() => download("pdf")}>
              Download PDF
            </Button>
            <Button variant="quiet" size="sm" busy={downloading === "pptx"}
              onClick={() => download("pptx")}>
              Download slides
            </Button>
          </>
        )}
      </div>

      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}

      {share && (
        <div className="well mt-5">
          <p className="label">Link to this article</p>
          <div className="row gap-3 mt-3">
            <input
              className="input"
              readOnly
              value={share.url}
              aria-label="Article link"
              onFocus={(e) => e.target.select()}
            />
            <Button variant="outline" size="sm" onClick={() => copy(share.url)}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>

          {share.targets && Object.keys(share.targets).length > 0 && (
            <p className="row gap-4 mt-4">
              {Object.entries(share.targets).map(([name, url]) => (
                <a
                  className="link-quiet"
                  key={name}
                  href={url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {name}
                </a>
              ))}
            </p>
          )}
        </div>
      )}

      {revisions && (
        <div className="well mt-5">
          <p className="label">Revision history</p>
          {revisions.length === 0 ? (
            <p className="meta mt-3">
              This article has not been edited since publication.
            </p>
          ) : (
            <ol className="revision-list mt-4">
              {revisions.map((r) => (
                <li key={r.id}>
                  <p className="comment-body">{r.title}</p>
                  {r.changeNote && <p className="meta mt-1">{r.changeNote}</p>}
                  <p className="meta mt-1">{formatDate(r.createdAt)}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
