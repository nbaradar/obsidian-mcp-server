"""Pydantic input models for MCP tool validation.

This package defines Pydantic models that provide automatic input validation
for all MCP tools. Each model represents the input schema for one or more tools,
with field-level validation, type checking, and descriptive error messages.

Benefits:
- Automatic JSON schema generation for MCP clients
- Field-level validation with detailed error messages
- Type safety at runtime
- Self-documenting API with Field descriptions
- Centralized validation logic

Architecture:
- base: Base models (BaseNoteInput, BaseSectionInput) for common validation
- note_models: Input models for note CRUD operations
- section_models: Input models for section manipulation operations

Usage:
    from obsidian_vault.models import RetrieveNoteInput, CreateNoteInput
"""

from .base import BaseNoteInput, BaseSectionInput
from .note_models import (
    RetrieveNoteInput,
    CreateNoteInput,
    ReplaceNoteInput,
    AppendNoteInput,
    PrependNoteInput,
    MoveNoteInput,
    DeleteNoteInput,
)
from .section_models import (
    InsertAfterHeadingInput,
    AppendToSectionInput,
    ReplaceSectionInput,
    DeleteSectionInput,
)

__all__ = [
    # Base models
    "BaseNoteInput",
    "BaseSectionInput",
    # Note CRUD models
    "RetrieveNoteInput",
    "CreateNoteInput",
    "ReplaceNoteInput",
    "AppendNoteInput",
    "PrependNoteInput",
    "MoveNoteInput",
    "DeleteNoteInput",
    # Section manipulation models
    "InsertAfterHeadingInput",
    "AppendToSectionInput",
    "ReplaceSectionInput",
    "DeleteSectionInput",
]
