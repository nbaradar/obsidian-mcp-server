"""Obsidian Vault MCP Server

Exposes multi-vault Obsidian note management via MCP tools.
Supports CRUD operations, structured heading-based edits, and token-efficient search.

Security: All operations are sandboxed within configured vaults (see vaults.yaml).
Session state: Active vault selection persists per MCP connection.
"""
from __future__ import annotations

import logging
import re
import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional
import platform

import frontmatter
import yaml
from mcp.server.fastmcp import Context, FastMCP

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("obsidian_vault")

# Constants
CONFIG_PATH = Path(__file__).with_name("vaults.yaml")
MAX_FRONTMATTER_BYTES = 10_240


@dataclass(frozen=True)
class VaultMetadata:
    """Normalized metadata describing an Obsidian vault."""

    name: str
    path: Path
    description: str
    exists: bool

    def as_payload(self) -> dict[str, Any]:
        """Return a serializable payload representation."""
        return {
            "name": self.name,
            "path": str(self.path),
            "description": self.description,
            "exists": self.path.is_dir(),
        }


class VaultConfiguration:
    """Holds vault metadata and default resolution helpers.

    Loaded once at module initialization from vaults.yaml.
    Provides vault lookup by name and payload serialization for MCP responses.
    """

    def __init__(self, default_vault: str, vaults: dict[str, VaultMetadata]) -> None:
        self.default_vault = default_vault
        self.vaults = vaults

    def get(self, name: str) -> VaultMetadata:
        try:
            return self.vaults[name]
        except KeyError as exc:
            raise ValueError(f"Unknown vault '{name}'") from exc

    def as_payload(self) -> dict[str, Any]:
        return {
            "default": self.default_vault,
            "vaults": [vault.as_payload() for vault in self.vaults.values()],
        }


