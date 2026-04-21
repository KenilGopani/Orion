"""
Bridge — OpenClaw communication layer.

Exports a shared `openclaw_client` singleton used by all tool modules.
"""

from bridge.openclaw_client import OpenClawClient
from orion.config import config

openclaw_client = OpenClawClient(
    base_url=config.openclaw_url,
    api_token=config.openclaw_token,
)

__all__ = ["openclaw_client"]
