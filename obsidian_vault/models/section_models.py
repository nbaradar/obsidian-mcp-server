"""Pydantic input models for section manipulation operations.

This module defines input models for heading-based section operations:
- Insert content after a heading
- Append content to end of section (before subsections)
- Replace entire section content
- Delete heading and its section
"""

from __future__ import annotations

from pydantic import Field, field_validator

from .base import BaseSectionInput


class InsertAfterHeadingInput(BaseSectionInput):
    """Input model for insert_after_heading_obsidian_note tool.

    Inserts content immediately after a heading, before any existing content
    or subsections. Useful for adding intro text to sections.

    Examples:
        >>> InsertAfterHeadingInput(title="My Note", heading="Tasks", content="\\n- New task")
    """

    content: str = Field(
        min_length=1,
        description=(
            "Markdown content to insert after the heading. "
            "Must not be empty."
        )
    )

    @field_validator('content')
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Validate that content is not empty or just whitespace."""
        if not v.strip():
            raise ValueError(
                "Content cannot be empty when inserting after heading. "
                "Provide the text you want to add."
            )
        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Projects/My Project",
                    "heading": "Tasks",
                    "content": "\n- Review code\n- Write tests",
                    "vault": None
                },
                {
                    "title": "Meeting Notes",
                    "heading": "Action Items",
                    "content": "\n**Priority:** Follow up on client feedback",
                    "vault": "work"
                }
            ]
        }


class AppendToSectionInput(BaseSectionInput):
    """Input model for append_to_section_obsidian_note tool.

    Appends content to the end of a section's direct content, placing it right
    before any subsections. Different from insert_after_heading which puts
    content immediately after the heading line.

    Examples:
        >>> AppendToSectionInput(title="Log", heading="Daily", content="\\n- 5pm: Meeting")
    """

    content: str = Field(
        min_length=1,
        description=(
            "Markdown content to append to the section. "
            "Placed at end of section before subsections. "
            "Must not be empty."
        )
    )

    @field_validator('content')
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Validate that content is not empty or just whitespace."""
        if not v.strip():
            raise ValueError(
                "Content cannot be empty when appending to section. "
                "Provide the text you want to add."
            )
        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Daily Log",
                    "heading": "Today",
                    "content": "\n- 5:00 PM: Completed Phase 2 migration",
                    "vault": None
                }
            ]
        }


class ReplaceSectionInput(BaseSectionInput):
    """Input model for replace_section_obsidian_note tool.

    Replaces everything under a heading until the next heading of equal or
    higher level. Preserves the heading itself. Use for rewriting entire sections.

    Examples:
        >>> ReplaceSectionInput(title="Doc", heading="Overview", content="New overview text")
    """

    content: str = Field(
        description=(
            "New content for the section body. "
            "Replaces everything under heading until next same-level heading. "
            "Can be empty to clear section while keeping heading."
        )
    )

    # Note: Unlike append/prepend/insert, we allow empty content here since
    # users might want to clear a section while keeping the heading structure

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Documentation",
                    "heading": "API Reference",
                    "content": "## Endpoints\n\n### GET /api/users\n\nReturns user list.",
                    "vault": None
                },
                {
                    "title": "README",
                    "heading": "Installation",
                    "content": "",  # Clear section
                    "vault": "work"
                }
            ]
        }


class DeleteSectionInput(BaseSectionInput):
    """Input model for delete_section_obsidian_note tool.

    Removes heading and everything under it until the next heading of equal or
    higher level. The heading itself is also deleted.

    Examples:
        >>> DeleteSectionInput(title="Note", heading="Deprecated")
    """

    # Inherits title, heading, and vault from BaseSectionInput
    # No additional fields needed for delete operation

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Project Plan",
                    "heading": "Old Ideas",
                    "vault": None
                },
                {
                    "title": "Archive/Notes",
                    "heading": "Outdated Section",
                    "vault": "personal"
                }
            ]
        }
