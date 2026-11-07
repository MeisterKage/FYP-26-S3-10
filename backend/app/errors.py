"""Uniform error shape and last-resort failure handling.

Every failure the client can see is JSON in exactly one shape, so the React layer
has a single error contract to render against:

    {"error": {"message": "...", "field": "password"}}

That includes failures Flask raises on our behalf. Without the HTTPException
handler below, a wrong HTTP method returns an HTML error page, and `response
.json()` in the client throws a parse error that reaches the user as
"Unexpected token '<'" rather than anything actionable.

Three things are guaranteed here:

  1. No response is ever HTML.
  2. No internal detail (exception text, SQL, stack trace) reaches a client.
  3. No failed request leaves a dirty session behind for the next one.
"""
from __future__ import annotations

import logging

from flask import jsonify
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    """A failure that is safe, and intended, to show the user."""

    def __init__(self, message: str, status: int = 400, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field

    def to_response(self):
        return _payload(self.message, self.status, self.field)


def _payload(message: str, status: int, field: str | None = None):
    body = {"error": {"message": message}}
    if field:
        body["error"]["field"] = field
    return jsonify(body), status


#: Generic text for Flask's own HTTP errors. Werkzeug's default descriptions leak
#: routing detail ("The method is not allowed for the requested URL"), which tells
#: a prober which endpoints exist.
HTTP_MESSAGES = {
    400: "The request could not be understood.",
    401: "Sign in to continue.",
    403: "You do not have permission for this action.",
    404: "Not found.",
    405: "That action is not supported on this resource.",
    409: "That conflicts with the current state.",
    413: "The uploaded content is too large.",
    415: "Send this request as JSON.",
    422: "Some of the submitted values are not valid.",
    429: "Too many requests. Please wait and try again.",
}


def register_error_handlers(app):
    from .extensions import db

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        #An ApiError can be raised after rows were staged but before commit.
        #Discarding them stops a rejected request leaking a partial write into
        #whatever the next request commits on this connection.
        _safe_rollback(db)
        return exc.to_response()

    @app.errorhandler(IntegrityError)
    def _integrity_error(exc: IntegrityError):
        """A database constraint the application code did not catch.

        Almost always a race: two requests both passed the same "does this exist
        already?" check before either committed. The constraint is the real
        guard; this turns losing that race into a sensible 409 rather than a 500.
        """
        _safe_rollback(db)
        log.warning("Integrity constraint violated: %s", exc.orig)
        return _payload(
            "That conflicts with something that already exists. Please try again.", 409
        )

    @app.errorhandler(OperationalError)
    def _operational_error(exc: OperationalError):
        """The database is unreachable, or dropped the connection.

        Expected occasionally against a pooled Supabase connection, so it gets a
        retryable 503 rather than being reported to the user as a bug.
        """
        _safe_rollback(db)
        log.error("Database unavailable: %s", exc.orig)
        return _payload("The service is temporarily unavailable. Please try again.", 503)

    @app.errorhandler(SQLAlchemyError)
    def _database_error(exc: SQLAlchemyError):
        _safe_rollback(db)
        log.exception("Unhandled database error")
        return _payload("Something went wrong.", 500)

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        """Flask's own errors, as JSON.

        Covers 405, 415, malformed-body 400s, and anything else raised by routing
        or request parsing before a handler runs.
        """
        _safe_rollback(db)
        status = exc.code or 500
        return _payload(HTTP_MESSAGES.get(status, "Something went wrong."), status)

    @app.errorhandler(Exception)
    def _unexpected_error(exc: Exception):
        """The backstop.

        Anything not handled above is a bug. It is logged in full for us and
        reported as a bare 500 to the client, because an exception message can
        carry a query, a file path, or a value from another user's row.
        """
        _safe_rollback(db)
        log.exception("Unhandled exception")
        return _payload("Something went wrong.", 500)

    @app.teardown_request
    def _teardown(exc):
        #Belt and braces: if anything escaped the handlers above, the session is
        #still returned to the pool clean.
        if exc is not None:
            _safe_rollback(db)


def _safe_rollback(db) -> None:
    try:
        db.session.rollback()
    except Exception:  # noqa: BLE001 - a failed rollback must not mask the original error
        log.exception("Rollback failed")
