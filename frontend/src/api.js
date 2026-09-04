/**
 * The single place the client talks to Flask.
 *
 * Every response the API can fail with has the same shape
 * ({ error: { message, field? } }), so error handling lives here once rather
 * than in every component.
 */

const BASE = import.meta.env.VITE_API_BASE || "";

const TOKEN_KEY = "nrs.token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private browsing -- the session simply does not persist */
  }
}

export class ApiError extends Error {
  constructor(message, status, field) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${BASE}/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const error = payload?.error ?? {};
    // An expired or revoked session should not leave a dead token behind.
    if (response.status === 401) setToken(null);
    throw new ApiError(error.message || "Something went wrong.", response.status, error.field);
  }

  return payload;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  // DELETE carries a body in one place: removing an account also decides what
  // happens to that account's published articles.
  del: (path, body) => request(path, { method: "DELETE", body }),

  // Auth is the one group that must work without a token.
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  register: (payload) =>
    request("/auth/register", { method: "POST", body: payload, auth: false }),
};
