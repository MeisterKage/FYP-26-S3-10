/**
 * The notification bell and its panel (PDD Figure 5.21).
 *
 * Notifications are written to the database by whichever module triggers them,
 * so the bell is always accurate even when email delivery has not run yet.
 *
 * The unread count is polled rather than pushed. A websocket would be the right
 * answer for a live product; on a free tier with one worker it would cost a held
 * connection per reader for a number that changes a few times an hour.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import { BellIcon } from "./Icon";
import { formatDate } from "./UI";

const POLL_MS = 60000;

export default function Notifications() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const wrapRef = useRef(null);

  const load = useCallback(() => {
    api
      .get("/notifications")
      // A failed poll is not worth interrupting the page for; the bell simply
      // keeps its last known count.
      .then(setData)
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  // Close on an outside click or Escape, the two things a reader will try.
  useEffect(() => {
    if (!open) return;

    function onPointer(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unread = data?.unreadCount ?? 0;
  const items = data?.notifications ?? [];

  async function openItem(item) {
    setOpen(false);
    if (!item.read) {
      try {
        await api.post(`/notifications/${item.id}/read`);
        load();
      } catch {
        /* Following the link matters more than recording the read. */
      }
    }
    if (item.link) navigate(item.link);
  }

  async function markAll() {
    try {
      await api.post("/notifications/read-all");
      load();
    } catch {
      /* ignored: the next poll will show the true state */
    }
  }

  return (
    <div className="bell-wrap" ref={wrapRef}>
      <button
        type="button"
        className="bell"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        onClick={() => setOpen((v) => !v)}
      >
        <BellIcon size={18} />
        {/* The count is the accessible label too, so the dot is decorative and
            an unread state is never signalled by a coloured dot alone. */}
        {unread > 0 && (
          <span className="bell-count" aria-hidden="true">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="bell-panel" role="dialog" aria-label="Notifications">
          <div className="bell-head">
            <p className="label">Notifications</p>
            {unread > 0 && (
              <button type="button" className="link-button" onClick={markAll}>
                Mark all read
              </button>
            )}
          </div>

          {items.length === 0 ? (
            <p className="meta bell-empty">Nothing yet.</p>
          ) : (
            <ul className="bell-list">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="bell-item"
                    data-unread={!item.read || undefined}
                    onClick={() => openItem(item)}
                  >
                    <span className="bell-item-title">{item.title}</span>
                    {item.body && <span className="bell-item-body">{item.body}</span>}
                    <span className="meta">{formatDate(item.createdAt)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
