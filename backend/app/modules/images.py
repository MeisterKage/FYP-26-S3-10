"""Cover image upload and serving.

The only module that reads or writes ArticleImage rows. Images live in the
database today; moving them to object storage later means changing this file
and nothing else, because everywhere else refers to an image by its key and
its URL.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from flask import Blueprint, Response, g, jsonify, request

from ..enums import AUTHORING_ROLES
from ..errors import ApiError
from ..extensions import db
from ..image_provenance import ai_markers
from ..images import MAX_UPLOAD_BYTES, ImageRejected, process
from ..models import Article, ArticleImage, utcnow
from ..ratelimit import client_address, limiter
from ..security import current_user, roles_required

bp = Blueprint("images", __name__)

#: Generous for a writer choosing between a few photos, tight enough that one
#: account cannot fill the database with uploads.
UPLOAD_LIMIT = "30 per hour"
#: An uploaded image nobody attached to an article after this long is removed
#: by `flask prune-images`.
ORPHAN_AGE = timedelta(days=1)


def _uploader() -> str:
    user = current_user()
    return f"user:{user.id}" if user else client_address()


def image_urls(image: ArticleImage | None) -> dict | None:
    """Public URLs for an image. Relative to the API root, which the client prefixes."""
    if image is None:
        return None
    return {
        "key": image.key,
        "url": f"/images/{image.key}.webp",
        "thumbUrl": f"/images/{image.key}/thumb.webp",
        "width": image.width,
        "height": image.height,
    }


def find_attachable(key: str, user) -> ArticleImage:
    """An image the current writer may put on their article: one they uploaded."""
    image = ArticleImage.query.filter_by(key=key).first()
    if image is None or image.owner_id != user.id:
        raise ApiError("That image was not found. Upload it again.", status=422,
                       field="coverImage")
    return image


@bp.post("/images")
@limiter.limit(UPLOAD_LIMIT, key_func=_uploader)
@roles_required(*AUTHORING_ROLES)
def upload_image():
    """Upload one image as multipart/form-data, field `file`.

    Returns its key and URLs. Nothing is public until the key is attached to an
    article and that article is published; until then only the key's holder
    knows it, and keys are random.
    """
    upload = request.files.get("file")
    if upload is None:
        raise ApiError("Choose an image to upload.", status=422, field="file")
    #AI-generated images are not allowed. The writer says so for each upload;
    #the file's own metadata is checked below as well.
    if request.form.get("declaration") != "not-ai":
        raise ApiError("Confirm that this image is not AI-generated.", status=422,
                       field="declaration")

    #Read one byte past the limit, so an oversized file is refused without
    #holding the whole thing in memory.
    data = upload.stream.read(MAX_UPLOAD_BYTES + 1)
    #Before re-encoding, which drops the metadata this reads.
    markers = ai_markers(data[:MAX_UPLOAD_BYTES])
    if markers:
        raise ApiError(
            f"This image looks AI-generated: {markers[0]}. AI-generated images are not "
            "allowed on Sterling Wire.", status=422, field="file")
    try:
        processed = process(data)
    except ImageRejected as e:
        raise ApiError(str(e), status=422, field="file")

    image = ArticleImage(
        key=secrets.token_hex(16),
        owner_id=g.current_user.id,
        width=processed.width,
        height=processed.height,
        large=processed.large,
        thumb=processed.thumb,
    )
    db.session.add(image)
    db.session.commit()
    return jsonify({"image": image_urls(image)}), 201


def _serve(key: str, variant: str) -> Response:
    column = ArticleImage.large if variant == "large" else ArticleImage.thumb
    row = db.session.query(column).filter(ArticleImage.key == key).first()
    if row is None:
        raise ApiError("Image not found.", status=404)
    response = Response(row[0], mimetype="image/webp")
    #The bytes behind a key never change (a new upload gets a new key), so a
    #browser may keep its copy for a year. This overrides the API-wide
    #no-store, which exists for authorised JSON, not for public images.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@bp.get("/images/<key>.webp")
def serve_large(key: str):
    return _serve(key, "large")


@bp.get("/images/<key>/thumb.webp")
def serve_thumb(key: str):
    return _serve(key, "thumb")


def prune_orphans(now=None) -> int:
    """Delete uploads never attached to any article. Returns how many."""
    now = now or utcnow()
    attached = db.session.query(Article.cover_image_id).filter(
        Article.cover_image_id.isnot(None)
    )
    orphans = ArticleImage.query.filter(
        ~ArticleImage.id.in_(attached),
        ArticleImage.created_at < now - ORPHAN_AGE,
    ).all()
    for image in orphans:
        db.session.delete(image)
    db.session.commit()
    return len(orphans)
