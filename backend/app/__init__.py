"""Flask application factory.

The eight blueprints below map onto the functional modules in PDD Section 2.2,
onto platform capabilities, not onto database tables.
"""
from flask import Flask, jsonify

from config import Config
from .errors import register_error_handlers
from .extensions import cors, db, migrate
from .headers import register_security_headers
from .ratelimit import limiter, register_rate_limit_handler
from .security import load_current_user


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )

    # Import models so Alembic's autogenerate sees every table.
    from . import models  # noqa: F401

    # PDD Section 3: every request passes through the auth and role middleware
    # before it reaches an application service.
    app.before_request(load_current_user)

    from .modules.auth import bp as auth_bp
    from .modules.users import bp as users_bp
    from .modules.articles import bp as articles_bp
    from .modules.review import bp as review_bp
    from .modules.discovery import bp as discovery_bp
    from .modules.engagement import bp as engagement_bp
    from .modules.moderation import bp as moderation_bp
    from .modules.notifications import bp as notifications_bp
    from .modules.subscriptions import bp as subscriptions_bp
    from .modules.admin import bp as admin_bp
    from .modules.editors import bp as editors_bp
    from .modules.images import bp as images_bp
    from .modules.originality import bp as originality_bp
    from .modules.digests import bp as digests_bp
    from .modules.payments import bp as payments_bp
    from .modules.insights import bp as insights_bp
    from .modules.share import bp as share_bp

    for blueprint in (
        auth_bp, users_bp, articles_bp, review_bp, discovery_bp,
        engagement_bp, moderation_bp, notifications_bp, subscriptions_bp, admin_bp,
        editors_bp, images_bp, originality_bp, digests_bp, payments_bp, insights_bp, share_bp,
    ):
        app.register_blueprint(blueprint, url_prefix="/api")

    register_security_headers(app)

    register_error_handlers(app)
    # Registered after the generic handlers so the 429 keeps the API's error
    # shape rather than falling through to the HTTPException handler.
    register_rate_limit_handler(app)

    from .cli import register_cli

    register_cli(app)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app
