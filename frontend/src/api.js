/**
 * The single place the client talks to Flask.
 *
 * Every response the API can fail with has the same shape
 * ({ error: { message, field? } }), so error handling lives here once rather
 * than in every component.
 */

const BASE = import.meta.env.VITE_API_BASE || "";

const TOKEN_KEY = "nrs.token";

// The reader's language (see i18n.jsx), sent with every read so lists and
// articles come back translated where a translation exists.
let lang = "en";
export function setApiLang(next) {
  lang = next;
}
function withLang(path) {
  if (lang === "en") return path;
  return `${path}${path.includes("?") ? "&" : "?"}lang=${lang}`;
}

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

/** Absolute URL for an image path the API returned, e.g. "/images/<key>.webp". */
export function imageUrl(path) {
  return path ? `${BASE}/api${path}` : null;
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
  // A file upload is FormData, and the browser must set its own Content-Type
  // (it carries the multipart boundary). Everything else is JSON.
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${BASE}/api${method === "GET" ? withLang(path) : path}`, {
    method,
    headers,
    body: body === undefined || isForm ? body : JSON.stringify(body),
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

/**
 * Fetch a file the API builds (an article as PDF or slides) and hand it to the
 * browser to save. Sent with the reader's sign-in, so a subscriber can download
 * a subscriber-only article.
 */
export async function downloadFile(path, filename) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BASE}/api${withLang(path)}`, { headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(payload?.error?.message || "The download failed.", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  // DELETE carries a body in one place: removing an account also decides what
  // happens to that account's published articles.
  del: (path, body) => request(path, { method: "DELETE", body }),

  /** Upload one image file. Resolves to { key, url, thumbUrl, width, height }. */
  uploadImage: (file) => {
    const form = new FormData();
    form.append("file", file);
    // The writer has confirmed the image is not AI-generated (see CoverImage).
    form.append("declaration", "not-ai");
    return request("/images", { method: "POST", body: form }).then((d) => d.image);
  },

  // Auth is the one group that must work without a token.
  login: (email, password) =>
    request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  register: (payload) =>
    request("/auth/register", { method: "POST", body: payload, auth: false }),
};
