"""Security response headers.

The API returns JSON to a browser, which means a browser will act on whatever
the response headers tell it. Without these, three attacks stay open that no
amount of correct application logic closes:

  * Clickjacking. Any site can frame this one, overlay an invisible button on a
    real control, and have a signed-in administrator click it. `frame-ancestors
    'none'` refuses framing outright; X-Frame-Options says the same thing to
    browsers predating CSP Level 2.

  * MIME sniffing. A browser that ignores our Content-Type and guesses can be
    persuaded to execute a JSON response as script. `nosniff` removes the guess.

  * Referrer leakage. A full URL in the Referer header follows every outbound
    link, and article URLs carry slugs a reader may not want disclosed to third
    parties. `strict-origin-when-cross-origin` sends the origin and nothing more.

The Content-Security-Policy here is deliberately strict because this application
serves only JSON. Nothing it returns should ever load a script, a frame, or an
image, so everything is denied rather than allow-listed. The static site is
served by Render, not by Flask, and carries its own headers from render.yaml.
"""
from __future__ import annotations

from flask import Flask

#: Applied to every response. Values are fixed rather than configurable: an
#: environment variable that can weaken a security header is a way to ship a
#: weakened security header by accident.
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    #This API is read with a bearer token, never a cookie, so there is no
    #reason for a browser to keep a shared cached copy of an authorised reply.
    "Cache-Control": "no-store",
}


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def _apply(response):
        for header, value in HEADERS.items():
            #setdefault semantics: a route that deliberately sets its own
            #caching or framing rule keeps it.
            response.headers.setdefault(header, value)
        return response
