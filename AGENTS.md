# Hiivmind Documentation Profile

Build auditable module-by-module package profiles before writing documentation for large projects, with audience facets and git-hash-based incremental refresh.

## Project Context

Hiivmind Documentation Profile is a portable plugin that provides skills for use across Claude Code, Gemini CLI, and Codex. Skills are defined using the open `SKILL.md` standard and can be invoked through each platform's native skill mechanism.

## Skills

This plugin provides the following skills. Read the linked `SKILL.md` file to understand how to invoke and execute each skill:

- `skills/package-documentation-profile/SKILL.md`

## Tool Name Mapping

Skills use Claude Code tool names. Platform equivalents:

- `Read` -> your platform's file-read tool
- `Write` -> your platform's file-write tool
- `Edit` -> your platform's file-edit tool
- `Bash` -> your platform's shell/command tool
- `Grep` -> your platform's content-search tool
- `Glob` -> your platform's file-search tool
- `Skill` -> your platform's skill-invoke tool
- `Task` -> your platform's subagent-dispatch tool, if supported

See each skill's `references/` directory for platform-specific tool mapping notes.
