"""Application configuration, loaded from environment.

No secret has a default. A missing value fails loudly at boot rather than
silently running with a guessable key.
"""
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

    # PRD 5.1 Security: "passwords of at least 12 characters"
    MIN_PASSWORD_LENGTH = 12

    # Largest request body Flask will read: a 5 MB image plus multipart
    # overhead. Anything bigger is refused with 413 before it is buffered.
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    # Rate-limit counters. In-process memory is correct for development and a
    # single-process demo, but it resets on restart and is not shared between
    # workers -- so a multi-worker deployment gives each worker its own budget.
    # Point this at Redis (redis://...) before that matters.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    # Off by default: the suite signs in repeatedly and would trip its own
    # limits. tests/test_rate_limit.py turns it back on explicitly.
    RATELIMIT_ENABLED = False
