# Codex Tool Mapping

Skills may use Claude Code tool names. When executing this skill in Codex, use Codex equivalents:

| Skill references | Codex equivalent |
| ---------------- | ---------------- |
| `Read`, `Write`, `Edit` | Use native file read/write/edit tools |
| `Bash` | Use the shell command tool |
| `Grep` | Use `rg` through the shell command tool |
| `Glob` | Use `rg --files`, `find`, or native file search |
| `TodoWrite` | Use `update_plan` |
| `Skill` | Skills are discovered natively; follow the `SKILL.md` instructions |
| `Task` | Use `spawn_agent` when available |

For this skill, subagents are optional. The core workflow can run in a single session.
