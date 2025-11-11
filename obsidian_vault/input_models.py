"""Pydantic input models for MCP tool validation.

This module defines Pydantic models that provide automatic input validation
for all MCP tools. Each model represents the input schema for one or more tools,
with field-level validation, type checking, and descriptive error messages.

Benefits:
- Automatic JSON schema generation for MCP clients
- Field-level validation with detailed error messages
- Type safety at runtime
- Self-documenting API with Field descriptions
- Centralized validation logic

Architecture:
- BaseNoteInput: Common validation for note-related operations
- Specific models inherit from base classes and add tool-specific fields
- Custom validators enforce business rules (e.g., path safety, format constraints)
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class BaseNoteInput(BaseModel):
    """Base model for note operations with common validation.

    Provides standard validation for note identifiers and vault names.
    All note-related input models should inherit from this class.
    """

    title: str = Field(
        min_length=1,
        description=(
            "Note identifier (path without .md extension). "
            "Examples: 'Daily Notes/2025-10-27', 'Projects/New Project'. "
            "Forward slashes for folders, case-sensitive."
        ),
        examples=["Daily Notes/2025-10-27", "Mental Health/Reflections", "README"]
    )

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate note title for safety and format.

        Enforces:
        - Non-empty title
        - No path traversal attempts (.., .)
        - Relative path only (no absolute paths)
        - Strips .md extension if present (normalized internally)

        Args:
            v: The title to validate

        Returns:
            The validated (and potentially normalized) title

        Raises:
            ValueError: If title contains invalid characters or patterns
        """
        # Strip whitespace
        cleaned = v.strip()

        if not cleaned:
            raise ValueError(
                "Note title cannot be empty. "
                "Provide a valid note identifier like 'Daily Notes/2025-10-27'."
            )

        # Check for path traversal attempts
        parts = cleaned.split("/")
        if any(part in {".", ".."} for part in parts):
            raise ValueError(
                "Note title cannot contain '.' or '..' path segments. "
                "These are not allowed for security reasons. "
                f"Invalid title: '{cleaned}'"
            )

        # Check for absolute paths (starting with /)
        if cleaned.startswith("/"):
            raise ValueError(
                "Note title must be a relative path within the vault. "
                "Do not start with '/'. "
                f"Invalid title: '{cleaned}'"
            )

        # Note: We normalize by stripping .md in the validator for user convenience,
        # but the actual path resolution happens in core operations
        if cleaned.endswith(".md"):
            # Strip but return the normalized form
            # This allows users to optionally include .md in their input
            cleaned = cleaned[:-3]

        # Ensure we still have content after stripping
        if not cleaned:
            raise ValueError(
                "Note title cannot be just '.md'. "
                "Provide a valid note name."
            )

        return cleaned

    @field_validator('vault')
    @classmethod
    def validate_vault(cls, v: Optional[str]) -> Optional[str]:
        """Validate vault name format.

        Args:
            v: The vault name to validate

        Returns:
            The validated vault name or None

        Raises:
            ValueError: If vault name is empty string
        """
        if v is not None and not v.strip():
            raise ValueError(
                "Vault name cannot be empty. "
                "Either omit the vault parameter to use the active vault, "
                "or provide a valid vault name from list_vaults()."
            )

        return v.strip() if v else None


class RetrieveNoteInput(BaseNoteInput):
    """Input model for retrieve_obsidian_note tool.

    Retrieves complete note content (full markdown). Can be expensive for
    large notes (5000+ tokens). Consider search_obsidian_content() first
    for preview.

    Examples:
        >>> RetrieveNoteInput(title="Daily Notes/2025-10-27")
        >>> RetrieveNoteInput(title="Projects/My Project", vault="work")
    """

    # Inherits title and vault from BaseNoteInput
    # No additional fields needed for retrieve operation

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Daily Notes/2025-10-27",
                    "vault": None
                },
                {
                    "title": "Mental Health/Reflections Oct 26 2025",
                    "vault": "personal"
                }
            ]
        }
