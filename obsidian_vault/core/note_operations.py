"""Core business logic for note CRUD operations."""

from __future__ import annotations

import logging
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from obsidian_vault.core.vault_operations import (
    ensure_vault_ready,
    resolve_note_path,
    note_display_name,
)
from obsidian_vault.data_models import VaultMetadata

logger = logging.getLogger(__name__)


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def _combine_with_newline(left: str, right: str) -> str:
    """Concatenate two strings, inserting a single newline between them when needed.

    Args:
        left: Existing text.
        right: Text to append.

    Returns:
        The combined text with at most one newline separating the segments.
    """
    if not left:
        return right
    if not right:
        return left
    if not left.endswith("\n") and not right.startswith("\n"):
        return f"{left}\n{right}"
    return left + right


def _get_note_metadata(note_path: Path) -> dict[str, Any]:
    """Extract filesystem metadata for a note in a cross-platform friendly way.

    Args:
        note_path: Absolute path to the markdown file.

    Returns:
        A dictionary containing modification timestamp, optional creation timestamp,
        and file size in bytes.
    """
    stat = note_path.stat()
    metadata: dict[str, Any] = {
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "size": stat.st_size,
    }

    system = platform.system()
    if system in ("Darwin", "Windows"):
        metadata["created"] = datetime.fromtimestamp(stat.st_ctime).isoformat()
    elif hasattr(stat, "st_birthtime"):
        metadata["created"] = datetime.fromtimestamp(stat.st_birthtime).isoformat()

    return metadata


def _update_backlinks(
    vault: VaultMetadata,
    old_title: str,
    new_title: str,
) -> int:
    """Update wikilinks and markdown links that reference a note.

    Args:
        vault: Vault metadata.
        old_title: Previous note identifier (without ``.md``).
        new_title: New note identifier (without ``.md``).

    Returns:
        Number of notes that were modified.
    """
    wikilink_pattern = re.compile(
        r"\[\[" + re.escape(old_title) + r"(?P<alias>\|[^\]]+)?\]\]"
    )
    markdown_link_pattern = re.compile(
        r"\[(?P<label>[^\]]+)\]\(" + re.escape(old_title) + r"(?P<ext>\.md)?\)"
    )

    updated_count = 0

    for note_path in vault.path.rglob("*.md"):
        if not note_path.is_file():
            continue

        try:
            content = note_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read note '%s' while updating backlinks: %s", note_path, exc)
            continue

        updated_content = content
        updated_content = wikilink_pattern.sub(
            lambda match: f"[[{new_title}{match.group('alias') or ''}]]",
            updated_content,
        )

        def _markdown_replacer(match: re.Match[str]) -> str:
            ext = match.group("ext") or ""
            return f"[{match.group('label')}]({new_title}{ext})"

        updated_content = markdown_link_pattern.sub(_markdown_replacer, updated_content)

        if updated_content != content:
            try:
                note_path.write_text(updated_content, encoding="utf-8")
                updated_count += 1
            except OSError as exc:
                logger.warning(
                    "Failed to write updated backlinks to '%s': %s",
                    note_path,
                    exc,
                )

    return updated_count


# ==============================================================================
# NOTE OPERATIONS
# ==============================================================================


def create_note(vault: VaultMetadata, title: str, content: str) -> dict[str, Any]:
    """Create a markdown note with the given title and content.

    Args:
        vault: Vault metadata describing where the note should reside.
        title: Human-friendly note identifier; folders can be expressed with ``/``.
        content: Markdown body to write into the new file.

    Returns:
        A dictionary describing the created note (vault name, note identifier, full
        path, and status).

    Raises:
        FileExistsError: If the note already exists.
        FileNotFoundError: If the vault directory is missing.
        ValueError: If ``title`` fails normalization (e.g., traversal attempt).
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        raise FileExistsError(
            f"Note '{note_display_name(vault, target_path)}' already exists in vault '{vault.name}'."
        )

    target_path.write_text(content, encoding="utf-8")
    logger.info("Created note '%s' in vault '%s'", note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "created",
    }


def retrieve_note(vault: VaultMetadata, title: str) -> dict[str, Any]:
    """Retrieve the content of a markdown note.

    Args:
        vault: Vault metadata.
        title: Note identifier.

    Returns:
        A dictionary containing vault metadata plus the raw note content.

    Raises:
        FileNotFoundError: If the note cannot be located.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    content = target_path.read_text(encoding="utf-8")
    return {
        "vault": vault.name,
        "note": note_display_name(vault, target_path),
        "path": str(target_path),
        "content": content,
    }


