# Hiivmind Documentation Profile

Portable skill plugin for building documentation-ready profiles of large software packages before writing prose documentation.

The main skill, `package-documentation-profile`, stocktakes a package module by module, classifies each module by role and audience, records evidence, and tracks the git commit used for progressive refreshes. The output profile can then drive user docs, maintainer architecture guides, contributor onboarding, and higher-level positioning material.

## Contents

- `skills/package-documentation-profile/SKILL.md` - the procedural skill.
- `.claude-plugin/` - Claude Code plugin metadata.
- `gemini-extension.json` and `GEMINI.md` - Gemini CLI extension metadata and context.
- `.codex-plugin/` and `.agents/plugins/marketplace.json` - Codex plugin metadata.
- `AGENTS.md` and `CLAUDE.md` - platform context files.

## Installation

See [INSTALL.md](INSTALL.md).

## Publishing

See [PUBLISHING.md](PUBLISHING.md).