def _load_vaults_config(config_path: Path = CONFIG_PATH) -> VaultConfiguration:
    """Load and validate the vault configuration file.

    Args:
        config_path: Path to the YAML configuration file. Defaults to ``vaults.yaml``
        next to this module.

    Returns:
        A fully populated :class:`VaultConfiguration` containing normalized vault
        metadata and the configured default vault name.

    Raises:
        FileNotFoundError: If the configuration file is missing.
        ValueError: If the file exists but does not provide the expected structure
            (missing default, empty mapping, invalid entries, etc.).
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Vault configuration file not found at {config_path}")

    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    vaults_section = raw_config.get("vaults")
    if not isinstance(vaults_section, dict) or not vaults_section:
        raise ValueError("Vault configuration must include a non-empty 'vaults' mapping")

    processed: dict[str, VaultMetadata] = {}
    for name, entry in vaults_section.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Vault '{name}' must map to a dictionary of settings")

        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"Vault '{name}' is missing a valid 'path' string")

        resolved_path = Path(raw_path).expanduser()
        try:
            resolved_path = resolved_path.resolve(strict=False)
        except RuntimeError:
            # resolve can raise if underlying filesystem is inaccessible; fall back to expanded path
            resolved_path = resolved_path

        description = entry.get("description", "").strip()
        exists = resolved_path.is_dir()

        processed[name] = VaultMetadata(
            name=name,
            path=resolved_path,
            description=description,
            exists=exists,
        )

    default_vault = raw_config.get("default")
    if not isinstance(default_vault, str) or default_vault not in processed:
        raise ValueError("Vault configuration must specify a 'default' vault present in the mapping")

    return VaultConfiguration(default_vault=default_vault, vaults=processed)


VAULT_CONFIGURATION = _load_vaults_config()
ACTIVE_VAULTS: Dict[int, str] = {}


def _session_key(ctx: Context) -> int:
    """Produce a stable per-session key for active vault tracking.

    Args:
        ctx: The request context supplied by FastMCP.

    Returns:
        An integer derived from the underlying session object identity. This value
        remains stable for the lifetime of the MCP session and is suitable as a
        dictionary key.
    """
    return id(ctx.session)


def set_active_vault_for_session(ctx: Context, vault_name: str) -> VaultMetadata:
    """Set the active vault for a client session.

    Args:
        ctx: The request context supplied by FastMCP.
        vault_name: Friendly vault name as defined in ``vaults.yaml``.

    Returns:
        The :class:`VaultMetadata` associated with ``vault_name``.

    Raises:
        ValueError: If ``vault_name`` is not present in the allow list.
    """
    metadata = VAULT_CONFIGURATION.get(vault_name)
    ACTIVE_VAULTS[_session_key(ctx)] = metadata.name
    return metadata


def get_active_vault_for_session(ctx: Context) -> VaultMetadata:
    """Retrieve the active vault for a session, falling back to the default.

    Args:
        ctx: The request context supplied by FastMCP.

    Returns:
        The :class:`VaultMetadata` representing the currently selected vault, or the
        configuration default if the session has not yet selected one.
    """
    vault_name = ACTIVE_VAULTS.get(_session_key(ctx), VAULT_CONFIGURATION.default_vault)
    return VAULT_CONFIGURATION.get(vault_name)


def resolve_vault(vault: Optional[str], ctx: Optional[Context] = None) -> VaultMetadata:
    """Resolve which vault metadata should be used for an operation.

    Args:
        vault: Optional friendly vault name provided directly by the caller.
        ctx: Optional FastMCP context used to infer the active vault when ``vault``
            is not supplied.

    Returns:
        The resolved :class:`VaultMetadata`.

    Raises:
        ValueError: If the supplied ``vault`` name is not recognized.
    """
    if vault:
        return VAULT_CONFIGURATION.get(vault)

    if ctx is not None:
        return get_active_vault_for_session(ctx)

    return VAULT_CONFIGURATION.get(VAULT_CONFIGURATION.default_vault)

def _ensure_vault_ready(vault: VaultMetadata) -> None:
    """Ensure the target vault directory is accessible before performing operations.

    Args:
        vault: Metadata describing the vault to use.

    Raises:
        FileNotFoundError: If the vault path does not exist or is not a directory.
    """
    if not vault.path.is_dir():
        raise FileNotFoundError(f"Vault '{vault.name}' is not accessible at {vault.path}")


def _normalize_note_identifier(identifier: str) -> Path:
    """Normalize user-provided note identifiers to a safe, relative markdown path.

    Args:
        identifier: Note identifier supplied by the caller. May include relative
            folder segments or the ``.md`` suffix.

    Returns:
        A :class:`Path` pointing to the markdown file within the vault (relative).

    Raises:
        ValueError: If the identifier is empty, contains reserved path segments, or
            resolves outside of the vault namespace.
    """
    cleaned = identifier.strip()
    if not cleaned:
        raise ValueError("Note title cannot be empty.")

    if cleaned.lower().endswith(".md"):
        cleaned = cleaned[: -len(".md")]

    parts = [segment.strip() for segment in cleaned.split("/") if segment.strip()]
    if not parts:
        raise ValueError("Note title must contain at least one valid segment.")
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Note title cannot contain '.' or '..' segments.")

    leaf = parts[-1]
    leaf_with_extension = f"{leaf}.md"
    if len(parts) == 1:
        relative = Path(leaf_with_extension)
    else:
        relative = Path(*parts[:-1]) / leaf_with_extension
    if relative.is_absolute():
        raise ValueError("Note title must be a relative path within the vault.")

    return relative


def _resolve_note_path(vault: VaultMetadata, title: str) -> Path:
    """Resolve a note title to an absolute vault path, enforcing sandbox rules.

    Args:
        vault: Vault metadata.
        title: Note identifier in user-facing form.

    Returns:
        The absolute :class:`Path` to the note inside ``vault``.

    Raises:
        ValueError: If the computed path would escape the vault root.
    """
    relative = _normalize_note_identifier(title)
    candidate = (vault.path / relative).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)
    if not candidate.is_relative_to(vault_root):
        raise ValueError("Note path escapes the configured vault.")
    return candidate


def _note_display_name(vault: VaultMetadata, path: Path) -> str:
    """Convert a note path into a normalized display name without extension.

    Args:
        vault: Vault metadata.
        path: Absolute path to the note within the vault.

    Returns:
        A forward-slash separated string suitable for UI display.
    """
    relative = path.relative_to(vault.path).with_suffix("")
    return relative.as_posix()


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
    """Load a note and parse its frontmatter."""
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    try:
        raw_text = target_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Note '{_note_display_name(vault, target_path)}' is not UTF-8 encoded and cannot be processed."
        ) from exc

    metadata, content = _parse_frontmatter(raw_text)
    has_frontmatter = _frontmatter_present(raw_text, content)
    return target_path, metadata, content, has_frontmatter


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


HEADING_PATTERN = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)


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


def create_note(title: str, content: str, vault: VaultMetadata) -> dict[str, Any]:
    """Create a markdown note with the given title and content.

    Args:
        title: Human-friendly note identifier; folders can be expressed with ``/``.
        content: Markdown body to write into the new file.
        vault: Vault metadata describing where the note should reside.

    Returns:
        A dictionary describing the created note (vault name, note identifier, full
        path, and status).

    Raises:
        FileExistsError: If the note already exists.
        FileNotFoundError: If the vault directory is missing.
        ValueError: If ``title`` fails normalization (e.g., traversal attempt).
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        raise FileExistsError(
            f"Note '{_note_display_name(vault, target_path)}' already exists in vault '{vault.name}'."
        )

    target_path.write_text(content, encoding="utf-8")
    logger.info("Created note '%s' in vault '%s'", _note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "created",
    }


