"""Core vault operations and validation."""

from pathlib import Path
from obsidian_vault.models import VaultMetadata


def ensure_vault_ready(vault: VaultMetadata) -> None:
    """Ensure the target vault directory is accessible before performing operations.

    Args:
        vault: Metadata describing the vault to use.

    Raises:
        FileNotFoundError: If the vault path does not exist or is not a directory.
    """
    if not vault.path.is_dir():
        raise FileNotFoundError(f"Vault '{vault.name}' is not accessible at {vault.path}")


def normalize_note_identifier(identifier: str) -> Path:
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

    # Strip .md suffix if present for normalization
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]

    parts = cleaned.split("/")
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


def resolve_note_path(vault: VaultMetadata, title: str) -> Path:
    """Resolve a note title to an absolute vault path, enforcing sandbox rules.

    Args:
        vault: Vault metadata.
        title: Note identifier in user-facing form.

    Returns:
        The absolute :class:`Path` to the note inside ``vault``.

    Raises:
        ValueError: If the computed path would escape the vault root.
    """
    relative = normalize_note_identifier(title)
    candidate = (vault.path / relative).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)
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
