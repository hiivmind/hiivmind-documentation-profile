# Change Classification Reference

This reference describes how source code changes are classified and what
regeneration action each classification triggers.

## Classification Hierarchy

```
Source file changed
  ├─ File added         → new_module
  ├─ File deleted       → removed_module
  └─ File modified
       ├─ Public API changed
       │    ├─ Symbols added only      → new_symbols
       │    ├─ Symbols removed only    → removed_symbols
       │    ├─ Symbols added+removed
       │    │    ├─ Rename detected    → renamed_symbols
       │    │    └─ No rename match    → mixed_changes
       │    └─ Same symbols, different signatures → signature_change
       └─ Public API unchanged
            ├─ Docstrings changed      → docstring_only
            └─ Internal code changed   → internal_refactor
```

## Classifications

### new_module

**Detection:** File path exists in current commit but not in baseline.

**Chapter impact:** High. A new module may introduce concepts not covered by
any existing chapter. The refresh skill flags this for review — the user must
decide whether to:
- Add concepts to the learning graph and assign them to an existing chapter
- Create a new chapter (requires re-running book-chapter-generator)
- Skip (the module is an internal implementation detail not worth teaching)

**API page impact:** A new API reference page should be created.

**Learning graph impact:** May need new concept nodes and dependency edges.

**Automated action:** Flag for manual review. Do not auto-generate content
for unmapped modules.

---

### removed_module

**Detection:** File path exists in baseline but not in current commit.

**Chapter impact:** High. Concepts taught from this module may be orphaned.
The refresh skill identifies which chapters and concepts are affected.

**API page impact:** The corresponding API page should be removed or marked
as deprecated.

**Learning graph impact:** Concepts may need removal or reassignment.

**Automated action:** Flag for manual review. Identify affected chapters and
concepts. Do not auto-delete content — the concepts may still be teachable
from a different angle.

---

### new_symbols

**Detection:** New class or function names appear in `public_api` that were
not in the old profile.

**Chapter impact:** Medium. New sections should be added to the chapter(s)
that cover this module. Use concept markers to insert content at the
appropriate position.

**API page impact:** Automatic (mkdocstrings picks up new symbols).

**Learning graph impact:** New concepts may be needed if the symbols represent
teachable concepts.

**Automated action:** Generate new section content for each new symbol,
inserting after the last related concept marker in the chapter.

---

### removed_symbols

**Detection:** Class or function names from the old `public_api` are absent
in the current source.

**Chapter impact:** Medium. Sections teaching the removed symbol should be
revised or removed. Simply deleting prose can leave gaps — the surrounding
narrative may reference the removed concept.

**API page impact:** Automatic (mkdocstrings drops absent symbols).

**Learning graph impact:** Concepts may need removal.

**Automated action:** Regenerate the sections covering the removed concepts,
using the surrounding context to produce a coherent narrative without the
removed content. Flag the concept for potential removal from the learning
graph.

---

### renamed_symbols

**Detection:** A symbol was removed AND a new symbol was added with a
similar name or identical structure (same methods, same parameters).

**Rename detection heuristics:**
1. Edit distance between old and new name is ≤ 3 characters
2. Old and new symbols have the same number and types of methods/parameters
3. The new symbol appears in the same file or a file with a similar path

**Chapter impact:** Low. Find-and-replace the old name with the new name
throughout the chapter. No structural changes needed.

**API page impact:** Automatic.

**Learning graph impact:** Update concept label if it references the old name.

**Automated action:** String replacement across affected chapters and
learning graph. No LLM regeneration needed.

---

### mixed_changes

**Detection:** Both symbols added and removed, but no rename pattern detected.
This typically indicates a significant API redesign.

**Chapter impact:** High. Affected sections should be regenerated using the
new source code as context.

**API page impact:** Automatic.

**Learning graph impact:** Review concept coverage.

**Automated action:** Regenerate all sections in the chapter that cover
concepts from this module. This is the most expensive classification short
of full chapter regeneration.

---

### signature_change

**Detection:** The same symbols exist in both old and new versions, but their
signatures differ (different parameters, return types, or method signatures).

**Chapter impact:** Medium. Code examples in the chapter that demonstrate
the changed signatures need updating. Prose explaining parameters may also
need revision.

**API page impact:** Automatic.

**Learning graph impact:** None.

**Automated action:** Regenerate the concept sections that contain code
examples for the changed symbols. Focus on code blocks and parameter
explanations rather than conceptual prose.

---

### docstring_only

**Detection:** Source file changed but `public_api` list and all symbol
signatures are identical. Only docstrings, comments, or type annotations
changed.

**Chapter impact:** None. The chapter teaches concepts, not docstrings.

**API page impact:** Automatic (mkdocstrings re-renders updated docstrings).

**Learning graph impact:** None.

**Automated action:** No chapter regeneration needed. The API reference pages
update automatically on next `mkdocs build`.

---

### internal_refactor

**Detection:** Changes are in non-public code (private methods, internal
helpers, implementation details). The public API surface is unchanged.

**Chapter impact:** None.

**API page impact:** None (private symbols are not rendered).

**Learning graph impact:** None.

**Automated action:** No action needed. Log the change for audit purposes.

---

## Cost by Classification

| Classification | Regeneration Scope | Approx Tokens |
|---------------|-------------------|---------------|
| `internal_refactor` | None | 0 |
| `docstring_only` | None (API auto-updates) | 0 |
| `renamed_symbols` | String replacement | < 1k |
| `signature_change` | Code examples in 1-3 sections | 3-8k |
| `new_symbols` | 1-3 new sections | 5-15k |
| `removed_symbols` | 1-3 sections revised | 5-15k |
| `mixed_changes` | All sections for affected module | 10-30k |
| `new_module` | Manual review + potential new sections | 15-40k |
| `removed_module` | Manual review + section removal | 5-15k |

## Priority Order

When multiple classifications apply to a single chapter (e.g. one module
had a rename and another had new symbols), process in this order:

1. `renamed_symbols` — apply string replacements first (cheapest, no conflicts)
2. `removed_symbols` — remove stale content before adding new content
3. `signature_change` — update existing code examples
4. `new_symbols` — add new sections
5. `mixed_changes` — regenerate remaining sections

This order minimises conflicts between regeneration passes.
