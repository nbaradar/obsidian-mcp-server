from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from mcp.server.fastmcp import Context, FastMCP

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("obsidian_vault")

# Constants
CONFIG_PATH = Path(__file__).with_name("vaults.yaml")


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
    """Holds vault metadata and default resolution helpers."""

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
    """Load the vault configuration from disk."""
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
    """Produce a stable per-session key for active vault tracking."""
    return id(ctx.session)


def set_active_vault_for_session(ctx: Context, vault_name: str) -> VaultMetadata:
    """Set the active vault for the given session."""
    metadata = VAULT_CONFIGURATION.get(vault_name)
    ACTIVE_VAULTS[_session_key(ctx)] = metadata.name
    return metadata


def get_active_vault_for_session(ctx: Context) -> VaultMetadata:
    """Retrieve the active vault for the session, falling back to the default."""
    vault_name = ACTIVE_VAULTS.get(_session_key(ctx), VAULT_CONFIGURATION.default_vault)
    return VAULT_CONFIGURATION.get(vault_name)


def resolve_vault(vault: Optional[str], ctx: Optional[Context] = None) -> VaultMetadata:
    """Resolve which vault metadata should be used for an operation."""
    if vault:
        return VAULT_CONFIGURATION.get(vault)

    if ctx is not None:
        return get_active_vault_for_session(ctx)

    return VAULT_CONFIGURATION.get(VAULT_CONFIGURATION.default_vault)

def _ensure_vault_ready(vault: VaultMetadata) -> None:
    """Ensure the target vault directory is available before performing operations."""
    if not vault.path.is_dir():
        raise FileNotFoundError(f"Vault '{vault.name}' is not accessible at {vault.path}")


def _normalize_note_identifier(identifier: str) -> Path:
    """Normalize user-provided note identifiers to a safe relative markdown path."""
    cleaned = identifier.strip()
    if not cleaned:
        raise ValueError("Note title cannot be empty.")

    if cleaned.endswith(".md"):
        cleaned = cleaned[: -len(".md")]

    parts = [segment.strip() for segment in cleaned.split("/") if segment.strip()]
    if not parts:
        raise ValueError("Note title must contain at least one valid segment.")
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Note title cannot contain '.' or '..' segments.")

    relative = Path(*parts).with_suffix(".md")
    if relative.is_absolute():
        raise ValueError("Note title must be a relative path within the vault.")

    return relative


def _resolve_note_path(vault: VaultMetadata, title: str) -> Path:
    """Resolve a note title to an absolute path within the vault, enforcing sandbox rules."""
    relative = _normalize_note_identifier(title)
    candidate = (vault.path / relative).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)
    if not candidate.is_relative_to(vault_root):
        raise ValueError("Note path escapes the configured vault.")
    return candidate


def _note_display_name(vault: VaultMetadata, path: Path) -> str:
    """Convert a note path into a normalized display name without extension."""
    relative = path.relative_to(vault.path).with_suffix("")
    return relative.as_posix()


def _combine_with_newline(left: str, right: str) -> str:
    """Concatenate two strings, inserting a newline between them when needed."""
    if not left:
        return right
    if not right:
        return left
    if not left.endswith("\n") and not right.startswith("\n"):
        return f"{left}\n{right}"
    return left + right


HEADING_PATTERN = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)


def _normalize_heading_key(value: str) -> str:
    """Normalize heading text for case-insensitive comparisons."""
    return " ".join(value.strip().split()).lower()


def _parse_headings(text: str) -> list[dict[str, Any]]:
    """Return a list of headings with positional metadata."""
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
    """Find a heading within the given text, returning metadata and position index."""
    headings = _parse_headings(text)
    normalized_target = _normalize_heading_key(heading)
    for index, info in enumerate(headings):
        if info["normalized"] == normalized_target:
            return info, index, headings
    raise ValueError(f"Heading '{heading}' was not found.")


def _section_bounds(headings: list[dict[str, Any]], index: int, text_length: int) -> tuple[int, int]:
    """Compute the content boundaries for the heading's section."""
    current = headings[index]
    section_start = current["end"]
    for subsequent in headings[index + 1 :]:
        if subsequent["level"] <= current["level"]:
            return section_start, subsequent["start"]
    return section_start, text_length


