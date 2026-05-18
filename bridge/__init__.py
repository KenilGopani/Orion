"""
Bridge — OpenClaw communication layer.

Exports a lazy singleton ``get_openclaw_client()`` used by all tool modules.
The client is created on first access to avoid circular imports between
``bridge`` and ``orion.config``.
"""

from __future__ import annotations

from bridge.openclaw_client import OpenClawClient

_openclaw_client: OpenClawClient | None = None


def get_openclaw_client() -> OpenClawClient:
    """Return the shared OpenClaw client singleton (created lazily)."""
    global _openclaw_client
    if _openclaw_client is None:
        from orion.config import config

        _openclaw_client = OpenClawClient(
            base_url=config.openclaw_url,
            api_token=config.openclaw_token,
        )
    return _openclaw_client


# Keep backward-compatible module-level attribute for existing imports.
# Accessing this triggers lazy creation.
class _LazyProxy:
    """Proxy that defers OpenClawClient creation to first attribute access."""

    def __getattr__(self, name: str):
        return getattr(get_openclaw_client(), name)


openclaw_client: OpenClawClient = _LazyProxy()  # type: ignore[assignment]

__all__ = ["get_openclaw_client", "openclaw_client"]
