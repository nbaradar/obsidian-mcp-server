# Obsidian MCP Server
This project exposes one or more local Obsidian vaults to Claude Desktop through the Model Context Protocol (MCP). The server is built with FastMCP, uses `vaults.yaml` to whitelist vault paths, and provides tools for listing, creating, reading, updating, deleting, and searching markdown notes. 

## Tool Calls Available:
### Management
- **list_vaults** — Returns the default vault, the caller’s active vault (if set), and metadata for each configured vault (name, path, description, existence flag). Primary discovery entry point.
- **set_active_vault** — Stores the caller’s preferred vault for the lifetime of the MCP session. Subsequent tool calls without a vault argument use this value.

### Notes
- **create_obsidian_note** — Create a markdown file (fails if the note already exists).
- **retrieve_obsidian_note** — Read the full contents of a note.
- **update_obsidian_note** — Replace the file contents entirely.
- **delete_obsidian_note** — Remove the note from disk.
- **list_obsidian_notes** — Return all note identifiers (forward-slash separated, extension stripped) within the vault.
- **search_obsidian_notes** — Shallow search against note identifiers (not file contents yet).

See `AGENTS.md` for the detailed design notes and roadmap.
