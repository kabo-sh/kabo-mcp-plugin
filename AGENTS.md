# Kabo plugin repository

- Everything in this public repository is written in English: commit messages, PR titles and PR descriptions,
  code comments, docstrings, test names, `CHANGELOG.md`, release notes, maintainer documentation in `docs/`,
  plugin metadata and user-facing content. `docs/i18n/` holds the localized README translations and is the
  only directory where prose in another language is allowed. Outside it, non-English text may appear only as
  data: localized report strings, patterns that match non-English user input or platform content, and test
  fixtures that exercise them. `scripts/repo-rules.test.mjs` enforces this; a file that needs such data must be
  listed in its allowlist, and its comments, docstrings and messages stay in English (a comment may quote the
  literal token it is about).
- The repository root is the plugin root. Maintain one `skills/` directory, one `kabo` entry and one
  build entry point. Codex, Claude Code and Cursor add only host metadata; do not copy business content
  or remove features for a particular host.
- The user selected twenty-two Skills; see `skills.lock.json`. Eighteen were adapted from
  creator-skills and are now edited directly in this repository; four more were written here: three for
  the creator's daily routine (`start-with-kabo`, `pick-daily-viral-videos`, `review-new-posts`) and
  `review-thumbnail`, which reviews uploaded images and calls no Kabo data tool. Do not
  overwrite any of them with a new creator-skills import. The lock file records only the starting point of the adaptation.
  Follow `docs/skills-spec.md` when changing a Skill. Enforcement stays off: keep `enforced` in
  `skills-spec.json` empty and do not add entries.
  Default builds and verification read only this repository. They do not read neighboring
  repositories or download Skills at install or run time.
- The Kabo service, not this repository, owns the API, OAuth, database, web app and deployment.
  Research judgments, scripts and reports run in the AI host. The plugin runs independently of Kabo's
  web agent and never calls it, directly or through the API, a queue or another proxy.
  They share no sessions, tasks, model loop, sandbox or report chain; only the Skills share an origin.
- A multi-round fetch runs in one backend data tool, not as rounds handed to the host model
  (`docs/skills-spec.md` KS9, enforced by `scripts/fetch-orchestration.test.mjs`). Judgment needed between
  fetch rounds may run as a backend prompt node inside that tool; analysis and the report stay in the host.
  Scripts never branch on the host to choose a fetch path.
- The only production MCP connection is `/mcp-pub`. Each data operation is pinned and must match the
  provider's artifacts. Do not introduce a registry, a general-purpose executor or remote end-to-end
  research tasks. The provider keeps the old dynamic server protocol compatible.
- One lifecycle hook only: `hooks/hooks.json` runs `SessionStart` (`startup`) in Claude Code to offer
  `start-with-kabo` once after install, because the host has no install-time event. It only adds a note to
  the model's context: it never starts a Skill, calls Kabo, or saves results for the model. It is not a
  package component, so the release ZIP excludes it and the OpenAI package check still rejects `hooks/`.
  Add no other hooks. Save complete MCP responses explicitly and verify digests, run ownership and
  reports; do not read host session records. The static package version and the source Skills'
  business versions are maintained separately, and packaged content never updates itself at run time.
- The package must not contain apps, `.app.json`, a private registry, real local paths, test URLs or
  credentials. The host manages user authentication. A public signature-verification key may be
  packaged, but a content digest must not be presented as a digital signature or server attestation.
- Use Node 24 to run `npm ci --ignore-scripts` and `npm run verify`; use Python 3 to check the static
  scripts. A release ZIP reads only a full commit and must not include working-tree changes. Every
  Skill resource must be packaged in full.
- Code goes through PR review; never push directly to main. Do not deploy automatically, upload to a
  marketplace console or Publish. CI, a buildable ZIP, real-host and production acceptance, and
  marketplace review are separate facts. State any missing acceptance explicitly and never claim the
  plugin is ready for listing.
- Kabo Web serves the Skills of the latest GitHub release (desktop stays on its frozen channel). Publishing a
  release runs `.github/workflows/web-publish.yml`, which packs each Skill and rewrites the Web overlay
  (`scripts/web-publish/plugin-web.mjs`; it never writes a channel index) when the `web-publish` environment
  variable `PLUGIN_WEB_AUTO` is `on`; `PLUGIN_WEB_HOLD` keeps listed Skills on their Registry version in production (the pre test target ignores it; `PLUGIN_WEB_TEST_HOLD` is its own list). A Skill on no channel and not yet on the overlay is skipped unless it is in `PLUGIN_WEB_DEBUT` (both targets), in which case it debuts at its SKILL.md `metadata.version` (required); hold wins over debut, and listing an already-live Skill has no effect. To
  publish by hand, or to the pre test accounts, run `gh workflow run web-publish.yml -f tag=<tag> -f target=index|test`
  (idempotent; a no-op when Web is already on the release). Check with
  `curl -s https://agent.kabo.sh/health | jq '.skill_channels.production.runtime.plugin_overlay'`.
