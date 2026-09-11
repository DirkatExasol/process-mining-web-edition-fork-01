"""Shared HTTP security-response-header middleware for the browser-facing servers
(the admin panel and the GUI/app server).

These are defense-in-depth headers, not the primary control: state-changing
requests are already protected by SameSite=Lax session cookies (and the compute
backend additionally by the proxy-auth HMAC). The headers close the residual gaps
— clickjacking, MIME-sniffing, referrer leakage — that those controls don't cover.

A deliberately minimal set: NO restrictive Content-Security-Policy, because the
login page paints an admin-supplied `data:` image background and the SPA relies on
inline styles, both of which a strict `script-src`/`img-src` CSP would break. The
anti-framing protection is delivered via X-Frame-Options + `frame-ancestors 'none'`
instead, which carries no such risk.
"""

from __future__ import annotations

from fastapi import FastAPI, Request


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        # setdefault so an endpoint that intentionally sets its own value wins.
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy", "frame-ancestors 'none'"
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response
