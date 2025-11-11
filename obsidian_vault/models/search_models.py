"""Pydantic input models for search and discovery operations.

This module defines input models for search and discovery tools:
- List all notes in vault
- Search notes by title/path
- Search note contents with snippets
- Search notes by frontmatter tags
- List notes in specific folder
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ListNotesInput(BaseModel):
    """Input model for list_obsidian_notes tool.

    Lists all notes in vault. For large vaults (100+ notes), use
    search_obsidian_notes() for filtered results.

    Examples:
        >>> ListNotesInput(vault=None, include_metadata=False)
        >>> ListNotesInput(vault="personal", include_metadata=True)
    """

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    include_metadata: bool = Field(
        False,
        description=(
            "If True, include file metadata (modified, created, size) for each note. "
            "Increases token cost by ~9 tokens per note."
        )
    )

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

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {"vault": None, "include_metadata": False},
                {"vault": "personal", "include_metadata": True}
            ]
        }


class SearchNotesInput(BaseModel):
    """Input model for search_obsidian_notes tool.

    Case-insensitive substring search across note paths/titles.
    Returns only matching notes.

    Examples:
        >>> SearchNotesInput(query="Mental Health", vault=None)
        >>> SearchNotesInput(query="2025", include_metadata=True, sort_by="modified")
    """

    query: str = Field(
        min_length=1,
        description=(
            "Search string (case-insensitive). "
            "Searches in note paths and titles. "
            "Examples: 'Mental Health', '2025', 'Project'"
        )
    )

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    include_metadata: bool = Field(
        False,
        description=(
            "If True, include file metadata (modified, created, size) for each match. "
            "Increases token cost."
        )
    )

    sort_by: Optional[str] = Field(
        None,
        description=(
            "Sort results by 'modified', 'created', 'size', or 'name'. "
            "Default: 'name' without metadata, 'modified' with metadata."
        )
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate search query is not empty."""
        if not v.strip():
            raise ValueError(
                "Search query cannot be empty. "
                "Provide a search term to find notes."
            )
        return v.strip()

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

    @field_validator('sort_by')
    @classmethod
    def validate_sort_by(cls, v: Optional[str]) -> Optional[str]:
        """Validate sort_by is one of the allowed values."""
        if v is None:
            return None

        v = v.strip().lower()
        allowed_values = {"modified", "created", "size", "name"}

        if v not in allowed_values:
            raise ValueError(
                f"sort_by must be one of: {', '.join(sorted(allowed_values))}. "
                f"Got: '{v}'"
            )

        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "query": "Mental Health",
                    "vault": None,
                    "include_metadata": False,
                    "sort_by": None
                },
                {
                    "query": "2025",
                    "vault": "personal",
                    "include_metadata": True,
                    "sort_by": "modified"
                }
            ]
        }


class SearchContentInput(BaseModel):
    """Input model for search_obsidian_content tool.

    Searches inside note files and returns contextual snippets. Designed for
    preview before full retrieval.

    Examples:
        >>> SearchContentInput(query="machine learning", vault=None)
        >>> SearchContentInput(query="API design", vault="work")
    """

    query: str = Field(
        min_length=1,
        description=(
            "Search string (case-insensitive). "
            "Searches inside note contents and returns snippets. "
            "Examples: 'machine learning', 'API design'"
        )
    )

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate search query is not empty."""
        if not v.strip():
            raise ValueError(
                "Search query cannot be empty. "
                "Provide a search term to find in note contents."
            )
        return v.strip()

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

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {"query": "machine learning", "vault": None},
                {"query": "API design", "vault": "work"}
            ]
        }


class SearchNotesByTagInput(BaseModel):
    """Input model for search_notes_by_tag tool.

    Searches notes by tags using frontmatter-only filtering. Supports AND/OR
    semantics and both string and list tag formats.

    Examples:
        >>> SearchNotesByTagInput(tags=["machine-learning"], match_all=False)
        >>> SearchNotesByTagInput(tags=["obsidian", "mcp"], match_all=True, include_metadata=True)
    """

    tags: list[str] = Field(
        min_length=1,
        description=(
            "Tags to search for (case-insensitive). "
            "Examples: ['machine-learning'], ['obsidian', 'mcp']"
        )
    )

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    match_all: bool = Field(
        False,
        description=(
            "If True, require all tags (AND logic). "
            "If False, match any tag (OR logic). "
            "Default: False"
        )
    )

    include_metadata: bool = Field(
        False,
        description=(
            "If True, include file metadata (modified, created, size, tags). "
            "Increases token cost."
        )
    )

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags list is not empty and contains valid tags."""
        if not v:
            raise ValueError(
                "Tags list cannot be empty. "
                "Provide at least one tag to search for."
            )

        # Strip whitespace from each tag and filter out empty strings
        cleaned_tags = [tag.strip() for tag in v if tag.strip()]

        if not cleaned_tags:
            raise ValueError(
                "Tags list cannot contain only empty strings. "
                "Provide valid tag names."
            )

        return cleaned_tags

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

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "tags": ["machine-learning"],
                    "vault": None,
                    "match_all": False,
                    "include_metadata": False
                },
                {
                    "tags": ["obsidian", "mcp"],
                    "vault": "personal",
                    "match_all": True,
                    "include_metadata": True
                }
            ]
        }


