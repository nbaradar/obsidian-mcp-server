from __future__ import annotations

import logging
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


def update_note(title: str, content: str, vault: VaultMetadata) -> dict[str, Any]:
    """Update an existing markdown note with the given title and new content."""
    _ensure_vault_ready(vault)
    target_path = _resolve_note_path(vault, title)
    if not target_path.is_file():
        raise FileNotFoundError(
            f"Note '{_note_display_name(vault, target_path)}' not found in vault '{vault.name}'."
        )

    target_path.write_text(content, encoding="utf-8")
    logger.info("Updated note '%s' in vault '%s'", _note_display_name(vault, target_path), vault.name)
    return {
        "vault": vault.name,
        "note": _note_display_name(vault, target_path),
        "path": str(target_path),
        "status": "updated",
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
async def update_obsidian_note(
    title: str,
    content: str,
    vault: Optional[str] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Replace a note's contents. If `vault` is omitted the active vault is used (see `set_active_vault`). Use `list_vaults` to discover names."""
    metadata = resolve_vault(vault, ctx)
    return update_note(title, content, metadata)


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

def main():
    #Initialize and run the FastMCP server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
