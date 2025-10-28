"""
Test suite for search_notes_by_tag functionality
Add to your test suite (e.g., tests/test_tag_search.py)
"""

import pytest
from pathlib import Path
from obsidian_vault import (
    search_notes_by_tags,
    VaultMetadata,
)


@pytest.fixture
def test_vault(tmp_path):
    """Create a test vault with various tagged notes."""
    vault_path = tmp_path / "test_vault"
    vault_path.mkdir()
    
    # Note 1: List format, multiple tags
    note1 = vault_path / "ml-basics.md"
    note1.write_text("""---
tags: [machine-learning, ai, tutorial]
title: ML Basics
---
# Machine Learning Basics
Introduction to ML concepts.
""")
    
    # Note 2: String format, single tag
    note2 = vault_path / "research.md"
    note2.write_text("""---
tags: research
author: Test Author
---
# Research Notes
Some research content.
""")
    
    # Note 3: Mixed case tags
    note3 = vault_path / "deep-learning.md"
    note3.write_text("""---
tags: [Deep-Learning, Machine-Learning, Research]
---
# Deep Learning Guide
""")
    
    # Note 4: No frontmatter
    note4 = vault_path / "no-frontmatter.md"
    note4.write_text("""# Regular Note
No frontmatter here.
""")
    
    # Note 5: Empty tags
    note5 = vault_path / "empty-tags.md"
    note5.write_text("""---
tags: []
title: Empty Tags
---
# Empty Tags Note
""")
    
    # Note 6: No tags field
    note6 = vault_path / "no-tags.md"
    note6.write_text("""---
title: No Tags Field
author: Someone
---
# No Tags
""")
    
    # Note 7: Nested folder with tags
    subfolder = vault_path / "projects"
    subfolder.mkdir()
    note7 = subfolder / "mcp-server.md"
    note7.write_text("""---
tags: [obsidian, mcp, python]
---
# MCP Server Project
""")
    
    # Note 8: Special characters in tags
    note8 = vault_path / "cpp-notes.md"
    note8.write_text("""---
tags: [c++, programming, low-level]
---
# C++ Programming Notes
""")
    
    return VaultMetadata(
        name="test",
        path=vault_path,
        description="Test vault",
        exists=True
    )


class TestTagSearchBasics:
    """Test basic tag search functionality."""
    
    def test_single_tag_match(self, test_vault):
        """Search for single tag should return matching notes."""
        result = search_notes_by_tags(["machine-learning"], test_vault)
        
        assert result["vault"] == "test"
        assert result["tags"] == ["machine-learning"]
        assert result["match_mode"] == "any"
        assert len(result["matches"]) == 2  # ml-basics.md, deep-learning.md
        assert "ml-basics" in result["matches"][0] or "ml-basics" in result["matches"][1]
    
    def test_single_tag_no_match(self, test_vault):
        """Search for non-existent tag should return empty results."""
        result = search_notes_by_tags(["nonexistent"], test_vault)
        
        assert result["matches"] == []
        assert result["match_mode"] == "any"
    
    def test_multiple_tags_any_mode(self, test_vault):
        """Search with match_all=False should match ANY tag."""
        result = search_notes_by_tags(
            ["machine-learning", "research"],
            test_vault,
            match_all=False
        )
        
        # Should match: ml-basics (ml), research (research), deep-learning (both)
        assert len(result["matches"]) == 3
        assert result["match_mode"] == "any"
    
    def test_multiple_tags_all_mode(self, test_vault):
        """Search with match_all=True should require ALL tags."""
        result = search_notes_by_tags(
            ["machine-learning", "research"],
            test_vault,
            match_all=True
        )
        
        # Should match only: deep-learning (has both tags)
        assert len(result["matches"]) == 1
        assert "deep-learning" in result["matches"][0]
        assert result["match_mode"] == "all"


class TestTagFormats:
    """Test different tag format handling."""
    
    def test_list_format_tags(self, test_vault):
        """Should handle tags as YAML list."""
        result = search_notes_by_tags(["ai"], test_vault)
        
        assert len(result["matches"]) == 1
        assert "ml-basics" in result["matches"][0]
    
    def test_string_format_tags(self, test_vault):
        """Should handle tags as single string."""
        result = search_notes_by_tags(["research"], test_vault)
        
        # Should match: research.md (string), deep-learning.md (list with research)
        assert len(result["matches"]) == 2
    
    def test_special_characters_in_tags(self, test_vault):
        """Should handle tags with special characters."""
        result = search_notes_by_tags(["c++"], test_vault)
        
        assert len(result["matches"]) == 1
        assert "cpp-notes" in result["matches"][0]


