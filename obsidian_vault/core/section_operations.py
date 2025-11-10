"""Heading-based section manipulation operations."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from obsidian_vault.core.vault_operations import (
    ensure_vault_ready,
    resolve_note_path,
    note_display_name,
)
from obsidian_vault.models import VaultMetadata

logger = logging.getLogger(__name__)

# Pattern for matching markdown headings (H1-H6)
HEADING_PATTERN = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def _normalize_heading_key(value: str) -> str:
    """Normalize heading text for case-insensitive comparisons."""
    return " ".join(value.strip().split()).lower()


def _parse_headings(text: str) -> list[dict[str, Any]]:
    """Return a list of markdown headings with positional metadata.

    Args:
        text: Full markdown document contents.

    Returns:
        A list of dictionaries describing each heading. Each dictionary contains the
        heading level, original title, a normalized lookup key, and byte offsets for
        the heading line.
    """
    headings: list[dict[str, Any]] = []
    for match in HEADING_PATTERN.finditer(text):
        start = match.start()
        end = match.end()

        # Extend end to include trailing newline characters
        if text[end : end + 2] == "\r\n":
            end += 2
        elif end < len(text) and text[end] in ("\n", "\r"):
            end += 1

        title = match.group("title").strip()
        headings.append(
            {
                "level": len(match.group("hashes")),
                "title": title,
                "normalized": _normalize_heading_key(title),
                "start": start,
                "end": end,
            }
        )
    return headings


def _locate_heading(text: str, heading: str) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Find a heading within text, returning metadata and the heading list.

    Args:
        text: Full markdown document contents.
        heading: Heading title to match (case-insensitive, leading ``#`` not required).

    Returns:
        A tuple of ``(match_metadata, index, headings)`` where ``match_metadata`` is
        the dictionary describing the located heading, ``index`` is its position
        within the heading list, and ``headings`` is the full list returned by
        :func:`_parse_headings`.

    Raises:
        ValueError: If no matching heading is found.
    """
    headings = _parse_headings(text)
    normalized_target = _normalize_heading_key(heading)
    for index, info in enumerate(headings):
        if info["normalized"] == normalized_target:
            return info, index, headings
    raise ValueError(f"Heading '{heading}' was not found.")


def _section_bounds(headings: list[dict[str, Any]], index: int, text_length: int) -> tuple[int, int]:
    """Compute the byte offsets for the content belonging to a heading.

    Args:
        headings: Full heading list for the document.
        index: Index into ``headings`` of the heading of interest.
        text_length: Length of the document string.

    Returns:
        A two-element tuple ``(start, end)`` representing the byte offsets that
        bracket the section content for the heading at ``index``. The start offset
        is immediately after the heading line; the end offset is either the next
        heading of equal or higher level, or the end of the document.
    """
    current = headings[index]
    section_start = current["end"]
    for subsequent in headings[index + 1 :]:
        if subsequent["level"] <= current["level"]:
            return section_start, subsequent["start"]
    return section_start, text_length


# ==============================================================================
# SECTION OPERATIONS
# ==============================================================================