def create_note(title: str, content: str, vault: VaultMetadata) -> dict[str, Any]:
    """Create a markdown note with the given title and content."""
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
    """Retrieve the content of a markdown note with the given title."""
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
    """Replace the entire content of an existing markdown note."""
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
    """Append content to the end of a markdown note."""
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
    """Prepend content to the beginning of a markdown note."""
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
    """Insert content immediately after the specified heading."""
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


def replace_section(
    title: str,
    content: str,
    heading: str,
    vault: VaultMetadata,
) -> dict[str, Any]:
    """Replace the content under a heading (until the next heading of same or higher level)."""
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
    replacement = content

    if replacement:
        if before and not before.endswith("\n") and not replacement.startswith("\n"):
            replacement = "\n" + replacement
        if not replacement.endswith("\n") and after and not after.startswith("\n"):
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
    """Delete a heading and its section content."""
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
    """Delete a markdown note with the given title."""
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


def list_notes(vault: VaultMetadata) -> dict[str, Any]:
    """List all note titles in the Obsidian vault."""
    _ensure_vault_ready(vault)
    markdown_files = [
        path.relative_to(vault.path).with_suffix("")
        for path in vault.path.rglob("*.md")
        if path.is_file()
    ]

    notes = sorted(str(note.as_posix()) for note in markdown_files)
    return {
        "vault": vault.name,
        "notes": notes,
    }


def search_notes(query: str, vault: VaultMetadata) -> dict[str, Any]:
    """Search within the vault's note names for the provided query."""
    listing = list_notes(vault)
    query_lower = query.lower()
    matches = [note for note in listing["notes"] if query_lower in note.lower()]
    return {
        "vault": vault.name,
        "query": query,
        "matches": matches,
    }


def search_note_content(query: str, vault: VaultMetadata) -> dict[str, Any]:
    """Search note file contents for the query and return bounded snippets."""
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

# MCP tools
@mcp.tool()
async def list_vaults(ctx: Context | None = None) -> dict[str, Any]:
    """List configured Obsidian vaults and connection defaults. Use this to discover valid vault names."""
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


@mcp.tool()
async def set_active_vault(vault: str, ctx: Context) -> dict[str, Any]:
    """Set the active vault for this connection. Use `list_vaults` to discover valid names."""
    metadata = set_active_vault_for_session(ctx, vault)
    logger.info("Active vault for session %s set to '%s'", _session_key(ctx), metadata.name)
    return {
        "vault": metadata.name,
        "path": str(metadata.path),
        "status": "active",
    }


@mcp.tool()
async def create_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create a note. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return create_note(title, content, metadata)


@mcp.tool()
async def retrieve_obsidian_note(
    title: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Retrieve a note. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return retrieve_note(title, metadata)


@mcp.tool()
async def replace_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace a note's entire content. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return replace_note(title, content, metadata)


@mcp.tool()
async def append_to_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append content to a note. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return append_note(title, content, metadata)


@mcp.tool()
async def prepend_to_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Prepend content to a note. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return prepend_note(title, content, metadata)


@mcp.tool()
async def insert_after_heading_obsidian_note(
    title: str,
    content: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Insert content immediately after a heading (case-insensitive). If `vault` is omitted the active vault is used (see `set_active_vault`). Use `retrieve_obsidian_note` to inspect headings and `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return insert_after_heading(title, content, heading, metadata)


@mcp.tool()
async def replace_section_obsidian_note(
    title: str,
    content: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace the content under a heading (case-insensitive). If `vault` is omitted the active vault is used (see `set_active_vault`). Use `retrieve_obsidian_note` to inspect headings and `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return replace_section(title, content, heading, metadata)


@mcp.tool()
async def delete_section_obsidian_note(
    title: str,
    heading: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Delete a heading and its section (case-insensitive). If `vault` is omitted the active vault is used (see `set_active_vault`). Use `retrieve_obsidian_note` to inspect headings and `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return delete_section(title, heading, metadata)


@mcp.tool()
async def delete_obsidian_note(
    title: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Delete a note. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return delete_note(title, metadata)


@mcp.tool()
async def list_obsidian_notes(
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """List notes. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return list_notes(metadata)


@mcp.tool()
async def search_obsidian_notes(
    query: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Search note names. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return search_notes(query, metadata)


@mcp.tool()
async def search_obsidian_content(
    query: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Search note contents for snippets. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    result = search_note_content(query, metadata)
    logger.info(
        "Content search in vault '%s' for query '%s' matched %s files",
        metadata.name,
        result["query"],
        len(result["results"]),
    )
    return result

def main():
    #Initialize and run the FastMCP server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
