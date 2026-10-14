"""Application configuration, loaded from environment.

No secret has a default. A missing value fails loudly at boot rather than
silently running with a guessable key.
"""
import hashlib
import hmac
import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy backend/.env.example to backend/.env and fill it in."
        )
    return value


class Config:
    SECRET_KEY = _required("SECRET_KEY")
    JWT_SECRET = _required("JWT_SECRET")

    SQLALCHEMY_DATABASE_URI = _required("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Supabase's pooler drops idle connections; recycle before it does.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    JWT_ACCESS_TTL_MINUTES = int(os.environ.get("JWT_ACCESS_TTL_MINUTES", 60))
    JWT_REFRESH_TTL_DAYS = int(os.environ.get("JWT_REFRESH_TTL_DAYS", 14))
    RESET_TOKEN_TTL_MINUTES = int(os.environ.get("RESET_TOKEN_TTL_MINUTES", 30))

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    # The public website, for links the API hands out (shared articles). Taken
    # from the allowed origins, which already name it, unless set explicitly.
    SITE_URL = os.environ.get("SITE_URL") or next(
        (o for o in CORS_ORIGINS if "localhost" not in o and "127.0.0.1" not in o),
        CORS_ORIGINS[0],
    ).strip()

    # PRD 5.1 Security: "passwords of at least 12 characters"
    MIN_PASSWORD_LENGTH = 12

    # Largest request body Flask will read: a 5 MB image plus multipart
    # overhead. Anything bigger is refused with 413 before it is buffered.
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    # Whether originality checks fetch the pages an article cites. On in every
    # real deployment; off in tests, which must not depend on the network.
    ORIGINALITY_FETCH_SOURCES = True

    # Payments (app/payments.py). "sandbox" works end to end with no money;
    # "stripe" needs the skeleton completed and the two Stripe keys set.
    PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "sandbox")
    # Signs sandbox webhooks. Derived from SECRET_KEY unless set, so it is never
    # a value committed to the repository.
    PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET") or hmac.new(
        SECRET_KEY.encode(), b"sandbox-payment-webhooks", hashlib.sha256
    ).hexdigest()
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

    # Reading aids and writing signals (app/insights_service.py). The built-in
    # providers need no account; the others are skeletons until completed.
    SUMMARY_PROVIDER = os.environ.get("SUMMARY_PROVIDER", "extractive")
    NARRATION_PROVIDER = os.environ.get("NARRATION_PROVIDER", "browser")
    WRITING_SIGNALS_PROVIDER = os.environ.get("WRITING_SIGNALS_PROVIDER", "stylometric")
    # Every article gets an In brief summary; raise this to keep it off short ones.
    IN_BRIEF_MIN_WORDS = int(os.environ.get("IN_BRIEF_MIN_WORDS", "0"))
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-5-5")
    NARRATION_API_KEY = os.environ.get("NARRATION_API_KEY")
    NARRATION_VOICE = os.environ.get("NARRATION_VOICE")
    WRITING_SIGNALS_API_URL = os.environ.get("WRITING_SIGNALS_API_URL")
    WRITING_SIGNALS_API_KEY = os.environ.get("WRITING_SIGNALS_API_KEY")

    # Where article translations come from (app/translation_service.py).
    # "auto" translates new articles with Claude once ANTHROPIC_API_KEY is set,
    # and otherwise serves only the translations already saved ("stored").
    TRANSLATION_PROVIDER = os.environ.get("TRANSLATION_PROVIDER", "auto")
    TRANSLATION_MODEL = os.environ.get("TRANSLATION_MODEL", "claude-sonnet-5-5")
    # Translate in a background thread, so publishing never waits for it.
    TRANSLATE_IN_BACKGROUND = True

    # How long a public page is remembered for signed-out visitors
    # (app/response_cache.py). 0 turns the cache off.
    RESPONSE_CACHE_SECONDS = int(os.environ.get("RESPONSE_CACHE_SECONDS", "60"))

    # Rate-limit counters. In-process memory is correct for development and a
    # single-process demo, but it resets on restart and is not shared between
    # workers -- so a multi-worker deployment gives each worker its own budget.
    # Point this at Redis (redis://...) before that matters.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class TestConfig(Config):
    TESTING = True
    # Tests change the database directly between requests; a cached page
    # would hide that. The cache has its own tests, which switch it on.
    RESPONSE_CACHE_SECONDS = 0
    ORIGINALITY_FETCH_SOURCES = False
    # Never call a translation service from the tests; the translation tests
    # supply their own and run the jobs themselves.
    TRANSLATION_PROVIDER = "stored"
    TRANSLATE_IN_BACKGROUND = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    # Off by default: the suite signs in repeatedly and would trip its own
    # limits. tests/test_rate_limit.py turns it back on explicitly.
    RATELIMIT_ENABLED = False
