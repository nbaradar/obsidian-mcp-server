"""Pydantic input models for note CRUD operations.

This module defines input models for basic note management operations:
- Retrieve note content
- Create new notes
- Replace note content
- Append to notes
- Prepend to notes
- Move/rename notes
- Delete notes
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from .base import BaseNoteInput


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


class CreateNoteInput(BaseNoteInput):
    """Input model for create_obsidian_note tool.

    Creates a new markdown file with the given content. Fails if the note
    already exists. Parent folders are created automatically.

    Examples:
        >>> CreateNoteInput(title="Projects/New Project", content="# New Project\\n\\nGoals...")
        >>> CreateNoteInput(title="Daily Notes/2025-10-27", content="", vault="personal")
    """

    content: str = Field(
        description=(
            "Full markdown content for the note. "
            "Can be empty string to create a blank note."
        )
    )

    # Note: We allow empty content since users might want to create a blank note
    # and fill it in later. This is a valid use case.

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Projects/New Project",
                    "content": "# New Project\n\nGoals:\n- Goal 1\n- Goal 2",
                    "vault": None
                },
                {
                    "title": "Daily Notes/2025-10-27",
                    "content": "",
                    "vault": "personal"
                }
            ]
        }


class ReplaceNoteInput(BaseNoteInput):
    """Input model for replace_obsidian_note tool.

    Completely replaces note content with new markdown. Use for rewriting
    or major restructuring. For adding content, use append/prepend instead.

    Examples:
        >>> ReplaceNoteInput(title="My Note", content="# Updated\\n\\nNew content")
    """

    content: str = Field(
        description=(
            "New complete markdown content that will replace the existing note. "
            "Can be empty string to clear the note."
        )
    )

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Projects/Old Project",
                    "content": "# Archived Project\n\nThis project has been archived.",
                    "vault": None
                }
            ]
        }


class AppendNoteInput(BaseNoteInput):
    """Input model for append_to_obsidian_note tool.

    Appends content to the end of an existing note. Most token-efficient
    way to add content without reading the entire note first.

    Examples:
        >>> AppendNoteInput(title="Daily Log", content="\\n- 3:00 PM: Meeting notes")
    """

    content: str = Field(
        min_length=1,
        description=(
            "Markdown content to append to the note. "
            "Newline separator is added automatically if needed. "
            "Must not be empty."
        )
    )

    @field_validator('content')
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Validate that content is not empty or just whitespace.

        Args:
            v: The content to validate

        Returns:
            The validated content

        Raises:
            ValueError: If content is empty or only whitespace
        """
        if not v.strip():
            raise ValueError(
                "Content cannot be empty when appending to a note. "
                "Provide the text you want to add to the note."
            )
        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Daily Notes/2025-10-27",
                    "content": "\n## Evening Notes\n\n- Completed project review",
                    "vault": None
                }
            ]
        }


class PrependNoteInput(BaseNoteInput):
    """Input model for prepend_to_obsidian_note tool.

    Prepends content to the beginning of an existing note. Useful for
    frontmatter, summaries, or reverse chronological entries.

    Examples:
        >>> PrependNoteInput(title="Log", content="[2025-10-27] Important update\\n")
    """

    content: str = Field(
        min_length=1,
        description=(
            "Markdown content to prepend to the note. "
            "Newline separator is added automatically if needed. "
            "Must not be empty."
        )
    )

    @field_validator('content')
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        """Validate that content is not empty or just whitespace.

        Args:
            v: The content to validate

        Returns:
            The validated content

        Raises:
            ValueError: If content is empty or only whitespace
        """
        if not v.strip():
            raise ValueError(
                "Content cannot be empty when prepending to a note. "
                "Provide the text you want to add to the beginning of the note."
            )
        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Changelog",
                    "content": "## 2025-10-27\n\n- Added new feature X\n- Fixed bug Y\n\n",
                    "vault": None
                }
            ]
        }


