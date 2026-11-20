# The `kabo-sh` installer

`npx kabo-sh install` installs Kabo with one command. The source is `installer/` in this repository and it
is published to npm as [`kabo-sh`](https://www.npmjs.com/package/kabo-sh).

The installer does not bundle the plugin. Where a host has its own commands it runs them (`claude plugin
marketplace add` and `claude plugin install`, `codex plugin marketplace add` and `codex plugin add`, and the
same plugin commands through the CodeBuddy command line inside WorkBuddy). For Doubao Work, Qwen Work and
DeepSeek Harness it copies the Skill folders from a clone of the `stable` branch and, for Qwen Work and
DeepSeek Harness, adds only the Kabo entry to the host's connection file after writing a timestamped backup.
Muse and Grok Bot get the Skills on their cloud computers. It never handles credentials. Its one dependency
is the pinned `yaml` parser, used only for DeepSeek Harness's patch file.

Which assistants it installs into:

- `--host <name>` installs into that assistant only. `INSTALL.md` always gives the command with `--host`,
  because an assistant that runs the installer should set up only itself.
- Without `--host`, it detects the assistants on the computer. When it finds exactly one, it installs there.
  When it finds several, it installs nothing, lists one `--host` command per assistant and exits with
  status 2. `--host all` installs into every one it found. Installing into all of them by default changed
  another product's settings and mixed that product's steps into the reply of the assistant that ran the
  command (a WorkBuddy user was told to restart DeepSeek Harness).

Each result says what was done (plugin installed, Skills copied, connection added) and what is not done yet
(reload, connector trust, sign-in, the Bot saving its Skills). None of them says Kabo is ready: that needs
the sign-in and a successful `get_research_capabilities` call (`INSTALL.md`, "After installing").

`installer/` is not a plugin component: the release ZIP and the OpenAI package leave it out
(`scripts/package-layout.mjs`).

## When the installer needs a release

A plugin release does **not** need an installer release. Publish a new installer version only when one of
these changes:

1. the repository or marketplace names (`kabo-sh/kabo-mcp-plugin`, `kabo@kabo-mcp-plugin`,
   `kabo@kabo-plugin-openai`);
2. the MCP address (`https://kabo.sh/mcp-pub`);
3. the OAuth scopes in the Codex sign-in command (`host-auth.json`);
4. a host's install commands;
5. the supported hosts, or the steps printed after install.

`scripts/installer.test.mjs` (part of `npm run verify`) runs the installer in dry-run mode and compares its
commands, sign-in command, MCP address, clone command and links with `INSTALL.md`, `host-auth.json`,
`mcp.json`, `.mcp.json` and the two marketplace manifests. It also checks that several detected assistants
without `--host` change nothing, that every `kabo-sh install` in `INSTALL.md` names a known `--host`, and that
`INSTALL.md` and the installer both tell WorkBuddy users to restart WorkBuddy. A pull request that changes
one side without the other fails CI. The installer's own tests (`installer/test/`, the DeepSeek patch-file
edits) run in the same CI job after `npm ci` in `installer/`. When it does, update `installer/bin/kabo.js` in the same pull request and release the
installer after it merges. The test does not compare the wording of the printed follow-up steps; review
those by hand.

## Releasing

1. In a pull request, change `installer/` and bump `version` in `installer/package.json`. Check the output
   with `node installer/bin/kabo.js install --host <host> --dry-run` for each host you changed, and run
   `npm ci --ignore-scripts && npm test` in `installer/`.
2. After the pull request merges, tag the merge commit on main and push the tag:

   ```sh
   git tag installer-v<version> <merge commit>
   git push origin installer-v<version>
   ```

3. The tag runs `.github/workflows/installer-publish.yml`. It checks that the tag matches
   `installer/package.json` and points at a commit on main, runs the drift test and the installer's own
   tests, and publishes with `npm publish`. If the `npm-publish` environment requires a reviewer, approve the run in GitHub Actions.
4. Check the result with `npm view kabo-sh version` and `npx kabo-sh@<version> install --dry-run`.

Installer tags (`installer-v*`) are separate from plugin release tags (`v*`) and do not create a GitHub
release.

## npm setup (one time)

- The package uses npm trusted publishing: no npm token is stored in this repository. On npmjs.com, the
  `kabo-sh` package's trusted publisher names the GitHub repository `kabo-sh/kabo-mcp-plugin`, the workflow
  `installer-publish.yml` and the environment `npm-publish`.
- The `npm-publish` GitHub environment should allow only `installer-v*` tags and require a reviewer.
- The package belongs to the team's npm organization and has at least two maintainers with two-factor
  authentication, so a release never depends on one person's account.
