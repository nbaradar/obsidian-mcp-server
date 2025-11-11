"""Obsidian Vault MCP Server

Multi-vault Obsidian note management via Model Context Protocol.
"""

from obsidian_vault.config import VAULT_CONFIGURATION
from obsidian_vault.data_models import VaultMetadata, VaultConfiguration
from obsidian_vault.session import resolve_vault, set_active_vault, get_active_vault
from obsidian_vault.server import mcp, run_server

# Import tools to register them with the MCP server
from obsidian_vault import tools  # noqa: F401

__version__ = "1.4.3"
__all__ = [
    "VAULT_CONFIGURATION",
    "VaultMetadata",
    "VaultConfiguration",
    "resolve_vault",
    "set_active_vault",
    "get_active_vault",
    "mcp",
    "run_server",
]
