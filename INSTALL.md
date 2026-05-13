# Installation

This plugin ships platform manifests and context files at the repository root, so install or clone the full repository rather than copying only the `skills/` directory.

## Claude Code

### Marketplace install

```bash
claude plugin install hiivmind-documentation-profile@hiivmind-documentation-profile-dev
```

### Local development

```bash
claude --plugin-dir /path/to/hiivmind-documentation-profile
```

### Project install

Add the development marketplace to `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": ["/path/to/hiivmind-documentation-profile/.claude-plugin"]
}
```

## Gemini CLI

### Install from GitHub

```bash
gemini extensions install https://github.com/hiivmind/hiivmind-documentation-profile
```

### Install from local path

```bash
gemini extensions install /path/to/hiivmind-documentation-profile
```

### Verify

```bash
gemini extensions list
```

Look for `hiivmind-documentation-profile` in the output. Restart Gemini CLI if it was running during install.

## Codex

### Native plugin packaging

If the repo includes both `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`, install it as a Codex plugin:

```bash
codex marketplace add https://github.com/hiivmind/hiivmind-documentation-profile
```

Then open `/plugins` in Codex and install `hiivmind-documentation-profile`.

### Local development

```bash
codex marketplace add /path/to/hiivmind-documentation-profile
```

Then open `/plugins` in Codex and install `hiivmind-documentation-profile`.

### Verify

Start a new Codex session and check one of:

- `/plugins` shows `hiivmind-documentation-profile` as installed.
- `~/.codex/config.toml` contains the marketplace and enabled plugin entries.
- The `package-documentation-profile` skill resolves in a fresh session.
