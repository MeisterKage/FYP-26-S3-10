/**
 * The editor panel, and one editor's public record.
 *
 * A credibility score says an article is well sourced and its writer accurate.
 * This says who read it before it went out. Every editor's record includes how
 * many of their corrections were overturned on appeal: an editor panel that
 * only lists achievements would be marketing, not accountability.
 *
 * Titles and credentials are set by an administrator, never by the editor.
 * Rejected drafts are never shown, only counted: they are the writer's work.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import { CredibilityInline } from "../components/Credibility";
import { ArticleEntry, Empty, EntrySkeleton, Notice, SectionHead, formatDate } from "../components/UI";
import { usePageTitle } from "../usePageTitle";

/** The figure that answers "who checks the checkers". Withheld with nothing to measure. */
function UpheldRate({ record }) {
  if (record.correctionsUpheldRate == null) return "No corrections yet";
  return `${record.correctionsUpheldRate}% of corrections upheld`;
}

function Sections({ sections }) {
  if (!sections.length) return null;
  return (
    <span className="editor-sections">
      {sections.map((s) => (
        <Link className="tag" key={s.id} to={`/categories/${s.slug}`}>
          {s.name}
        </Link>
      ))}
    </span>
  );
}

export function EditorPanel() {
  const [editors, setEditors] = useState(null);
  usePageTitle("Our editors");
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/editors")
      .then((d) => setEditors(d.editors))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="wide">
      <header className="read">
        <h1 className="display">The editors</h1>
        <p className="lead mt-6">
          Every article here was read by one of these people before it went out,
          and each one carries the name of the editor who approved it. Their
          records are public too, including how often a correction they issued
          was overturned on appeal.
        </p>
      </header>

      <section className="section mt-8">
        {error && <Notice>{error}</Notice>}
        {!editors && !error && <EntrySkeleton rows={2} />}
        {editors?.length === 0 && (
          <Empty title="No editors yet">The panel appears once editors are appointed.</Empty>
        )}
        {editors?.length > 0 && (
          <div className="index">
            {editors.map((e) => (
              <article className="entry editor-entry" key={e.id}>
                <div className="entry-main">
                  <h2 className="entry-title">
                    <Link className="link-quiet" to={`/editors/${e.id}`}>
                      {e.name}
                    </Link>
                  </h2>
                  {e.title && <p className="editor-title">{e.title}</p>}
                  {e.credentials && <p className="entry-summary mt-2">{e.credentials}</p>}
                  <p className="entry-meta mt-3">
                    <Sections sections={e.sections} />
                  </p>
                </div>
                <dl className="editor-record">
                  <div>
                    <dt className="label">Approved</dt>
                    <dd className="editor-figure">{e.record.articlesApproved}</dd>
                  </div>
                  <div>
                    <dt className="label">Corrections</dt>
                    <dd className="editor-figure">{e.record.correctionsIssued}</dd>
                  </div>
                  <div>
                    <dt className="label">Overturned</dt>
                    <dd className="editor-figure">{e.record.correctionsOverturned}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export function EditorProfile() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  usePageTitle(data?.editor?.name);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api
      .get(`/editors/${id}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <Empty
        level={1}
        title="This editor isn't on the panel"
        action={
          <Link className="link-quiet mt-4" to="/editors">
            See all editors
          </Link>
        }
      >
        {error}
      </Empty>
    );
  }
  if (!data) return <div className="skeleton" style={{ height: "18rem" }} />;

  const e = data.editor;
  const r = e.record;

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <p className="label">
            <Link className="link-quiet" to="/editors">
              The editors
            </Link>
          </p>
          <h1 className="title mt-3">{e.name}</h1>
          <p className="entry-meta mt-4">
            {e.title && <span>{e.title}</span>}
            {e.title && e.since && <span className="dot" aria-hidden="true" />}
            {e.since && <span>On the platform since {formatDate(e.since)}</span>}
          </p>
          {e.credentials && <p className="lead mt-5">{e.credentials}</p>}
          {e.sections.length > 0 && (
            <p className="entry-meta mt-4">
              <span>Reviews</span>
              <Sections sections={e.sections} />
            </p>
          )}
        </div>
      </header>

      <section className="section mt-7">
        <SectionHead title="Record" />
        <div className="stat-grid">
          <div className="stat">
            <p className="label">Articles approved</p>
            <p className="stat-figure">{r.articlesApproved}</p>
          </div>
          <div className="stat">
            <p className="label">Returned to the writer</p>
            <p className="stat-figure">{r.articlesReturned}</p>
          </div>
          <div className="stat">
            <p className="label">Corrections issued</p>
            <p className="stat-figure">{r.correctionsIssued}</p>
          </div>
          <div className="stat">
            <p className="label">Overturned on appeal</p>
            <p className="stat-figure">{r.correctionsOverturned}</p>
          </div>
        </div>
        <p className="meta mt-4">
          <UpheldRate record={r} />. An overturned correction is one an
          administrator reversed after review, usually on the writer&rsquo;s
          appeal. Returned articles are counted, never shown: they are the
          writer&rsquo;s unpublished work.
        </p>
      </section>

      <section className="section mt-7">
        <SectionHead title="Recently approved" />
        {data.articles.length === 0 ? (
          <Empty title="Nothing approved yet">
            Articles appear here once this editor approves them.
          </Empty>
        ) : (
          <div className="index">
            {data.articles.map((a) => (
              <ArticleEntry
                key={a.id}
                article={a}
                aside={<CredibilityInline credibility={a.credibility} review={a.review} />}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
