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
* Each resource will have basic metadata such as file path and frontmatter (now surfaced through dedicated tools).

### Tools (current)

All MCP tools live in `obsidian_vault.py` and are simple wrappers over helper functions that enforce our sandbox rules. Every tool now accepts an optional `vault` argument; omitting it causes the server to use the caller’s per-session active vault (falling back to the config default). Responses always include the resolved vault name so downstream automations have an audit trail.

Management
1. `list_vaults` — Returns the default vault, the caller’s active vault (if set), and metadata for each configured vault (name, path, description, existence flag). Primary discovery entry point.
2. `set_active_vault` — Stores the caller’s preferred vault for the lifetime of the MCP session. Subsequent tool calls without a `vault` argument use this value.

Notes — Core edits
1. `create_obsidian_note` — Create a markdown file (fails if the note already exists).
2. `retrieve_obsidian_note` — Read the full contents of a note.
3. `replace_obsidian_note` — Replace the file contents entirely (former `update_obsidian_note`).
4. `append_to_obsidian_note` — Append content to the end of a note, inserting separators when helpful.
5. `prepend_to_obsidian_note` — Prepend content before the existing body, handling separators automatically.
6. `delete_obsidian_note` — Remove the note from disk.
7. `move_obsidian_note` — Rename or relocate a note; optionally updates backlinks across the vault.

Notes — Structured inserts & sections
1. `insert_after_heading_obsidian_note` — Insert content immediately after a heading (case-insensitive match, supports `#`-style levels).
2. `append_to_section_obsidian_note` — Append content to a section’s direct body, placing it before the first nested heading.
3. `replace_section_obsidian_note` — Replace everything under a heading until the next heading of equal or higher level.
4. `delete_section_obsidian_note` — Remove a heading and its section (up to the next heading of equal or higher level).

Frontmatter Management
1. `read_obsidian_frontmatter` — Return only the YAML frontmatter block for token-efficient metadata reads.
2. `update_obsidian_frontmatter` — Merge supplied fields into existing frontmatter (creates the block if missing).
3. `replace_obsidian_frontmatter` — Overwrite the entire frontmatter with a sanitized payload.
4. `delete_obsidian_frontmatter` — Remove the frontmatter block while preserving body content.

Helpers underpinning these tools:
* `_parse_frontmatter(text)` — Splits raw markdown into metadata + body using `python-frontmatter`, normalizing nested mappings.
* `_serialize_frontmatter(metadata, content)` — Reconstructs markdown with or without a YAML block.
* `_ensure_valid_yaml(metadata)` — Validates size, key/value types, and converts datetimes to ISO strings before serialization.

Notes — Discovery & search
1. `list_obsidian_notes` — Return all note identifiers (forward-slash separated, extension stripped) within the vault; accepts `include_metadata` to attach modified/created/size (adds ~9 tokens per note).
2. `search_obsidian_notes` — Token-efficient substring search across note identifiers with optional metadata and sorting controls (`sort_by` supporting `modified/created/size/name`).
3. `list_notes_in_folder` — Folder-targeted listing with optional recursion and metadata; ideal for "most recent note in X" queries without scanning the entire vault.
4. `search_obsidian_content` — Token-efficient content search that returns up to three 200-character snippets per file (100 chars of context on each side of the hit), capped at ten files and sorted by match count.
5. `search_notes_by_tag` — Token-efficient tag search that inspects YAML frontmatter only, supporting ANY/ALL matching and optional metadata.

Each tool’s docstring includes UX hints explicitly telling Claude Desktop to use `list_vaults` for discovery and that omitting `vault` defers to the active or default vault. This dramatically improves agent behavior: Claude can respond to requests like “update my work vault” by first setting the vault, then calling note helpers without needing to restate the name every time.

### Security

Security is enforced in multiple layers inside `obsidian_vault.py`:

