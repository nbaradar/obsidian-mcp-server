"""Search and discovery operations for notes."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

import frontmatter
import yaml

from obsidian_vault.core.vault_operations import ensure_vault_ready
from obsidian_vault.core.note_operations import _get_note_metadata, list_notes
from obsidian_vault.data_models import VaultMetadata

logger = logging.getLogger(__name__)


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter metadata and note body from raw text.

    Args:
        text: Raw markdown text, possibly containing a frontmatter block.

    Returns:
        A tuple of ``(metadata, content)`` where ``metadata`` is the parsed YAML
        dictionary (empty when no frontmatter is present) and ``content`` is the
        markdown body without the frontmatter block.

    Raises:
        ValueError: If the frontmatter block exists but cannot be parsed as YAML.
    """
    if not text:
        return {}, ""

    try:
        post = frontmatter.loads(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Frontmatter contains invalid YAML: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unable to parse frontmatter: {exc}") from exc

    metadata = dict(post.metadata or {})

    def _convert(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {k: _convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_convert(item) for item in value]
        return value

    metadata = {key: _convert(value) for key, value in metadata.items()}
    content = post.content if post.content is not None else ""
    return metadata, content


def _resolve_folder_path(vault: VaultMetadata, folder_path: str) -> Path:
    """Resolve a folder path within the vault, enforcing sandbox constraints.

    Args:
        vault: Vault metadata.
        folder_path: Folder path supplied by the caller (relative to vault root).

    Returns:
        Absolute :class:`Path` to the folder inside the vault.

    Raises:
        ValueError: If the folder escapes the vault boundaries.
    """
    candidate = (vault.path / Path(folder_path)).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)
    if not candidate.is_relative_to(vault_root):
        raise ValueError(f"Folder '{folder_path}' escapes vault '{vault.name}'.")
    return candidate


# ==============================================================================
# SEARCH OPERATIONS
# ==============================================================================


def search_notes(
    query: str,
    vault: VaultMetadata,
    include_metadata: bool = False,
    sort_by: Optional[str] = None,
) -> dict[str, Any]:
    """Search within the vault's note identifiers for the provided query.

    Args:
        query: Case-insensitive substring to match against note identifiers.
        vault: Vault metadata.
        include_metadata: When ``True`` include metadata for each match.
        sort_by: Optional sort column when metadata is included (``"modified"``,
            ``"created"``, ``"size"``, ``"name"``). Defaults to modification time when
            metadata is included, or alphabetical order otherwise.

    Returns:
        A dictionary containing the vault name, original query, and matching identifiers.
    """
    listing = list_notes(vault, include_metadata=include_metadata)
    query_lower = query.lower()

    if include_metadata:
        matches = [
            note for note in listing["notes"] if query_lower in note["path"].lower()
        ]

        sort_key = (sort_by or "modified").lower()
        if sort_key == "modified":
            matches.sort(key=lambda item: item["modified"], reverse=True)
        elif sort_key == "created":
            matches.sort(
                key=lambda item: item.get("created", ""),
                reverse=True,
            )
        elif sort_key == "size":
            matches.sort(key=lambda item: item["size"], reverse=True)
        else:
            matches.sort(key=lambda item: item["path"])
    else:
        matches = [
            note for note in listing["notes"] if query_lower in note.lower()
        ]

    return {
        "vault": vault.name,
        "query": query,
        "matches": matches,
    }


def search_note_content(query: str, vault: VaultMetadata) -> dict[str, Any]:
    """Search note file contents for the query and return bounded snippets.

    Args:
        query: Search string (case-insensitive).
        vault: Vault metadata.

    Returns:
        A dictionary containing the normalized query along with a list of match payloads.
        Each payload includes the vault-relative path, a match count, and up to three snippets.

    Raises:
        ValueError: If the query is empty or whitespace.
    """
    ensure_vault_ready(vault)

    trimmed_query = query.strip()
    if not trimmed_query:
        raise ValueError("Search query cannot be empty.")

    query_lower = trimmed_query.lower()
    results: list[dict[str, Any]] = []

    for path in vault.path.rglob("*.md"):
        if not path.is_file():
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            logger.warning(
                "Skipping file '%s' in vault '%s' due to read error: %s",
                path,
                vault.name,
                exc,
            )
            continue

        if not text:
            continue

        text_lower = text.lower()
        match_positions: list[int] = []
        start_index = 0

        while True:
            index = text_lower.find(query_lower, start_index)
            if index == -1:
                break
            match_positions.append(index)
            start_index = index + len(query_lower)

        if not match_positions:
            continue

        snippets: list[str] = []
        for position in match_positions[:3]:
            snippet_start = max(0, position - 100)
            snippet_end = min(len(text), position + len(trimmed_query) + 100)
            snippet = text[snippet_start:snippet_end]

            if snippet_start > 0:
                snippet = "..." + snippet
            if snippet_end < len(text):
                snippet = snippet + "..."

            snippets.append(snippet)

        results.append(
            {
                "path": path.relative_to(vault.path).as_posix(),
                "match_count": len(match_positions),
                "snippets": snippets,
            }
        )

    results.sort(key=lambda item: item["match_count"], reverse=True)

    return {
        "vault": vault.name,
        "query": trimmed_query,
        "results": results[:10],
    }


def search_notes_by_tags(
    tags: list[str],
    vault: VaultMetadata,
    match_all: bool = False,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """Search notes by tags, parsing only frontmatter for efficiency.

    Args:
        tags: List of tags to search for (case-insensitive).
        vault: Vault metadata describing the target vault.
        match_all: When True require all tags; when False match any tag.
        include_metadata: When True include file metadata for each match.

    Returns:
        Dictionary containing the vault name, search parameters, and matches.

    Raises:
        ValueError: If the tags list is empty or contains only whitespace.
    """
    ensure_vault_ready(vault)

    if not tags or not any(tag.strip() for tag in tags):
        raise ValueError("Must specify at least one non-empty tag.")

    normalized_search_tags = [tag.strip().lower() for tag in tags if tag.strip()]
    matches: list[Any] = []

    for note_path in vault.path.rglob("*.md"):
        if not note_path.is_file():
            continue

        try:
            raw_text = note_path.read_text(encoding="utf-8", errors="ignore")
            if not raw_text.lstrip().startswith("---"):
                continue

            metadata, _ = _parse_frontmatter(raw_text)
            note_tags_raw = metadata.get("tags", [])

            if isinstance(note_tags_raw, str):
                note_tags = [note_tags_raw.strip()]
            elif isinstance(note_tags_raw, list):
                note_tags = [str(tag).strip() for tag in note_tags_raw]
            else:
                continue

            normalized_note_tags = [tag.lower() for tag in note_tags if tag]
            if not normalized_note_tags:
                continue

            if match_all:
                has_match = all(
                    search_tag in normalized_note_tags for search_tag in normalized_search_tags
                )
            else:
                has_match = any(
                    search_tag in normalized_note_tags for search_tag in normalized_search_tags
                )

            if not has_match:
                continue

            relative_path = note_path.relative_to(vault.path).with_suffix("")
            if include_metadata:
                file_metadata = _get_note_metadata(note_path)
                file_metadata["path"] = relative_path.as_posix()
                file_metadata["tags"] = note_tags
                matches.append(file_metadata)
            else:
                matches.append(relative_path.as_posix())

        except (OSError, UnicodeDecodeError, ValueError) as exc:
            logger.debug("Skipping file '%s' during tag search: %s", note_path, exc)
            continue

    if include_metadata:
        matches.sort(key=lambda item: item["modified"], reverse=True)
    else:
        matches.sort()

    return {
        "vault": vault.name,
        "tags": tags,
        "match_mode": "all" if match_all else "any",
        "matches": matches,
    }


def list_notes_in_folder(
    vault: VaultMetadata,
    folder_path: str,
    recursive: bool = False,
    include_metadata: bool = True,
    sort_by: str = "modified",
) -> dict[str, Any]:
    """List notes within a specific vault folder with optional metadata.

    Args:
        vault: Vault metadata.
        folder_path: Folder path relative to the vault root.
        recursive: When ``True`` include notes in subdirectories.
        include_metadata: When ``True`` return metadata for each note; otherwise only paths.
        sort_by: Sort column when metadata is included (``"modified"``, ``"created"``,
            ``"size"``, ``"name"``). Defaults to ``"modified"``.

    Returns:
        A dictionary containing the vault name, requested folder path, and list of notes.

    Raises:
        ValueError: If the folder does not exist or escapes the vault root.
    """
    ensure_vault_ready(vault)
    target_folder = _resolve_folder_path(vault, folder_path)

    if not target_folder.is_dir():
        raise ValueError(f"Folder '{folder_path}' not found in vault '{vault.name}'.")

    pattern = "**/*.md" if recursive else "*.md"
    notes: list[Any] = []

    for path in target_folder.glob(pattern):
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
        sort_key = (sort_by or "modified").lower()
        if sort_key == "modified":
            notes.sort(key=lambda item: item["modified"], reverse=True)
        elif sort_key == "created":
            notes.sort(
                key=lambda item: item.get("created", ""),
                reverse=True,
            )
        elif sort_key == "size":
            notes.sort(key=lambda item: item["size"], reverse=True)
        else:
            notes.sort(key=lambda item: item["path"])
    else:
        notes.sort()

    return {
        "vault": vault.name,
        "folder": folder_path,
        "notes": notes,
    }
