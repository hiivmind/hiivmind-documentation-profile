# Profile Schema

Use these files as the canonical profile layout. JSON is preferred for machine-readable inventories; Markdown is acceptable for human reports.

```text
docs/package-profile/
├── manifest.json
├── coverage.md
├── modules/
│   └── <module-id>.json
└── facets/
    └── <audience>.json
```

## `manifest.json`

Required fields:

```json
{
  "profile_version": "1.0",
  "generated_at": "ISO-8601 timestamp",
  "source": {
    "root": "absolute or repo-relative path",
    "git": {
      "previous_hash": "nullable commit hash",
      "current_hash": "commit hash",
      "branch": "branch name or detached HEAD",
      "working_tree_dirty": false
    }
  },
  "scope": {
    "include": [],
    "exclude": [],
    "package_roots": []
  },
  "audiences": [],
  "counts": {
    "modules_discovered": 0,
    "modules_profiled": 0,
    "profiles_ignored": 0,
    "facets_written": 0
  },
  "changed_scopes": {
    "files": [],
    "modules": [],
    "facets": []
  },
  "ignored_paths": [
    {
      "path": "string",
      "reason": "string"
    }
  ],
  "profile_files": {
    "modules": {},
    "facets": {}
  }
}
```

## `modules/<module-id>.json`

Required fields:

```json
{
  "id": "package.module",
  "path": "src/package/module.py",
  "summary": "Short factual summary.",
  "role": "public-api",
  "visibility": "public",
  "stability": "stable",
  "audiences": ["users", "maintainers"],
  "doc_priority": "essential",
  "confidence": "high",
  "public_api": [],
  "key_classes": [],
  "key_functions": [],
  "dependencies": [],
  "dependents": [],
  "extension_points": [],
  "lifecycle_notes": [],
  "documentation_hooks": [],
  "examples": [],
  "tests": [],
  "risks": [],
  "open_questions": [],
  "evidence": [
    {
      "kind": "symbol|test|example|doc|config|import",
      "path": "string",
      "detail": "string"
    }
  ],
  "source_hash": "commit hash",
  "manual": {
    "notes": "",
    "editorial_status": "",
    "owner": "",
    "manual_summary": ""
  }
}
```

Preserve the `manual` object during refreshes.

## `facets/<audience>.json`

Required fields:

```json
{
  "audience": "users",
  "summary": "What this audience needs from the package.",
  "concepts": [
    {
      "name": "string",
      "module_ids": [],
      "recommended_docs": [],
      "evidence": []
    }
  ],
  "featured_modules": [],
  "hidden_or_internal_modules": [],
  "documentation_plan": [],
  "open_questions": []
}
```
