"""YAML frontmatter manipulation operations."""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from obsidian_vault.constants import MAX_FRONTMATTER_BYTES
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


def _serialize_frontmatter(metadata: dict[str, Any], content: str) -> str:
    """Serialize metadata and content back into markdown with optional frontmatter.

    Args:
        metadata: Sanitized frontmatter dictionary. Empty dict removes the block.
        content: Markdown body (without frontmatter).

    Returns:
        Markdown text including a YAML frontmatter block when ``metadata`` is not empty.
    """
    if not metadata:
        return content

    post = frontmatter.Post(content)
    post.metadata.update(metadata)
    return frontmatter.dumps(post)


def _ensure_valid_yaml(metadata: dict[str, Any]) -> None:
    """Validate and sanitize metadata prior to serialization.

    This function mutates ``metadata`` in-place to coerce unsupported values into
    YAML-safe representations (e.g., ``datetime`` → ISO string). It also enforces
    key constraints and a size limit to prevent abusive payloads.

    Args:
        metadata: Mutable dictionary supplied by the caller.

    Raises:
        ValueError: If the metadata is not a mapping, contains invalid keys/types,
            or exceeds the permitted size.
    """
    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter must be a dictionary of key/value pairs.")

    def _sanitize(value: Any, path: str) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (list, tuple)):
            return [_sanitize(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, Mapping):
            nested: dict[str, Any] = {}
            for sub_key, sub_value in value.items():
                if not isinstance(sub_key, str) or not sub_key.strip():
                    raise ValueError(f"Frontmatter key '{path}.{sub_key}' must be a non-empty string.")
                nested[sub_key] = _sanitize(sub_value, f"{path}.{sub_key}" if path else sub_key)
            return nested
        raise ValueError(f"Frontmatter field '{path}' uses unsupported type '{type(value).__name__}'.")

    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Frontmatter keys must be non-empty strings.")
        sanitized[key] = _sanitize(value, key)

    try:
        dumped = yaml.safe_dump(sanitized, sort_keys=False)
    except yaml.YAMLError as exc:
        raise ValueError(f"Frontmatter cannot be serialized to YAML: {exc}") from exc

    if len(dumped.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        raise ValueError(
            f"Frontmatter exceeds maximum size of {MAX_FRONTMATTER_BYTES // 1024}KB."
        )

    metadata.clear()
    metadata.update(sanitized)


def _deep_merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries without mutating inputs."""
    merged: dict[str, Any] = copy.deepcopy(base)
    for key, value in updates.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged


def _frontmatter_present(raw_text: str, content: str) -> bool:
    """Return True when ``raw_text`` contained a YAML frontmatter block."""
    if not raw_text:
        return False
    return raw_text.lstrip().startswith("---") and raw_text != content


def _load_note_frontmatter(
    vault: VaultMetadata,
    title: str,
) -> tuple[Path, dict[str, Any], str, bool]:
    """Load a note and parse its frontmatter.

    Args:
        vault: Vault metadata.
        title: Note identifier.

    Returns:
        Tuple of (target_path, metadata, content, has_frontmatter).

    Raises:
        FileNotFoundError: If note doesn't exist.
        ValueError: If note is not UTF-8 encoded.
    """
    ensure_vault_ready(vault)
    target_path = resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    try:
        raw_text = target_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Note '{note_display_name(vault, target_path)}' is not UTF-8 encoded and cannot be processed."
        ) from exc

    metadata, content = _parse_frontmatter(raw_text)
    has_frontmatter = _frontmatter_present(raw_text, content)
    return target_path, metadata, content, has_frontmatter


# ==============================================================================
# FRONTMATTER OPERATIONS
# ==============================================================================


def read_frontmatter(vault: VaultMetadata, title: str) -> dict[str, Any]:
    """Read frontmatter metadata without reading the entire note body.

    Args:
        vault: Vault metadata.
        title: Note identifier.

    Returns:
        Dictionary with vault, note, path, frontmatter, has_frontmatter, and status.
    """
    target_path, metadata, _, has_frontmatter = _load_note_frontmatter(vault, title)
    note_name = note_display_name(vault, target_path)
    logger.info(
        "Read frontmatter for note '%s' in vault '%s' (present=%s)",
        note_name,
        vault.name,
        has_frontmatter,
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "frontmatter": metadata,
        "has_frontmatter": has_frontmatter,
        "status": "read",
    }


def update_frontmatter(
    vault: VaultMetadata,
    title: str,
    frontmatter: dict[str, Any],
) -> dict[str, Any]:
    """Merge new fields into existing frontmatter.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        frontmatter: Fields to merge/update.

    Returns:
        Dictionary with vault, note, path, status, and fields_updated.

    Raises:
        ValueError: If frontmatter is not a dictionary or contains invalid YAML.
    """
    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter update payload must be a dictionary.")

    updates = copy.deepcopy(frontmatter)
    _ensure_valid_yaml(updates)

    target_path, current_metadata, content, _ = _load_note_frontmatter(vault, title)
    merged = _deep_merge_dicts(current_metadata, updates)

    if merged == current_metadata:
        note_name = note_display_name(vault, target_path)
        logger.info(
            "Frontmatter update skipped for note '%s' in vault '%s' (no changes detected)",
            note_name,
            vault.name,
        )
        return {
            "vault": vault.name,
            "note": note_name,
            "path": str(target_path),
            "status": "unchanged",
            "fields_updated": [],
        }

    merged_sanitized = copy.deepcopy(merged)
    _ensure_valid_yaml(merged_sanitized)

    note_name = note_display_name(vault, target_path)
    serialized = _serialize_frontmatter(merged_sanitized, content)
    target_path.write_text(serialized, encoding="utf-8")

    changed_fields = sorted(updates.keys())

    logger.info(
        "Frontmatter updated for note '%s' in vault '%s' (fields=%s)",
        note_name,
        vault.name,
        ", ".join(changed_fields) or "none",
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "status": "updated",
        "fields_updated": changed_fields,
    }


def replace_frontmatter(
    vault: VaultMetadata,
    title: str,
    frontmatter: dict[str, Any],
) -> dict[str, Any]:
    """Replace entire frontmatter block.

    Args:
        vault: Vault metadata.
        title: Note identifier.
        frontmatter: Complete replacement frontmatter.

    Returns:
        Dictionary with vault, note, path, status, and had_frontmatter.

    Raises:
        ValueError: If frontmatter is not a dictionary or contains invalid YAML.
    """
    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter replacement payload must be a dictionary.")

    replacement = copy.deepcopy(frontmatter)
    _ensure_valid_yaml(replacement)

    target_path, _, content, has_frontmatter = _load_note_frontmatter(vault, title)
    serialized = _serialize_frontmatter(replacement, content)
    target_path.write_text(serialized, encoding="utf-8")
    note_name = note_display_name(vault, target_path)

    logger.info(
        "Frontmatter replaced for note '%s' in vault '%s' (previously_present=%s)",
        note_name,
        vault.name,
        has_frontmatter,
    )
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "status": "replaced",
        "had_frontmatter": has_frontmatter,
    }


def delete_frontmatter(vault: VaultMetadata, title: str) -> dict[str, Any]:
    """Remove frontmatter block entirely.

    Args:
        vault: Vault metadata.
        title: Note identifier.

    Returns:
        Dictionary with vault, note, path, status, and optionally removed_fields.
    """
    target_path, metadata, content, has_frontmatter = _load_note_frontmatter(vault, title)
    note_name = note_display_name(vault, target_path)

    if not has_frontmatter:
        logger.info(
            "Frontmatter deletion skipped for note '%s' in vault '%s' (no block present)",
            note_name,
            vault.name,
        )
        return {
            "vault": vault.name,
            "note": note_name,
            "path": str(target_path),
            "status": "no_frontmatter",
        }

    serialized = _serialize_frontmatter({}, content)
    target_path.write_text(serialized, encoding="utf-8")

    logger.info("Frontmatter deleted for note '%s' in vault '%s'", note_name, vault.name)
    return {
        "vault": vault.name,
        "note": note_name,
        "path": str(target_path),
        "status": "deleted",
        "removed_fields": sorted(metadata.keys()),
    }
