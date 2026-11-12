# The `kabo-sh` installer

`npx kabo-sh install` installs Kabo with one command. The source is `installer/` in this repository and it
is published to npm as [`kabo-sh`](https://www.npmjs.com/package/kabo-sh).

The installer does not bundle the plugin. It runs each host's own commands (`claude plugin marketplace add`
and `claude plugin install`, `codex plugin marketplace add` and `codex plugin add`), or clones the `stable`
branch when neither host is found, and prints the steps left for the user. It has no dependencies, never
edits a host's config files and never handles credentials.

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
`mcp.json`, `.mcp.json` and the two marketplace manifests. A pull request that changes one side without the
other fails CI. When it does, update `installer/bin/kabo.js` in the same pull request and release the
installer after it merges. The test does not compare the wording of the printed follow-up steps; review
those by hand.

## Releasing

1. In a pull request, change `installer/` and bump `version` in `installer/package.json`. Check the output
   with `node installer/bin/kabo.js install --host claude-code --dry-run` (and `codex`, `skills-only`).
2. After the pull request merges, tag the merge commit on main and push the tag:

   ```sh
   git tag installer-v<version> <merge commit>
   git push origin installer-v<version>
   ```

3. The tag runs `.github/workflows/installer-publish.yml`. It checks that the tag matches
   `installer/package.json` and points at a commit on main, runs the drift test and publishes with
   `npm publish`. If the `npm-publish` environment requires a reviewer, approve the run in GitHub Actions.
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
