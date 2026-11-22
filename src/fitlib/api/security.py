"""Keeping other websites away from the local server.

Listening on 127.0.0.1 keeps other computers out, but not web pages open in your own browser:
any site can send requests to ``localhost``. Three defences:

- **Host check.** Requests must name a loopback host (``localhost``, ``127.0.0.1``, ``[::1]``,
  any port). A page that rebinds its own domain to 127.0.0.1 ("DNS rebinding") still sends
  its domain as the Host, so it can't read the library.
- **Same-origin writes.** A request that changes something (POST, PUT, PATCH, DELETE) from a
  browser must come from the app itself: its ``Origin`` must match the Host, and when a
  browser sends no Origin, ``Sec-Fetch-Site`` must not say another site. Requests without
  either (the command line, curl, tests) are allowed: only browsers add them.
- **Security headers** on every response: no framing, no MIME sniffing, no referrer, and a
  Content-Security-Policy allowing only the app's own scripts and connections.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, MutableMapping
from typing import Any
from urllib.parse import urlsplit

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SAME_SITE_FETCHES = frozenset({"same-origin", "none"})

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        # React and ECharts set style attributes.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
)
# FastAPI's API docs load their scripts from a CDN, so they go without the policy.
DOCS_PATHS = ("/docs", "/redoc")


def host_name(host: str) -> str:
    """The host name of a Host header or URL netloc, without the port or IPv6 brackets.

    Args:
        host: E.g. ``localhost:8000``, ``[::1]:8000`` or ``127.0.0.1``.

    Returns:
        E.g. ``localhost``, ``::1``, ``127.0.0.1``, lower-cased.
    """
    host = host.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _header(scope: Scope, name: bytes) -> str | None:
    """Read a request header.

    Args:
        scope: The ASGI scope.
        name: The header's name, lower-case.

    Returns:
        Its value, or ``None``.
    """
    for key, value in scope.get("headers", ()):
        if key == name:
            return value.decode("latin-1")
    return None


def refusal(scope: Scope, allowed_hosts: frozenset[str] | None) -> tuple[int, str] | None:
    """Decide whether a request must be refused.

    Args:
        scope: The request's ASGI scope.
        allowed_hosts: Host names requests may name, or ``None`` to allow any (serving on a
            network address the user chose).

    Returns:
        The status and reason to refuse with, or ``None`` to let it through.
    """
    host = _header(scope, b"host") or ""
    if allowed_hosts is not None and host_name(host) not in allowed_hosts:
        return 421, "This server only answers requests for localhost."
    if scope.get("method", "GET") in SAFE_METHODS:
        return None
    origin = _header(scope, b"origin")
    if origin is not None:
        parts = urlsplit(origin)
        if origin == "null" or parts.netloc.lower() != host.lower():
            return 403, "Changes are only accepted from fitlib's own pages."
        return None
    fetch_site = _header(scope, b"sec-fetch-site")
    if fetch_site is not None and fetch_site not in SAME_SITE_FETCHES:
        return 403, "Changes are only accepted from fitlib's own pages."
    return None


class LocalOnly:
    """ASGI middleware applying the host check, same-origin writes and security headers.

    Args:
        app: The app to wrap.
        allowed_hosts: Host names requests may name; ``None`` allows any.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str] | None = LOOPBACK_HOSTS):
        self.app = app
        self.allowed_hosts = None if allowed_hosts is None else frozenset(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI event.

        Args:
            scope: The connection's scope.
            receive: Reads request messages.
            send: Sends response messages.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        refused = refusal(scope, self.allowed_hosts)
        if refused is not None:
            status, reason = refused
            body = json.dumps({"detail": reason}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        *SECURITY_HEADERS,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        docs = scope.get("path", "").startswith(DOCS_PATHS)

        async def with_headers(message: Message) -> None:
            """Add the security headers to the response's start.

            Args:
                message: An ASGI response message.
            """
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", ()))
                headers += SECURITY_HEADERS
                if not docs:
                    headers.append((b"content-security-policy", CONTENT_SECURITY_POLICY.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, with_headers)