def replace_note(vault: VaultMetadata, title: str, content: str) -> dict[str, Any]:
    """Replace the entire content of an existing markdown note.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        content: New markdown body that will replace the previous contents.

    Returns:
        A dictionary describing the updated note.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    target_path.write_text(content, encoding="utf-8")
    logger.info("Replaced note '%s' in vault '%s'", note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "replaced",
    }


def append_to_note(vault: VaultMetadata, title: str, content: str) -> dict[str, Any]:
    """Append content to the end of a markdown note.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        content: Markdown fragment to append.

    Returns:
        A dictionary describing the resulting note.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    existing = target_path.read_text(encoding="utf-8")
    updated = _combine_with_newline(existing, content)
    target_path.write_text(updated, encoding="utf-8")
    logger.info("Appended content to note '%s' in vault '%s'", note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "appended",
    }


def prepend_to_note(vault: VaultMetadata, title: str, content: str) -> dict[str, Any]:
    """Prepend content to the beginning of a markdown note.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        content: Markdown fragment to insert before the current body.

    Returns:
        A dictionary describing the resulting note.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    existing = target_path.read_text(encoding="utf-8")
    updated = _combine_with_newline(content, existing)
    target_path.write_text(updated, encoding="utf-8")
    logger.info("Prepended content to note '%s' in vault '%s'", note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "prepended",
    }


def delete_note(vault: VaultMetadata, title: str) -> dict[str, Any]:
    """Delete a markdown note with the given title.

    Args:
        vault: Vault metadata.
        title: Note identifier.

    Returns:
        A dictionary summarizing the deletion.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    target_path.unlink(missing_ok=False)
    logger.info("Deleted note '%s' in vault '%s'", note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "deleted",
    }


def move_note(
    vault: VaultMetadata,
    old_title: str,
    new_title: str,
    update_links: bool = True,
) -> dict[str, Any]:
    """Move or rename a note, optionally updating backlinks across the vault.

    Args:
        vault: Vault metadata.
        old_title: Current note identifier (without ``.md``).
        new_title: Desired note identifier (without ``.md``).
        update_links: When ``True`` update wikilinks/markdown links referencing the note.

    Returns:
        A dictionary summarizing the operation outcome, including the number of notes that
        required backlink adjustments.

    Raises:
        FileNotFoundError: If the original note cannot be located.
        FileExistsError: If a note already exists at the new location.
        ValueError: If either identifier fails sandbox validation.
    """
    ensure_vault_ready(vault)
    old_path = resolve_note_path(vault, old_title)
    new_path = resolve_note_path(vault, new_title)

    if not old_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, old_path)}' not found in vault '{vault.name}'."
        )

    if old_path == new_path:
        links_updated = 0
        if update_links:
            links_updated = _update_backlinks(
                vault,
                note_display_name(vault, old_path),
                note_display_name(vault, new_path),
            )
        return {
            "vault": vault.name,
            "old_path": note_display_name(vault, old_path),
            "new_path": note_display_name(vault, new_path),
            "links_updated": links_updated,
            "status": "moved",
        }

    if new_path.exists():
        raise FileExistsError(
            f"Note '{note_display_name(vault, new_path)}' already exists in vault '{vault.name}'."
        )

    new_path.parent.mkdir(parents=True, exist_ok=True)

    old_display = note_display_name(vault, old_path)
    old_path.rename(new_path)

    links_updated = 0
    if update_links:
        links_updated = _update_backlinks(vault, old_display, note_display_name(vault, new_path))

    logger.info(
        "Moved note from '%s' to '%s' in vault '%s' (%d links updated)",
        old_display,
        note_display_name(vault, new_path),
        vault.name,
        links_updated,
    )

    return {
        "vault": vault.name,
        "old_path": old_display,
        "new_path": note_display_name(vault, new_path),
        "links_updated": links_updated,
        "status": "moved",
    }


def list_notes(vault: VaultMetadata, include_metadata: bool = False) -> dict[str, Any]:
    """List all note titles in the Obsidian vault.

    Args:
        vault: Vault metadata.
        include_metadata: When ``True`` each entry contains metadata (modified, created,
            size). Otherwise, only normalized note paths are returned.

    Returns:
        A dictionary containing the vault name and note list. Notes are sorted
        alphabetically when metadata is excluded, or by most recent modification when
        metadata is included.
    """
    ensure_vault_ready(vault)

    notes: list[Any] = []
    for path in vault.path.rglob("*.md"):
        if not path.is_file():
            continue

        relative = path.relative_to(vault.path).with_suffix("")
        if include_metadata:
            metadata = _get_note_metadata(path)
            metadata["path"] = relative.as_posix()
            notes.append(metadata)
        else:
            notes.append(relative.as_posix())

    if include_metadata:
        notes.sort(key=lambda item: item["modified"], reverse=True)
    else:
        notes.sort()

    return {
        "vault": vault.name,
        "notes": notes,
    }
