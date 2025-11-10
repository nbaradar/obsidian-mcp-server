"""MCP tool definitions for Obsidian vault operations.

This module imports all tool submodules to register them with the MCP server.
Each tool module uses the @mcp.tool() decorator to auto-register its tools.
"""

# Import all tool modules to register their @mcp.tool() decorated functions
from obsidian_vault.tools import vault_tools
from obsidian_vault.tools import note_tools
from obsidian_vault.tools import search_tools
from obsidian_vault.tools import section_tools
from obsidian_vault.tools import frontmatter_tools

__all__ = [
    "vault_tools",
    "note_tools",
    "search_tools",
    "section_tools",
    "frontmatter_tools",
]
