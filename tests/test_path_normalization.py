import pytest

from obsidian_vault import _normalize_note_identifier


def test_normalize_preserves_dot_in_basename():
    """Ensure dots within the note name are preserved before the .md suffix."""
    identifier = "v1.4 Release Changelog - Frontmatter Manipulation.md"
    normalized = _normalize_note_identifier(identifier)
    assert normalized.as_posix() == identifier


def test_normalize_preserves_dots_in_nested_paths():
    """Dots inside nested path segments should remain untouched."""
    identifier = "Projects/v1.4 Release Notes"
    normalized = _normalize_note_identifier(identifier)
    assert normalized.as_posix() == "Projects/v1.4 Release Notes.md"


def test_normalize_handles_uppercase_extension():
    """Existing .MD suffix should be treated case-insensitively."""
    identifier = "Docs/Version Overview.MD"
    normalized = _normalize_note_identifier(identifier)
    assert normalized.as_posix() == "Docs/Version Overview.md"


def test_normalize_rejects_directory_traversal():
    """Input containing traversal segments should still be rejected."""
    with pytest.raises(ValueError):
        _normalize_note_identifier("../outside")