def retrieve_note(title: str, vault: VaultMetadata) -> dict[str, Any]:
    """Retrieve the content of a markdown note.

    Args:
        title: Note identifier.
        vault: Vault metadata.

    Returns:
        A dictionary containing vault metadata plus the raw note content.

    Raises:
        FileNotFoundError: If the note cannot be located.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    content = target_path.read_text(encoding="utf-8")
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "content": content,
    }


def replace_note(title: str, content: str, vault: VaultMetadata) -> dict[str, Any]:
    """Replace the entire content of an existing markdown note.

    Args:
        title: Note identifier.
        content: New markdown body that will replace the previous contents.
        vault: Vault metadata.

    Returns:
        A dictionary describing the updated note.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    target_path.write_text(content, encoding="utf-8")
    logger.info("Replaced note '%s' in vault '%s'", _note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "replaced",
    }


def append_note(title: str, content: str, vault: VaultMetadata) -> dict[str, Any]:
    """Append content to the end of a markdown note.

    Args:
        title: Note identifier.
        content: Markdown fragment to append.
        vault: Vault metadata.

    Returns:
        A dictionary describing the resulting note.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    existing = target_path.read_text(encoding="utf-8")
    updated = _combine_with_newline(existing, content)
    target_path.write_text(updated, encoding="utf-8")
    logger.info("Appended content to note '%s' in vault '%s'", _note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "appended",
    }


def prepend_note(title: str, content: str, vault: VaultMetadata) -> dict[str, Any]:
    """Prepend content to the beginning of a markdown note.

    Args:
        title: Note identifier.
        content: Markdown fragment to insert before the current body.
        vault: Vault metadata.

    Returns:
        A dictionary describing the resulting note.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    existing = target_path.read_text(encoding="utf-8")
    updated = _combine_with_newline(content, existing)
    target_path.write_text(updated, encoding="utf-8")
    logger.info("Prepended content to note '%s' in vault '%s'", _note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "prepended",
    }


