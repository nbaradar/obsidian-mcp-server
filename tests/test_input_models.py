"""Tests for Pydantic input models.

This test suite validates the input validation logic for MCP tools,
ensuring that:
- Valid inputs are accepted and normalized correctly
- Invalid inputs raise ValidationError with descriptive messages
- Field-level validation works as expected
- Schema generation produces correct JSON schemas for MCP
"""

import pytest
from pydantic import ValidationError

from obsidian_vault.input_models import (
    BaseNoteInput,
    RetrieveNoteInput,
    CreateNoteInput,
    ReplaceNoteInput,
    AppendNoteInput,
    PrependNoteInput,
    MoveNoteInput,
    DeleteNoteInput,
)


class TestBaseNoteInput:
    """Test suite for BaseNoteInput model validation."""

    def test_valid_simple_title(self):
        """Test that simple valid titles are accepted."""
        model = BaseNoteInput(title="My Note")
        assert model.title == "My Note"
        assert model.vault is None

    def test_valid_nested_title(self):
        """Test that nested paths with folders are accepted."""
        model = BaseNoteInput(title="Daily Notes/2025-10-27")
        assert model.title == "Daily Notes/2025-10-27"

    def test_valid_deeply_nested_title(self):
        """Test that deeply nested paths are accepted."""
        model = BaseNoteInput(title="Projects/2025/Q4/Project Alpha")
        assert model.title == "Projects/2025/Q4/Project Alpha"

    def test_valid_title_with_spaces(self):
        """Test that titles with spaces are accepted."""
        model = BaseNoteInput(title="Mental Health/Reflections Oct 26 2025")
        assert model.title == "Mental Health/Reflections Oct 26 2025"

    def test_valid_title_with_dots_in_name(self):
        """Test that dots within the filename are allowed."""
        model = BaseNoteInput(title="Files/my.config.file")
        assert model.title == "Files/my.config.file"

    def test_title_with_md_extension_is_stripped(self):
        """Test that .md extension is automatically stripped."""
        model = BaseNoteInput(title="My Note.md")
        assert model.title == "My Note"

    def test_nested_title_with_md_extension_is_stripped(self):
        """Test that .md extension is stripped from nested paths."""
        model = BaseNoteInput(title="Daily Notes/2025-10-27.md")
        assert model.title == "Daily Notes/2025-10-27"

    def test_valid_vault_name(self):
        """Test that valid vault names are accepted."""
        model = BaseNoteInput(title="My Note", vault="personal")
        assert model.vault == "personal"

    def test_vault_none_is_accepted(self):
        """Test that vault=None is accepted (uses active vault)."""
        model = BaseNoteInput(title="My Note", vault=None)
        assert model.vault is None

    def test_vault_with_whitespace_is_stripped(self):
        """Test that vault names with leading/trailing whitespace are stripped."""
        model = BaseNoteInput(title="My Note", vault="  personal  ")
        assert model.vault == "personal"

    # Validation Error Tests

    def test_empty_title_raises_error(self):
        """Test that empty titles raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="")

        errors = exc_info.value.errors()
        assert len(errors) >= 1
        # Check that the error mentions title being empty
        error_messages = " ".join(str(e) for e in errors)
        assert "empty" in error_messages.lower()

    def test_whitespace_only_title_raises_error(self):
        """Test that titles with only whitespace raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="   ")

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_title_with_dot_segment_raises_error(self):
        """Test that titles with '.' path segment raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="./My Note")

        errors = exc_info.value.errors()
        assert any("'.'" in str(e) or "'..'" in str(e) for e in errors)

    def test_title_with_dotdot_segment_raises_error(self):
        """Test that titles with '..' path segment raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="../My Note")

        errors = exc_info.value.errors()
        assert any("'.'" in str(e) or "'..'" in str(e) for e in errors)

    def test_title_with_dotdot_in_middle_raises_error(self):
        """Test that '..' in the middle of path raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="Projects/../Secrets")

        errors = exc_info.value.errors()
        assert any("'.'" in str(e) or "'..'" in str(e) for e in errors)

    def test_absolute_path_raises_error(self):
        """Test that absolute paths (starting with /) raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="/etc/passwd")

        errors = exc_info.value.errors()
        error_messages = " ".join(str(e) for e in errors)
        assert "relative" in error_messages.lower()

    def test_only_md_extension_raises_error(self):
        """Test that a title of just '.md' raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title=".md")

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_empty_vault_string_raises_error(self):
        """Test that empty vault string raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="My Note", vault="")

        errors = exc_info.value.errors()
        error_messages = " ".join(str(e) for e in errors)
        assert "vault" in error_messages.lower()

    def test_whitespace_only_vault_raises_error(self):
        """Test that vault with only whitespace raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BaseNoteInput(title="My Note", vault="   ")

        errors = exc_info.value.errors()
        assert len(errors) >= 1


class TestRetrieveNoteInput:
    """Test suite for RetrieveNoteInput model validation."""

    def test_valid_retrieve_input_minimal(self):
        """Test valid input with only required fields."""
        model = RetrieveNoteInput(title="My Note")
        assert model.title == "My Note"
        assert model.vault is None

    def test_valid_retrieve_input_with_vault(self):
        """Test valid input with vault specified."""
        model = RetrieveNoteInput(title="Daily Notes/2025-10-27", vault="personal")
        assert model.title == "Daily Notes/2025-10-27"
        assert model.vault == "personal"

    def test_retrieve_inherits_base_validation(self):
        """Test that RetrieveNoteInput inherits validation from BaseNoteInput."""
        with pytest.raises(ValidationError):
            RetrieveNoteInput(title="")

        with pytest.raises(ValidationError):
            RetrieveNoteInput(title="../escape")

    def test_model_json_schema_generation(self):
        """Test that JSON schema is generated correctly for MCP."""
        schema = RetrieveNoteInput.model_json_schema()

        # Verify schema structure
        assert "properties" in schema
        assert "title" in schema["properties"]
        assert "vault" in schema["properties"]

        # Verify title field has description
        assert "description" in schema["properties"]["title"]

        # Verify examples are included
        assert "examples" in schema or "example" in schema

    def test_model_validation_error_details(self):
        """Test that validation errors contain detailed field-level information."""
        with pytest.raises(ValidationError) as exc_info:
            RetrieveNoteInput(title="")

        errors = exc_info.value.errors()
        # Verify error structure contains field location
        assert any(error.get("loc") == ("title",) for error in errors)


class TestInputModelEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_unicode_in_title(self):
        """Test that Unicode characters in titles are accepted."""
        model = BaseNoteInput(title="Notes/日記 2025-10-27")
        assert model.title == "Notes/日記 2025-10-27"

    def test_special_chars_in_title(self):
        """Test that various special characters are accepted."""
        model = BaseNoteInput(title="Projects/My-Project_v1 (draft)")
        assert model.title == "Projects/My-Project_v1 (draft)"

    def test_very_long_title(self):
        """Test that long titles are accepted."""
        long_title = "A" * 200
        model = BaseNoteInput(title=long_title)
        assert model.title == long_title

    def test_very_deeply_nested_path(self):
        """Test that very deeply nested paths are accepted."""
        nested = "/".join([f"level{i}" for i in range(20)]) + "/note"
        model = BaseNoteInput(title=nested)
        assert model.title == nested

    def test_multiple_consecutive_slashes_accepted(self):
        """Test behavior with multiple consecutive slashes."""
        # This tests current behavior - may want to normalize later
        model = BaseNoteInput(title="folder//note")
        assert model.title == "folder//note"

    def test_title_ending_with_slash_accepted(self):
        """Test behavior with trailing slash."""
        # This tests current behavior - may want to validate later
        model = BaseNoteInput(title="folder/")
        assert model.title == "folder/"


class TestPydanticIntegration:
    """Test Pydantic-specific features and integration."""

    def test_model_dump_produces_dict(self):
        """Test that model_dump() produces expected dictionary."""
        model = RetrieveNoteInput(title="My Note", vault="personal")
        data = model.model_dump()

        assert data == {"title": "My Note", "vault": "personal"}

    def test_model_dump_json_produces_json(self):
        """Test that model_dump_json() produces valid JSON string."""
        model = RetrieveNoteInput(title="My Note", vault="personal")
        json_str = model.model_dump_json()

        assert isinstance(json_str, str)
        assert '"title"' in json_str
        assert '"My Note"' in json_str

    def test_model_validation_with_extra_fields(self):
        """Test behavior when extra fields are provided."""
        # By default, Pydantic ignores extra fields
        model = RetrieveNoteInput(
            title="My Note",
            vault="personal",
            extra_field="should be ignored"  # type: ignore
        )
        assert model.title == "My Note"
        assert not hasattr(model, "extra_field")

    def test_model_construct_bypasses_validation(self):
        """Test that model_construct can bypass validation (useful for testing core)."""
        # This is useful when testing core operations that need pre-validated data
        model = RetrieveNoteInput.model_construct(title="", vault="")
        # No validation error raised
        assert model.title == ""


class TestCreateNoteInput:
    """Test suite for CreateNoteInput model validation."""

    def test_valid_create_with_content(self):
        """Test creating note with content."""
        model = CreateNoteInput(title="New Note", content="# Hello\n\nWorld")
        assert model.title == "New Note"
        assert model.content == "# Hello\n\nWorld"

    def test_valid_create_with_empty_content(self):
        """Test creating blank note with empty content."""
        model = CreateNoteInput(title="Blank Note", content="")
        assert model.title == "Blank Note"
        assert model.content == ""

    def test_create_inherits_title_validation(self):
        """Test that title validation is inherited from BaseNoteInput."""
        with pytest.raises(ValidationError):
            CreateNoteInput(title="", content="test")

        with pytest.raises(ValidationError):
            CreateNoteInput(title="../escape", content="test")


class TestReplaceNoteInput:
    """Test suite for ReplaceNoteInput model validation."""

    def test_valid_replace_with_content(self):
        """Test replacing note with content."""
        model = ReplaceNoteInput(title="Existing Note", content="# Updated\n\nNew content")
        assert model.title == "Existing Note"
        assert model.content == "# Updated\n\nNew content"

    def test_valid_replace_with_empty_content(self):
        """Test clearing note by replacing with empty content."""
        model = ReplaceNoteInput(title="Note to Clear", content="")
        assert model.title == "Note to Clear"
        assert model.content == ""

    def test_replace_inherits_title_validation(self):
        """Test that title validation is inherited."""
        with pytest.raises(ValidationError):
            ReplaceNoteInput(title="", content="test")


class TestAppendNoteInput:
    """Test suite for AppendNoteInput model validation."""

    def test_valid_append_with_content(self):
        """Test appending content to note."""
        model = AppendNoteInput(title="Log", content="\n- New entry")
        assert model.title == "Log"
        assert model.content == "\n- New entry"

    def test_append_empty_content_raises_error(self):
        """Test that empty content raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AppendNoteInput(title="Log", content="")

        errors = exc_info.value.errors()
        error_messages = " ".join(str(e) for e in errors)
        assert "empty" in error_messages.lower() or "content" in error_messages.lower()

    def test_append_whitespace_only_content_raises_error(self):
        """Test that whitespace-only content raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AppendNoteInput(title="Log", content="   \n\t  ")

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_append_inherits_title_validation(self):
        """Test that title validation is inherited."""
        with pytest.raises(ValidationError):
            AppendNoteInput(title="../escape", content="test")


class TestPrependNoteInput:
    """Test suite for PrependNoteInput model validation."""

    def test_valid_prepend_with_content(self):
        """Test prepending content to note."""
        model = PrependNoteInput(title="Changelog", content="## 2025-10-27\n\n- New feature\n\n")
        assert model.title == "Changelog"
        assert model.content == "## 2025-10-27\n\n- New feature\n\n"

    def test_prepend_empty_content_raises_error(self):
        """Test that empty content raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PrependNoteInput(title="Log", content="")

        errors = exc_info.value.errors()
        error_messages = " ".join(str(e) for e in errors)
        assert "empty" in error_messages.lower() or "content" in error_messages.lower()

    def test_prepend_whitespace_only_content_raises_error(self):
        """Test that whitespace-only content raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PrependNoteInput(title="Log", content="   ")

        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_prepend_inherits_title_validation(self):
        """Test that title validation is inherited."""
        with pytest.raises(ValidationError):
            PrependNoteInput(title="", content="test")


class TestMoveNoteInput:
    """Test suite for MoveNoteInput model validation."""

    def test_valid_move_rename_only(self):
        """Test renaming a note without changing folder."""
        model = MoveNoteInput(old_title="Old Name", new_title="New Name")
        assert model.old_title == "Old Name"
        assert model.new_title == "New Name"
        assert model.update_links is True

    def test_valid_move_folder_only(self):
        """Test moving note to different folder without renaming."""
        model = MoveNoteInput(
            old_title="Projects/Note",
            new_title="Archive/Note"
        )
        assert model.old_title == "Projects/Note"
        assert model.new_title == "Archive/Note"

    def test_valid_move_folder_and_rename(self):
        """Test moving and renaming note."""
        model = MoveNoteInput(
            old_title="Projects/Old Name",
            new_title="Archive/New Name",
            update_links=False
        )
        assert model.old_title == "Projects/Old Name"
        assert model.new_title == "Archive/New Name"
        assert model.update_links is False

    def test_move_same_title_raises_error(self):
        """Test that same old_title and new_title raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            MoveNoteInput(old_title="Same Name", new_title="Same Name")

        errors = exc_info.value.errors()
        error_messages = " ".join(str(e) for e in errors)
        assert "different" in error_messages.lower() or "same" in error_messages.lower()

    def test_move_empty_old_title_raises_error(self):
        """Test that empty old_title raises ValidationError."""
        with pytest.raises(ValidationError):
            MoveNoteInput(old_title="", new_title="New Name")

    def test_move_empty_new_title_raises_error(self):
        """Test that empty new_title raises ValidationError."""
        with pytest.raises(ValidationError):
            MoveNoteInput(old_title="Old Name", new_title="")

    def test_move_path_traversal_old_title_raises_error(self):
        """Test that path traversal in old_title raises ValidationError."""
        with pytest.raises(ValidationError):
            MoveNoteInput(old_title="../escape", new_title="New Name")

    def test_move_path_traversal_new_title_raises_error(self):
        """Test that path traversal in new_title raises ValidationError."""
        with pytest.raises(ValidationError):
            MoveNoteInput(old_title="Old Name", new_title="../escape")

    def test_move_strips_md_extension(self):
        """Test that .md extension is stripped from titles."""
        model = MoveNoteInput(old_title="Old.md", new_title="New.md")
        assert model.old_title == "Old"
        assert model.new_title == "New"

    def test_move_update_links_default_true(self):
        """Test that update_links defaults to True."""
        model = MoveNoteInput(old_title="Old", new_title="New")
        assert model.update_links is True


