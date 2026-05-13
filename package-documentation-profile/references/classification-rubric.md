# Classification Rubric

Classify modules from evidence, not naming alone. Use `confidence: low` when evidence is thin or contradictory.

## Module Roles

| Role | Use When |
|------|----------|
| `public-api` | Imported by users, exported from package root, documented, or used in examples. |
| `api-builder` | Provides fluent builders, DSL methods, decorators, or user-facing construction helpers. |
| `protocol` | Defines interfaces, abstract methods, contracts, schemas, or backend obligations. |
| `backend` | Implements protocol behavior for a specific runtime, storage system, framework, or engine. |
| `model` | Defines serializable data structures, AST nodes, domain objects, or metadata containers. |
| `orchestration` | Coordinates multiple subsystems, dispatch, traversal, dependency ordering, or lifecycle. |
| `io` | Reads, writes, serializes, deserializes, or adapts external resources. |
| `integration` | Connects with third-party systems, plugins, CLIs, services, or framework hooks. |
| `test-support` | Fixtures, helpers, test data builders, or validation utilities. |
| `docs-example` | Examples, notebooks, tutorial code, or documentation-only support. |
| `legacy` | Retained for compatibility, superseded by newer modules, or marked deprecated. |
| `experimental` | Marked unstable, incubating, incomplete, TODO-heavy, or protected by feature flags. |

## Visibility

| Visibility | Use When |
|------------|----------|
| `public` | Part of documented or exported API. |
| `semi-public` | Used by advanced users, extension authors, or public configuration but not primary API. |
| `internal` | Maintainer-facing implementation detail. |
| `private` | File-local, underscore-prefixed, generated, or not intended for external reference. |

## Stability

| Stability | Use When |
|-----------|----------|
| `stable` | Covered by tests/docs and unlikely to change casually. |
| `evolving` | Active design surface, recently changed, or incomplete but intended to persist. |
| `experimental` | Feature-flagged, prototype, or explicitly unstable. |
| `deprecated` | Marked for removal or superseded. |
| `unknown` | Not enough evidence. |

## Audience Lenses

| Audience | Include Modules That Explain |
|----------|------------------------------|
| `users` | What users import, configure, call, or learn first. |
| `maintainers` | Invariants, internal architecture, tests, failure modes, and change risks. |
| `contributors` | Where to add features, how modules fit, naming conventions, and tests to update. |
| `backend-architecture` | Protocols, dispatch, backend implementations, adapters, and divergences. |
| `extension-authors` | Extension points, registries, plugin APIs, contracts, compatibility boundaries. |
| `executives-marketing` | Capabilities, differentiators, roadmap signals, and credible proof points. |
| `broader-hype` | Simple narrative hooks, demos, before/after value, and memorable product framing. |

## Documentation Priority

| Priority | Meaning |
|----------|---------|
| `essential` | Docs are incomplete or misleading without this module. |
| `useful` | Helps users or maintainers understand important workflows. |
| `reference-only` | Mention in generated reference material, not conceptual guides. |
| `internal-note` | Keep in maintainer docs or architecture notes only. |
| `skip-with-reason` | Excluded from docs; record a reason. |

## Evidence Rules

- Public exports, examples, and tests outweigh file names.
- Architecture docs and design principles outweigh inferred intent.
- Recent changes may indicate evolving areas, but do not imply public status.
- A module can serve multiple audiences, but must have one primary role.
- Marketing or hype claims require proof points from examples, tests, docs, or capabilities.
