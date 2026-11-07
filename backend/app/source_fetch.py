"""Fetch a cited source page, safely, for the originality check.

The URLs come from writers, which makes this the one place the server makes a
request to an address a user chose. Unguarded, that is server-side request
forgery: cite http://169.254.169.254/ or http://localhost:5432/ and the server
fetches its own cloud metadata or internal services on the attacker's behalf.
So every hop is checked:

  * http or https only, default ports only, no credentials in the URL
  * the hostname must resolve only to public addresses (not loopback, private,
    link-local, reserved or multicast), checked again on every redirect
  * redirects are followed by hand, at most three, each re-validated
  * five-second timeout, one megabyte read limit, HTML or plain text only

Known residual risk: DNS rebinding. The address is checked, then urllib resolves
the name again to connect, and a hostile DNS server could answer differently the
second time. Closing that fully means connecting to the checked address with
the original hostname for TLS, which urllib cannot do; the window is small and
the response is only ever compared as text, never returned to the requester.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIMEOUT_SECONDS = 5
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
USER_AGENT = "SterlingWire-SourceCheck/1.0 (+originality check of cited sources)"
ALLOWED_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class SourceUnavailable(Exception):
    """Why a source could not be checked. The message is shown to editors.

    `kind` separates "this page does not exist" from "this site would not let
    a script read it", which matter differently. A missing page is not a
    source. A site that refuses automated requests (many large outlets do)
    still exists, and its link keeps its value:

        missing       no such host, or 404 / 410
        refused       not a public web address (private network, odd port...)
        blocked       the site answered but refused us (401, 403, 429, 451)
        not_page      it exists but is a file, such as a PDF report
        unreachable   timed out, or the server failed (5xx); try again later
    """

    def __init__(self, message: str, kind: str = "unreachable"):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str
    body: str


def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        raise SourceUnavailable("The address does not resolve.", "missing")
    if not infos:
        raise SourceUnavailable("The address does not resolve.", "missing")
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global or address.is_multicast:
            raise SourceUnavailable("The address is not on the public internet.", "refused")


def check_url(url: str) -> urllib.parse.ParseResult:
    """Validate a URL before any request. Raises SourceUnavailable."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SourceUnavailable("Only web (http or https) links can be checked.", "refused")
    if not parsed.hostname:
        raise SourceUnavailable("The link has no host.", "refused")
    if parsed.username or parsed.password:
        raise SourceUnavailable("Links with embedded credentials are not fetched.", "refused")
    if parsed.port not in (None, 80, 443):
        raise SourceUnavailable("Only standard web ports are fetched.", "refused")
    _public_host(parsed.hostname)
    return parsed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  #surface 3xx to the caller, which validates the next hop


_opener = urllib.request.build_opener(_NoRedirect)


def fetch(url: str) -> Fetched:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        check_url(current)
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            response = _opener.open(request, timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                current = urllib.parse.urljoin(current, e.headers["Location"])
                continue
            if e.code in (404, 410):
                raise SourceUnavailable(f"The page does not exist ({e.code}).", "missing")
            if e.code in (401, 403, 429, 451):
                raise SourceUnavailable(
                    f"The site does not allow automated checks ({e.code}).", "blocked")
            raise SourceUnavailable(f"The page returned an error ({e.code}).")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise SourceUnavailable("The page could not be reached.")

        with response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if not content_type.startswith(ALLOWED_TYPES):
                raise SourceUnavailable(
                    "The link is not a web page (it may be a PDF or file).", "not_page")
            data = response.read(MAX_BYTES + 1)
            charset = response.headers.get_content_charset() or "utf-8"
        return Fetched(
            url=current,
            content_type=content_type.split(";")[0],
            body=data[:MAX_BYTES].decode(charset, errors="replace"),
        )
    raise SourceUnavailable("Too many redirects.")
