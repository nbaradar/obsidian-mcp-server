"""MCP tools for vault management."""

import logging
from typing import Any, Optional
from mcp.server.fastmcp import Context

from obsidian_vault.server import mcp
from obsidian_vault.config import VAULT_CONFIGURATION
from obsidian_vault.session import (
    set_active_vault as set_active_vault_session,
    get_active_vault,
    get_session_key,
)

logger = logging.getLogger(__name__)


@mcp.tool()
async def list_vaults(ctx: Context | None = None) -> dict[str, Any]:
    """List configured Obsidian vaults and current session state.

    Returns metadata for all configured vaults including the default vault
    and currently active vault for this session. Primary entry point for
    vault discovery.

    Returns:
        {
            "default": str,    # System default vault name
            "active": str,     # Currently active vault (or None)
            "vaults": [
                {
                    "name": str,
                    "path": str,
                    "description": str,
                    "exists": bool
                }
            ]
        }

    Examples:
        - Use when: Starting conversation, need to see available vaults
        - Use when: User mentions vault by name, verify it exists
        - Don't use: Already know vault name and just need to switch

    Error Handling:
        - Config file missing → Error with expected config path
        - Invalid config format → Error describing expected YAML structure
    """
    active = None
    if ctx is not None:
        try:
            active = get_active_vault(ctx).name
        except ValueError:
            active = None

    return {
        "default": VAULT_CONFIGURATION.default_vault,
        "active": active,
        "vaults": [metadata.as_payload() for metadata in VAULT_CONFIGURATION.vaults.values()],
    }


@mcp.tool()
async def set_active_vault(vault: str, ctx: Context) -> dict[str, Any]:
    """Set the active vault for this conversation session.

    All subsequent tool calls that omit the vault parameter will use the
    active vault. Session state persists for the conversation lifetime.

    Args:
        vault (str): Friendly vault name from vaults.yaml
            Examples: "nader", "work", "personal"
            Use list_vaults() to discover valid names

    Returns:
        {"vault": str, "path": str, "status": "active"}

    Examples:
        - Use when: User says "switch to my work vault"
        - Use when: Starting multi-operation workflow in one vault
        - Don't use: Single operation in another vault (pass vault param directly)

    Error Handling:
        - Unknown vault → Error listing available vaults, suggest list_vaults()
        - Vault path inaccessible → Error with specific path that failed
    """
    metadata = set_active_vault_session(ctx, vault)
    logger.info("Active vault for session %s set to '%s'", get_session_key(ctx), metadata.name)
    return {
        "vault": metadata.name,
        "path": str(metadata.path),
        "status": "active",
    }
