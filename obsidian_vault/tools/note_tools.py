"""Note management MCP tools.

This module provides MCP tool wrappers for basic note CRUD operations:
- Retrieve note content
- Create new notes
- Replace note content
- Append to notes
- Prepend to notes
- Move/rename notes
- Delete notes

All tools delegate to core operations in obsidian_vault.core.note_operations.
"""
from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import Context

from obsidian_vault.server import mcp
from obsidian_vault.session import resolve_vault
from obsidian_vault.models import (
    RetrieveNoteInput,
    CreateNoteInput,
    ReplaceNoteInput,
    AppendNoteInput,
    PrependNoteInput,
    MoveNoteInput,
    DeleteNoteInput,
)
from obsidian_vault.core.note_operations import (
    create_note,
    retrieve_note,
    replace_note,
    append_to_note,
    prepend_to_note,
    move_note,
    delete_note,
)


# ==============================================================================
# READ OPERATIONS
# ==============================================================================

# Returns the full markdown body along with metadata. Errors if the note is missing.
@mcp.tool()
async def retrieve_obsidian_note(
    input: RetrieveNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Retrieve complete note content (full markdown).

    Returns entire markdown content of a note. Can be expensive for large
    notes (5000+ tokens). Consider search_obsidian_content() first for preview.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (RetrieveNoteInput): Validated input containing:
            - title (str): Note identifier (path without .md extension)
                Examples: "Daily Notes/2025-10-26"
                         "Mental Health/Reflections Oct 26 2025"
                Forward slashes for folders, case-sensitive
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {
            "vault": str,
            "note": str,
            "path": str,
            "content": str  # Complete markdown content
        }

    Token Cost: Small (500 words) ~1000 tokens, Large (5000+ words) ~8000+ tokens

    Examples:
        - Use when: Need to read full note content
        - Use when: After search to get complete details
        - Workflow: search_obsidian_notes() → retrieve_obsidian_note()
        - Don't use: Just checking if note exists → Use search_obsidian_notes()
        - Don't use: Preview only → Use search_obsidian_content() for snippets

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note not found → Error with note path, use search_obsidian_notes()
        - Vault not accessible → Error with vault path
    """
    metadata = resolve_vault(input.vault, ctx)
    return retrieve_note(metadata, input.title)


# ==============================================================================
# CREATE OPERATIONS
# ==============================================================================

# Creates a new markdown file. ``vault`` defaults to the active session; result is
# ``{"vault", "note", "path", "status"}``.
@mcp.tool()
async def create_obsidian_note(
    input: CreateNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create new note with markdown content (fails if exists).

    Creates markdown file in vault. Automatically creates parent folders if
    needed. Fails if note already exists.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (CreateNoteInput): Validated input containing:
            - title (str): Note identifier (path without .md extension)
                Examples: "Daily Notes/2025-10-27", "Projects/New Project"
                Folders created automatically
            - content (str): Full markdown content (can be empty for blank note)
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "status": "created"}

    Examples:
        - Use when: Creating new note from scratch
        - Use when: User asks to "create", "make", or "start" a note
        - Don't use: Updating existing → Use replace/append_to_obsidian_note()
        - Don't use: Note might exist → Check with search_obsidian_notes() first

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note exists → Error, suggest retrieve_obsidian_note() or replace_obsidian_note()
        - Filesystem permission error → Error with details
    """
    metadata = resolve_vault(input.vault, ctx)
    return create_note(metadata, input.title, input.content)


# ==============================================================================
# UPDATE OPERATIONS
# ==============================================================================

# Moves or renames a note and optionally updates backlinks to preserve consistency.
@mcp.tool()
async def move_obsidian_note(
    input: MoveNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Move or rename a note, optionally updating backlinks.

    Moves a note to a new location and/or renames it. Can optionally update
    all wikilinks ([[link]]) and markdown links ([](link)) that reference
    the old path.

    The input is validated automatically by Pydantic, ensuring both titles
    are valid and different before any processing occurs.

    Args:
        input (MoveNoteInput): Validated input containing:
            - old_title (str): Current note path (without .md)
                Example: "Mental Health/Old Name"
            - new_title (str): New note path (without .md)
                Examples: "Mental Health/New Name" (rename only),
                         "Archive/Old Name" (move only),
                         "Archive/New Name" (move and rename)
            - update_links (bool): If True, update all backlinks to this note
                Default: True (recommended for vault consistency)
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {
            "vault": str,
            "old_path": str,
            "new_path": str,
            "links_updated": int,  # Number of notes with updated links
            "status": "moved"
        }

    Examples:
        - Use when: Renaming note to fix typo
        - Use when: Moving note to different folder
        - Use when: Reorganizing vault structure
        - Use update_links=False: Only if you manage links manually
        - Don't use: For simple content edits (use replace_obsidian_note)

    Error Handling:
        - ValidationError: Invalid title format, empty titles, or titles are the same
        - Old note not found → Error with path
        - New note already exists → Error: "Note already exists at new location"
    """
    metadata = resolve_vault(input.vault, ctx)
    return move_note(metadata, input.old_title, input.new_title, update_links=input.update_links)


# Replaces the entire file contents. The response includes ``status: "replaced"``.
@mcp.tool()
async def replace_obsidian_note(
    input: ReplaceNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace entire note content (overwrites everything).

    Completely replaces note content with new markdown. Use for rewriting or
    major restructuring. For adding content, use append/prepend instead.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (ReplaceNoteInput): Validated input containing:
            - title (str): Note identifier (path without .md extension)
            - content (str): New complete markdown content (can be empty to clear note)
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "status": "replaced"}

    Examples:
        - Use when: Rewriting entire note from scratch
        - Use when: Major restructuring of note
        - Don't use: Adding content → Use append_to_obsidian_note()
        - Don't use: Editing specific section → Use replace_section_obsidian_note()
        - Don't use: Note doesn't exist → Use create_obsidian_note()

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note not found → Error, suggest create_obsidian_note() instead
    """
    metadata = resolve_vault(input.vault, ctx)
    return replace_note(metadata, input.title, input.content)


# Appends raw markdown to the end of a note, auto-inserting a newline when needed.
@mcp.tool()
async def append_to_obsidian_note(
    input: AppendNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append content to end of note (most efficient for additions).

    Adds content to note end, automatically inserting newline separator if
    needed. Most token-efficient way to add content without reading entire note.

    The input is validated automatically by Pydantic, ensuring content is
    not empty before any processing occurs.

    Args:
        input (AppendNoteInput): Validated input containing:
            - title (str): Note identifier
            - content (str): Markdown to append (must not be empty)
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "status": "appended"}

    Token Cost: ~200-400 tokens (scales with appended content only)

    Examples:
        - Use when: Adding entries to logs/journals
        - Use when: Appending tasks to lists
        - Efficiency: append = ~300 tokens vs retrieve-modify-replace = ~8000+ tokens
        - Don't use: Adding to beginning → Use prepend_to_obsidian_note()
        - Don't use: Inserting at specific location → Use insert_after_heading

    Error Handling:
        - ValidationError: Invalid title, empty title, empty content, or path traversal
        - Note not found → Error, suggest create_obsidian_note() instead
    """
    metadata = resolve_vault(input.vault, ctx)
    return append_to_note(metadata, input.title, input.content)


# Inserts raw markdown at the start of the file, preserving existing content.
@mcp.tool()
async def prepend_to_obsidian_note(
    input: PrependNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Prepend content to beginning of note.

    Adds content before existing note content with automatic newline handling.
    Useful for frontmatter, summaries, or reverse chronological entries.

    The input is validated automatically by Pydantic, ensuring content is
    not empty before any processing occurs.

    Args:
        input (PrependNoteInput): Validated input containing:
            - title (str): Note identifier
            - content (str): Markdown to prepend (must not be empty)
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "status": "prepended"}

    Examples:
        - Use when: Adding frontmatter/metadata at top
        - Use when: Latest entries at top (reverse chronological)
        - Don't use: Adding to end → Use append_to_obsidian_note()
        - Don't use: Most cases (append is more common)

    Error Handling:
        - ValidationError: Invalid title, empty title, empty content, or path traversal
        - Note not found → Error, suggest create_obsidian_note()
    """
    metadata = resolve_vault(input.vault, ctx)
    return prepend_to_note(metadata, input.title, input.content)


# ==============================================================================
# DELETE OPERATIONS
# ==============================================================================

# Removes the markdown file entirely. Response includes the filesystem path for logging.
@mcp.tool()
async def delete_obsidian_note(
    input: DeleteNoteInput,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Delete note completely (permanently removes file).

    Permanently removes note file from vault. Cannot be undone through this
    tool. Always confirm with user before calling.

    The input is validated automatically by Pydantic, providing detailed
    error messages for invalid inputs before any processing occurs.

    Args:
        input (DeleteNoteInput): Validated input containing:
            - title (str): Note identifier (path without .md extension)
            - vault (str, optional): Vault name (omit to use active vault)

    Returns:
        {"vault": str, "note": str, "path": str, "status": "deleted"}

    Examples:
        - Use when: User explicitly asks to delete note
        - Always confirm with user before deleting
        - Don't use: Removing section → Use delete_section_obsidian_note()
        - Don't use: Clearing content → Use replace_obsidian_note() with minimal content

    Error Handling:
        - ValidationError: Invalid title format, empty title, or path traversal attempt
        - Note not found → Error, use search_obsidian_notes() to find correct title
        - Filesystem permission error → Error with details
    """
    metadata = resolve_vault(input.vault, ctx)
    return delete_note(metadata, input.title)