class TestCaseInsensitivity:
    """Test case-insensitive matching."""
    
    def test_lowercase_search_matches_titlecase(self, test_vault):
        """Lowercase search should match TitleCase tags."""
        result = search_notes_by_tags(["deep-learning"], test_vault)
        
        assert len(result["matches"]) == 1
        assert "deep-learning" in result["matches"][0]
    
    def test_uppercase_search_matches_lowercase(self, test_vault):
        """Uppercase search should match lowercase tags."""
        result = search_notes_by_tags(["MACHINE-LEARNING"], test_vault)
        
        assert len(result["matches"]) == 2
    
    def test_mixed_case_search(self, test_vault):
        """Mixed case search should work."""
        result = search_notes_by_tags(["MaChInE-LeArNiNg"], test_vault)
        
        assert len(result["matches"]) == 2


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_tags_list_raises_error(self, test_vault):
        """Empty tags list should raise ValueError."""
        with pytest.raises(ValueError, match="Must specify at least one"):
            search_notes_by_tags([], test_vault)
    
    def test_whitespace_only_tags_raises_error(self, test_vault):
        """Whitespace-only tags should raise ValueError."""
        with pytest.raises(ValueError, match="Must specify at least one"):
            search_notes_by_tags(["   ", "\t"], test_vault)
    
    def test_notes_without_frontmatter_skipped(self, test_vault):
        """Notes without frontmatter should be skipped gracefully."""
        result = search_notes_by_tags(["any-tag"], test_vault)
        
        # Should not include no-frontmatter.md
        assert not any("no-frontmatter" in match for match in result["matches"])
    
    def test_notes_with_empty_tags_skipped(self, test_vault):
        """Notes with empty tags list should be skipped."""
        result = search_notes_by_tags(["tutorial"], test_vault)
        
        # Should not include empty-tags.md
        assert not any("empty-tags" in match for match in result["matches"])
    
    def test_notes_without_tags_field_skipped(self, test_vault):
        """Notes without tags field should be skipped."""
        result = search_notes_by_tags(["tutorial"], test_vault)
        
        # Should not include no-tags.md
        assert not any("no-tags" in match for match in result["matches"])


class TestMetadataInclusion:
    """Test metadata inclusion functionality."""
    
    def test_without_metadata_returns_paths_only(self, test_vault):
        """include_metadata=False should return only paths."""
        result = search_notes_by_tags(
            ["machine-learning"],
            test_vault,
            include_metadata=False
        )
        
        assert isinstance(result["matches"][0], str)
        assert "ml-basics" in result["matches"][0] or "deep-learning" in result["matches"][0]
    
    def test_with_metadata_returns_dict(self, test_vault):
        """include_metadata=True should return dicts with metadata."""
        result = search_notes_by_tags(
            ["machine-learning"],
            test_vault,
            include_metadata=True
        )
        
        match = result["matches"][0]
        assert isinstance(match, dict)
        assert "path" in match
        assert "tags" in match
        assert "modified" in match
        assert "size" in match
        # "created" may not be present on all platforms
    
    def test_metadata_includes_matched_tags(self, test_vault):
        """Metadata should include the tags found in the note."""
        result = search_notes_by_tags(
            ["machine-learning"],
            test_vault,
            include_metadata=True
        )
        
        for match in result["matches"]:
            assert "tags" in match
            assert isinstance(match["tags"], list)
            # Check case-insensitive match
            normalized_tags = [tag.lower() for tag in match["tags"]]
            assert "machine-learning" in normalized_tags
    
    def test_metadata_sorting_by_modified(self, test_vault):
        """Results with metadata should be sorted by modified date."""
        result = search_notes_by_tags(
            ["machine-learning"],
            test_vault,
            include_metadata=True
        )
        
        if len(result["matches"]) > 1:
            # Verify descending order (newest first)
            for i in range(len(result["matches"]) - 1):
                current = result["matches"][i]["modified"]
                next_item = result["matches"][i + 1]["modified"]
                assert current >= next_item
    
    def test_without_metadata_sorting_alphabetical(self, test_vault):
        """Results without metadata should be sorted alphabetically."""
        result = search_notes_by_tags(
            ["machine-learning"],
            test_vault,
            include_metadata=False
        )
        
        if len(result["matches"]) > 1:
            # Verify alphabetical order
            sorted_matches = sorted(result["matches"])
            assert result["matches"] == sorted_matches


