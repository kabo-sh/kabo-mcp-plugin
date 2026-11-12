# kabo-sh

Install [Kabo](https://kabo.sh) into the AI assistant you already use. Kabo adds creator research
tools for public YouTube, Instagram and TikTok data, plus ready-made Skills (workflows).

```sh
npx kabo-sh install
```

What it does:

- **Claude Code** found: runs `claude plugin marketplace add kabo-sh/kabo-mcp-plugin` and
  `claude plugin install kabo@kabo-mcp-plugin`.
- **Codex** found: runs `codex plugin marketplace add kabo-sh/kabo-mcp-plugin` and
  `codex plugin add kabo@kabo-plugin-openai`.
- **Neither found** (for example on the cloud computer of Grok Bot or Muse): clones the Skills to
  `~/kabo-mcp-plugin` and prints how to add the connection.

It never signs in for you. Kabo sign-in happens in your browser (OAuth); no API key or password is
read, printed or stored. The command prints the one step that is left for you.

Options: `--host claude-code|codex|skills-only`, `--dry-run` (print the commands, run nothing).

Source and full instructions: https://github.com/kabo-sh/kabo-mcp-plugin
