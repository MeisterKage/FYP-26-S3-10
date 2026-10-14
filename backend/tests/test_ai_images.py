"""AI-generated images are refused at upload, from what their own files say."""
import io

from PIL import Image, PngImagePlugin

from app.image_provenance import ai_markers
from tests.test_images import auth, picture, upload, world  # noqa: F401

XMP_AI = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
          b'<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
          b'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"/>'
          b'</rdf:RDF></x:xmpmeta>')


def with_software(name, fmt="JPEG"):
    exif = Image.Exif()
    exif[0x0131] = name  # Software
    return picture(fmt=fmt, exif=exif)


def png_with_text(key, value):
    info = PngImagePlugin.PngInfo()
    info.add_text(key, value)
    out = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 20, 30)).save(out, format="PNG", pnginfo=info)
    return out.getvalue()


def with_xmp(fmt):
    out = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 20, 30)).save(out, format=fmt, xmp=XMP_AI)
    return out.getvalue()


def test_generator_names_and_credentials_are_recognised():
    assert ai_markers(with_software("Midjourney v6")) == ["it was made with Midjourney"]
    assert ai_markers(png_with_text("parameters", "a lighthouse, Steps: 30, Sampler: Euler a, CFG scale: 7"))
    assert ai_markers(with_xmp("JPEG")) == ["its content credentials record it as AI-generated"]
    assert ai_markers(with_xmp("WEBP")) == ["its content credentials record it as AI-generated"]


def test_ordinary_photos_pass_even_with_lookalike_words():
    assert ai_markers(with_software("Adobe Lightroom 7.1")) == []
    assert ai_markers(png_with_text("Description", "A plane on the runway at dawn")) == []
    assert ai_markers(picture()) == []


def test_an_ai_image_is_refused_at_upload(client, world):
    r = upload(client, auth(client, "writer@example.com"), data=with_software("DALL-E 3"))
    assert r.status_code == 422
    assert "AI-generated images are not allowed" in r.get_json()["error"]["message"]


def test_the_writer_must_confirm_each_upload(client, world):
    r = upload(client, auth(client, "writer@example.com"), declaration=None)
    assert r.status_code == 422 and r.get_json()["error"]["field"] == "declaration"
