# Obsidian MCP Server
Dev Notes: https://nbaradar.github.io/the-latent-space/Personal-Projects/MCP/Obsidian-MCP-Server

This project exposes one or more local Obsidian vaults to Claude Desktop through the Model Context Protocol (MCP). The server is built with FastMCP, uses `vaults.yaml` to whitelist vault paths, and provides tools for listing, creating, reading, replacing, appending/prepending, section-level editing, and searching markdown notes—including a content search tool that returns short, token-efficient snippets. See `AGENTS.md` for the detailed design notes and roadmap.

## Tool Calls Available:
### Management
- **list_vaults** — Returns the default vault, the caller’s active vault (if set), and metadata for each configured vault (name, path, description, existence flag). Primary discovery entry point.
- **set_active_vault** — Stores the caller’s preferred vault for the lifetime of the MCP session. Subsequent tool calls without a vault argument use this value.

### Notes — Core Edits
- **create_obsidian_note** — Create a markdown file (fails if the note already exists).
- **retrieve_obsidian_note** — Read the full contents of a note.
- **replace_obsidian_note** — Replace the file contents entirely (formerly `update_obsidian_note`).
- **append_to_obsidian_note** — Append content to the end of a note, inserting separators when helpful.
- **prepend_to_obsidian_note** — Prepend content before the existing body, handling separators automatically.
- **delete_obsidian_note** — Remove the note from disk.

### Notes — Structured Inserts & Sections
- **insert_after_heading_obsidian_note** — Insert content immediately after a heading (case-insensitive). Use `retrieve_obsidian_note` to inspect heading structure.
- **replace_section_obsidian_note** — Replace everything under a heading until the next heading of equal or higher level.
- **delete_section_obsidian_note** — Remove a heading and its section (up to the next heading of equal or higher level).

### Notes — Discovery & Search
- **list_obsidian_notes** — Return all note identifiers (forward-slash separated, extension stripped) within the vault.
- **search_obsidian_notes** — Shallow search against note identifiers (not file contents yet).
- **search_obsidian_content** — Snippet-focused content search across all notes in approved vaults (max 10 files, 3 snippets per match, ~200 characters each).

See `AGENTS.md` for the detailed design notes and roadmap.
