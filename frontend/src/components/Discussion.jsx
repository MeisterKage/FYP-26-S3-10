/**
 * Reader engagement on an article: like, save, and the comment thread
 * (PDD Figures 5.29, 5.30, 5.31, 5.34).
 *
 * Replies are one level deep because the server refuses to nest further. The
 * form enforces the same rule so a reader never composes something the API will
 * then reject.
 *
 * Like and save are optimistic: the count moves immediately and rolls back if
 * the request fails. A counter that waits for a round trip reads as a dead
 * button, and this is the one interaction a reader repeats.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { Button, Notice, formatDate } from "./UI";

function Comment({ comment, replies, onReply, onDelete, canReplyTo, user }) {
  const mine = user && comment.author.id === user.id;

  return (
    <li className="comment">
      <p className="comment-head">
        <span className="comment-author">{comment.author.name}</span>
        <span className="dot" aria-hidden="true" />
        <span className="meta">{formatDate(comment.createdAt)}</span>
      </p>
      <p className="comment-body mt-2">{comment.body}</p>

      <div className="row gap-4 mt-3">
        {canReplyTo && (
          <Button variant="quiet" size="sm" onClick={() => onReply(comment)}>
            Reply
          </Button>
        )}
        {mine && (
          <Button variant="quiet" size="sm" onClick={() => onDelete(comment)}>
            Delete
          </Button>
        )}
      </div>

      {replies.length > 0 && (
        <ul className="comment-replies">
          {replies.map((reply) => (
            <Comment
              key={reply.id}
              comment={reply}
              replies={[]}
              onReply={onReply}
              onDelete={onDelete}
              canReplyTo={false}
              user={user}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function Discussion({ article }) {
  const { user } = useAuth();

  const [liked, setLiked] = useState(Boolean(article.viewer?.liked));
  const [likeCount, setLikeCount] = useState(article.likeCount ?? 0);
  const [saved, setSaved] = useState(Boolean(article.viewer?.saved));

  const [comments, setComments] = useState(null);
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api
      .get(`/articles/${article.id}/comments`)
      .then((d) => setComments(d.comments || []))
      .catch((e) => setError(e.message));
  }, [article.id]);

  useEffect(load, [load]);

  async function toggleLike() {
    const next = !liked;
    setLiked(next);
    setLikeCount((c) => c + (next ? 1 : -1));
    try {
      const result = next
        ? await api.post(`/articles/${article.id}/like`)
        : await api.del(`/articles/${article.id}/like`);
      // The server is the authority on the count; adopt whatever it returns.
      if (typeof result?.likeCount === "number") setLikeCount(result.likeCount);
      setLiked(Boolean(result?.liked));
    } catch (e) {
      setLiked(!next);
      setLikeCount((c) => c + (next ? -1 : 1));
      setError(e.message);
    }
  }

  async function toggleSave() {
    const next = !saved;
    setSaved(next);
    try {
      const result = next
        ? await api.post(`/articles/${article.id}/save`)
        : await api.del(`/articles/${article.id}/save`);
      setSaved(Boolean(result?.saved));
    } catch (e) {
      setSaved(!next);
      setError(e.message);
    }
  }

  async function post(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/articles/${article.id}/comments`, {
        body,
        parentId: replyTo?.id ?? null,
      });
      setBody("");
      setReplyTo(null);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(comment) {
    if (!window.confirm("Delete this comment?")) return;
    try {
      await api.del(`/comments/${comment.id}`);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const roots = (comments || []).filter((c) => c.parentId == null);
  const repliesFor = (id) => (comments || []).filter((c) => c.parentId === id);

  return (
    <section className="discussion">
      <div className="engagement">
        {user ? (
          <>
            <Button variant={liked ? "outline" : "quiet"} size="sm" onClick={toggleLike}>
              {liked ? "Liked" : "Like"}
              <span className="tabular"> {likeCount}</span>
            </Button>
            <Button variant={saved ? "outline" : "quiet"} size="sm" onClick={toggleSave}>
              {saved ? "Saved to reading list" : "Save for later"}
            </Button>
          </>
        ) : (
          <p className="meta">
            <Link className="link-quiet" to="/login">
              Sign in
            </Link>{" "}
            to like, save, or join the discussion.
          </p>
        )}
      </div>

      <h2 className="sub mt-7">
        Discussion
        {comments && (
          <span className="meta"> · {comments.length}</span>
        )}
      </h2>

      {error && (
        <div className="mt-4">
          <Notice>{error}</Notice>
        </div>
      )}

      {user && (
        <form className="comment-form mt-5" onSubmit={post}>
          {replyTo && (
            <p className="field-hint">
              Replying to {replyTo.author.name}.{" "}
              <button type="button" className="link-button" onClick={() => setReplyTo(null)}>
                Cancel
              </button>
            </p>
          )}
          <label className="sr-only" htmlFor="comment-body">
            Your comment
          </label>
          <textarea
            id="comment-body"
            className="textarea"
            rows={3}
            maxLength={5000}
            placeholder={replyTo ? "Write a reply" : "Add to the discussion"}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
          />
          <div className="row gap-4 mt-3">
            <Button variant="primary" size="sm" type="submit" busy={busy} disabled={!body.trim()}>
              {replyTo ? "Post reply" : "Post comment"}
            </Button>
          </div>
        </form>
      )}

      {!comments && <div className="skeleton mt-5" style={{ height: "8rem" }} />}

      {comments && roots.length === 0 && (
        <p className="meta mt-5">No comments yet.</p>
      )}

      {comments && roots.length > 0 && (
        <ul className="comment-list mt-6">
          {roots.map((c) => (
            <Comment
              key={c.id}
              comment={c}
              replies={repliesFor(c.id)}
              onReply={setReplyTo}
              onDelete={remove}
              canReplyTo={Boolean(user)}
              user={user}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
