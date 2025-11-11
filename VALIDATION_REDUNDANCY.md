# Validation Redundancy Analysis - v1.5 Pydantic Migration

This document tracks validation logic that exists in multiple places and should be consolidated in Phase 6.

## Current Validation Architecture (Post-Phase 2)

### Layer 1: Pydantic Input Models (`input_models.py`)
**What it validates:**
- Note title format (empty, whitespace, path traversal, absolute paths)
- `.md` extension stripping
- Vault name format (empty string check)
- Content requirements (empty for append/prepend)
- Move operation constraints (old != new title)

**When it runs:** At MCP tool boundary, before any business logic

### Layer 2: Core Operations (`core/vault_operations.py`)
**What it validates:**
- Note title format via `normalize_note_identifier()` ⚠️ REDUNDANT
- `.md` extension stripping via `normalize_note_identifier()` ⚠️ REDUNDANT
- Path traversal via `normalize_note_identifier()` ⚠️ REDUNDANT
- Absolute path check via `normalize_note_identifier()` ⚠️ REDUNDANT
- Path sandboxing via `resolve_note_path()` ✓ KEEP (filesystem-specific)
- Vault directory existence via `ensure_vault_ready()` ✓ KEEP (filesystem-specific)

**When it runs:** In core business logic, called by tool wrappers

---

## Redundancies to Address in Phase 6

### 1. `vault_operations.normalize_note_identifier()` (lines 20-56)

**Current function:**
```python
def normalize_note_identifier(identifier: str) -> Path:
    """Normalize user-provided note identifiers to a safe, relative markdown path."""
    cleaned = identifier.strip()
    if not cleaned:
        raise ValueError("Note title cannot be empty.")  # ⚠️ REDUNDANT

    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]  # ⚠️ REDUNDANT

    parts = cleaned.split("/")
    if any(part in {".", ".."} for part in parts):
        raise ValueError("Note title cannot contain '.' or '..' segments.")  # ⚠️ REDUNDANT

    # ... path construction ...

    if relative.is_absolute():
        raise ValueError("Note title must be a relative path within the vault.")  # ⚠️ REDUNDANT

    return relative
```

**Redundant with:**
- `BaseNoteInput.validate_title()` - validates empty, `.md`, path traversal, absolute paths
- `MoveNoteInput.validate_title()` - same validation for old_title and new_title

**Phase 6 Refactor:**
```python
def construct_note_path(identifier: str) -> Path:
    """Construct a Path object from a pre-validated note identifier.

    IMPORTANT: This function assumes the identifier has already been validated
    by a Pydantic input model. It only performs path construction, not validation.

    Args:
        identifier: Pre-validated note identifier (already stripped, no .md, no traversal)

    Returns:
        Path object for the note within the vault
    """
    parts = identifier.split("/")
    leaf = parts[-1]
    leaf_with_extension = f"{leaf}.md"

    if len(parts) == 1:
        return Path(leaf_with_extension)
    else:
        return Path(*parts[:-1]) / leaf_with_extension
```

**Benefits:**
- Single source of truth for validation (Pydantic models)
- Faster execution (no duplicate checks)
- Clearer separation: validation at boundary, path construction in core
- Easier to test (path construction logic is simpler)

---

### 2. `vault_operations.resolve_note_path()` (lines 58-77)

**Current function:**
```python
def resolve_note_path(vault: VaultMetadata, title: str) -> Path:
    """Resolve a note title to an absolute vault path, enforcing sandbox rules."""
    relative = normalize_note_identifier(title)  # ⚠️ Calls redundant validation
    candidate = (vault.path / relative).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)
    if not candidate.is_relative_to(vault_root):
        raise ValueError("Note path escapes the configured vault.")  # ✓ KEEP (filesystem check)
    return candidate
```

