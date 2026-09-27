/**
 * The writer card at the end of an article.
 *
 * A reader who has just finished an article they liked is exactly the reader
 * who might follow or subscribe, and asking them to find the profile first
 * loses most of them. So both actions sit here, beside who the writer is and
 * how accurate their record is.
 *
 * Following is free and fills the reader's feed. Subscribing is paid, opens
 * the writer's subscriber-only articles, and goes through checkout.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { startSubscription } from "../pages/Checkout";
import { AccuracyRate } from "./Credibility";
import { Button, Notice } from "./UI";

export function WriterCard({ writer }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [following, setFollowing] = useState(writer.following);
  const [followers, setFollowers] = useState(writer.followerCount);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  if (writer.isSelf) return null;

  async function toggleFollow() {
    const next = !following;
    setBusy("follow");
    setError(null);
    setFollowing(next);
    setFollowers((n) => n + (next ? 1 : -1));
    try {
      if (next) await api.post(`/contributors/${writer.id}/follow`);
      else await api.del(`/contributors/${writer.id}/follow`);
    } catch (e) {
      setFollowing(!next);
      setFollowers((n) => n + (next ? -1 : 1));
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function subscribe() {
    setBusy("subscribe");
    setError(null);
    try {
      await startSubscription(writer.id, navigate);
    } catch (e) {
      setError(e.message);
      setBusy(null);
    }
  }

  return (
    <aside className="writer-card" aria-label={`About ${writer.name}`}>
      <p className="label">About the writer</p>
      <div className="writer-card-main">
        <div className="writer-card-who">
          <Link className="writer-card-name link-quiet" to={`/contributors/${writer.id}`}>
            {writer.name}
          </Link>
          <p className="writer-card-meta">
            <AccuracyRate rate={writer.accuracyRate} />
            <span className="dot" aria-hidden="true" />
            <span>{followers} follower{followers === 1 ? "" : "s"}</span>
          </p>
          {writer.bio && <p className="writer-card-bio">{writer.bio}</p>}
        </div>

        <div className="writer-card-actions">
          {!user ? (
            <>
              <Button variant="primary" size="sm" as={Link} to="/register">
                Subscribe
              </Button>
              <p className="writer-card-note">
                <Link className="link-quiet" to="/login">Sign in</Link> or create a free
                account to follow or subscribe.
              </p>
            </>
          ) : (
            <>
              {writer.offersSubscription && (
                writer.subscribed ? (
                  <Button variant="outline" size="sm" as={Link} to="/account">
                    Subscribed
                  </Button>
                ) : (
                  <Button variant="primary" size="sm" busy={busy === "subscribe"}
                    onClick={subscribe}>
                    Subscribe
                  </Button>
                )
              )}
              <Button variant={following ? "outline" : "quiet"} size="sm"
                busy={busy === "follow"} onClick={toggleFollow} aria-pressed={following}>
                {following ? "Following" : "Follow"}
              </Button>
            </>
          )}
        </div>
      </div>
      {error && <div className="mt-4"><Notice>{error}</Notice></div>}
    </aside>
  );
}
