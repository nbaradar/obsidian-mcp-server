"""Frontmatter management MCP tools.

This module provides MCP tool wrappers for YAML frontmatter operations:
- Read frontmatter metadata
- Update frontmatter fields (merge)
- Replace entire frontmatter block
- Delete frontmatter block

All tools delegate to core operations in obsidian_vault.core.frontmatter_operations.
"""
from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context

from obsidian_vault.server import mcp
from obsidian_vault.session import resolve_vault
from obsidian_vault.models import (
    ReadFrontmatterInput,
    UpdateFrontmatterInput,
    ReplaceFrontmatterInput,
    DeleteFrontmatterInput,
)
from obsidian_vault.core.frontmatter_operations import (
    read_frontmatter,
    update_frontmatter,
    replace_frontmatter,
    delete_frontmatter,
)


# ==============================================================================
# FRONTMATTER OPERATIONS
# ==============================================================================

@mcp.tool()
async def read_obsidian_frontmatter(
    input: ReadFrontmatterInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Read frontmatter metadata without returning the markdown body.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (ReadFrontmatterInput): Validated input containing:
            - title (str): Note identifier (folders separated by /)
            - vault (str, optional): Target vault (omit to use active vault)

    Returns:
        {
            "vault": str,
            "note": str,
            "path": str,
            "frontmatter": dict,
            "has_frontmatter": bool,
            "status": "read"
        }

    Examples:
        - Use when: Checking tags or status fields before editing content
        - Follow-up: Call retrieve_obsidian_note() for full body if needed
        - Empty frontmatter → ``frontmatter`` is ``{}``, ``has_frontmatter`` is False

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note not found → Error with note path
    """
    metadata = resolve_vault(input.vault, ctx)
    return read_frontmatter(metadata, input.title)


@mcp.tool()
async def update_obsidian_frontmatter(
    input: UpdateFrontmatterInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Merge new fields into an existing frontmatter block.

    Creates a frontmatter block when missing. Preserves fields that are not
    mentioned in frontmatter and recursively merges nested dictionaries.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (UpdateFrontmatterInput): Validated input containing:
            - title (str): Note identifier
            - frontmatter (dict): Fields to upsert. Lists replace existing lists.
            - vault (str, optional): Target vault (omit to use active vault)

    Returns:
        {
            "vault": str,
            "note": str,
            "path": str,
            "status": "updated" | "unchanged",
            "fields_updated": list[str],
        }

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Invalid YAML or unsupported types → ValueError with details
        - Frontmatter too large (>10KB) → ValueError
        - Note not found → FileNotFoundError
    """
    metadata = resolve_vault(input.vault, ctx)
    return update_frontmatter(metadata, input.title, input.frontmatter)


@mcp.tool()
async def replace_obsidian_frontmatter(
    input: ReplaceFrontmatterInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace the entire frontmatter block (destructive).

    Use when you need the frontmatter to match an exact schema, such as when
    applying templates or resetting metadata.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (ReplaceFrontmatterInput): Validated input containing:
            - title (str): Note identifier
            - frontmatter (dict): Complete replacement frontmatter. Empty dict removes block.
            - vault (str, optional): Target vault (omit to use active vault)

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note not found → FileNotFoundError
    """
    metadata = resolve_vault(input.vault, ctx)
    return replace_frontmatter(metadata, input.title, input.frontmatter)


@mcp.tool()
async def delete_obsidian_frontmatter(
    input: DeleteFrontmatterInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Remove the frontmatter block while preserving body content.

    Returns status: "no_frontmatter" when the note does not contain a block,
    allowing callers to short-circuit follow-up workflows.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (DeleteFrontmatterInput): Validated input containing:
            - title (str): Note identifier
            - vault (str, optional): Target vault (omit to use active vault)

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note not found → FileNotFoundError
    """
    metadata = resolve_vault(input.vault, ctx)
    return delete_frontmatter(metadata, input.title)
