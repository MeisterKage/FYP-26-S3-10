/**
 * A writer's public page (PDD Figures 5.22, 5.23).
 *
 * The Accuracy Rate leads, because it is the number that feeds every article
 * below it. A writer below the minimum article count reads "New contributor"
 * and shows no figure at all: a withheld rate is not a zero, and rendering it
 * as one would say the opposite of what it means.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import { EntryThumb } from "../components/CoverImage";
import { useAuth } from "../auth";
import { AccuracyRate, CredibilityInline } from "../components/Credibility";
import { Button, Empty, Notice, SectionHead, formatDate } from "../components/UI";
import { startSubscription } from "./Checkout";
import { usePageTitle } from "../usePageTitle";

export default function ContributorProfile() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  usePageTitle(data?.contributor?.name);
  const [notice, setNotice] = useState(null);
  const [following, setFollowing] = useState(false);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    api
      .get(`/contributors/${id}`)
      .then((d) => {
        setData(d);
        setFollowing(Boolean(d.contributor.isFollowedByViewer));
      })
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);

  async function toggleFollow() {
    const next = !following;
    setFollowing(next);
    setBusy("follow");
    try {
      const result = next
        ? await api.post(`/contributors/${id}/follow`)
        : await api.del(`/contributors/${id}/follow`);
      setFollowing(Boolean(result?.following));
      load();
    } catch (e) {
      setFollowing(!next);
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function subscribe() {
    setBusy("subscribe");
    setError(null);
    try {
      // Goes to checkout. Access starts when the payment is confirmed.
      await startSubscription(id, navigate);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  if (error && !data) return <Notice>{error}</Notice>;
  if (!data) return <div className="skeleton" style={{ height: "18rem" }} />;

  const c = data.contributor;
  const isSelf = user?.id === c.id;

  return (
    <div className="wide">
      <header className="dash-head">
        <div>
          <h1 className="title">{c.name}</h1>
          <p className="entry-meta mt-4">
            <AccuracyRate rate={c.accuracyRate} />
            <span className="dot" aria-hidden="true" />
            <span>
              {c.followerCount} follower{c.followerCount === 1 ? "" : "s"}
            </span>
            <span className="dot" aria-hidden="true" />
            <span>
              {data.articles.length} article{data.articles.length === 1 ? "" : "s"}
            </span>
          </p>
          {c.bio && <p className="lead mt-5">{c.bio}</p>}
        </div>

        {user && !isSelf && (
          <div className="row gap-4">
            <Button
              variant={following ? "outline" : "quiet"}
              busy={busy === "follow"}
              onClick={toggleFollow}
            >
              {following ? "Following" : "Follow"}
            </Button>
            <Button variant="primary" busy={busy === "subscribe"} onClick={subscribe}>
              Subscribe
            </Button>
          </div>
        )}
      </header>

      {c.isNewContributor && (
        <div className="mt-6">
          <Notice tone="quiet">
            This writer has not yet published enough articles for an accuracy rate.
            That is a missing figure, not a low one.
          </Notice>
        </div>
      )}

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
        <SectionHead title="Published" />
        {data.articles.length === 0 ? (
          <Empty title="Nothing published yet">
            Articles appear here once an editor approves them.
          </Empty>
        ) : (
          <div className="index">
            {data.articles.map((a) => (
              <article className={`entry${a.coverImage ? " entry--media" : ""}`} key={a.id}>
                <EntryThumb image={a.coverImage} />
                <div className="entry-main">
                  <h3 className="entry-title">
                    <Link className="link-quiet" to={`/articles/${a.slug}`}>
                      {a.title}
                    </Link>
                  </h3>
                  {a.summary && <p className="entry-summary mt-2">{a.summary}</p>}
                  <p className="entry-meta mt-3">
                    <span>{formatDate(a.publishedAt)}</span>
                    {a.isPremium && (
                      <>
                        <span className="dot" aria-hidden="true" />
                        <span className="tag">Subscriber</span>
                      </>
                    )}
                  </p>
                </div>
                <div className="entry-aside">
                  <CredibilityInline credibility={a.credibility} review={a.review} />
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
