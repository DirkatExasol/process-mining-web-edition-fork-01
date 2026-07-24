"""Thin logging helpers shared by the GUI server and the admin server.

They extract the client IP from a request (honouring a reverse-proxy header) and
forward to the shared LogStore. Use the severity helpers for intent:

    log.usage("...", request=r, username=u, operation="login")   # user actions
    log.info(...)   # lifecycle / config changes
    log.warn(...)   # recoverable problems (failed login, unauthorised)
    log.error(...)  # exceptions / failures
    log.debug(...)  # verbose request/trace detail
"""

from __future__ import annotations

from typing import Any

from .store import logs as _logs


def client_ip(request: Any) -> str:
    if request is None:
        return ""
    try:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else ""
    except Exception:  # noqa: BLE001 — logging must never raise
        return ""


def _emit(
    severity: str,
    message: str,
    *,
    request: Any = None,
    username: str = "",
    operation: str = "",
) -> None:
    try:
        _logs.store.record(
            severity,
            message,
            client_ip=client_ip(request),
            username=username,
            operation=operation,
        )
    except Exception:  # noqa: BLE001 — never let logging break a request
        pass


def info(message: str, **kw: Any) -> None:
    _emit("INFO", message, **kw)


def usage(message: str, **kw: Any) -> None:
    _emit("USAGE", message, **kw)


def warn(message: str, **kw: Any) -> None:
    _emit("WARN", message, **kw)


def error(message: str, **kw: Any) -> None:
    _emit("ERROR", message, **kw)


def debug(message: str, **kw: Any) -> None:
    _emit("DEBUG", message, **kw)


def _operation_for(path: str) -> str:
    if path in ("/login", "/auth/login"):
        return "login"
    if path in ("/logout", "/auth/logout"):
        return "logout"
    if path in ("/", "/index.html"):
        return "page"
    return "request"


def install_request_logging(app: Any, resolve_user: Any) -> None:
    """Add an HTTP middleware that logs every request outcome.

    Classification: 5xx → ERROR, 401/403 → WARN (unauthorised), other → DEBUG (a
    verbose per-request trace). Explicit login/logout/page events are logged by the
    handlers at USAGE so they survive the default level; this middleware adds the
    trace and the security-relevant WARN/ERROR entries.
    """

    def _user(request: Any) -> str:
        try:
            user = resolve_user(request)
            if isinstance(user, str):
                return user
            return getattr(user, "username", "") or ""
        except Exception:  # noqa: BLE001
            return ""

    @app.middleware("http")
    async def _request_log(request: Any, call_next: Any):
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            error(
                f"unhandled error on {request.method} {request.url.path}: {exc!r}",
                request=request,
                username=_user(request),
                operation="error",
            )
            raise
        path = request.url.path
        status = response.status_code
        line = f"{request.method} {path} → {status}"
        if status >= 500:
            error(line, request=request, username=_user(request), operation="error")
        elif status in (401, 403):
            warn(
                f"unauthorised {line}",
                request=request,
                username=_user(request),
                operation="unauthorised",
            )
        else:
            debug(
                line,
                request=request,
                username=_user(request),
                operation=_operation_for(path),
            )
        return response
