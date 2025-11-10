"""Section manipulation MCP tools.

This module provides MCP tool wrappers for heading-based section operations:
- Insert content after a heading
- Append content to end of section (before subsections)
- Replace entire section content
- Delete heading and its section

All tools delegate to core operations in obsidian_vault.core.section_operations.
"""
from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context

from obsidian_vault.server import mcp
from obsidian_vault.session import resolve_vault
from obsidian_vault.core.section_operations import (
    insert_after_heading,
    append_to_section,
    replace_section,
    delete_section,
)


# ==============================================================================
# STRUCTURED EDITING (HEADING-BASED)
# ==============================================================================

# Inserts immediately after the matching heading (case-insensitive). ``heading`` should
# omit ``#`` markers. Response echoes the resolved heading title.
@mcp.tool()
async def insert_after_heading_obsidian_note(
    title: str,
    content: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Insert content immediately after a heading.

    Finds heading (case-insensitive) and inserts content right after it,
    before any existing content or subsections.

    Args:
        title (str): Note identifier
        content (str): Markdown to insert
        heading (str): Heading text (case-insensitive, without # markers)
            Examples: "Tasks", "Meeting Notes", "Summary"
            Matches first occurrence at any level
        vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "heading": str, "status": "inserted_after_heading"}

    Examples:
        - Use when: Adding content right after heading
        - Use when: Adding intro text to section
        - Don't use: Adding at end of section → Use append_to_section_obsidian_note()
        - Don't use: Replacing section → Use replace_section_obsidian_note()

    Error Handling:
        - Note not found → Error with note path
        - Heading not found → Error, suggest retrieve_obsidian_note() to see structure
    """
    metadata = resolve_vault(vault, ctx)
    return insert_after_heading(metadata, title, heading, content)


# Appends to the end of the heading's direct section content, just before any nested
# subsections. Response includes ``status: "section_appended"``.
@mcp.tool()
async def append_to_section_obsidian_note(
    title: str,
    content: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append content to end of section (before subsections).

    Adds content to end of heading's direct section content, placing it right
    before any subsections. Different from insert_after_heading which puts
    content immediately after heading line.

    Args:
        title (str): Note identifier
        content (str): Markdown to append
        heading (str): Heading text (case-insensitive, without # markers)
        vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "heading": str, "status": "section_appended"}

    Examples:
        - Use when: Adding to end of section content
        - Use when: Building up section content incrementally
        - Don't use: Adding right after heading → Use insert_after_heading
        - Don't use: Replacing section → Use replace_section_obsidian_note()

    Error Handling:
        - Note not found → Error with note path
        - Heading not found → Error with heading name
    """
    metadata = resolve_vault(vault, ctx)
    return append_to_section(metadata, title, heading, content)


# Replaces the section body beneath a heading until the next equal-or-higher heading.
@mcp.tool()
async def replace_section_obsidian_note(
    title: str,
    content: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace content under heading (until next same-level heading).

    Replaces everything under a heading until next heading of equal or higher
    level. Preserves the heading itself. Use for rewriting entire sections.

    Args:
        title (str): Note identifier
        content (str): New content for section body
        heading (str): Heading text (case-insensitive, without # markers)
        vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "heading": str, "status": "section_replaced"}

    Examples:
        - Use when: Rewriting entire section content
        - Use when: Updating outdated section
        - Don't use: Adding to section → Use append_to_section_obsidian_note()
        - Don't use: Removing section → Use delete_section_obsidian_note()

    Error Handling:
        - Note not found → Error with note path
        - Heading not found → Error, use retrieve_obsidian_note() to see structure
    """
    metadata = resolve_vault(vault, ctx)
    return replace_section(metadata, title, heading, content)


# Deletes a heading and its section content. Useful for removing stale blocks.
@mcp.tool()
async def delete_section_obsidian_note(
    title: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Delete heading and its section (removes heading and all content).

    Removes heading and everything under it until next heading of equal or
    higher level. Heading itself is also deleted.

    Args:
        title (str): Note identifier
        heading (str): Heading text (case-insensitive, without # markers)
        vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "heading": str, "status": "section_deleted"}

    Examples:
        - Use when: Removing obsolete sections
        - Use when: Cleaning up outdated content
        - Don't use: Clearing content but keeping heading → Use replace_section with empty content
        - Don't use: Deleting entire note → Use delete_obsidian_note()

    Error Handling:
        - Note not found → Error with note path
        - Heading not found → Error with heading name
    """
    metadata = resolve_vault(vault, ctx)
    return delete_section(metadata, title, heading)
