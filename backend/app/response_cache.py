"""A short-lived memory of public pages, for visitors who are not signed in.

The database is on another continent from the API server, so every query is a
long round trip. Most traffic is signed-out readers asking for the same few
lists, so the answer to a public GET is kept for a minute and served from
memory to the next signed-out visitor who asks for the same address.

Anything changed through the API clears it at once: every successful POST,
PUT, PATCH or DELETE empties the whole cache before its response goes out, so
a writer who publishes, an editor who approves or a reader who comments sees
the change on their next page. Only changes made outside the API (the command
line tools) can take up to a minute to show.

Signed-in requests are never served from or stored in the cache: their pages
carry per-person details (following, subscribed, saved).

The API runs as a single process (gunicorn --workers 1), so one in-memory cache is
shared by every request. Several processes would each keep their own, still
correct but less effective.
"""
from __future__ import annotations

import copy
import threading
import time

from flask import Flask, Response, current_app, request

#: Public list pages whose answer is the same for every signed-out visitor.
CACHEABLE = frozenset({
    "discovery.list_categories",
    "discovery.trending",
    "discovery.personalised",   # a signed-out visitor gets trending
    "discovery.by_category",
    "discovery.list_countries",
    "discovery.all_countries",
    "discovery.by_country",
    "discovery.search",
    "discovery.scoring_formula",
    "discovery.contributor_profile",
    "editors.editor_panel",
    "editors.editor_profile",
    "digests.archive",
    "digests.edition",
})
MAX_ENTRIES = 500
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_store: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _ttl() -> float:
    return float(current_app.config.get("RESPONSE_CACHE_SECONDS", 60))


def clear() -> None:
    with _lock:
        _store.clear()


def get(key: str):
    if _ttl() <= 0:
        return None
    with _lock:
        hit = _store.get(key)
        if hit is None:
            return None
        expires, value = hit
        if expires < time.monotonic():
            del _store[key]
            return None
        return value


def put(key: str, value) -> None:
    if _ttl() <= 0:
        return
    with _lock:
        if len(_store) >= MAX_ENTRIES:
            # Drop the entry closest to expiring; simple and good enough here.
            del _store[min(_store, key=lambda k: _store[k][0])]
        _store[key] = (time.monotonic() + _ttl(), value)


def signed_out() -> bool:
    return "Authorization" not in request.headers


def _eligible() -> bool:
    return request.method == "GET" and request.endpoint in CACHEABLE and signed_out()


def register_response_cache(app: Flask) -> None:
    @app.before_request
    def _serve_from_cache():
        if not _eligible():
            return None
        hit = get(f"page:{request.full_path}")
        if hit is None:
            return None
        body, mimetype = hit
        request.environ["response_cache.hit"] = True
        response = Response(body, status=200, mimetype=mimetype)
        response.headers["X-Cache"] = "HIT"
        return response

    @app.after_request
    def _store_or_clear(response):
        if request.method in WRITES and response.status_code < 400:
            clear()
        elif (_eligible() and not request.environ.get("response_cache.hit")
              and response.status_code == 200):
            put(f"page:{request.full_path}", (response.get_data(), response.mimetype))
            response.headers["X-Cache"] = "MISS"
        return response


def cached_copy(key: str):
    """A private copy of a cached value, safe for the caller to modify."""
    value = get(key)
    return copy.deepcopy(value) if value is not None else None
