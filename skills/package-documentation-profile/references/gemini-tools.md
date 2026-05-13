# Gemini CLI Tool Mapping

Skills may use Claude Code tool names. When executing this skill in Gemini CLI, use Gemini equivalents:

| Skill references | Gemini CLI equivalent |
| ---------------- | --------------------- |
| `Read` | `read_file` |
| `Write` | `write_file` |
| `Edit` | `replace` |
| `Bash` | `run_shell_command` |
| `Grep` | `grep_search` |
| `Glob` | `glob` |
| `TodoWrite` | `write_todos` |
| `Skill` | `activate_skill` |
| `Task` | No direct equivalent; run the step in-session |

For this skill, subagents are optional. The core workflow can run in a single session.