class TestDeleteNoteInput:
    """Test suite for DeleteNoteInput model validation."""

    def test_valid_delete(self):
        """Test deleting a note."""
        model = DeleteNoteInput(title="Old Note")
        assert model.title == "Old Note"
        assert model.vault is None

    def test_valid_delete_with_vault(self):
        """Test deleting a note from specific vault."""
        model = DeleteNoteInput(title="Archive/Old Project", vault="work")
        assert model.title == "Archive/Old Project"
        assert model.vault == "work"

    def test_delete_inherits_title_validation(self):
        """Test that title validation is inherited from BaseNoteInput."""
        with pytest.raises(ValidationError):
            DeleteNoteInput(title="")

        with pytest.raises(ValidationError):
            DeleteNoteInput(title="../escape")

        with pytest.raises(ValidationError):
            DeleteNoteInput(title="/absolute/path")


class TestAllModelsSchemaGeneration:
    """Test that all models can generate JSON schemas for MCP."""

    def test_create_note_schema(self):
        """Test CreateNoteInput schema generation."""
        schema = CreateNoteInput.model_json_schema()
        assert "properties" in schema
        assert "title" in schema["properties"]
        assert "content" in schema["properties"]

    def test_replace_note_schema(self):
        """Test ReplaceNoteInput schema generation."""
        schema = ReplaceNoteInput.model_json_schema()
        assert "properties" in schema
        assert "title" in schema["properties"]

    def test_append_note_schema(self):
        """Test AppendNoteInput schema generation."""
        schema = AppendNoteInput.model_json_schema()
        assert "properties" in schema
        assert "content" in schema["properties"]

    def test_prepend_note_schema(self):
        """Test PrependNoteInput schema generation."""
        schema = PrependNoteInput.model_json_schema()
        assert "properties" in schema

    def test_move_note_schema(self):
        """Test MoveNoteInput schema generation."""
        schema = MoveNoteInput.model_json_schema()
        assert "properties" in schema
        assert "old_title" in schema["properties"]
        assert "new_title" in schema["properties"]
        assert "update_links" in schema["properties"]

    def test_delete_note_schema(self):
        """Test DeleteNoteInput schema generation."""
        schema = DeleteNoteInput.model_json_schema()
        assert "properties" in schema
        assert "title" in schema["properties"]
