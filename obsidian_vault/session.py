"""Session state management for active vault selection."""

from typing import Dict, Optional
from mcp.server.fastmcp import Context

from obsidian_vault.config import VAULT_CONFIGURATION
from obsidian_vault.data_models import VaultMetadata

# Session state storage
_ACTIVE_VAULTS: Dict[int, str] = {}


def get_session_key(ctx: Context) -> int:
    """Produce a stable per-session key for active vault tracking.

    Args:
        ctx: The request context supplied by FastMCP.

    Returns:
        An integer derived from the underlying session object identity. This value
        remains stable for the lifetime of the MCP session and is suitable as a
        dictionary key.
    """
    return id(ctx.session)


def set_active_vault(ctx: Context, vault_name: str) -> VaultMetadata:
    """Set the active vault for a client session.

    Args:
        ctx: The request context supplied by FastMCP.
        vault_name: Friendly vault name as defined in ``vaults.yaml``.

    Returns:
        The :class:`VaultMetadata` associated with ``vault_name``.

    Raises:
        ValueError: If ``vault_name`` is not present in the configuration.
    """
    metadata = VAULT_CONFIGURATION.get(vault_name)
    _ACTIVE_VAULTS[get_session_key(ctx)] = metadata.name
    return metadata


def get_active_vault(ctx: Context) -> VaultMetadata:
    """Retrieve the active vault for a session, falling back to the default.

    Args:
        ctx: The request context supplied by FastMCP.

    Returns:
        The :class:`VaultMetadata` representing the currently selected vault, or the
        configuration default if the session has not yet selected one.
    """
    vault_name = _ACTIVE_VAULTS.get(get_session_key(ctx), VAULT_CONFIGURATION.default_vault)
    return VAULT_CONFIGURATION.get(vault_name)


def resolve_vault(vault: Optional[str], ctx: Optional[Context] = None) -> VaultMetadata:
    """Resolve which vault metadata should be used for an operation.

    Args:
        vault: Optional friendly vault name provided directly by the caller.
        ctx: Optional FastMCP context used to infer the active vault when ``vault``
            is not supplied.

    Returns:
        The resolved :class:`VaultMetadata`.

    Raises:
        ValueError: If the supplied ``vault`` name is not recognized.
    """
    if vault:
        return VAULT_CONFIGURATION.get(vault)

    if ctx is not None:
        return get_active_vault(ctx)

    return VAULT_CONFIGURATION.get(VAULT_CONFIGURATION.default_vault)
