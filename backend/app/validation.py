"""Input coercion for JSON request bodies.

A JSON body is attacker-controlled and arbitrarily shaped: any field can arrive
as the wrong type, and Python will often do something plausible-looking with it
rather than fail. `",".join(x for x in "notalist")` does not raise; it quietly
produces "n,o,t,a,l,i,s,t". `float("nan")` succeeds, and `nan < 0` is False, so a
naive range check passes it straight through to the database.

Every helper here raises ApiError with the offending field named, so a bad body
becomes a 422 the client can render against a form input, never a 500.
"""
from __future__ import annotations

import math
from typing import Any

from .errors import ApiError

MISSING = object()


def require_str(
    data: dict, field: str, *, max_length: int | None = None,
    default: Any = MISSING, allow_empty: bool = False,
) -> str | None:
    raw = data.get(field, default)
    if raw is MISSING:
        raise ApiError(f"'{field}' is required.", status=422, field=field)
    if raw is None:
        if default is not MISSING:
            return None
        raise ApiError(f"'{field}' is required.", status=422, field=field)
    if not isinstance(raw, str):
        raise ApiError(f"'{field}' must be text.", status=422, field=field)

    value = raw.strip()
    if not value and not allow_empty:
        raise ApiError(f"'{field}' cannot be empty.", status=422, field=field)
    if max_length is not None and len(value) > max_length:
        raise ApiError(
            f"'{field}' must be {max_length} characters or fewer.", status=422, field=field
        )
    return value


def require_int(
    data: dict, field: str, *, default: Any = MISSING,
    minimum: int | None = None, maximum: int | None = None,
) -> int | None:
    raw = data.get(field, default)
    if raw is MISSING:
        raise ApiError(f"'{field}' is required.", status=422, field=field)
    if raw is None and default is not MISSING:
        return None

    # bool is a subclass of int; True would silently become 1.
    if isinstance(raw, bool) or not isinstance(raw, (int, str, float)):
        raise ApiError(f"'{field}' must be a whole number.", status=422, field=field)

    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError(f"'{field}' must be a whole number.", status=422, field=field) from None

    if minimum is not None and value < minimum:
        raise ApiError(f"'{field}' must be at least {minimum}.", status=422, field=field)
    if maximum is not None and value > maximum:
        raise ApiError(f"'{field}' must be at most {maximum}.", status=422, field=field)
    return value


def require_number(
    data: dict, field: str, *, minimum: float | None = None, maximum: float | None = None,
) -> float:
    """A finite float.

    NaN and infinity are rejected explicitly. Both survive a naive `< 0` check
    (every comparison against NaN is False), and Postgres accepts both as valid
    double precision values, so without this they would be stored, and every
    calculation downstream would silently produce nonsense.
    """
    raw = data.get(field, MISSING)
    if raw is MISSING or raw is None:
        raise ApiError(f"'{field}' is required.", status=422, field=field)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ApiError(f"'{field}' must be a number.", status=422, field=field)

    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ApiError(f"'{field}' must be a number.", status=422, field=field) from None

    if not math.isfinite(value):
        raise ApiError(
            f"'{field}' must be a finite number.", status=422, field=field
        )
    if minimum is not None and value < minimum:
        raise ApiError(f"'{field}' must be at least {minimum}.", status=422, field=field)
    if maximum is not None and value > maximum:
        raise ApiError(f"'{field}' must be at most {maximum}.", status=422, field=field)
    return value


def require_list(
    data: dict, field: str, *, default: Any = MISSING, max_items: int = 100,
) -> list:
    """A JSON array.

    Strings are rejected rather than accepted-and-iterated: a string is iterable,
    so passing one where a list belongs yields a list of characters instead of an
    error.
    """
    raw = data.get(field, default)
    if raw is MISSING:
        raise ApiError(f"'{field}' is required.", status=422, field=field)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ApiError(f"'{field}' must be a list.", status=422, field=field)
    if len(raw) > max_items:
        raise ApiError(
            f"'{field}' is limited to {max_items} items.", status=422, field=field
        )
    return raw


def require_id_list(data: dict, field: str, *, max_items: int = 100) -> list[int]:
    """A list of integer ids, with non-integer entries rejected rather than dropped."""
    values = require_list(data, field, default=None, max_items=max_items)

    ids: list[int] = []
    for entry in values:
        if isinstance(entry, bool) or not isinstance(entry, (int, str)):
            raise ApiError(f"'{field}' must contain only ids.", status=422, field=field)
        try:
            ids.append(int(entry))
        except (TypeError, ValueError):
            raise ApiError(
                f"'{field}' must contain only ids.", status=422, field=field
            ) from None
    return ids


def require_choice(data: dict, field: str, choices) -> str:
    allowed = list(choices)
    raw = data.get(field)
    if raw not in allowed:
        readable = ", ".join(f"'{c}'" for c in allowed)
        raise ApiError(f"'{field}' must be one of {readable}.", status=422, field=field)
    return raw


def require_bool(data: dict, field: str, *, default: bool = False) -> bool:
    raw = data.get(field, default)
    if isinstance(raw, bool):
        return raw
    raise ApiError(f"'{field}' must be true or false.", status=422, field=field)


def json_body() -> dict:
    """The request body as a dict.

    A body that is absent, malformed, or a JSON array rather than an object all
    become the same clear 400 instead of an AttributeError deeper in the handler.
    """
    from flask import request

    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.", status=400)
    return payload
