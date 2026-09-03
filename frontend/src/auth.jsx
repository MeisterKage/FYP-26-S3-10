/**
 * Session state, shared across the four role-specific views (PDD Section 2.2).
 *
 * The role here drives navigation only. It is never the authority on what a user
 * may do, because Flask decides that on every request (PDD Section 3). Hiding a
 * button is a courtesy; the server is the control.
 */
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);

export const ROLES = {
  FREE: "free_registered",
  PREMIUM: "premium_registered",
  CONTRIBUTOR: "verified_contributor",
  EDITOR: "editor",
  ADMIN: "system_admin",
};

export const CAN_AUTHOR = [ROLES.CONTRIBUTOR, ROLES.EDITOR, ROLES.ADMIN];
export const CAN_REVIEW = [ROLES.EDITOR, ROLES.ADMIN];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((data) => setUser(data.user))
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      async signIn(email, password) {
        const data = await api.login(email, password);
        setToken(data.token);
        setUser(data.user);
        return data.user;
      },
      async register(payload) {
        const data = await api.register(payload);
        setToken(data.token);
        setUser(data.user);
        return data.user;
      },
      signOut() {
        setToken(null);
        setUser(null);
      },
      has(...roles) {
        return Boolean(user) && roles.includes(user.role);
      },
    }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider");
  return context;
}
