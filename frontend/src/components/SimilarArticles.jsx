/**
 * "More like this": the published articles closest in subject, after the
 * article. Chosen by the words the articles share (see backend app/similar.py),
 * with a small preference for the same section and country.
 */
import { Link } from "react-router-dom";

import { imageUrl } from "../api";
import { CredibilityInline } from "./Credibility";

export function SimilarArticles({ articles }) {
  if (!articles?.length) return null;
  return (
    <section className="similar" aria-labelledby="similar-title">
      <h2 className="heading" id="similar-title">More like this</h2>
      <ul className="similar-grid">
        {articles.map((a) => (
          <li key={a.id}>
            <Link className="similar-card" to={`/articles/${a.slug}`}>
              {a.coverImage ? (
                <img className="similar-thumb" src={imageUrl(a.coverImage.thumbUrl)} alt=""
                  width={640} height={Math.round((640 * a.coverImage.height) / a.coverImage.width)}
                  loading="lazy" decoding="async" />
              ) : (
                <span className="similar-thumb similar-thumb--empty" aria-hidden="true" />
              )}
              <span className="similar-meta">
                {a.country?.name ? `${a.country.name} · ` : ""}{a.contributor.name}
              </span>
              <span className="similar-title">{a.title}</span>
            </Link>
            <div className="similar-score">
              <CredibilityInline credibility={a.credibility} review={a.review} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
