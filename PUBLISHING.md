# Publishing & Discoverability

How to make **Hiivmind Documentation Profile** discoverable on each platform.

## Claude Code

The Claude plugin manifest lives at `.claude-plugin/plugin.json`.

For local marketplace testing, use `.claude-plugin/marketplace.json` and add the directory to Claude Code's known marketplaces.

## Gemini CLI

Gemini CLI discovers the extension through `gemini-extension.json`, which points at `GEMINI.md` as the context file.

Publish by making the repository accessible and installing with:

```bash
gemini extensions install https://github.com/hiivmind/hiivmind-documentation-profile
```

## Codex

Codex discovers the plugin through `.agents/plugins/marketplace.json`, which points at the repository root. The plugin manifest lives at `.codex-plugin/plugin.json` and exposes `./skills/`.

Publish by making the repository accessible and adding the marketplace:

```bash
codex marketplace add https://github.com/hiivmind/hiivmind-documentation-profile
```
