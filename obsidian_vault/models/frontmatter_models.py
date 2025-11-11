"""Pydantic input models for frontmatter operations.

This module defines input models for YAML frontmatter management:
- Read frontmatter metadata
- Update frontmatter fields (merge)
- Replace entire frontmatter block
- Delete frontmatter block
"""

from __future__ import annotations

from typing import Any
from pydantic import Field

from .base import BaseNoteInput


class ReadFrontmatterInput(BaseNoteInput):
    """Input model for read_obsidian_frontmatter tool.

    Reads frontmatter metadata without returning the markdown body.

    Examples:
        >>> ReadFrontmatterInput(title="My Note")
        >>> ReadFrontmatterInput(title="Projects/Project Alpha", vault="work")
    """

    # Inherits title and vault from BaseNoteInput
    # No additional fields needed for read operation

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {"title": "My Note", "vault": None},
                {"title": "Projects/Project Alpha", "vault": "work"}
            ]
        }


class UpdateFrontmatterInput(BaseNoteInput):
    """Input model for update_obsidian_frontmatter tool.

    Merges new fields into existing frontmatter block. Creates block if missing.
    Preserves fields not mentioned in the update.

    Examples:
        >>> UpdateFrontmatterInput(title="My Note", frontmatter={"tags": ["python", "mcp"]})
        >>> UpdateFrontmatterInput(title="Note", frontmatter={"status": "complete"}, vault="work")
    """

    frontmatter: dict[str, Any] = Field(
        description=(
            "Fields to upsert into frontmatter. "
            "Recursively merges nested dictionaries. "
            "Lists replace existing lists. "
            "Preserves other fields."
        ),
        examples=[
            {"tags": ["python", "mcp"], "status": "active"},
            {"created": "2025-01-01", "author": "Claude"}
        ]
    )

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "My Note",
                    "frontmatter": {"tags": ["python", "mcp"], "status": "active"},
                    "vault": None
                },
                {
                    "title": "Project Plan",
                    "frontmatter": {"status": "complete", "completed_date": "2025-01-15"},
                    "vault": "work"
                }
            ]
        }


class ReplaceFrontmatterInput(BaseNoteInput):
    """Input model for replace_obsidian_frontmatter tool.

    Replaces entire frontmatter block (destructive). Use when you need exact schema.

    Examples:
        >>> ReplaceFrontmatterInput(title="Note", frontmatter={"tags": ["new"]})
        >>> ReplaceFrontmatterInput(title="Note", frontmatter={})  # Removes block
    """

    frontmatter: dict[str, Any] = Field(
        description=(
            "Complete replacement frontmatter. "
            "Empty dict removes frontmatter block. "
            "All existing fields are discarded."
        ),
        examples=[
            {"tags": ["python"], "version": "1.0"},
            {}  # Removes frontmatter
        ]
    )

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Template Note",
                    "frontmatter": {"tags": ["template"], "version": "1.0"},
                    "vault": None
                },
                {
                    "title": "Old Note",
                    "frontmatter": {},  # Remove frontmatter
                    "vault": "archive"
                }
            ]
        }


class DeleteFrontmatterInput(BaseNoteInput):
    """Input model for delete_obsidian_frontmatter tool.

    Removes the frontmatter block while preserving body content.

    Examples:
        >>> DeleteFrontmatterInput(title="My Note")
        >>> DeleteFrontmatterInput(title="Archive/Old Note", vault="personal")
    """

    # Inherits title and vault from BaseNoteInput
    # No additional fields needed for delete operation

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {"title": "My Note", "vault": None},
                {"title": "Archive/Old Note", "vault": "personal"}
            ]
        }