* **Vault allow list:** `vaults.yaml` enumerates friendly vault names and their canonical paths. `_load_vaults_config` resolves each path and rejects unknown or malformed entries. Clients can never pass raw filesystem paths.
* **Per-session active vaults:** `set_active_vault` stores the chosen vault keyed by `id(ctx.session)` so each MCP connection has isolated state. `resolve_vault` (used by every tool) resolves the proper metadata in the order `vault argument -> session active -> default`.
* **Path sandboxing:** `_normalize_note_identifier` and `_resolve_note_path` strip extensions, reject `.`/`..`, preserve dots inside note titles, and ensure the resolved path stays inside the vault root before any filesystem touch. This blocks traversal attacks and absolute paths without truncating legitimate names.
* **Frontmatter validation:** `_ensure_valid_yaml` enforces YAML-safe schemas, converts date/datetime values to ISO strings, and caps metadata at 10 KB before writing to disk.
* **Logging:** Creating, updating, deleting notes, and changing the active vault emit `INFO` level logs with the vault name and normalized note identifier for traceability.
* **Execution environment:** The server still binds only to `127.0.0.1`, keeping operations local.

### Development Phases

**v1 — Minimal Working Server**

* Implement the six CRUD+list+search tools.
* Allow Claude Desktop to connect and perform file operations locally.

**v1.4 — Frontmatter Manipulation + Tag Search**

* Introduce `python-frontmatter` helpers for parsing/serializing metadata.
* Expose `read/update/replace/delete` frontmatter MCP tools with strict validation.
* Add regression tests covering YAML coercion, merges, and deletion flows.
* Add `search_notes_by_tag` for frontmatter-only tag filtering with AND/OR modes and optional metadata.

**v1.4.1 — Tag Search Enhancements**

* Added discovery-facing `search_notes_by_tag` MCP tool annotations to surface metadata about read-only behavior.
* Expanded README/AGENTS documentation and integration guides for token-efficient tag workflows.
* Introduced dedicated `tests/test_tag_search.py` suite (27 cases) covering format handling, metadata sorting, performance, and async MCP integration.

**v1.4.2 — Path Normalization Fixes**

* Updated `_normalize_note_identifier` to preserve dotted note titles while still enforcing sandbox constraints.
* Added regression coverage in `tests/test_path_normalization.py` for dotted basenames, nested paths, uppercase `.MD`, and traversal rejection.
* Documented behavior in README and AGENTS to clarify support for dotted note names.

**v1.5 — Enhancements**

* Improve search with snippets and partial reads.
* Add rename/move functionality with optional backlink updates.

**v2 — Advanced Behavior**

* Integration with Obsidian’s Local REST API for native operations.
* Multi-vault management and dynamic loading.
* Specialized vaults (e.g., “mental health”, “projects”) with custom toolsets.

### Example Use Cases

* Quickly create and edit notes directly from Claude Desktop.
* Search the vault for keywords or ideas, returning snippets first (`search_obsidian_content`) and escalating to full reads only when needed.
* Build higher-level automations later (e.g., summarizing a folder, appending daily entries).

### Summary

The MCP Server is now a local, multi-vault bridge for secure file management inside Obsidian. The current implementation emphasizes safety (allow list, per-session vault tracking, traversal guards) and auditability (vault-aware responses and logs) while providing dedicated YAML frontmatter helpers that unlock metadata-centric automations alongside heading-aware edits and token-efficient search.

---

## 2025-10 Status Notes (for future maintainers)

* `vaults.yaml` is the single source of truth for vault discovery. Add new vault entries there with `default: <name>` updated accordingly. Reloads happen at module import, so server restarts pick up changes.
* Regression tests live in `tests/test_frontmatter.py` (frontmatter), `tests/test_tag_search.py` (tag workflows), and `tests/test_path_normalization.py` (note identifier safety). Keep them updated before broader refactors.
* `python-frontmatter>=1.1.0` is now required. Recreate the virtualenv or run `uv pip install -r requirements.txt` after pulling updates.
* `vault.exists` in config is recomputed dynamically via `Path.is_dir()` when we build payloads, so stale metadata is less likely. We still surface the `exists` flag to clients so they can warn the user.
* The session cache (`ACTIVE_VAULTS`) keys off `id(ctx.session)`. FastMCP manages session lifetimes; when a session disappears the entry becomes unreachable and will be garbage collected. No explicit cleanup needed.
* Tool returns are dicts designed for Claude Desktop, but they’re equally useful for scripts or future REST layers—preserve this structure when extending functionality.
