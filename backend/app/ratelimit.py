"""Rate limiting for the endpoints an attacker hammers.

PRD 5.1 makes security a High-priority requirement, and password hashing alone
does not answer it: Argon2 makes each guess expensive for us, not for the
attacker. Unlimited attempts against a login form defeats any password policy.

Three endpoints need this:

  * login: credential stuffing and brute force
  * password reset request: an unthrottled mailer is an outbound spam relay
    aimed at whichever address the attacker names
  * register: automated account creation

Two different keys are needed, and using the wrong one silently does nothing:

  * Login and password reset are attacks against *one account*, so the key is
    address + target email. Address alone is weak (a botnet rotates addresses);
    email alone would let an attacker deny a victim service by exhausting their
    bucket on purpose.
  * Registration is an attack by *volume* from one source, and every request
    carries a brand-new email. Keying it on the email would hand each signup its
    own fresh bucket, so the limit would never trigger. Registration is
    therefore keyed on address alone.

Storage is in-process memory by default, which is correct for development and
for a single-process demo, but does not survive a restart and is not shared
across workers. Point RATELIMIT_STORAGE_URI at Redis before that matters.
"""
from __future__ import annotations

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .errors import ApiError

#: Login: tight enough to make brute force impractical, loose enough that a
#: person who genuinely forgot their password is not locked out.
LOGIN_LIMIT = "10 per 15 minutes"

#: Password reset: each request sends an email to an address the caller chose.
RESET_LIMIT = "5 per hour"

#: Registration, from one address. Generous enough for a shared campus NAT,
#: tight enough to stop bulk account creation.
REGISTER_LIMIT = "10 per hour"


def client_address() -> str:
    return get_remote_address() or "unknown"


def _identity() -> str:
    """Key for attacks aimed at one account: client address plus target email.

    Reading the JSON body here is safe: Flask caches the parsed body, so the
    view handler is unaffected, and `silent=True` means a malformed body degrades
    to limiting on address alone rather than raising inside the limiter.
    """
    address = client_address()

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        email = payload.get("email")
        if isinstance(email, str) and email.strip():
            return f"{address}|{email.strip().lower()}"

    return address


limiter = Limiter(
    key_func=_identity,
    # No blanket default: a rate limit on article reads would throttle ordinary
    # browsing. Only the endpoints that need one carry one.
    default_limits=[],
    headers_enabled=True,
    strategy="fixed-window",
)


def register_rate_limit_handler(app) -> None:
    """Report a rate-limit rejection in the API's own error shape."""
    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def _rate_limited(exc: RateLimitExceeded):
        # Deliberately vague about which limit was hit and how much budget
        # remains; that detail is a tuning guide for whoever triggered it.
        return ApiError(
            "Too many attempts. Please wait a few minutes and try again.",
            status=429,
        ).to_response()
