"""Test setup.

`config.py` deliberately refuses to boot without real secrets, so tests supply
throwaway ones here. These are set before any application module is imported.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-use-anywhere-else")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-use-anywhere-else")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from config import TestConfig  # noqa: E402


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db
