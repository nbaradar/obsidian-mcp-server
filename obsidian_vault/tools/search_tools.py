"""Search and discovery tools for Obsidian vault operations.

This module contains all MCP tool wrappers for search and discovery operations:
- list_obsidian_notes: List all notes in vault
- search_obsidian_notes: Search notes by title/path
- search_obsidian_content: Search note contents with snippets
- search_notes_by_tag: Find notes by frontmatter tags
- list_notes_in_folder: List notes in specific folder
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from mcp.server.fastmcp import Context

from obsidian_vault.server import mcp
from obsidian_vault.session import resolve_vault
from obsidian_vault.core.search_operations import (
    search_notes,
    search_note_content,
    search_notes_by_tags,
    list_notes_in_folder,
)
from obsidian_vault.core.note_operations import list_notes

logger = logging.getLogger(__name__)

# ==============================================================================
# DISCOVERY & SEARCH TOOLS
# ==============================================================================


@mcp.tool()
async def list_obsidian_notes(
    vault: Optional[str] = None,
    include_metadata: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """List ALL notes in vault (complete inventory).

    Returns every note path in the vault. For large vaults (100+ notes),
    use search_obsidian_notes() for filtered results.

    Args:
        vault (str, optional): Vault name (omit to use active vault)
        include_metadata (bool): If True, include modified/created/size info

    Returns (without metadata):
        {"vault": str, "notes": [str, ...]}

    Returns (with metadata):
        {
            "vault": str,
            "notes": [
                {
                    "path": str,
                    "modified": str,  # ISO timestamp
                    "created": str,   # ISO timestamp
                    "size": int       # Bytes
                },
                ...
            ]
        }

    Token Cost:
        - Without metadata: 200-2000 tokens (vault size dependent)
        - With metadata: 300-5800 tokens (add ~9 tokens per note)

    Examples:
        - Use when: Need complete vault overview
        - Use include_metadata=True: When need to find recent/large notes
        - Use include_metadata=False: When just browsing note list
    """
    metadata = resolve_vault(vault, ctx)
    return list_notes(metadata, include_metadata=include_metadata)


@mcp.tool()
async def search_obsidian_notes(
    query: str,
    vault: Optional[str] = None,
    include_metadata: bool = False,
    sort_by: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Find notes matching search pattern (efficient, token-optimized).

    Case-insensitive substring search across note paths/titles. Returns only
    matching notes.

    Args:
        query (str): Search string (case-insensitive)
            Examples: "Mental Health", "2025", "Project"
        vault (str, optional): Vault name (omit to use active vault)
        include_metadata (bool): If True, include file metadata
        sort_by (str, optional): Sort by "modified", "created", "size", or "name"
            Default: "name" without metadata, "modified" with metadata

    Returns (without metadata):
        {"vault": str, "query": str, "matches": [str, ...]}

    Returns (with metadata):
        {
            "vault": str,
            "query": str,
            "matches": [
                {"path": str, "modified": str, "created": str, "size": int},
                ...
            ]
        }

    Token Cost:
        - Without metadata: ~200-500 tokens
        - With metadata: ~250-1400 tokens (add ~9 tokens per match)

    Examples:
        - Use when: Looking for notes in folder → query="Mental Health"
        - Use include_metadata=True: To find most recent note in folder
        - Use sort_by="modified": To get chronologically ordered results
        - Don't use: For content search → Use search_obsidian_content()
    """
    metadata = resolve_vault(vault, ctx)
    return search_notes(
        query,
        metadata,
        include_metadata=include_metadata,
        sort_by=sort_by,
    )


