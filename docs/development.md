# Developing and releasing the Kabo plugin

For maintainers. Installation is covered in [installation.md](installation.md); the Skill rules are in
[skills-spec.md](skills-spec.md).

## Repository layout

```text
plugin.json                     # Portable manifest for Codex / Cursor
mcp.json                        # Production MCP connection
.claude-plugin/plugin.json       # Claude Code metadata
.claude-plugin/marketplace.json  # Claude Code marketplace (not included in the ZIP)
.agents/plugins/marketplace.json # Codex marketplace (not included in the ZIP)
.mcp.json                       # Claude Code HTTP MCP configuration
skills/                         # Twenty-two complete Skills and their resources
skills.lock.json                # Original Skill source and versions
runtime-contract.json           # Fixed tool and Skill inventory
INSTALL.md                      # Installation steps written for an AI assistant to follow
CHANGELOG.md                    # Version history
```

The twenty-two Skills cover video analysis, standard and deep account reviews, scripts and packaging,
content ideas, Instagram/TikTok/YouTube trends, creator/TikTok competitor research, reach-drop
diagnosis, publish-timing recommendations, platform monetization plans, official platform rule checks,
brand identity options and media kits, content calendars, brand-deal pricing, thumbnail reviews (`review-thumbnail`), and `remake-viral-video`, which remakes a viral talking-head or voice-over video of 10 minutes or less
(talking videos may cut to screen recordings or show a product) with the creator in it. Three more form a daily routine
for a creator: `start-with-kabo` (first session: link one public account, read its posts, propose content pillars for the
creator to confirm and save them to Kabo, give today's picks, offer three daily jobs), `pick-daily-viral-videos` (three picks a day
from Kabo's daily "for you" list, never repeated) and `review-new-posts` (a 24-hour review of each new post plus a daily
account recap). See
[skills.lock.json](../skills.lock.json) for exact IDs and source versions. All hosts use the
same Skills.

`diagnose-reach-drop`, `recommend-publish-timing`, `plan-platform-monetization` and
`verify-platform-rule` are included in 1.0.9. Their complete cross-host acceptance is still pending;
Current release acceptance focuses on short-window content-language checks and user-approved cross-language searches.
`verify-platform-rule` needs the `official_page_render_page` tool on `/mcp-pub` (restored by kabo#1817).
`optimize-creator-brand`, `plan-content-calendar` and `price-creator-brand-deals` are ported from
creator-skills; their cross-host acceptance is pending.

`start-with-kabo`, `pick-daily-viral-videos` and `review-new-posts` keep their state in the workspace
(`kabo-library/<platform>-<handle>/`) through a shared `creator_library.py`; the three copies are identical. In the
first session the assistant proposes 2 to 4 content pillars from the account's posts, the creator confirms or changes
them, and the whole set is saved to Kabo once (`update_content_preferences` with `declare_pillars`). From then on Kabo
holds the pillars (read back with `get_creator_profile` and `pillars: true`) and uses them for the daily picks; the
local library is only a copy. If the save fails, the pillars stay on this computer and are saved the next time the
Skill can. Kabo's own statistics (signature content) are shown only as a reference. The daily picks come only from
`get_for_you_videos`; `pick-daily-viral-videos` only chooses which three of Kabo's videos to show each day and
remembers which were shown. `review-new-posts` refreshes the pillars from Kabo on every run, and builds its own
library when none exists. The
Skills are written to run unattended from a host's own scheduled tasks and never post, comment or message anyone.
Host-specific scheduling notes live in `skills/start-with-kabo/references/host-schedules.md`.

`get_for_you_videos` (`workspace:read`) and `prepare_creator_profile` (`workspace:write`) come from kabo-sh/kabo#2176
and are pinned in `contracts/directory-mcp/`. Building the profile needs write access to the creator's Kabo account,
so it happens only in the first session; the scheduled jobs run only `pick-daily-viral-videos` and `review-new-posts`.
The new flow has been tested offline; real-host acceptance is still pending.

`remake-viral-video` uses the `start_remake_video`, `get_remake_video` and `render_remake_video`
tools on `/mcp-pub`, plus `edit_remake_video` to change a delivered video and `start_video_project`,
`make_video_step` and `finish_video_project` to build a video outside the remake formats step by step. Its scripts download the brief and the finished MP4 from the same signed
`storage.googleapis.com` links as evidence downloads; there is no `stage` fallback for them.

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

Follow the [Kabo Skills specification](skills-spec.md). Run `npm run skills:lint` for
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

## Acceptance and release

Passing CI and building a ZIP establish local structure and test results. Production acceptance still
covers tool visibility (including YouTube), complete tasks and reports delivered once, photo/carousel/
video evidence, OAuth, incorrect audience/scope, account isolation, deletion, five positive and three
negative review cases, and a reviewer account. Without complete production evidence,
`submissionReady=false`.

Deployment, marketplace upload and Publish are separate actions.


Format references: [OpenAI plugins](https://developers.openai.com/plugins/build/plugins),
[Claude Code manifests](https://code.claude.com/docs/en/plugins-reference), and
[Cursor portable plugins](https://cursor.com/docs/plugins).