class MoveNoteInput(BaseModel):
    """Input model for move_obsidian_note tool.

    Moves or renames a note, optionally updating all backlinks that reference
    the old path to point to the new path.

    Examples:
        >>> MoveNoteInput(old_title="Old Name", new_title="New Name")
        >>> MoveNoteInput(old_title="Folder/Note", new_title="Archive/Note", update_links=False)
    """

    old_title: str = Field(
        min_length=1,
        description=(
            "Current note identifier (path without .md extension). "
            "Example: 'Mental Health/Old Name'"
        )
    )

    new_title: str = Field(
        min_length=1,
        description=(
            "New note identifier (path without .md extension). "
            "Examples: 'Mental Health/New Name' (rename), "
            "'Archive/Old Name' (move), 'Archive/New Name' (move and rename)"
        )
    )

    update_links: bool = Field(
        True,
        description=(
            "If True, update all wikilinks ([[link]]) and markdown links "
            "that reference the old path. Default: True (recommended for vault consistency)."
        )
    )

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    @field_validator('old_title', 'new_title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate note title using same rules as BaseNoteInput.

        This duplicates the validation from BaseNoteInput because MoveNoteInput
        has two title fields and doesn't inherit from BaseNoteInput.

        Args:
            v: The title to validate

        Returns:
            The validated (and potentially normalized) title

        Raises:
            ValueError: If title contains invalid characters or patterns
        """
        cleaned = v.strip()

        if not cleaned:
            raise ValueError(
                "Note title cannot be empty. "
                "Provide a valid note identifier."
            )

        parts = cleaned.split("/")
        if any(part in {".", ".."} for part in parts):
            raise ValueError(
                "Note title cannot contain '.' or '..' path segments. "
                f"Invalid title: '{cleaned}'"
            )

        if cleaned.startswith("/"):
            raise ValueError(
                "Note title must be a relative path within the vault. "
                f"Invalid title: '{cleaned}'"
            )

        if cleaned.endswith(".md"):
            cleaned = cleaned[:-3]

        if not cleaned:
            raise ValueError("Note title cannot be just '.md'.")

        return cleaned

    @field_validator('vault')
    @classmethod
    def validate_vault(cls, v: Optional[str]) -> Optional[str]:
        """Validate vault name format."""
        if v is not None and not v.strip():
            raise ValueError(
                "Vault name cannot be empty. "
                "Either omit the vault parameter or provide a valid vault name."
            )
        return v.strip() if v else None

    @model_validator(mode='after')
    def validate_titles_different(self) -> 'MoveNoteInput':
        """Validate that old_title and new_title are different.

        Args:
            self: The model instance

        Returns:
            The validated model instance

        Raises:
            ValueError: If old_title equals new_title
        """
        if self.old_title == self.new_title:
            raise ValueError(
                "Old title and new title must be different. "
                f"Both are set to '{self.old_title}'. "
                "If you want to keep the same name, you don't need to move the note."
            )
        return self

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "old_title": "Projects/Old Name",
                    "new_title": "Projects/New Name",
                    "update_links": True,
                    "vault": None
                },
                {
                    "old_title": "Daily Notes/2025-10-27",
                    "new_title": "Archive/Daily/2025-10-27",
                    "update_links": True,
                    "vault": "personal"
                }
            ]
        }


class DeleteNoteInput(BaseNoteInput):
    """Input model for delete_obsidian_note tool.

    Permanently removes a note file from the vault. Cannot be undone through
    this tool. Always confirm with user before calling.

    Examples:
        >>> DeleteNoteInput(title="Old Note")
        >>> DeleteNoteInput(title="Archive/Deprecated", vault="work")
    """

    # Inherits title and vault from BaseNoteInput
    # No additional fields needed for delete operation

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "title": "Temporary Note",
                    "vault": None
                },
                {
                    "title": "Archive/Old Project",
                    "vault": "work"
                }
            ]
        }
