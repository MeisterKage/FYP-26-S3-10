"""Cover images: what gets in, what comes out, and what readers see.

The properties that matter are about trust: a file that is not really an image
never reaches a reader, a phone photo's location never leaves the server, a
writer cannot attach someone else's upload, and a published image always says
what it shows and where it came from.
"""
import io
from datetime import timedelta

import pytest
from PIL import Image

from app import images
from app.enums import ArticleStatus, Role
from app.extensions import db as _db
from app.models import Article, ArticleImage, Category, User, utcnow
from app.modules.images import prune_orphans
from app.security import hash_password

PASSWORD = "ImagesTest12345!"


def picture(width=800, height=600, fmt="JPEG", exif=None, mode="RGB"):
    out = io.BytesIO()
    image = Image.new(mode, (width, height), (30, 90, 160) if mode == "RGB" else (30, 90, 160, 128))
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def gps_exif():
    exif = Image.Exif()
    # GPSInfo IFD: latitude/longitude of the Wollongong lighthouse, roughly.
    exif[0x8825] = {1: "S", 2: (34.0, 25.0, 12.0), 3: "E", 4: (150.0, 54.0, 36.0)}
    exif[0x010F] = "PhoneMaker"  # camera make
    return exif


# --------------------------------------------------------------------------- #
#  Pure processing
# --------------------------------------------------------------------------- #

