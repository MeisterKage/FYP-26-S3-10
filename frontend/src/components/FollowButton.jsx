/**
 * Follow a section or a country: its articles join your front page.
 *
 * Open to every registered account. Signed out, it offers to sign in and comes
 * back to the same page afterwards.
 */
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { Button } from "./UI";

export function FollowButton({ kind, id, name }) {
  const { user, refresh } = useAuth();
  const { t } = useI18n();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (id == null) return null;

  if (!user) {
    return (
      <Link className="btn btn-outline btn-sm follow-btn" to="/login" state={{ from: location.pathname }}>
        {t("follow.signIn")}
      </Link>
    );
  }

  const following = kind === "country"
    ? (user.countryCodes || []).includes(String(id).toUpperCase())
    : (user.categoryIds || []).includes(id);
  const path = kind === "country"
    ? `/me/interests/countries/${String(id).toLowerCase()}`
    : `/me/interests/categories/${id}`;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      if (following) await api.del(path);
      else await api.put(path);
      await refresh?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="follow">
      <Button
        variant={following ? "outline" : "primary"}
        size="sm"
        busy={busy}
        aria-pressed={following}
        onClick={toggle}
        className="follow-btn"
        aria-label={following ? t("follow.unfollowName", { name }) : t("follow.followName", { name })}
      >
        {following ? t("follow.following") : t("follow.follow")}
      </Button>
      {error && <span className="follow-error" role="alert">{error}</span>}
    </span>
  );
}
