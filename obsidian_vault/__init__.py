"""Obsidian Vault MCP Server

Multi-vault Obsidian note management via Model Context Protocol.
"""

from obsidian_vault.config import VAULT_CONFIGURATION
from obsidian_vault.models import VaultMetadata, VaultConfiguration

__version__ = "1.4.3"
__all__ = ["VAULT_CONFIGURATION", "VaultMetadata", "VaultConfiguration"]
