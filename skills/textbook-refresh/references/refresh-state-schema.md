# Refresh State Schema

The `refresh-state.json` file tracks ephemeral operational state for a textbook
project. For the explicit target source repository root `R`, it lives at
`R/docs-site/site/refresh-state.json`, alongside `mkdocs.yml`.

**Important:** The concept-to-module-to-chapter mapping does NOT live here.
It lives in the enriched `learning-graph.json` nodes (fields: `source_module`,
`source_path`, `chapter`, `match_confidence`). This file tracks only the state
that changes between refreshes: content hashes, tool versions, and history.

## Schema

```json
{
  "schema_version": "1.0",
  "project": "<project-name>",

  "baseline": {
    "source_commit": "<git-sha>",
    "refresh_date": "YYYY-MM-DD",
    "tool_versions": {
      "chapter-content-generator": "0.09",
      "learning-graph-generator": "0.05",
      "faq-generator": "1.0",
      "textbook-refresh": "1.0"
    }
  },

  "chapter_state": {
    "<chapter-dir-name>": {
      "content_hash": "sha256:<hex>",
      "word_count": <int>,
      "has_concept_markers": <bool>,
      "last_generated": "YYYY-MM-DD",
      "generator_version": "<semver>"
    }
  },

  "learning_graph_state": {
    "concept_count": <int>,
    "edge_count": <int>,
    "enriched_count": <int>,
    "content_hash": "sha256:<hex>"
  },

  "faq_state": {
    "question_count": <int>,
    "content_hash": "sha256:<hex>"
  },

  "refresh_history": [
    {
      "date": "YYYY-MM-DD",
      "from_commit": "<git-sha>",
      "to_commit": "<git-sha>",
      "chapters_updated": ["<chapter-dir-name>"],
      "sections_regenerated": <int>,
      "faq_questions_updated": <int>,
      "learning_graph_nodes_updated": <int>,
      "tokens_used": <int>
    }
  ]
}
```

## Field Descriptions

### Top-level

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Schema version for forward compatibility |
| `project` | string | Project name (matches directory name) |

### baseline

| Field | Type | Description |
|-------|------|-------------|
| `source_commit` | string | Git SHA the textbook was last refreshed from (mirrors `learning-graph.json` → `metadata.source_commit`) |
| `refresh_date` | string | ISO date of last refresh |
| `tool_versions` | object | Version strings of tools used in last generation |

### chapter_state

Keyed by chapter directory name (e.g. `01-foundation-concepts`).

| Field | Type | Description |
|-------|------|-------------|
| `content_hash` | string | SHA-256 of the chapter index.md — used to detect manual edits |
| `word_count` | int | Word count of the chapter |
| `has_concept_markers` | bool | Whether chapter has `<!-- concept:N -->` markers |
| `last_generated` | string | ISO date of last generation/refresh |
| `generator_version` | string | Version of chapter-content-generator used |

### learning_graph_state

| Field | Type | Description |
|-------|------|-------------|
| `concept_count` | int | Number of concepts in the learning graph |
| `edge_count` | int | Number of dependency edges |
| `enriched_count` | int | Number of nodes with `source_module` set (non-null) |
| `content_hash` | string | SHA-256 of learning-graph.json |

### faq_state

| Field | Type | Description |
|-------|------|-------------|
| `question_count` | int | Number of FAQ questions |
| `content_hash` | string | SHA-256 of faq.md |

### refresh_history

Append-only log of past refreshes.

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | ISO date of the refresh |
| `from_commit` | string | Baseline commit before refresh |
| `to_commit` | string | New commit after refresh |
| `chapters_updated` | string[] | Which chapters were touched |
| `sections_regenerated` | int | Number of concept sections regenerated |
| `faq_questions_updated` | int | Number of FAQ entries refreshed |
| `learning_graph_nodes_updated` | int | Number of learning graph nodes modified |
| `tokens_used` | int | Approximate token usage |

## What Lives Where

| Data | Location | Reason |
|------|----------|--------|
| Concept → module mapping | `learning-graph.json` nodes | Stable knowledge; shared across skills |
| Concept → chapter mapping | `learning-graph.json` nodes | Stable knowledge; shared across skills |
| Concept → source path | `learning-graph.json` nodes | Stable knowledge; shared across skills |
| Source baseline commit | `learning-graph.json` metadata + `refresh-state.json` baseline | Duplicated for convenience; graph is authoritative |
| Profile directory path | `learning-graph.json` metadata | `docs-site/profile`, relative to source root `R`; provenance, never an output redirect |
| Chapter content hashes | `refresh-state.json` chapter_state | Ephemeral; changes every refresh |
| Manual edit detection | `refresh-state.json` chapter_state | Ephemeral; operational concern |
| Refresh audit log | `refresh-state.json` refresh_history | Ephemeral; append-only |
| Tool versions | `refresh-state.json` baseline | Ephemeral; version-mismatch detection |
