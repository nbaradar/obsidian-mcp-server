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

## Codebase Structure (v1.4.3 - Modular Refactor)

**As of v1.4.3**, the codebase has been refactored from a single monolithic `obsidian_vault.py` file into a well-organized package structure for better maintainability, testability, and extensibility.

### Package Structure

```
obsidian-mcp-server/
├── obsidian_vault/              # Main package directory
│   ├── __init__.py              # Package initialization, exports server and tools
│   ├── server.py                # FastMCP server setup and tool registration
│   ├── config.py                # Configuration loading (vaults.yaml)
│   ├── models.py                # Pydantic models and dataclasses
│   ├── session.py               # Session state management (active vault)
│   ├── constants.py             # Module-level constants
│   │
│   ├── core/                    # Core business logic (NO MCP dependencies)
│   │   ├── vault_operations.py       # Path validation and sandboxing
│   │   ├── note_operations.py        # Note CRUD operations
│   │   ├── search_operations.py      # Search and discovery
│   │   ├── section_operations.py     # Heading-based manipulation
│   │   └── frontmatter_operations.py # YAML frontmatter ops
│   │
│   └── tools/                   # MCP tool definitions (thin wrappers)
│       ├── vault_tools.py       # list_vaults, set_active_vault
│       ├── note_tools.py        # CRUD tool wrappers
│       ├── search_tools.py      # Search/discovery tool wrappers
│       ├── section_tools.py     # Section manipulation tool wrappers
│       └── frontmatter_tools.py # Frontmatter tool wrappers
│
├── main.py                      # Entry point for MCP server
├── vaults.yaml                  # Vault configuration
└── tests/                       # Test suite
```

### Design Principles

1. **Separation of Concerns**: Core business logic (`core/`) is completely independent of MCP. Tool modules (`tools/`) are thin wrappers that handle MCP-specific concerns (context, vault resolution, response formatting).

2. **Single Responsibility**: Each module has a clear, focused purpose:
   - `vault_operations.py`: Path validation ONLY
   - `note_operations.py`: CRUD operations ONLY
   - `search_operations.py`: Search/discovery ONLY
   - Tool modules: MCP decorators and vault resolution ONLY

3. **Testability**: Core modules can be tested without MCP server infrastructure. Tool modules test MCP integration separately.

4. **Import Flow**:
   - `main.py` → `obsidian_vault/__init__.py` → imports `tools/` → registers with `server.py`
   - Tools import from `core/` for business logic
   - `core/` modules import from `models.py`, `constants.py` (no circular deps)

### Working with the Codebase

**Adding a New Tool:**
1. Add core logic function to appropriate `core/*.py` module
2. Create MCP wrapper in appropriate `tools/*.py` module
3. Import is automatic via `tools/__init__.py`

**Modifying Business Logic:**
1. Edit the appropriate `core/*.py` module
2. No changes needed to tool wrappers (they just delegate)
3. Update tests in `tests/`

**Configuration Changes:**
1. Edit `vaults.yaml` for vault configuration
2. Edit `constants.py` for module-level constants
3. Changes picked up on next import/restart

## 2025-10 Status Notes (for future maintainers)

* **Codebase**: As of v1.4.3, the codebase uses a modular package structure. The old `obsidian_vault.py` monolith has been refactored into `obsidian_vault/` package with clear separation between core business logic (`core/`) and MCP tool wrappers (`tools/`).
* **Configuration**: `vaults.yaml` is the single source of truth for vault discovery. Add new vault entries there with `default: <name>` updated accordingly. Loaded by `config.py` at module import time.
* **Testing**: Regression tests live in `tests/test_frontmatter.py` (frontmatter), `tests/test_tag_search.py` (tag workflows), and `tests/test_path_normalization.py` (note identifier safety). Keep them updated before broader refactors.
* **Dependencies**: `python-frontmatter>=1.1.0` is required. Use `uv pip install -r requirements.txt` to install dependencies.
* **Session Management**: The session cache (`_ACTIVE_VAULTS` in `session.py`) keys off `id(ctx.session)`. FastMCP manages session lifetimes; garbage collection handles cleanup automatically.
* **Tool Returns**: All tool return dicts are designed for Claude Desktop but are equally useful for scripts or future REST layers—preserve this structure when extending functionality.
* **Vault Metadata**: `vault.exists` in config payloads is computed dynamically via `Path.is_dir()` in `models.py`, so stale metadata is less likely.