**Phase 6 Refactor:**
```python
def resolve_note_path(vault: VaultMetadata, title: str) -> Path:
    """Resolve a pre-validated note title to an absolute vault path.

    IMPORTANT: Assumes title has been validated by Pydantic input model.
    Only performs path resolution and sandbox enforcement.

    Args:
        vault: Vault metadata
        title: Pre-validated note identifier

    Returns:
        Absolute path to note within vault

    Raises:
        ValueError: If resolved path escapes vault (filesystem-level check)
    """
    relative = construct_note_path(title)  # No validation, just construction
    candidate = (vault.path / relative).resolve(strict=False)
    vault_root = vault.path.resolve(strict=False)

    # This is the only validation we keep - ensures path doesn't escape vault
    # This is a filesystem-level check that can't be done in Pydantic
    if not candidate.is_relative_to(vault_root):
        raise ValueError("Note path escapes the configured vault.")

    return candidate
```

**Benefits:**
- Removes redundant validation calls
- Keeps only filesystem-specific security check
- Clear documentation that validation happened earlier

---

## Validation Responsibility Matrix

| Validation Type | Pydantic Models | Core Operations | Reason |
|----------------|-----------------|-----------------|---------|
| Empty title | ✓ | ❌ Remove | Format validation at boundary |
| Whitespace-only title | ✓ | ❌ Remove | Format validation at boundary |
| Path traversal (`.`, `..`) | ✓ | ❌ Remove | Security check at boundary |
| Absolute path (`/...`) | ✓ | ❌ Remove | Security check at boundary |
| `.md` extension stripping | ✓ | ❌ Remove | Normalization at boundary |
| Path escapes vault root | ❌ | ✓ Keep | Filesystem check (can't be done in Pydantic) |
| Vault directory exists | ❌ | ✓ Keep | Filesystem check (runtime state) |
| Note file exists | ❌ | ✓ Keep | Filesystem check (runtime state) |
| Empty content (append/prepend) | ✓ | ❌ N/A | Business rule at boundary |
| Same old/new title (move) | ✓ | ❌ Remove | Business rule at boundary |

---

## Phase 6 Checklist

- [ ] Refactor `normalize_note_identifier()` → `construct_note_path()`
  - [ ] Remove empty title check
  - [ ] Remove `.md` stripping
  - [ ] Remove path traversal check
  - [ ] Remove absolute path check
  - [ ] Keep only path construction logic
  - [ ] Update docstring to indicate pre-validation assumption

- [ ] Update `resolve_note_path()`
  - [ ] Call `construct_note_path()` instead of `normalize_note_identifier()`
  - [ ] Keep only vault escape check
  - [ ] Update docstring to indicate pre-validation assumption

- [ ] Update all call sites
  - [ ] Search for `normalize_note_identifier()` calls
  - [ ] Replace with `construct_note_path()` if called after Pydantic validation
  - [ ] Add comments explaining validation happened at boundary

- [ ] Update tests
  - [ ] Move validation tests from `test_path_normalization.py` to `test_input_models.py`
  - [ ] Keep only path construction tests in core tests
  - [ ] Add integration tests that verify validation + construction flow

- [ ] Performance testing
  - [ ] Benchmark before/after refactor
  - [ ] Measure reduction in redundant checks
  - [ ] Document performance improvements

- [ ] Documentation
  - [ ] Update AGENTS.md with new architecture
  - [ ] Update function docstrings
  - [ ] Add migration guide for future maintainers
  - [ ] Document why filesystem checks stay in core

---

## Benefits of Consolidation

1. **Single Source of Truth**: Validation logic lives in one place (Pydantic models)
2. **Better Error Messages**: Pydantic provides field-level errors with context
3. **Performance**: No redundant validation on every core operation call
4. **Maintainability**: Changes to validation rules only need one update
5. **Testability**: Validation tests focus on input models, core tests focus on business logic
6. **Clarity**: Clear architectural boundary between validation and execution

---

## Migration Safety

To ensure safe migration in Phase 6:

1. **Add assertions in dev mode**: Temporarily add assertions that Pydantic validation matches old validation
2. **Gradual rollout**: Refactor one function at a time, verify tests pass
3. **Regression testing**: Run full test suite after each change
4. **Documentation**: Update docs to explain new architecture to future maintainers