def insert_after_heading(
    title: str,
    content: str,
    heading: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Insert content immediately after the specified heading.

    Args:
        title: Note identifier.
        content: Markdown fragment to insert after the heading line.
        heading: Heading text (case-insensitive, without ``#`` markers).
        vault: Vault metadata.

    Returns:
        A dictionary with vault information, note name, heading, and operation status.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, _, _ = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{_note_display_name(vault, target_path)}'. "
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
    note_name = _note_display_name(vault, target_path)
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
    title: str,
    content: str,
    heading: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Append content to the end of a heading's direct section content.

    Args:
        title: Note identifier.
        content: Markdown fragment to append within the section.
        heading: Heading text (case-insensitive, without ``#`` markers).
        vault: Vault metadata.

    Returns:
        A dictionary describing the updated note and the target heading.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, index, headings = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{_note_display_name(vault, target_path)}'. "
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
            "note": _note_display_name(vault, target_path),
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
    note_name = _note_display_name(vault, target_path)
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
    title: str,
    content: str,
    heading: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Replace the content under a heading until the next heading of equal or higher level.

    Args:
        title: Note identifier.
        content: Replacement markdown for the section body.
        heading: Heading text (case-insensitive, without ``#`` markers).
        vault: Vault metadata.

    Returns:
        A dictionary describing the updated note and target heading.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, index, headings = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{_note_display_name(vault, target_path)}'. "
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
    note_name = _note_display_name(vault, target_path)
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
    title: str,
    heading: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Delete a heading and the content belonging to that section.

    Args:
        title: Note identifier.
        heading: Heading text (case-insensitive, without ``#`` markers).
        vault: Vault metadata.

    Returns:
        A dictionary describing the updated note and removed heading.

    Raises:
        FileNotFoundError: If the note does not exist.
        ValueError: If the heading cannot be located.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    text = target_path.read_text(encoding="utf-8")
    try:
        heading_info, index, headings = _locate_heading(text, heading)
    except ValueError as exc:
        raise ValueError(
            f"Heading '{heading}' not found in note '{_note_display_name(vault, target_path)}'. "
            "Use `retrieve_obsidian_note` to inspect the note structure."
        ) from exc

    section_start, section_end = _section_bounds(headings, index, len(text))
    updated = text[: heading_info["start"]] + text[section_end:]

    # Clean up double blank lines introduced by deletion
    updated = re.sub(r"\n{3,}", "\n\n", updated)

    target_path.write_text(updated, encoding="utf-8")
    note_name = _note_display_name(vault, target_path)
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


def delete_note(title: str, vault: VaultMetadata) -> dict[str, Any]:
    """Delete a markdown note with the given title.

    Args:
        title: Note identifier.
        vault: Vault metadata.

    Returns:
        A dictionary summarizing the deletion.

    Raises:
        FileNotFoundError: If the note does not exist.
    """
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    target_path.unlink(missing_ok=False)
    logger.info("Deleted note '%s' in vault '%s'", _note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "deleted",
    }


def move_note(
    old_title: str,
    new_title: str,
    vault: VaultMetadata,
    update_links: bool = True,
) -> dict[str, Any]:
    """Move or rename a note, optionally updating backlinks across the vault.

    Args:
        old_title: Current note identifier (without ``.md``).
        new_title: Desired note identifier (without ``.md``).
        vault: Vault metadata.
        update_links: When ``True`` update wikilinks/markdown links referencing the note.

    Returns:
        A dictionary summarizing the operation outcome, including the number of notes that
        required backlink adjustments.

    Raises:
        FileNotFoundError: If the original note cannot be located.
        FileExistsError: If a note already exists at the new location.
        ValueError: If either identifier fails sandbox validation.
    """
    _ensure_vault_ready(vault)
    old_path = _resolve_note_path(vault, old_title)
    new_path = _resolve_note_path(vault, new_title)

    if not old_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, old_path)}' not found in vault '{vault.name}'."
        )

    if old_path == new_path:
        links_updated = 0
        if update_links:
            links_updated = _update_backlinks(
                vault,
                _note_display_name(vault, old_path),
                _note_display_name(vault, new_path),
            )
        return {
            "vault": vault.name,
            "old_path": _note_display_name(vault, old_path),
            "new_path": _note_display_name(vault, new_path),
            "links_updated": links_updated,
            "status": "moved",
        }

    if new_path.exists():
        raise FileExistsError(
            f"Note '{_note_display_name(vault, new_path)}' already exists in vault '{vault.name}'."
        )

    new_path.parent.mkdir(parents=True, exist_ok=True)

    old_display = _note_display_name(vault, old_path)
    old_path.rename(new_path)

    links_updated = 0
    if update_links:
        links_updated = _update_backlinks(vault, old_display, _note_display_name(vault, new_path))

    logger.info(
        "Moved note from '%s' to '%s' in vault '%s' (%d links updated)",
        old_display,
        _note_display_name(vault, new_path),
        vault.name,
        links_updated,
    )

    return {
        "vault": vault.name,
        "old_path": old_display,
        "new_path": _note_display_name(vault, new_path),
        "links_updated": links_updated,
        "status": "moved",
    }


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
    _ensure_vault_ready(vault)

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
    _ensure_vault_ready(vault)

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


def list_notes_in_folder_core(
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
    _ensure_vault_ready(vault)
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
    _ensure_vault_ready(vault)

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


def read_frontmatter(
    title: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Return frontmatter metadata without reading the entire note."""
    target_path, metadata, _, has_frontmatter = _load_note_frontmatter(vault, title)
    note_name = _note_display_name(vault, target_path)
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
    title: str,
    frontmatter_payload: dict[str, Any],
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Merge provided metadata with existing frontmatter."""
    if not isinstance(frontmatter_payload, dict):
        raise ValueError("Frontmatter update payload must be a dictionary.")

    updates = copy.deepcopy(frontmatter_payload)
    _ensure_valid_yaml(updates)

    target_path, current_metadata, content, _ = _load_note_frontmatter(vault, title)
    merged = _deep_merge_dicts(current_metadata, updates)

    if merged == current_metadata:
        note_name = _note_display_name(vault, target_path)
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

    note_name = _note_display_name(vault, target_path)
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
    title: str,
    frontmatter_payload: dict[str, Any],
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Overwrite the frontmatter block entirely."""
    if not isinstance(frontmatter_payload, dict):
        raise ValueError("Frontmatter replacement payload must be a dictionary.")

    replacement = copy.deepcopy(frontmatter_payload)
    _ensure_valid_yaml(replacement)

    target_path, _, content, has_frontmatter = _load_note_frontmatter(vault, title)
    serialized = _serialize_frontmatter(replacement, content)
    target_path.write_text(serialized, encoding="utf-8")
    note_name = _note_display_name(vault, target_path)

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


def delete_frontmatter_block(
    title: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Remove the frontmatter block entirely."""
    target_path, metadata, content, has_frontmatter = _load_note_frontmatter(vault, title)
    note_name = _note_display_name(vault, target_path)

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

# MCP tools
# ==============================================================================
# VAULT MANAGEMENT
# ==============================================================================


# Returns ``{"default", "active", "vaults"}``. ``ctx`` may be omitted when called outside
# a request (e.g., CLI).
@mcp.tool()
async def list_vaults(ctx: Context | None = None) -> dict[str, Any]:
    """List configured Obsidian vaults and current session state.
    
    Returns metadata for all configured vaults including the default vault
    and currently active vault for this session. Primary entry point for
    vault discovery.
    
    Returns:
        {
            "default": str,    # System default vault name
            "active": str,     # Currently active vault (or None)
            "vaults": [
                {
                    "name": str,
                    "path": str,
                    "description": str,
                    "exists": bool
                }
            ]
        }
    
    Examples:
        - Use when: Starting conversation, need to see available vaults
        - Use when: User mentions vault by name, verify it exists
        - Don't use: Already know vault name and just need to switch
    
    Error Handling:
        - Config file missing → Error with expected config path
        - Invalid config format → Error describing expected YAML structure
    """
    active = None
    if ctx is not None:
        try:
            active = get_active_vault_for_session(ctx).name
        except ValueError:
            active = None

    return {
        "default": VAULT_CONFIGURATION.default_vault,
        "active": active,
        "vaults": [metadata.as_payload() for metadata in VAULT_CONFIGURATION.vaults.values()],
    }


# Expects a friendly vault name defined in ``vaults.yaml``. Response mirrors
# ``list_vaults`` payloads so callers can confirm the active vault.
@mcp.tool()
async def set_active_vault(vault: str, ctx: Context) -> dict[str, Any]:
    """Set the active vault for this conversation session.
    
    All subsequent tool calls that omit the vault parameter will use the
    active vault. Session state persists for the conversation lifetime.
    
    Args:
        vault (str): Friendly vault name from vaults.yaml
            Examples: "nader", "work", "personal"
            Use list_vaults() to discover valid names
    
    Returns:
        {"vault": str, "path": str, "status": "active"}
    
    Examples:
        - Use when: User says "switch to my work vault"
        - Use when: Starting multi-operation workflow in one vault
        - Don't use: Single operation in another vault (pass vault param directly)
    
    Error Handling:
        - Unknown vault → Error listing available vaults, suggest list_vaults()
        - Vault path inaccessible → Error with specific path that failed
    """
    metadata = set_active_vault_for_session(ctx, vault)
    logger.info("Active vault for session %s set to '%s'", _session_key(ctx), metadata.name)
    return {
        "vault": metadata.name,
        "path": str(metadata.path),
        "status": "active",
    }

# ==============================================================================
# DISCOVERY & SEARCH
# ==============================================================================

# Lists normalized note identifiers (folder segments + basename without ``.md``).
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

# Performs case-insensitive substring matching across note identifiers. Supports
# optional metadata payloads and sorting when ``include_metadata`` is ``True``.
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

# Searches note contents and returns up to 10 files, each with a match count and up to
# three 200-character snippets. Designed for token-efficient previews.
# Provides targeted folder listings to avoid large vault scans. Defaults to
# returning metadata sorted by latest modification time.
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
    return list_notes_in_folder_core(
        metadata,
        folder_path=folder_path,
        recursive=recursive,
        include_metadata=include_metadata,
        sort_by=sort_by,
    )

# Searches note contents and returns up to 10 files, each with a match count and up to
# three 200-character snippets. Designed for token-efficient previews.
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

# ==============================================================================
# READ OPERATIONS
# ==============================================================================

# Returns the full markdown body along with metadata. Errors if the note is missing.
@mcp.tool()
async def retrieve_obsidian_note(
    title: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Retrieve complete note content (full markdown).
    
    Returns entire markdown content of a note. Can be expensive for large
    notes (5000+ tokens). Consider search_obsidian_content() first for preview.
    
    Args:
        title (str): Note identifier (path without .md extension)
            Examples: "Daily Notes/2025-10-26"
                     "Mental Health/Reflections Oct 26 2025"
            Forward slashes for folders, case-sensitive
        vault (str, optional): Vault name (omit to use active vault)
    
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
        - Note not found → Error with note path, use search_obsidian_notes()
        - Invalid title (../) → Error: "Note title cannot contain '..'"
        - Vault not accessible → Error with vault path
    """
    metadata = resolve_vault(vault, ctx)
    return retrieve_note(title, metadata)

# ==============================================================================
# CREATE OPERATIONS
# ==============================================================================

# Creates a new markdown file. ``vault`` defaults to the active session; result is
# ``{"vault", "note", "path", "status"}``.
@mcp.tool()
async def create_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create new note with markdown content (fails if exists).
    
    Creates markdown file in vault. Automatically creates parent folders if
    needed. Fails if note already exists.
    
    Args:
        title (str): Note identifier (path without .md extension)
            Examples: "Daily Notes/2025-10-27", "Projects/New Project"
            Folders created automatically
        content (str): Full markdown content
        vault (str, optional): Vault name (omit to use active vault)
    
    Returns:
        {"vault": str, "note": str, "path": str, "status": "created"}
    
    Examples:
        - Use when: Creating new note from scratch
        - Use when: User asks to "create", "make", or "start" a note
        - Don't use: Updating existing → Use replace/append_to_obsidian_note()
        - Don't use: Note might exist → Check with search_obsidian_notes() first
    
    Error Handling:
        - Note exists → Error, suggest retrieve_obsidian_note() or replace_obsidian_note()
        - Invalid title → Error describing issue
        - Filesystem permission error → Error with details
    """
    metadata = resolve_vault(vault, ctx)
    return create_note(title, content, metadata)

# ==============================================================================
# UPDATE OPERATIONS
# ==============================================================================

# Moves or renames a note and optionally updates backlinks to preserve consistency.
@mcp.tool()
async def move_obsidian_note(
    old_title: str,
    new_title: str,
    update_links: bool = True,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Move or rename a note, optionally updating backlinks.
    
    Moves a note to a new location and/or renames it. Can optionally update
    all wikilinks ([[link]]) and markdown links ([](link)) that reference
    the old path.
    
    Args:
        old_title (str): Current note path (without .md)
            Example: "Mental Health/Old Name"
        new_title (str): New note path (without .md)
            Examples: 
                "Mental Health/New Name" (rename only)
                "Archive/Old Name" (move only)
                "Archive/New Name" (move and rename)
        update_links (bool): If True, update all backlinks to this note
            Default: True (recommended for vault consistency)
        vault (str, optional): Vault name (omit to use active vault)
    
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
        - Old note not found → Error with path
        - New note already exists → Error: "Note already exists at new location"
        - Invalid paths → Error describing issue
    """    
    metadata = resolve_vault(vault, ctx)
    return move_note(old_title, new_title, metadata, update_links=update_links)

# Replaces the entire file contents. The response includes ``status: "replaced"``.
@mcp.tool()
async def replace_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace entire note content (overwrites everything).
    
    Completely replaces note content with new markdown. Use for rewriting or
    major restructuring. For adding content, use append/prepend instead.
    
    Args:
        title (str): Note identifier (path without .md extension)
        content (str): New complete markdown content
        vault (str, optional): Vault name (omit to use active vault)
    
    Returns:
        {"vault": str, "note": str, "path": str, "status": "replaced"}
    
    Examples:
        - Use when: Rewriting entire note from scratch
        - Use when: Major restructuring of note
        - Don't use: Adding content → Use append_to_obsidian_note()
        - Don't use: Editing specific section → Use replace_section_obsidian_note()
        - Don't use: Note doesn't exist → Use create_obsidian_note()
    
    Error Handling:
        - Note not found → Error, suggest create_obsidian_note() instead
        - Invalid title → Error describing issue
    """
    metadata = resolve_vault(vault, ctx)
    return replace_note(title, content, metadata)

# Appends raw markdown to the end of a note, auto-inserting a newline when needed.
@mcp.tool()
async def append_to_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append content to end of note (most efficient for additions).
    
    Adds content to note end, automatically inserting newline separator if
    needed. Most token-efficient way to add content without reading entire note.
    
    Args:
        title (str): Note identifier
        content (str): Markdown to append
        vault (str, optional): Vault name (omit to use active vault)
    
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
        - Note not found → Error, suggest create_obsidian_note() instead
    """
    metadata = resolve_vault(vault, ctx)
    return append_note(title, content, metadata)

# Inserts raw markdown at the start of the file, preserving existing content.
@mcp.tool()
async def prepend_to_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Prepend content to beginning of note.
    
    Adds content before existing note content with automatic newline handling.
    Useful for frontmatter, summaries, or reverse chronological entries.
    
    Args:
        title (str): Note identifier
        content (str): Markdown to prepend
        vault (str, optional): Vault name (omit to use active vault)
    
    Returns:
        {"vault": str, "note": str, "path": str, "status": "prepended"}
    
    Examples:
        - Use when: Adding frontmatter/metadata at top
        - Use when: Latest entries at top (reverse chronological)
        - Don't use: Adding to end → Use append_to_obsidian_note()
        - Don't use: Most cases (append is more common)
    
    Error Handling:
        - Note not found → Error, suggest create_obsidian_note()
    """
    metadata = resolve_vault(vault, ctx)
    return prepend_note(title, content, metadata)

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
    return insert_after_heading(title, content, heading, metadata)


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
    return append_to_section(title, content, heading, metadata)


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
    return replace_section(title, content, heading, metadata)


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
    return delete_section(title, heading, metadata)

# ==============================================================================
# FRONTMATTER OPERATIONS
# ==============================================================================

@mcp.tool()
async def read_obsidian_frontmatter(
    title: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Read frontmatter metadata without returning the markdown body.

    Args:
        title (str): Note identifier (folders separated by ``/``).
        vault (str, optional): Target vault; omit to use the active vault.

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
    """
    metadata = resolve_vault(vault, ctx)
    return read_frontmatter(title, metadata)


@mcp.tool()
async def update_obsidian_frontmatter(
    title: str,
    frontmatter: dict[str, Any],
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Merge new fields into an existing frontmatter block.

    Creates a frontmatter block when missing. Preserves fields that are not
    mentioned in ``frontmatter`` and recursively merges nested dictionaries.

    Args:
        title (str): Note identifier.
        frontmatter (dict): Fields to upsert. Lists replace existing lists.

    Returns:
        {
            "vault": str,
            "note": str,
            "path": str,
            "status": "updated" | "unchanged",
            "fields_updated": list[str],
        }

    Error Handling:
        - Invalid YAML or unsupported types → ValueError with details
        - Frontmatter too large (>10KB) → ValueError
        - Note not found → FileNotFoundError
    """
    metadata = resolve_vault(vault, ctx)
    return update_frontmatter(title, frontmatter, metadata)


@mcp.tool()
async def replace_obsidian_frontmatter(
    title: str,
    frontmatter: dict[str, Any],
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace the entire frontmatter block (destructive).

    Use when you need the frontmatter to match an exact schema, such as when
    applying templates or resetting metadata.

    Args:
        title (str): Note identifier.
        frontmatter (dict): Complete replacement frontmatter. Empty dict removes block.
    """
    metadata = resolve_vault(vault, ctx)
    return replace_frontmatter(title, frontmatter, metadata)


@mcp.tool()
async def delete_obsidian_frontmatter(
    title: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Remove the frontmatter block while preserving body content.

    Returns ``status: "no_frontmatter"`` when the note does not contain a block,
    allowing callers to short-circuit follow-up workflows.
    """
    metadata = resolve_vault(vault, ctx)
    return delete_frontmatter_block(title, metadata)

# ==============================================================================
# DELETE OPERATIONS
# ==============================================================================

# Removes the markdown file entirely. Response includes the filesystem path for logging.
@mcp.tool()
async def delete_obsidian_note(
    title: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Delete note completely (permanently removes file).
    
    Permanently removes note file from vault. Cannot be undone through this
    tool. Always confirm with user before calling.
    
    Args:
        title (str): Note identifier (path without .md extension)
        vault (str, optional): Vault name (omit to use active vault)
    
    Returns:
        {"vault": str, "note": str, "path": str, "status": "deleted"}
    
    Examples:
        - Use when: User explicitly asks to delete note
        - Always confirm with user before deleting
        - Don't use: Removing section → Use delete_section_obsidian_note()
        - Don't use: Clearing content → Use replace_obsidian_note() with minimal content
    
    Error Handling:
        - Note not found → Error, use search_obsidian_notes() to find correct title
        - Filesystem permission error → Error with details
    """
    metadata = resolve_vault(vault, ctx)
    return delete_note(title, metadata)

def main():
    #Initialize and run the FastMCP server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