class ListNotesInFolderInput(BaseModel):
    """Input model for list_notes_in_folder tool.

    Lists notes in a specific folder. More efficient than list_obsidian_notes()
    when you know the folder.

    Examples:
        >>> ListNotesInFolderInput(folder_path="Mental Health", recursive=False)
        >>> ListNotesInFolderInput(folder_path="Projects/Tech", recursive=True, sort_by="modified")
    """

    folder_path: str = Field(
        min_length=1,
        description=(
            "Folder path relative to vault root. "
            "Examples: 'Mental Health', 'Projects/Tech', 'Daily Notes'"
        )
    )

    vault: Optional[str] = Field(
        None,
        description=(
            "Vault name (omit to use active vault). "
            "Use list_vaults() to discover available vaults."
        )
    )

    recursive: bool = Field(
        False,
        description=(
            "If True, include subfolders recursively. "
            "Default: False (only direct children)"
        )
    )

    include_metadata: bool = Field(
        True,
        description=(
            "If True, include file metadata (modified, created, size). "
            "Default: True"
        )
    )

    sort_by: str = Field(
        "modified",
        description=(
            "Sort results by 'modified', 'created', 'size', or 'name'. "
            "Default: 'modified' (most recent first)"
        )
    )

    @field_validator('folder_path')
    @classmethod
    def validate_folder_path(cls, v: str) -> str:
        """Validate folder path is not empty and doesn't contain path traversal."""
        cleaned = v.strip()

        if not cleaned:
            raise ValueError(
                "Folder path cannot be empty. "
                "Provide a valid folder path like 'Mental Health' or 'Projects/Tech'."
            )

        # Check for path traversal attempts
        parts = cleaned.split("/")
        if any(part in {".", ".."} for part in parts):
            raise ValueError(
                "Folder path cannot contain '.' or '..' path segments. "
                "These are not allowed for security reasons. "
                f"Invalid path: '{cleaned}'"
            )

        # Check for absolute paths (starting with /)
        if cleaned.startswith("/"):
            raise ValueError(
                "Folder path must be relative to vault root. "
                "Do not start with '/'. "
                f"Invalid path: '{cleaned}'"
            )

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

    @field_validator('sort_by')
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        """Validate sort_by is one of the allowed values."""
        v = v.strip().lower()
        allowed_values = {"modified", "created", "size", "name"}

        if v not in allowed_values:
            raise ValueError(
                f"sort_by must be one of: {', '.join(sorted(allowed_values))}. "
                f"Got: '{v}'"
            )

        return v

    class Config:
        """Pydantic model configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "folder_path": "Mental Health",
                    "vault": None,
                    "recursive": False,
                    "include_metadata": True,
                    "sort_by": "modified"
                },
                {
                    "folder_path": "Projects/Tech",
                    "vault": "work",
                    "recursive": True,
                    "include_metadata": True,
                    "sort_by": "name"
                }
            ]
        }
