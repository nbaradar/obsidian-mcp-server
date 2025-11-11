"""Base Pydantic models for MCP tool input validation.

This module defines base models that provide common validation patterns
for note and section operations. Other input models inherit from these bases.

Base Models:
- BaseNoteInput: Common validation for note-related operations
- BaseSectionInput: Adds heading validation for section-based operations
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


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


class BaseSectionInput(BaseNoteInput):
    """Base model for section manipulation operations.

    Extends BaseNoteInput with heading validation for heading-based operations.
    All section manipulation tools require a heading to identify the section.
    """

    heading: str = Field(
        min_length=1,
        description=(
            "Heading text to match (case-insensitive, without # markers). "
            "Examples: 'Tasks', 'Meeting Notes', 'Summary'. "
            "Matches first occurrence at any level."
        ),
        examples=["Tasks", "Meeting Notes", "Daily Summary"]
    )

    @field_validator('heading')
    @classmethod
    def validate_heading(cls, v: str) -> str:
        """Validate heading format.

        Strips whitespace and leading # markers. Ensures heading is not empty.

        Args:
            v: The heading to validate

        Returns:
            The validated (and cleaned) heading

        Raises:
            ValueError: If heading is empty after stripping
        """
        # Strip whitespace
        cleaned = v.strip()

        if not cleaned:
            raise ValueError(
                "Heading cannot be empty. "
                "Provide the heading text you want to find (without # markers)."
            )

        # Strip leading # markers if user accidentally included them
        # Users are supposed to provide heading without #, but we'll be forgiving
        while cleaned.startswith("#"):
            cleaned = cleaned[1:].strip()

        if not cleaned:
            raise ValueError(
                "Heading cannot be just '#' markers. "
                "Provide the actual heading text (e.g., 'Tasks', 'Summary')."
            )

        return cleaned
