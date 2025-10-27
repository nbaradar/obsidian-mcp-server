import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from obsidian_vault import (
    VaultMetadata,
    _ensure_valid_yaml,
    _parse_frontmatter,
    delete_frontmatter_block,
    read_frontmatter,
    replace_frontmatter,
    update_frontmatter,
)


class FrontmatterHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.vault_path = Path(self.tmpdir.name).resolve()
        self.vault = VaultMetadata(
            name="test",
            path=self.vault_path,
            description="test vault",
            exists=True,
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _write_note(self, name: str, content: str) -> Path:
        note_path = self.vault_path / f"{name}.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        return note_path

    def test_parse_frontmatter_handles_metadata_and_content(self) -> None:
        raw = "---\ntitle: Example Note\ntags:\n  - test\n---\n\nBody text."
        metadata, body = _parse_frontmatter(raw)
        self.assertEqual(metadata["title"], "Example Note")
        self.assertEqual(metadata["tags"], ["test"])
        self.assertEqual(body.strip(), "Body text.")

    def test_parse_frontmatter_without_block_returns_original_content(self) -> None:
        raw = "No frontmatter here."
        metadata, body = _parse_frontmatter(raw)
        self.assertEqual(metadata, {})
        self.assertEqual(body, raw)

    def test_ensure_valid_yaml_converts_datetime(self) -> None:
        metadata = {"date": datetime(2025, 1, 1, 12, 0)}
        _ensure_valid_yaml(metadata)
        self.assertEqual(metadata["date"], "2025-01-01T12:00:00")

    def test_ensure_valid_yaml_converts_date(self) -> None:
        metadata = {"created": date(2025, 10, 27)}
        _ensure_valid_yaml(metadata)
        self.assertEqual(metadata["created"], "2025-10-27")

    def test_ensure_valid_yaml_rejects_unsupported_types(self) -> None:
        metadata = {"bad": {1, 2}}
        with self.assertRaises(ValueError):
            _ensure_valid_yaml(metadata)

    def test_read_frontmatter_returns_expected_metadata(self) -> None:
        self._write_note(
            "example",
            "---\nstatus: active\n---\nContent\n",
        )
        result = read_frontmatter("example", self.vault)
        self.assertEqual(result["frontmatter"], {"status": "active"})
        self.assertTrue(result["has_frontmatter"])

    def test_update_frontmatter_merges_nested_dicts(self) -> None:
        note_path = self._write_note(
            "project",
            "---\nproject:\n  status: planned\n---\nNotes\n",
        )
        update_frontmatter(
            "project",
            {"project": {"status": "active", "owner": "alice"}, "tags": ["obsidian"]},
            self.vault,
        )
        updated = note_path.read_text(encoding="utf-8")
        metadata, _ = _parse_frontmatter(updated)
        self.assertEqual(metadata["project"]["status"], "active")
        self.assertEqual(metadata["project"]["owner"], "alice")
        self.assertEqual(metadata["tags"], ["obsidian"])

    def test_update_frontmatter_handles_existing_date(self) -> None:
        note_path = self._write_note(
            "dated",
            "---\ncreated: 2025-10-27\n---\nBody\n",
        )
        result = update_frontmatter(
            "dated",
            {"status": "active"},
            self.vault,
        )
        self.assertEqual(result["status"], "updated")
        text = note_path.read_text(encoding="utf-8")
        metadata, _ = _parse_frontmatter(text)
        self.assertEqual(metadata["status"], "active")
        self.assertIsInstance(metadata["created"], str)
        self.assertEqual(metadata["created"], "2025-10-27")

    def test_replace_frontmatter_overwrites_entire_block(self) -> None:
        note_path = self._write_note(
            "replace",
            "---\nold: value\n---\nBody\n",
        )
        replace_frontmatter("replace", {"new": "value"}, self.vault)
        updated = note_path.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(updated)
        self.assertEqual(metadata, {"new": "value"})
        self.assertEqual(body.strip(), "Body")

    def test_delete_frontmatter_removes_block(self) -> None:
        note_path = self._write_note(
            "cleanup",
            "---\ntitle: Remove Me\n---\nContent\n",
        )
        delete_frontmatter_block("cleanup", self.vault)
        updated = note_path.read_text(encoding="utf-8")
        self.assertFalse(updated.lstrip().startswith("---"))
        self.assertEqual(updated.strip(), "Content")

    def test_delete_frontmatter_is_noop_when_missing(self) -> None:
        note_path = self._write_note("plain", "Content only.")
        result = delete_frontmatter_block("plain", self.vault)
        self.assertEqual(result["status"], "no_frontmatter")
        self.assertEqual(note_path.read_text(encoding="utf-8"), "Content only.")


if __name__ == "__main__":
    unittest.main()
