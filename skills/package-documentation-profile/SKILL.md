---
name: package-documentation-profile
description: Build or refresh a documentation-ready profile of a large software package before writing docs. Use when documentation needs to cover many modules, subpackages, public APIs, backend architecture, maintainers, users, contributors, or marketing audiences; when raw code is too large or uneven for direct LLM documentation; or when incremental documentation updates must track the last profiled git commit hash.
---

# Package Documentation Profile

Create an auditable package profile first, then derive documentation from that profile. The profile is a stocktake of modules, APIs, architecture roles, audience relevance, and provenance. It is not prose documentation until the user explicitly asks for docs synthesis.

**Input:** `package_path` or repository root. Optional: existing profile directory, audience lenses, include/exclude globs, output path.
**Output:** Profile manifest, per-module profiles, audience facet maps, coverage report, and update notes.

> **External references:**
> `references/profile-schema.md` | `references/classification-rubric.md` | `references/update-algorithm.md`

---

## Verification Gates

Every phase that depends on an external reference must read the file and prove it was loaded before executing phase logic.

```pseudocode
LOAD_AND_VERIFY(path, proof):
  content = Read(path)
  IF content IS empty OR unreadable:
    HALT "Cannot proceed: {path} not found or empty"
  extracted = proof(content)
  DISPLAY "Loaded {path}: {extracted}"
```

Before writing output, verify:

- Every discovered module is represented in a profile or an explicit ignore record.
- Every public API surface has an audience classification.
- The manifest records `source.git.current_hash`.
- Incremental updates record `previous_hash`, `current_hash`, and changed scopes.

---

## Overview

| Phase | Description | Runs |
|-------|-------------|------|
| **0: Intent** | Determine mode, scope, audiences, output location | Always |
| **1: Baseline** | Capture repository metadata, git hash, package layout | Always |
| **2: Discover** | Inventory modules, public exports, tests, examples, docs | Always |
| **3: Classify** | Assign module role, stability, audience, documentation priority | Always |
| **4: Profile** | Write or refresh per-module profile records | Always |
| **5: Facets** | Build audience-specific maps from the module profiles | Always |
| **6: Coverage** | Detect missing, stale, ambiguous, or undocumented areas | Always |
| **7: Update Manifest** | Persist provenance and incremental update metadata | Always |
| **8: Synthesize Docs** | Produce docs outlines or prose from the profile | Only if requested |

---

## Phase 0: Intent

Runs before scanning large code areas.

```pseudocode
INTENT():
  mode = choose one:
    - "initial-profile"       # no trusted profile exists
    - "incremental-refresh"   # profile exists; update from last hash
    - "docs-synthesis"        # profile exists; write docs from it

  audiences = choose any:
    - users
    - maintainers
    - contributors
    - backend-architecture
    - extension-authors
    - executives-marketing
    - broader-hype

  scope = determine:
    - repository root or package root
    - output profile directory
    - include/exclude globs
    - whether tests/examples/docs are included as evidence

  IF mode == "docs-synthesis" AND no profile exists:
    REPORT "No profile found; run initial-profile first."
    STOP
```

Default output path if the user does not specify one:

```text
docs/package-profile/
```

Do not overwrite hand-written documentation unless the user explicitly asks for docs synthesis.

---

## Phase 1: Baseline

```pseudocode
BASELINE(package_path):
  LOAD_AND_VERIFY("references/profile-schema.md",
    proof: content contains "manifest.json" and "modules/")

  current_hash = git rev-parse HEAD
  branch = git branch --show-current
  status = git status --short

  IF status is not empty:
    record working_tree_dirty = true
    record changed files separately from committed hash provenance

  detect package manager and language:
    - pyproject.toml, setup.cfg, package.json, Cargo.toml, go.mod, etc.
  detect package roots:
    - src layout
    - top-level package directories
    - namespace packages
  detect existing documentation:
    - README, docs/, examples/, notebooks, design notes

  write baseline into computed.repo
```

The commit hash is a provenance anchor, not a claim that the working tree is clean. If dirty files are present, keep them visible in the manifest.

---

## Phase 2: Discover

```pseudocode
DISCOVER(package_path):
  discover source files from include/exclude globs
  group files into modules using language-native boundaries
  discover public API signals:
    - __init__ exports, __all__, package entrypoints
    - public classes/functions/types
    - CLI commands, plugins, routes, tasks, schemas
  discover evidence:
    - tests that reference each module
    - examples that use each module
    - docs that mention each module
    - config files that wire each module

  FOR each module:
    computed.modules[module_id].files = source files
    computed.modules[module_id].public_symbols = symbols
    computed.modules[module_id].evidence = tests/examples/docs/config
```

Prefer language-aware tools when available: LSP, package metadata, AST parsers, and test discovery. Use text search for comments, docs, config keys, and framework conventions.

---

## Phase 3: Classify

```pseudocode
CLASSIFY(computed):
  LOAD_AND_VERIFY("references/classification-rubric.md",
    proof: content contains module roles and audience lenses)

  FOR module IN computed.modules:
    module.role = classify primary role:
      public-api | api-builder | protocol | backend | model | orchestration |
      io | integration | test-support | docs-example | legacy | experimental

    module.visibility = classify:
      public | semi-public | internal | private

    module.audiences = classify relevance:
      users | maintainers | contributors | backend-architecture |
      extension-authors | executives-marketing | broader-hype

    module.stability = classify:
      stable | evolving | experimental | deprecated | unknown

    module.doc_priority = classify:
      essential | useful | reference-only | internal-note | skip-with-reason

    module.confidence = high | medium | low
    IF confidence == low:
      add open_question with evidence gap
```