def test_a_photo_is_resized_to_two_known_sizes():
    out = images.process(picture(4000, 3000))
    large = (images.LARGE_WIDTH, images.LARGE_WIDTH * 3 // 4)
    assert (out.width, out.height) == large
    assert Image.open(io.BytesIO(out.large)).size == large
    assert Image.open(io.BytesIO(out.thumb)).size == (images.THUMB_WIDTH, images.THUMB_WIDTH * 3 // 4)
    assert Image.open(io.BytesIO(out.large)).format == "WEBP"


def test_location_and_camera_metadata_do_not_survive():
    original = picture(exif=gps_exif())
    assert Image.open(io.BytesIO(original)).getexif()  # the fixture really has it

    out = images.process(original)
    for data in (out.large, out.thumb):
        served = Image.open(io.BytesIO(data))
        assert not served.getexif()
        assert b"PhoneMaker" not in data


def test_a_small_image_is_not_enlarged():
    out = images.process(picture(500, 400))
    assert (out.width, out.height) == (500, 400)


def test_transparency_is_kept():
    out = images.process(picture(fmt="PNG", mode="RGBA"))
    assert Image.open(io.BytesIO(out.large)).mode == "RGBA"


@pytest.mark.parametrize("data,reason", [
    (b"", "empty"),
    (b"<script>alert(1)</script>", "not an image"),
    (b"GIF89a" + b"\0" * 100, "not an image"),
])
def test_things_that_are_not_images_are_refused(data, reason):
    with pytest.raises(images.ImageRejected):
        images.process(data)


def test_a_gif_is_refused_even_though_it_is_an_image():
    with pytest.raises(images.ImageRejected, match="JPEG, PNG or WebP"):
        images.process(picture(fmt="GIF"))


def test_too_small_to_use_is_refused():
    with pytest.raises(images.ImageRejected, match="too small"):
        images.process(picture(200, 150))


def test_an_oversized_file_is_refused_before_decoding(monkeypatch):
    with pytest.raises(images.ImageRejected, match="5 MB"):
        images.process(b"\xff" * (images.MAX_UPLOAD_BYTES + 1))


def test_a_decompression_bomb_is_refused_from_its_header(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 100_000)
    with pytest.raises(images.ImageRejected, match="megapixels"):
        images.process(picture(800, 600))


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #

def make_user(email, role):
    user = User(email=email, display_name=email.split("@")[0],
                password_hash=hash_password(PASSWORD), role=role)
    _db.session.add(user)
    _db.session.commit()
    return user


def auth(client, email):
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}
                        ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def world(app):
    category = Category(name="Politics", slug="politics")
    _db.session.add(category)
    _db.session.commit()
    return {
        "category": category,
        "writer": make_user("writer@example.com", Role.VERIFIED_CONTRIBUTOR),
        "other": make_user("other@example.com", Role.VERIFIED_CONTRIBUTOR),
        "reader": make_user("reader@example.com", Role.FREE_REGISTERED),
    }


def upload(client, headers, data=None, name="photo.jpg"):
    return client.post(
        "/api/images",
        data={"file": (io.BytesIO(data or picture(exif=gps_exif())), name)},
        headers=headers, content_type="multipart/form-data",
    )


def test_a_writer_uploads_and_the_image_is_served_clean(client, world):
    response = upload(client, auth(client, "writer@example.com"))
    assert response.status_code == 201
    image = response.get_json()["image"]
    assert len(image["key"]) == 32

    served = client.get(f"/api{image['url']}")
    assert served.status_code == 200
    assert served.mimetype == "image/webp"
    assert "immutable" in served.headers["Cache-Control"]
    assert not Image.open(io.BytesIO(served.data)).getexif()
    assert client.get(f"/api{image['thumbUrl']}").status_code == 200


def test_a_renamed_script_is_refused(client, world):
    response = upload(client, auth(client, "writer@example.com"),
                      data=b"<?php system($_GET['c']); ?>", name="photo.jpg")
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "file"


def test_a_reader_cannot_upload(client, world):
    assert upload(client, auth(client, "reader@example.com")).status_code == 403


def test_an_unknown_image_is_not_found(client, world):
    assert client.get("/api/images/" + "0" * 32 + ".webp").status_code == 404


def new_article(client, headers, world, **extra):
    return client.post("/api/articles", json={
        "title": "With a picture", "categoryId": world["category"].id,
        "body": "<p>Text.</p>", **extra,
    }, headers=headers).get_json()


def test_an_article_carries_its_image_alt_and_credit(client, world):
    headers = auth(client, "writer@example.com")
    key = upload(client, headers).get_json()["image"]["key"]
    article = new_article(client, headers, world, coverImage=key,
                          coverImageAlt="The harbour at dawn",
                          coverImageCredit="Photo: A. Writer")
    cover = article["coverImage"]
    assert cover["key"] == key
    assert cover["alt"] == "The harbour at dawn"
    assert cover["credit"] == "Photo: A. Writer"


def test_a_writer_cannot_attach_someone_elses_upload(client, world):
    key = upload(client, auth(client, "other@example.com")).get_json()["image"]["key"]
    response = client.post("/api/articles", json={
        "title": "Borrowed", "categoryId": world["category"].id, "coverImage": key,
    }, headers=auth(client, "writer@example.com"))
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == "coverImage"


@pytest.mark.parametrize("missing,field", [
    ({"coverImageCredit": "Photo: me"}, "coverImageAlt"),
    ({"coverImageAlt": "A harbour"}, "coverImageCredit"),
])
def test_submission_needs_alt_text_and_a_credit(client, world, missing, field):
    headers = auth(client, "writer@example.com")
    key = upload(client, headers).get_json()["image"]["key"]
    article = new_article(client, headers, world, coverImage=key, **missing)

    response = client.post(f"/api/articles/{article['id']}/submit", headers=headers)
    assert response.status_code == 422
    assert response.get_json()["error"]["field"] == field


def test_an_article_without_an_image_submits_as_before(client, world):
    headers = auth(client, "writer@example.com")
    article = new_article(client, headers, world)
    assert client.post(f"/api/articles/{article['id']}/submit", headers=headers).status_code == 200


def test_removing_the_image_clears_it(client, world):
    headers = auth(client, "writer@example.com")
    key = upload(client, headers).get_json()["image"]["key"]
    article = new_article(client, headers, world, coverImage=key)
    cleared = client.patch(f"/api/articles/{article['id']}", json={"coverImage": None},
                           headers=headers).get_json()
    assert cleared["coverImage"] is None


def test_prune_removes_only_old_unattached_uploads(app, client, world):
    headers = auth(client, "writer@example.com")
    attached = upload(client, headers).get_json()["image"]["key"]
    orphan = upload(client, headers).get_json()["image"]["key"]
    fresh = upload(client, headers).get_json()["image"]["key"]
    new_article(client, headers, world, coverImage=attached)

    for key in (attached, orphan):
        ArticleImage.query.filter_by(key=key).one().created_at = utcnow() - timedelta(days=2)
    _db.session.commit()

    assert prune_orphans() == 1
    remaining = {i.key for i in ArticleImage.query.all()}
    assert remaining == {attached, fresh}
