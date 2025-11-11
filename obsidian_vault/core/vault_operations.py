"""Core vault operations and validation."""

from pathlib import Path
from obsidian_vault.data_models import VaultMetadata


def ensure_vault_ready(vault: VaultMetadata) -> None:
    """Ensure the target vault directory is accessible before performing operations.

    Args:
        vault: Metadata describing the vault to use.

    Raises:
        FileNotFoundError: If the vault path does not exist or is not a directory.
    """
    if not vault.path.is_dir():
        raise FileNotFoundError(f"Vault '{vault.name}' is not accessible at {vault.path}")


def construct_note_path(identifier: str) -> Path:
    """Construct a Path object from a pre-validated note identifier.

    IMPORTANT: This function assumes the identifier has already been validated
    by a Pydantic input model. It only performs path construction, not validation.

    Validation (empty, .md suffix, path traversal, absolute paths) is now handled
    at the MCP tool boundary by Pydantic models in obsidian_vault.models.
    This function focuses solely on path construction for performance.

    Args:
        identifier: Pre-validated note identifier (already stripped, no .md suffix,
            no path traversal, relative path only).

    Returns:
        Path object for the note within the vault (relative, with .md extension).

    Examples:
        >>> construct_note_path("My Note")
        PosixPath('My Note.md')
        >>> construct_note_path("Folder/My Note")
        PosixPath('Folder/My Note.md')
    """
    # Split into path components
    parts = identifier.split("/")

    # Get the leaf (filename) and add .md extension
    leaf = parts[-1]
    leaf_with_extension = f"{leaf}.md"

    # Construct path: single level or nested
    if len(parts) == 1:
        return Path(leaf_with_extension)
    else:
        return Path(*parts[:-1]) / leaf_with_extension


def normalize_note_identifier(identifier: str) -> Path:
    """DEPRECATED: Use construct_note_path() for new code.

    This function is kept for backwards compatibility during the transition period.
    It wraps construct_note_path() but still performs validation for any code
    that hasn't been migrated to use Pydantic input models yet.

    New code should rely on Pydantic validation at the MCP tool boundary and
    call construct_note_path() directly for path construction.

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

    # Strip .md suffix if present for normalization
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]

    parts = cleaned.split("/")
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Note title cannot contain '.' or '..' segments.")

    # Use the new construction function
    relative = construct_note_path(cleaned)

    if relative.is_absolute():
        raise ValueError("Note title must be a relative path within the vault.")

    return relative


def resolve_note_path(vault: VaultMetadata, title: str) -> Path:
    """Resolve a pre-validated note title to an absolute vault path.

    IMPORTANT: Assumes title has been validated by Pydantic input model.
    Only performs path resolution and sandbox enforcement (filesystem-level check).

    Input validation (empty, .md suffix, path traversal, relative path) is handled
    at the MCP tool boundary by Pydantic models. This function focuses on:
    1. Path construction (via construct_note_path)
    2. Filesystem-level sandbox enforcement (ensures path doesn't escape vault)

    Args:
        vault: Vault metadata.
        title: Pre-validated note identifier (from Pydantic model).

    Returns:
        The absolute :class:`Path` to the note inside ``vault``.

    Raises:
        ValueError: If the resolved path escapes the vault root (filesystem check).
    """
    # Construct path from pre-validated identifier (no validation, just construction)
    relative = construct_note_path(title)

    # Resolve to absolute path
    candidate = (vault.path / relative).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)

    # Filesystem-level security check: ensure path doesn't escape vault
    # This is the ONLY validation we keep here - can't be done in Pydantic
    if not candidate.is_relative_to(vault_root):
        raise ValueError("Note path escapes the configured vault.")

    return candidate


def note_display_name(vault: VaultMetadata, path: Path) -> str:
    """Convert a note path into a normalized display name without extension.

    Args:
        vault: Vault metadata.
        path: Absolute path to the note within the vault.

    Returns:
        A forward-slash separated string suitable for UI display.
    """
    relative = path.relative_to(vault.path)
    return str(relative.with_suffix("")).replace("\\", "/")
