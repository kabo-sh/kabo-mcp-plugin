# kabo-sh

Install [Kabo](https://kabo.sh) into the AI assistant you already use. Kabo adds creator research
tools for public YouTube, Instagram and TikTok data, plus ready-made Skills (workflows).

```sh
npx kabo-sh install --host <your assistant>
```

Name your assistant with `--host` (the list is below). Without it, the installer detects the assistants on
this computer: if it finds one, it installs there; if it finds several, it installs nothing and prints one
command per assistant (`--host all` installs into every one it found). An AI assistant running the command
should always pass its own `--host` and relay only its own steps.

Each result says what was done and what is not done yet (reload, trust, sign-in). Kabo is ready only after
the sign-in and a successful `get_research_capabilities` call.

What it does, by assistant:

- **Claude Code** found: `claude plugin marketplace add kabo-sh/kabo-mcp-plugin` (skipped when a
  marketplace with that name is already registered) and `claude plugin install kabo@kabo-mcp-plugin`.
- **Codex** found: `codex plugin marketplace add kabo-sh/kabo-mcp-plugin` and
  `codex plugin add kabo@kabo-plugin-openai`.
- **WorkBuddy** (desktop app) found: runs the command line that ships inside WorkBuddy against
  WorkBuddy's own settings folder, with the same two plugin commands as Claude Code. Quit WorkBuddy
  completely and open it again, then click Trust on Kabo in its connector management and sign in.
- **CodeBuddy Code** (`codebuddy` command) found: the same two plugin commands.
- **Doubao Work** (豆包工作) found: copies every Kabo Skill folder in full to `~/.agents/skills` (the
  folder Doubao reads). Doubao has no config file for connections, so the command prints the exact steps
  to add it in the app (插件 · 技能 · 工作台 → 管理 → 连接器 → 添加 → 自定义连接器, name `kabo`, type HTTP,
  address `https://kabo.sh/mcp-pub`, then 去授权 and sign in). Doubao never picks a Skill by itself, so the
  first message must name it: 「请用 start-with-kabo 技能带我开始」.
- **Qwen Work** (千问工作) found: copies the Skills to `~/.qwenworkcn/skills` and adds
  `{"mcpServers":{"kabo":{"url":"https://kabo.sh/mcp-pub"}}}` to `~/.qwenworkcn/mcp.json`, keeping every
  other server and the rest of the file (a timestamped `.kabo-backup-*` copy is written first; the file is
  left alone if it is not valid JSON). Restart Qwen Work and sign in when it asks. Create a project with a working folder you choose,
  and start Kabo and create daily tasks inside that project. First message:
  「请用 start-with-kabo 技能带我开始」. Unattended runs with this project setup still need verification.
- **DeepSeek Harness** found: copies the Skills to `~/.agents/skills` and appends an `mcp-kabo` entry to
  `~/.dsh/profiles/desktop/cordis.patch.yml` (`cordis.yml` is never edited). DeepSeek cannot sign in to a
  remote connection itself, so the entry runs the open-source `mcp-remote` bridge through the absolute
  path of `npx` (Node.js required), with `--static-oauth-client-metadata` so Kabo grants write access at
  the first sign-in. Everything already in the patch file is kept, a timestamped backup is written first,
  and an existing `mcp-kabo` entry is updated without removing other entries in the same insert group.
  Invalid YAML, duplicate Kabo entries and Kabo entries using anchors or aliases are left untouched
  with an explanation, so a shared reference cannot silently change another plugin. Restart DeepSeek Harness and sign in
  in the browser; first message: 「请用 start-with-kabo 技能带我开始」.
- `~/.agents/skills` is shared by Doubao Work, DeepSeek Harness and Codex: the Skills also show up in the others
  found on the computer, which can use them only once Kabo is connected there; the installer names them. If
  Kabo is also installed in Codex, Codex lists the Skills twice
  (harmless; the installer prints a note).
- **Muse** (run by Muse on its cloud computer): copies each Skill into `~/workspace/custom-skills/`
  with the `skill.yaml` file Muse needs to find it. The connection is made by Muse's own custom
  connector flow and the user's browser sign-in.
- **Grok Bot** (run by the Bot on its cloud computer): clones the Skills to `~/kabo-mcp-plugin` and
  tells the Bot to save each one with its own skill tool. The connection is added from the chat and the
  user signs in through the Connect card.
- **Anything else**: clones the Skills to `~/kabo-mcp-plugin` and prints how to add the connection.

It never signs in for you. Kabo sign-in happens in your browser (OAuth); no API key or password is
read, printed or stored. The command prints the steps that are left for you.

Options: `--host claude-code|codex|workbuddy|codebuddy|doubao|qwen-work|deepseek|grok-bot|muse|skills-only|all`,
`--dry-run` (print the commands, run nothing). `npx kabo-sh doctor` shows what was detected.

The tests use temporary folders and override the home-directory lookup only in their child process;
they never install into your real assistants. `KABO_DETECT_FOLDERS_ONLY=1` makes detection of the three
desktop apps look only at their data folders and skip the app-bundle lookup.

Source and full instructions: https://github.com/kabo-sh/kabo-mcp-plugin

Development checks (Node 24):

```sh
npm ci --ignore-scripts
npm test
npm pack --dry-run
```

DeepSeek configuration updates use the ISC-licensed [yaml](https://github.com/eemeli/yaml) parser.
The source is `installer/` in [kabo-mcp-plugin](https://github.com/kabo-sh/kabo-mcp-plugin); releases are
described in `docs/installer.md` there.
