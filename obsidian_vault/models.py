"""Data models for vault metadata and configuration."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        """Get vault metadata by name.

        Args:
            name: The name of the vault to retrieve.

        Returns:
            VaultMetadata for the requested vault.

        Raises:
            ValueError: If the vault name is not found in configuration.
        """
        try:
            return self.vaults[name]
        except KeyError as exc:
            raise ValueError(f"Unknown vault '{name}'") from exc

    def as_payload(self) -> dict[str, Any]:
        """Return serializable configuration payload.

        Returns:
            Dictionary with default vault name and list of vault metadata.
        """
        return {
            "default": self.default_vault,
            "vaults": [vault.as_payload() for vault in self.vaults.values()],
        }