def insert_after_heading(
    vault: VaultMetadata,
    title: str,
    heading: str,
    content: str,
) -> dict[str, Any]:
    """Insert content immediately after the specified heading.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        heading: Heading text (case-insensitive, without ``#`` markers).
        content: Markdown fragment to insert after the heading line.

    Returns:
        A dictionary with vault information, note name, heading, and operation status.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, _, _ = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{note_display_name(vault, target_path)}'. "
            "Use `retrieve_obsidian_note` to inspect the note structure."
        ) from exc

    insert_pos = heading_info["end"]
    before = text[:insert_pos]
    after = text[insert_pos:]
    insertion = content

    if insertion:
        if before and not before.endswith("\n") and not insertion.startswith("\n"):
            insertion = "\n" + insertion
        if not insertion.endswith("\n") and after and not after.startswith("\n"):
            insertion = insertion + "\n"

    updated = before + insertion + after
    target_path.write_text(updated, encoding="utf-8")
    note_name = note_display_name(vault, target_path)
    logger.info(
        "Inserted content after heading '%s' in note '%s' (vault '%s')",
        heading_info["title"],
        note_name,
        vault.name,
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "heading": heading_info["title"],
        "status": "inserted_after_heading",
    }


def append_to_section(
    vault: VaultMetadata,
    title: str,
    heading: str,
    content: str,
) -> dict[str, Any]:
    """Append content to the end of a heading's direct section content.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        heading: Heading text (case-insensitive, without ``#`` markers).
        content: Markdown fragment to append within the section.

    Returns:
        A dictionary describing the updated note and the target heading.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, index, headings = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{note_display_name(vault, target_path)}'. "
            "Use `retrieve_obsidian_note` to inspect the note structure."
        ) from exc

    next_heading = headings[index + 1] if index + 1 < len(headings) else None
    insertion_pos = next_heading["start"] if next_heading else len(text)

    section_body = text[heading_info["end"] : insertion_pos]
    before = text[:insertion_pos]
    after = text[insertion_pos:]

    insertion = content.rstrip("\r\n")
    if not insertion:
        # Nothing to append; return unchanged metadata.
        return {
            "vault": vault.name,
            "note": note_display_name(vault, target_path),
            "path": str(target_path),
            "heading": heading_info["title"],
            "status": "section_appended",
        }

    # Ensure there is a newline between existing section body and the appended content.
    if section_body:
        if section_body.endswith("\n\n"):
            insertion = insertion.lstrip("\n")
        elif section_body.endswith("\n"):
            if not insertion.startswith("\n"):
                insertion = "\n" + insertion
        else:
            insertion = "\n\n" + insertion.lstrip("\n")
    else:
        if not before.endswith("\n"):
            insertion = "\n" + insertion.lstrip("\n")

    has_following_content = bool(after)

    if has_following_content:
        if not insertion.endswith("\n"):
            insertion += "\n"
        if not after.startswith(("\n", "\r")):
            insertion += "\n"
    else:
        if not insertion.endswith("\n"):
            insertion += "\n"

    updated = before + insertion + after
    target_path.write_text(updated, encoding="utf-8")
    note_name = note_display_name(vault, target_path)
    logger.info(
        "Appended content to section '%s' in note '%s' (vault '%s')",
        heading_info["title"],
        note_name,
        vault.name,
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "heading": heading_info["title"],
        "status": "section_appended",
    }


def replace_section(
    vault: VaultMetadata,
    title: str,
    heading: str,
    content: str,
) -> dict[str, Any]:
    """Replace the content under a heading until the next heading of equal or higher level.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        heading: Heading text (case-insensitive, without ``#`` markers).
        content: Replacement markdown for the section body.

    Returns:
        A dictionary describing the updated note and target heading.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, index, headings = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{note_display_name(vault, target_path)}'. "
            "Use `retrieve_obsidian_note` to inspect the note structure."
        ) from exc

    section_start, section_end = _section_bounds(headings, index, len(text))
    before = text[:section_start]
    after = text[section_end:]
    replacement = content.rstrip("\r\n")

    if before and replacement and not before.endswith("\n") and not replacement.startswith("\n"):
        replacement = "\n" + replacement

    after = after.lstrip("\r\n")
    has_following_content = bool(after)

    if has_following_content:
        replacement = replacement.rstrip("\n")
        replacement = (replacement + "\n\n") if replacement else "\n\n"
    elif replacement and not replacement.endswith("\n"):
        replacement = replacement + "\n"

    updated = before + replacement + after
    target_path.write_text(updated, encoding="utf-8")
    note_name = note_display_name(vault, target_path)
    logger.info(
        "Replaced section under heading '%s' in note '%s' (vault '%s')",
        heading_info["title"],
        note_name,
        vault.name,
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "heading": heading_info["title"],
        "status": "section_replaced",
    }


def delete_section(
    vault: VaultMetadata,
    title: str,
    heading: str,
) -> dict[str, Any]:
    """Delete a heading and the content belonging to that section.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        heading: Heading text (case-insensitive, without ``#`` markers).

    Returns:
        A dictionary describing the updated note and removed heading.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, index, headings = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{note_display_name(vault, target_path)}'. "
            "Use `retrieve_obsidian_note` to inspect the note structure."
        ) from exc

    section_start, section_end = _section_bounds(headings, index, len(text))
    updated = text[: heading_info["start"]] + text[section_end:]

    # Clean up double blank lines introduced by deletion
    updated = re.sub(r"\n{3,}", "\n\n", updated)

    target_path.write_text(updated, encoding="utf-8")
    note_name = note_display_name(vault, target_path)
    logger.info(
        "Deleted heading '%s' and its section in note '%s' (vault '%s')",
        heading_info["title"],
        note_name,
        vault.name,
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "heading": heading_info["title"],
        "status": "section_deleted",
    }