@mcp.tool()
async def search_obsidian_content(
    query: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Search note contents and return contextual snippets (token-efficient).

    Searches inside note files and returns up to 3 snippets per file (200 chars
    each, 100 chars context on each side). Returns top 10 files by match count.
    Designed for preview before full retrieval.

    Args:
        query (str): Search string (case-insensitive)
            Examples: "machine learning", "API design"
        vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {
            "vault": str,
            "query": str,
            "results": [
                {
                    "path": str,
                    "match_count": int,
                    "snippets": [str, str, str]  # Up to 3 snippets
                }
            ]  # Up to 10 files, sorted by match_count
        }

    Token Cost: ~800-1500 tokens (vs ~30,000+ to retrieve all matches)

    Examples:
        - Use when: Searching for concepts/topics in notes
        - Use when: Preview before retrieval (saves 90%+ tokens)
        - Workflow: search_obsidian_content() → review snippets → retrieve_obsidian_note()
        - Don't use: Searching titles/paths → Use search_obsidian_notes()
        - Don't use: Need complete text → Use retrieve_obsidian_note() after finding

    Error Handling:
        - Empty query → Error: "Search query cannot be empty"
        - No matches → Returns {"results": []}
        - File read errors → Skips file, continues with others
    """
    metadata = resolve_vault(vault, ctx)
    result = search_note_content(query, metadata)
    logger.info(
        "Content search in vault '%s' for query '%s' matched %s files",
        metadata.name,
        result["query"],
        len(result["results"]),
    )
    return result


@mcp.tool(
    annotations={
        "title": "Search Notes by Tag",
        "readOnlyHint": True,
        "openWorldHint": False,
    }
)
async def search_notes_by_tag(
    tags: list[str],
    vault: Optional[str] = None,
    match_all: bool = False,
    include_metadata: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Search notes by tags using frontmatter-only filtering (token-efficient).

    Loads only note frontmatter to find tagged notes, making it substantially more
    token-efficient than listing all notes and filtering in the client. Supports
    AND/OR semantics, metadata inclusion, and both string and list tag formats.

    Args:
        tags: Tags to search for (case-insensitive).
        vault: Optional vault name; omit to use the active/default vault.
        match_all: When True require all tags; when False match any tag.
        include_metadata: When True include metadata (modified, created, size, tags).
        ctx: Optional FastMCP context for vault resolution.

    Returns:
        Dictionary containing vault name, original tags, match mode, and matches.

    Examples:
        - Use when: "Find notes tagged with machine-learning"
        - Use when: "Show notes tagged both obsidian and mcp" (match_all=True)
        - Use include_metadata=True: Prioritize most recently modified tagged notes
        - Workflow: search_notes_by_tag() → retrieve_obsidian_note() for detail
        - Don't use: Full text search → Use search_obsidian_content()
        - Don't use: Title search → Use search_obsidian_notes()

    Raises:
        ValueError: If no non-empty tags are provided.
    """
    metadata = resolve_vault(vault, ctx)
    result = search_notes_by_tags(
        tags,
        metadata,
        match_all=match_all,
        include_metadata=include_metadata,
    )

    logger.info(
        "Tag search in vault '%s' for tags %s (%s mode) found %d matches",
        metadata.name,
        tags,
        result["match_mode"],
        len(result["matches"]),
    )

    return result


@mcp.tool()
async def list_notes_in_folder(
    folder_path: str,
    vault: Optional[str] = None,
    recursive: bool = False,
    include_metadata: bool = True,
    sort_by: str = "modified",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """List notes in a specific folder (token-efficient, targeted).

    More efficient than list_obsidian_notes() when you know the folder.
    Returns only notes in specified folder, sorted by your preference.

    Args:
        folder_path (str): Folder relative to vault root
            Examples: "Mental Health", "Projects/Tech", "Daily Notes"
        vault (str, optional): Vault name (omit to use active vault)
        recursive (bool): If True, include subfolders (default: False)
        include_metadata (bool): Include file metadata (default: True)
        sort_by (str): Sort by "modified", "created", "size", "name"
            Default: "modified" (most recent first)

    Returns:
        {
            "vault": str,
            "folder": str,
            "notes": [
                {"path": str, "modified": str, "created": str, "size": int},
                ...
            ]
        }

    Token Cost: ~250-800 tokens (scales with folder size, not vault size)

    Examples:
        - Use when: Finding notes in specific folder
        - Use when: Need most recent note in folder
        - Use sort_by="modified": Get chronological order (newest first)
        - Don't use: Searching across vault → Use search_obsidian_notes()

    Error Handling:
        - Folder not found → Error with folder path
        - Empty folder → Returns {"notes": []}
    """
    metadata = resolve_vault(vault, ctx)
    return list_notes_in_folder(
        metadata,
        folder_path=folder_path,
        recursive=recursive,
        include_metadata=include_metadata,
        sort_by=sort_by,
    )