class TestNestedFolders:
    """Test handling of notes in nested folders."""
    
    def test_searches_nested_folders(self, test_vault):
        """Should find notes in subdirectories."""
        result = search_notes_by_tags(["obsidian"], test_vault)
        
        assert len(result["matches"]) == 1
        assert "projects/mcp-server" in result["matches"][0]
    
    def test_path_format_uses_forward_slashes(self, test_vault):
        """Paths should use forward slashes regardless of OS."""
        result = search_notes_by_tags(["obsidian"], test_vault)
        
        # Should use forward slash even on Windows
        assert "/" in result["matches"][0]
        assert "projects/mcp-server" in result["matches"][0]


class TestComplexQueries:
    """Test complex search scenarios."""
    
    def test_three_tags_any_mode(self, test_vault):
        """Should handle searching for 3+ tags in ANY mode."""
        result = search_notes_by_tags(
            ["machine-learning", "research", "python"],
            test_vault,
            match_all=False
        )
        
        # Should match: ml-basics (ml), research (research), 
        # deep-learning (ml+research), mcp-server (python)
        assert len(result["matches"]) >= 3
    
    def test_three_tags_all_mode(self, test_vault):
        """Should handle searching for 3+ tags in ALL mode."""
        result = search_notes_by_tags(
            ["obsidian", "mcp", "python"],
            test_vault,
            match_all=True
        )
        
        # Should match only: mcp-server (has all three)
        assert len(result["matches"]) == 1
        assert "mcp-server" in result["matches"][0]
    
    def test_overlapping_tag_sets(self, test_vault):
        """Test with tags that partially overlap across notes."""
        # Get ml notes
        ml_result = search_notes_by_tags(["machine-learning"], test_vault)
        ml_count = len(ml_result["matches"])
        
        # Get research notes
        research_result = search_notes_by_tags(["research"], test_vault)
        research_count = len(research_result["matches"])
        
        # Get combined (OR)
        or_result = search_notes_by_tags(
            ["machine-learning", "research"],
            test_vault,
            match_all=False
        )
        
        # Get intersection (AND)
        and_result = search_notes_by_tags(
            ["machine-learning", "research"],
            test_vault,
            match_all=True
        )
        
        # OR should be <= sum (accounting for overlap)
        assert len(or_result["matches"]) <= ml_count + research_count
        
        # AND should be <= each individual
        assert len(and_result["matches"]) <= ml_count
        assert len(and_result["matches"]) <= research_count


class TestPerformance:
    """Test performance characteristics (optional, for large vaults)."""
    
    @pytest.mark.slow
    def test_large_vault_performance(self, tmp_path):
        """Test performance with many notes (skip in quick tests)."""
        vault_path = tmp_path / "large_vault"
        vault_path.mkdir()
        
        # Create 1000 notes with various tags
        for i in range(1000):
            note = vault_path / f"note-{i}.md"
            tags = ["tag-" + str(j) for j in range(i % 5)]  # 0-4 tags per note
            tags_yaml = str(tags) if tags else "[]"
            note.write_text(f"""---
tags: {tags_yaml}
---
# Note {i}
""")
        
        vault = VaultMetadata(
            name="large",
            path=vault_path,
            description="Large test vault",
            exists=True
        )
        
        # Should complete in reasonable time
        import time
        start = time.time()
        result = search_notes_by_tags(["tag-1"], vault)
        elapsed = time.time() - start
        
        # Should be fast even with 1000 notes
        assert elapsed < 2.0  # 2 seconds max
        assert len(result["matches"]) > 0


# Integration test to verify MCP tool works
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_tool_integration(test_vault):
    """Test that the MCP tool wrapper works correctly."""
    from obsidian_vault import search_notes_by_tag
    from mcp.server.fastmcp import Context
    
    # Mock context (would normally come from MCP client)
    mock_ctx = None  # When None, uses default vault
    
    result = await search_notes_by_tag(
        tags=["machine-learning"],
        vault="test",  # Explicit vault
        ctx=mock_ctx
    )
    
    assert "vault" in result
    assert "matches" in result
    assert isinstance(result["matches"], list)


if __name__ == "__main__":
    # Run tests with: python -m pytest test_tag_search.py -v
    pytest.main([__file__, "-v"])
