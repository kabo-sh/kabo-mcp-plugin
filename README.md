# Kabo plugin

Kabo helps you research public creator accounts, compare competitors, find trends, analyze videos,
and develop content ideas and scripts. This repository contains one plugin: a `kabo` MCP connection,
ten bundled Skills, and the metadata needed by each host. The AI host runs the workflows and writes
reports; Kabo provides the data tools. The plugin does not hand work to Kabo's web agent, download
Skills at runtime, or register lifecycle hooks.

The current GitHub package release is [**1.0.0**](https://github.com/kabo-sh/kabo-mcp-plugin/releases/tag/v1.0.0),
packaged as `kabo-1.0.0.zip`. This resets the public release numbering while retaining the latest
implementation. Earlier version history and source Skill versions remain separate. OpenAI marketplace
review and production acceptance remain separate from this GitHub release.

## Repository layout

```text
plugin.json                     # Portable manifest for Codex / Cursor
mcp.json                        # Production MCP connection
.claude-plugin/plugin.json       # Claude Code metadata
.claude-plugin/marketplace.json  # Claude Code marketplace (not included in the ZIP)
.agents/plugins/marketplace.json # Codex marketplace (not included in the ZIP)
.mcp.json                       # Claude Code HTTP MCP configuration
skills/                         # Ten complete Skills and their resources
skills.lock.json                # Original Skill source and versions
runtime-contract.json           # Fixed tool and Skill inventory
CHANGELOG.md                    # Version history (Chinese)
```

The ten Skills cover video analysis, standard and deep account reviews, scripts and packaging,
content ideas, Instagram/TikTok/YouTube trends, and creator/TikTok competitor research. See
[skills.lock.json](skills.lock.json) for exact IDs and source versions. All hosts use the same Skills.

- The Kabo service, which is not part of this repository, owns MCP, OAuth, data tools, asynchronous
  jobs, the website and deployment.
- The Skills were adapted from the ones used by Kabo's web agent and are now maintained here.
- This repository owns the plugin Skills, offline checks, host metadata, reproducible packages and
  acceptance evidence.

## Development

Use Node 24 and Python 3. Normal builds do not read neighboring repositories or a Skill registry.

```sh
npm ci --ignore-scripts
npm run verify
```

Edit the bundled `skills/` here and submit changes for PR review. Do not overwrite them with a fresh
upstream export. The web agent's Skills are maintained separately.
`skills.lock.json` records the original source, not a byte-for-byte comparison; update it and
`runtime-contract.json` when adding or removing a Skill.

Follow the [Kabo Skills specification](docs/skills-spec.md) (Chinese). Run `npm run skills:lint` for
details. Enforcement remains disabled (`skills-spec.json` has an empty `enforced` list), and
`npm run verify` prints the summary. The MCP artifacts in `contracts/directory-mcp/` record the
provider commit and file hashes. New tools require an explicit update to those artifacts.

Build from a committed revision:

```sh
npm run build -- --commit <full-40-character-commit> --output <new-output-directory>
```

The build reads Git blobs from that commit and produces `kabo-<version>.zip`, its SHA-256, and a file
manifest. Every declared component is included. Development documentation, tests, dependencies and
marketplace listings are excluded. The repository's resource limits are 512 files and 5 MiB per Skill,
and 2,048 files and 64 MiB for the whole package; these are local build limits.

## Installation and authentication

This repository also serves as a Claude Code and Codex marketplace. Each listing points to the same
`kabo` plugin at the repository root.

Hosts fetch the repository through local, noninteractive `git`.

| Host | Marketplace | Plugin ID |
| --- | --- | --- |
| Claude Code | `kabo-mcp-plugin` | `kabo@kabo-mcp-plugin` |
| Codex | `kabo-plugin-openai` | `kabo@kabo-plugin-openai` |

The marketplace names differ because existing Codex installations already reference
`kabo-plugin-openai`. Renaming it would break those references.

### Claude Code

In Claude Code 2.1.275 or later:

```text
/plugin install kabo --marketplace kabo-sh/kabo-mcp-plugin
```

Or add the marketplace first:

```text
/plugin marketplace add kabo-sh/kabo-mcp-plugin
/plugin install kabo@kabo-mcp-plugin
```

The terminal equivalents are `claude plugin marketplace add kabo-sh/kabo-mcp-plugin` and
`claude plugin install kabo@kabo-mcp-plugin`. If you do not have a GitHub SSH key, set
`CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` to clone over HTTPS.
For development, use `claude --plugin-dir <plugin-root>` to load the working directory directly.

### Codex

Codex 0.163 supports GitHub marketplace sources (`owner/repo[@ref]`, HTTPS or SSH):

```sh
codex plugin marketplace add kabo-sh/kabo-mcp-plugin
codex plugin add kabo@kabo-plugin-openai
```

If you already added `kabo-plugin-openai` from a local clone, run `git pull` there, then run
`codex plugin add kabo@kabo-plugin-openai` again. Codex caches plugins by version. Only one marketplace
can have this name; to switch to a GitHub source, remove the old listing with
`codex plugin marketplace remove kabo-plugin-openai`, then add the new source.

Kabo data tools use your Kabo data allowance. Codex asks for approval on each call by default. If you
want to approve these calls in advance, add this to `~/.codex/config.toml`:

```toml
[plugins."kabo@kabo-plugin-openai".mcp_servers.kabo]
default_tools_approval_mode = "approve"
```

This configuration has been tested. The equivalent command-line `-c` override did not work for the
plugin ID containing `@`.

### Cursor

Place the extracted package in a supported local plugin directory and reload it. The package uses the
portable format; installation in Cursor still needs to be tested.

### Skills only (skills CLI)

You can also install the ten Skills without the plugin using the
[skills CLI](https://github.com/vercel-labs/skills). It copies only the Skill folders and does not add
the Kabo MCP connection, so add that separately. Use either the plugin or this method, not both;
otherwise the host lists each Skill twice.

```sh
npx skills add kabo-sh/kabo-mcp-plugin#stable --agent codex --skill '*'
codex mcp add kabo --url https://kabo.sh/mcp-pub
```

`codex mcp add` opens the Kabo sign-in page. To sign in again later, run `codex mcp login kabo`.
Skills are installed in `.agents/skills/` in the current project; add `-g` to install them in
`~/.agents/skills/` for all projects.

**Versions and updates.** The skills CLI does not use version numbers. It records the Git ref you
installed from and a content hash in `skills-lock.json` (or in its global lock file with `-g`).

- `#stable` follows releases. The branch moves only when a new version is released. Run
  `npx skills check` to see whether an update is available and `npx skills update` to install it.
- `#v1.0.0` pins one release. `npx skills update` never moves it to a newer tag; to upgrade, run
  `npx skills add` again with the new tag.
- Without a ref, the CLI follows `main`, which includes unreleased changes.

The skills CLI collects anonymous usage data; set `DISABLE_TELEMETRY=1` to turn it off.

Installing all ten Skills and their discovery by Codex 0.164 were checked on October 27, 2026. Kabo
sign-in and a complete Skill run through this method still need testing, as do other agents.

### Validation status

Use `claude plugin validate <plugin-root>` to check the Claude Code manifest and marketplace. Codex
metadata is covered by portable-schema and package tests. Under the old version numbering, 3.1.0
passed an end-to-end YouTube video-analysis run in Codex 0.163. That historical result does not replace
acceptance testing for 1.0.0; record results against the exact candidate commit and ZIP.

### Requirements and connection

The workflows need Python 3 and workspace file access. Local video analysis also needs ffmpeg and
ffprobe. Full evidence normally arrives through download links valid for 10 minutes on
`storage.googleapis.com`. The scripts download it and check its size and SHA-256. If downloads are
unavailable, the host must be able to export complete tool results for the `stage` fallback.
Sandbox network behavior still needs testing in each host. ChatGPT and Claude.ai web environments
require separate validation of these capabilities; a local installation does not establish web support.
A successful build also does not establish source-distribution rights or marketplace approval.

The only connection is `https://kabo.sh/mcp-pub`. Follow the host's OAuth flow on first use
(or during installation in Codex). The host manages login, refresh and revocation. Version 1.0.0 keeps
the `/mcp-pub` address introduced in the old 3.0.1 release. The former `/mcp-directory` endpoint was
removed and has returned 404 since October 22, 2026. Installations still using that address must update and reconnect. If `/mcp-pub` is unavailable,
report the failure rather than switching endpoints or reusing a token issued for another audience.

**Repeated `invalid_token` errors after connecting:** the host may have omitted
`resource=https://kabo.sh/mcp-pub` (RFC 8707) and obtained a token for another Kabo endpoint.
Disconnect and reconnect Kabo through the host so it uses
`https://kabo.sh/.well-known/oauth-protected-resource/mcp-pub`. Do not paste a token manually or alter
requests to bypass authentication. Tokens for `/mcp` or the removed `/mcp-directory` endpoint do not
work here. Once the corresponding server change is deployed, the 401 response's `authorization_hint`
and `WWW-Authenticate` error description provide the same guidance.

Each research run uses a separate local directory and saves complete MCP results. Do not reconstruct
truncated evidence or read the host's credentials or session logs. Follow the steps in each Skill.

**Claude Code is authorized interactively, but `claude -p` says authentication is needed:** an old
`plugin:kabo:kabo` entry in `~/.claude/mcp-needs-auth-cache.json` may still mark it as `needs-auth` with
zero tools, even when `claude mcp list` says Connected. Remove only that entry, or wait for it to expire,
then retry. This host behavior was observed in Claude Code 2.1.308 on October 22, 2026.

**Frame images:** frame reads also request `delivery: "download"`. The script saves images in the run
directory, and the host opens those local files. Claude Code may store inline images in its own
session directory, outside the exportable result. If an entire result has no ready download, export
the full inline result and use `stage`. If only some artifacts are unavailable or the script cannot
access the network, read those artifacts again without `delivery`, then export and stage them.
Skills do not read the host's session or `tool-results` directories.

## Updating, uninstalling and rollback

Moving from a development version to 1.0.0 resets the version numbering while keeping the latest
implementation; see [CHANGELOG](CHANGELOG.md) (Chinese). SemVer ranks `1.0.0` below the former `3.x`
versions, so do not rely on automatic upgrade detection. Refresh the marketplace, update the
installation, and confirm that the host loads `1.0.0`. If it retains the old version, uninstall the
plugin through the host and reinstall it. Keep research files and credentials intact. Host behavior
when moving to a lower version number still needs testing.

Normal update commands:

- Claude Code: `/plugin marketplace update kabo-mcp-plugin`, or
  `claude plugin update kabo@kabo-mcp-plugin` in the terminal.
- Codex: `codex plugin marketplace upgrade kabo-plugin-openai` for a GitHub source, or `git pull` for a
  local clone; then run `codex plugin add kabo@kabo-plugin-openai` again.

The connection and OAuth resource stay at `/mcp-pub` when moving from the old 3.0.1 or 3.1.x versions.
Renumbering alone does not change authorization. Older installations using `/mcp-directory` must
reauthorize for `/mcp-pub`. The current package has ten fixed Skills, downloads full evidence, and
stores raw tool results in each run's `host-results/` directory. The old dynamic menu, channel switch,
download cache and Node runner are no longer included. Validate in a separate workspace before
updating the existing `kabo` entry. Old research directories are not migrated or deleted automatically.

Do not roll back to 3.0.0 or earlier under the **old numbering scheme**, including the former 2.0.0
ZIP: their `/mcp-directory` connection no longer works. Fix current problems in a new release instead
of replacing signed content with an old package. Uninstall through the host to remove the plugin and
connection. Delete local research files only when the user asks.

## Acceptance and release

Passing CI and building a ZIP establish local structure and test results. Production acceptance still
covers tool visibility (including YouTube), complete tasks and reports delivered once, photo/carousel/
video evidence, OAuth, incorrect audience/scope, account isolation, deletion, five positive and three
negative review cases, and a reviewer account. Without complete production evidence,
`submissionReady=false`.

Maintainer guides are in Chinese: [production acceptance](docs/acceptance.md) and
[submission materials](docs/submission.md).
Deployment, marketplace upload and Publish are separate actions.

[Privacy](https://kabo.sh/privacy) · [Terms](https://kabo.sh/terms)

Format references: [OpenAI plugins](https://developers.openai.com/plugins/build/plugins),
[Claude Code manifests](https://code.claude.com/docs/en/plugins-reference), and
[Cursor portable plugins](https://cursor.com/docs/plugins).
