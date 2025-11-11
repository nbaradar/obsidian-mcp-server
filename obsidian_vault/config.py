"""Configuration loading and vault registry."""

import logging
from pathlib import Path
import yaml

from obsidian_vault.constants import CONFIG_PATH
from obsidian_vault.data_models import VaultMetadata, VaultConfiguration

logger = logging.getLogger(__name__)


def load_vault_configuration(config_path: Path = CONFIG_PATH) -> VaultConfiguration:
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


# Module-level singleton - loaded once at import time
VAULT_CONFIGURATION = load_vault_configuration()
