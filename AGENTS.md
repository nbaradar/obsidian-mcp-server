# Obsidian MCP Server — AGENTS.md

## Purpose

This document outlines the purpose and structure of the **Obsidian MCP Server**, which connects Claude Desktop (as an MCP client) to a local Obsidian vault. The server allows the model to perform basic operations on markdown files in a secure, sandboxed environment.

## Overview

The goal of the MCP server is to expose the contents of one or more local Obsidian vaults (for example `nader_obsidian_vault`) as resources that can be read and modified through defined MCP tool calls. This enables local automation, structured note editing, and future integration with other projects or vaults.

The server will:

* Serve as a bridge between Claude Desktop and the local Obsidian vault.
* Expose CRUD functionality for markdown files across approved vaults.
* Operate locally (localhost only) for privacy and security.
* Be extensible for future specialized vaults or tools.

## Implementation Plan

The first version will be written in **Python**, using **FastMCP** for rapid setup and **uv** as the package manager. It will not include any prompts yet—only resources (markdown files) and tools (file operations).

### Resources (planned)

* **Markdown Files:** Each `.md` file in the vault is a resource.
* Each resource will have basic metadata such as file path and possibly frontmatter for future versions.

### Tools (current)

All MCP tools live in `obsidian_vault.py` and are simple wrappers over helper functions that enforce our sandbox rules. Every tool now accepts an optional `vault` argument; omitting it causes the server to use the caller’s per-session active vault (falling back to the config default). Responses always include the resolved vault name so downstream automations have an audit trail.

Management
1. `list_vaults` — Returns the default vault, the caller’s active vault (if set), and metadata for each configured vault (name, path, description, existence flag). Primary discovery entry point.
2. `set_active_vault` — Stores the caller’s preferred vault for the lifetime of the MCP session. Subsequent tool calls without a `vault` argument use this value.

Notes
1. `create_obsidian_note` — Create a markdown file (fails if the note already exists).
2. `retrieve_obsidian_note` — Read the full contents of a note.
3. `update_obsidian_note` — Replace the file contents entirely.
4. `delete_obsidian_note` — Remove the note from disk.
5. `list_obsidian_notes` — Return all note identifiers (forward-slash separated, extension stripped) within the vault.
6. `search_obsidian_notes` — Shallow search against note identifiers (not file contents yet).

Each tool’s docstring includes UX hints explicitly telling Claude Desktop to use `list_vaults` for discovery and that omitting `vault` defers to the active or default vault. This dramatically improves agent behavior: Claude can respond to requests like “update my work vault” by first setting the vault, then calling note helpers without needing to restate the name every time.

### Security

Security is enforced in multiple layers inside `obsidian_vault.py`:

* **Vault allow list:** `vaults.yaml` enumerates friendly vault names and their canonical paths. `_load_vaults_config` resolves each path and rejects unknown or malformed entries. Clients can never pass raw filesystem paths.
* **Per-session active vaults:** `set_active_vault` stores the chosen vault keyed by `id(ctx.session)` so each MCP connection has isolated state. `resolve_vault` (used by every tool) resolves the proper metadata in the order `vault argument -> session active -> default`.
* **Path sandboxing:** `_normalize_note_identifier` and `_resolve_note_path` strip extensions, reject `.`/`..`, and ensure the resolved path stays inside the vault root before any filesystem touch. This blocks traversal attacks and absolute paths.
* **Logging:** Creating, updating, deleting notes, and changing the active vault emit `INFO` level logs with the vault name and normalized note identifier for traceability.
* **Execution environment:** The server still binds only to `127.0.0.1`, keeping operations local.

### Development Phases

**v1 — Minimal Working Server**

* Implement the six CRUD+list+search tools.
* Allow Claude Desktop to connect and perform file operations locally.

**v1.5 — Enhancements**

* Add handling for YAML frontmatter and heading-based inserts.
* Improve search with snippets and partial reads.
* Add rename/move functionality with optional backlink updates.

**v2 — Advanced Behavior**

* Integration with Obsidian’s Local REST API for native operations.
* Multi-vault management and dynamic loading.
* Specialized vaults (e.g., “mental health”, “projects”) with custom toolsets.

### Example Use Cases

* Quickly create and edit notes directly from Claude Desktop.
* Search the vault for keywords or ideas.
* Build higher-level automations later (e.g., summarizing a folder, appending daily entries).

### Summary

The MCP Server is now a local, multi-vault bridge for secure file management inside Obsidian. The current implementation emphasizes safety (allow list, per-session vault tracking, traversal guards) and auditability (vault-aware responses and logs) while setting the stage for richer automations such as frontmatter handling and content-aware searches in future iterations.

---

## 2025-10 Status Notes (for future maintainers)

* `vaults.yaml` is the single source of truth for vault discovery. Add new vault entries there with `default: <name>` updated accordingly. Reloads happen at module import, so server restarts pick up changes.
* The helper unit tests do not exist yet. If regressions are a concern, start with tests around `_normalize_note_identifier` and `_resolve_note_path`.
* `vault.exists` in config is recomputed dynamically via `Path.is_dir()` when we build payloads, so stale metadata is less likely. We still surface the `exists` flag to clients so they can warn the user.
* The session cache (`ACTIVE_VAULTS`) keys off `id(ctx.session)`. FastMCP manages session lifetimes; when a session disappears the entry becomes unreachable and will be garbage collected. No explicit cleanup needed.
* Tool returns are dicts designed for Claude Desktop, but they’re equally useful for scripts or future REST layers—preserve this structure when extending functionality.
