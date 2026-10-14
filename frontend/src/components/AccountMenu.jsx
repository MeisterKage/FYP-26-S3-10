/**
 * The signed-in reader's menu: one compact button that stays in the masthead
 * at every width.
 *
 * The name used to be a nav link that was hidden whenever the window narrowed,
 * because the administrator's nav ran out of room, which left no visible way
 * to the account page. Now an initial is always shown, the name beside it only
 * when there is space, and Account, the reading list, liked articles and Sign
 * out live in the menu it opens.
 *
 * A disclosure menu: Escape or a click outside closes it, and following a link
 * closes it. The panel is placed against the window, under its button, because
 * on narrower screens the nav scrolls sideways and would clip anything inside it.
 */
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth";
import { useI18n } from "../i18n";

export function AccountMenu() {
  const { user, signOut } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState(null);
  const root = useRef(null);
  const button = useRef(null);

  useEffect(() => setOpen(false), [location.pathname, location.search]);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    }
    function onClick(event) {
      if (!root.current?.contains(event.target)) setOpen(false);
    }
    function onResize() {
      setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  if (!user) return null;
  const initial = (user.displayName || user.email || "?").trim().charAt(0).toUpperCase();

  return (
    <div className="account-menu" ref={root}>
      <button
        ref={button}
        type="button"
        className="account-trigger"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="account-menu-panel"
        onClick={() => {
          const box = button.current.getBoundingClientRect();
          setPlace({
            top: box.bottom + 8,
            right: Math.max(16, document.documentElement.clientWidth - box.right),
          });
          setOpen((o) => !o);
        }}
      >
        <span className="account-initial" aria-hidden="true">{initial}</span>
        <span className="account-name">{user.displayName}</span>
        <span className="sr-only">{t("account.menu")}</span>
      </button>

      {open && (
        <div className="account-panel" id="account-menu-panel" style={place || undefined}>
          <div className="account-who">
            <p className="account-who-name">{user.displayName}</p>
            <p className="account-who-email">{user.email}</p>
          </div>
          <ul className="account-links">
            <li><Link to="/account">{t("account.yourAccount")}</Link></li>
            <li><Link to="/account?tab=reading">{t("account.readingList")}</Link></li>
            <li><Link to="/account?tab=liked">{t("account.liked")}</Link></li>
            <li><Link to="/account?tab=subs">{t("account.subscriptions")}</Link></li>
          </ul>
          <button
            type="button"
            className="account-signout"
            onClick={async () => {
              setOpen(false);
              await signOut();
              navigate("/");
            }}
          >
            {t("account.signOut")}
          </button>
        </div>
      )}
    </div>
  );
}