Classifications must be evidence-based. Record the evidence path, symbol, test, doc, or import relationship that supports each non-obvious classification.

---

## Phase 4: Profile

```pseudocode
PROFILE(computed, output_path):
  LOAD_AND_VERIFY("references/profile-schema.md",
    proof: content contains "module-profile.json")

  FOR module IN computed.modules:
    profile = {
      id,
      path,
      summary,
      role,
      visibility,
      stability,
      audiences,
      public_api,
      key_classes,
      key_functions,
      dependencies,
      dependents,
      extension_points,
      lifecycle_notes,
      documentation_hooks,
      examples,
      tests,
      risks,
      open_questions,
      evidence,
      source_hash
    }

    write module profile to:
      output_path + "/modules/" + safe_module_id + ".json"

  preserve user-authored fields if refreshing an existing profile:
    - notes
    - editorial_status
    - owner
    - manual_summary
```

Keep summaries short and factual. Avoid marketing language in module profiles; marketing and positioning belong in facet maps or docs synthesis.

---

## Phase 5: Facets

```pseudocode
FACETS(computed, output_path):
  FOR audience IN intent.audiences:
    facet = build ordered view from module profiles:
      - concepts this audience needs first
      - modules relevant to those concepts
      - public APIs and examples to feature
      - internals to hide, footnote, or reserve for maintainer docs
      - unresolved documentation questions

    write output_path + "/facets/" + audience + ".json"
```

Required default facets:

- **users:** concepts, workflows, public APIs, examples, common errors.
- **maintainers:** architecture, invariants, dependencies, tests, change risks.
- **backend-architecture:** protocols, implementations, dispatch, extension seams, known divergences.
- **broader-hype:** value proposition, differentiators, impressive capabilities, proof points.

The broader-hype facet must still cite real module evidence. Do not invent claims.

---

## Phase 6: Coverage

```pseudocode
COVERAGE(computed):
  missing_profiles = discovered modules without profiles
  stale_profiles = profiles whose source_hash differs from current_hash or changed files
  orphan_profiles = profiles for modules no longer found
  public_without_user_facet = public modules absent from users facet
  internal_without_maintainer_facet = internal architecture modules absent from maintainers facet
  low_confidence = modules with confidence == low

  write coverage report:
    output_path + "/coverage.md"

  IF missing_profiles is non-empty:
    fail verification unless each has an ignore reason
```

Use coverage to guide documentation planning. Do not hide gaps in generated prose.

---

## Phase 7: Update Manifest

```pseudocode
MANIFEST(computed, output_path):
  LOAD_AND_VERIFY("references/update-algorithm.md",
    proof: content contains "previous_hash" and "changed_scopes")

  manifest = {
    profile_version,
    generated_at,
    source: {
      root,
      git: {
        previous_hash,
        current_hash,
        branch,
        working_tree_dirty
      }
    },
    scope,
    audiences,
    counts,
    changed_scopes,
    ignored_paths,
    profile_files
  }

  write output_path + "/manifest.json"
```

The manifest is the entry point for future refreshes. If it is missing or invalid, fall back to initial profiling.

---

## Phase 8: Synthesize Docs

Run only when the user asks to write documentation from the profile.

```pseudocode
SYNTHESIZE(intent, output_path):
  read manifest and relevant facet files
  choose document type:
    - README section
    - user guide
    - API reference outline
    - maintainer architecture guide
    - contributor onboarding
    - marketing narrative
    - documentation roadmap

  write from profile evidence, not raw code alone
  include unresolved questions where they affect accuracy
  keep audience boundaries explicit
```

When writing docs, prefer generating an outline first for large projects. For high-level narratives, connect claims back to module evidence or examples.

---

## Incremental Refresh

Use this path when a profile manifest already exists.

```pseudocode
INCREMENTAL_REFRESH(package_path, profile_path):
  LOAD_AND_VERIFY("references/update-algorithm.md",
    proof: content contains REFRESH_SCOPE)

  manifest = read profile_path + "/manifest.json"
  previous_hash = manifest.source.git.current_hash
  current_hash = git rev-parse HEAD

  changed_files = git diff --name-only previous_hash current_hash
  changed_uncommitted = git status --short
  changed_scopes = map files to modules and facets

  FOR module IN changed_scopes.modules:
    rerun DISCOVER, CLASSIFY, PROFILE for module and local dependents

  rerun FACETS for affected audiences
  rerun COVERAGE
  rerun MANIFEST
```

If the previous hash is unavailable locally, record that incremental ancestry could not be verified and run a conservative full refresh.

---

## Reporting Format

End every run with:

```text
Profile path: <path>
Source hash: <current_hash>
Mode: <initial-profile|incremental-refresh|docs-synthesis>
Modules discovered: <n>
Modules profiled: <n>
Facets written: <list>
Coverage gaps: <n>
Changed scopes: <list or none>
Next recommended documentation work: <short list>
```
