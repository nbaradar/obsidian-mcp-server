"""Module-level constants for the Obsidian MCP server."""

from pathlib import Path

# Configuration
CONFIG_PATH = Path(__file__).parent.parent / "vaults.yaml"

# Limits
MAX_FRONTMATTER_BYTES = 10_240
CHARACTER_LIMIT = 25_000  # For future use

# Logging
LOG_LEVEL = "INFO"
