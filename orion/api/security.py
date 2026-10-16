"""
Local API protection: a per-install token and a Host allow-list.

Threats this addresses (see SECURITY.md):

- **Cross-site request forgery.** A web page on another site can make the
  browser POST to ``127.0.0.1``, but it cannot attach a custom header without a
  CORS grant, which Orion never gives. State-changing routes require the
  ``X-Orion-Token`` header, so forged requests fail.
- **DNS rebinding.** A hostile domain that resolves to 127.0.0.1 would make that
  page "same-origin". Every request must carry a loopback ``Host`` header, so a
  rebinding page (``Host: evil.example``) is refused before it reaches a route.

Not addressed: other programs running as the same OS user. They can read
``~/.orion/`` directly, so no local secret can stop them.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import stat
from collections.abc import Iterable
from pathlib import Path

from fastapi import Header, HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("orion.security")

TOKEN_HEADER = "X-Orion-Token"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


def load_or_create_token(path: Path) -> str:
    """Return the install token at ``path``, creating it (mode 0600) if absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            logger.warning("%s was readable by other users; restricting it to 0600.", path)
            path.chmod(0o600)
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
        path.unlink()
        return load_or_create_token(path)
    token = secrets.token_urlsafe(32)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token + "\n")
    logger.info("Created API token at %s", path)
    return token


def _hostname(host_header: str) -> str:
    """``"127.0.0.1:8000"`` → ``"127.0.0.1"``; ``"[::1]:8000"`` → ``"[::1]"``."""
    if host_header.startswith("["):
        return host_header[: host_header.find("]") + 1]
    return host_header.rsplit(":", 1)[0] if ":" in host_header else host_header


class LoopbackHostMiddleware:
    """Refuse any request whose Host header isn't an allowed (loopback) name."""

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str] = ()) -> None:
        self.app = app
        self.allowed = LOOPBACK_HOSTS | {h.lower() for h in allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope["headers"])
            host = headers.get(b"host", b"").decode("latin-1").lower()
            if _hostname(host) not in self.allowed:
                if scope["type"] == "http":
                    await send({"type": "http.response.start", "status": 421,
                                "headers": [(b"content-type", b"text/plain")]})
                    await send({"type": "http.response.body", "body": b"Misdirected request"})
                return
        await self.app(scope, receive, send)


def require_token(expected: str):
    """FastAPI dependency: the request must carry the install token."""

    def check(x_orion_token: str | None = Header(default=None)) -> None:
        if not x_orion_token or not hmac.compare_digest(x_orion_token, expected):
            raise HTTPException(status_code=401, detail=f"Missing or invalid {TOKEN_HEADER} header")

    return check
