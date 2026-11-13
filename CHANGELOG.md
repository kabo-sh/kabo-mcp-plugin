# Changelog

The version number follows `plugin.json`; the root package version in `.claude-plugin/plugin.json`, `package.json` and `package-lock.json` is kept in sync with it.

## 1.0.50 (unreleased)

- `review-thumbnail` 0.1.5: SKILL.md now runs `prepare` and `deliver` with `--run-dir review` and says the run
  directory must not exist yet. In production the host wrote `request-input.json` into a working folder and
  passed that folder (`--run-dir .`) as the run directory, so the first `prepare` call failed with "Use a new run
  directory" in almost every run and only a retry succeeded. The error now names the fix (a new subdirectory);
  the no-reuse rule is unchanged.

## 1.0.49 (unreleased)

- `develop-content-ideas`: the final batch's omitted `gates` lists (`selection_missing`, `production_missing`,
  `blocked_reasons`) now default to empty. In production a final batch without `blocked_reasons` was rejected,
  the host could not repair the stored batch file, and the user received no ideas. Status rules still apply
  (a blocked status still needs non-empty `blocked_reasons`).

## 1.0.48 (2026-11-13; GitHub Release)

- `develop-content-ideas`: prep writes `idea_work_plan.json` and the host authors candidates in batches of at
  most ten (`ceil(idea_count / 10)` passes) through `run_ideas_stages.py batch`; the script fills IDs, ranks
  and request metadata and assembles `idea_set.json` only when every batch is present. Batch replays are
  idempotent and conflicting replays are rejected (`references/batched-authoring.md`).
- Each batch is schema-checked before acceptance; a rejected batch returns `status="needs_revision"` with
  `idea_id` and field paths, exit `0`, and nothing from it is stored.
- Assembly moves `overview.recommended_candidate_ids[0]` to rank 1 (others keep their order) and reports
  `rank_adjustment`, so "rank 1 must be the first recommended candidate" no longer fails batched sets.
- New `run_ideas_stages.py revise --input revision.json`: field-level edits keyed by `idea_id`/path, read back
  and dry-run validated without using a core attempt; script-owned fields are locked. Core `needs_revision`
  returns `error_details`, `revise_command` and a template; the rank error names both IDs.
- `awaiting_batches` results say how many batches remain, name the next IDs and state that ending the turn
  before the next batch is a failed run; the result carries `turn_complete: false`. SKILL.md and
  `references/batched-authoring.md` say the same.
- New `scripts/ideas-batches-regression.py` covers 3, 15 and 20 candidate sets.
- Web publishing: bump the three Skills that declare `metadata.version` by one patch so the Web overlay accepts
  them: `optimize-creator-brand` 0.3.25, `plan-content-calendar` 0.1.28 (including the `candidate_skill` constant
  in the schema) and `price-creator-brand-deals` 0.4.15. Their content changed after 1.0.43 (the English-only
  rewrite), but the declared versions still equalled the versions already on the overlay, so the v1.0.47
  web-publish run failed with "metadata.version 0.3.24 must be above the live version 0.3.24".
- `review-thumbnail` 0.1.3 -> 0.1.4: the pre test overlay still holds the earlier 0.1.3 package, whose content
  differs from the English-only port in 1.0.47, so publishing to the test target needs a higher declared
  version. No other content changes.

## 1.0.47 (unreleased)

- New Skill `review-thumbnail` (Skill version 0.1.3): reviews and compares one to three uploaded PNG/JPEG/WebP
  thumbnails with ten editorial pass/fail checks (topic match, emotion, harmony, eye-catching element,
  uncluttered, color and contrast, unique concept, execution, curiosity, resolution and aspect ratio). Each check
  gives one concrete reason and, when it fails, a fix; each candidate lists its first 2-3 changes, and pairwise
  comparisons explain both sides before recommending one candidate, a tie or none. There are no scores, no CTR
  prediction and no backend checker; the review is platform-independent and needs no Kabo data tool or account.
- Before judging, the host records per-image `observations` (verbatim visible text, main subject, disclosure
  labels). `scripts/review_thumbnail.py deliver` rejects quoted text that is not on that candidate, comparison
  quotes from outside the pair, and any reason or fix that asks to remove or hide a recorded source,
  AI-generated, cloned-voice or financial disclosure. It renders a validated `FINAL_REVIEW.md` (English, or
  Chinese labels from `references/labels-zh.json`) that the host displays unchanged through its file-display
  capability. Python 3 and Pillow prepare local copies and 320px previews.
- Integration: registered in `skills.lock.json`, `runtime-contract.json` and the package checks; the fetch-runtime
  tests skip it explicitly because it ships no `static_host.py`. Pre web testing passed; cross-host acceptance
  on Claude Code, Codex and ChatGPT is pending.

## 1.0.46 (unreleased)

- Declare `extensions.com.openai.onboardingSkill` as `./skills/start-with-kabo/SKILL.md` so Codex's
  setup entry point resolves the bundled Start With Kabo workflow after installation or reinstallation.
- Update the installation guidance and package versions so Codex loads the new metadata from its
  versioned cache.

## 1.0.45 (2026-11-12; GitHub Release)

- `remake-viral-video`: when the talking models are listed, each `est_usd` is described as the whole video's estimated total, rounded up, with the final charge usually a little lower. Pairs with kabo#2194, which changed the estimate from "talking video + a fixed $0.28" to a total counted from the first-frame job list (kabo#2166: estimated $0.49, charged $1.25-1.30).

## 1.0.44 (2026-11-12; GitHub Release)

- After the plugin is installed in Claude Code, it now offers onboarding on its own initiative: the host has no "after install" event, so
  a single `SessionStart` (`startup`) hook is added, `hooks/hooks.json` -> `hooks/onboarding-nudge.sh`, which gives the model a piece of
  context in the first session after installation. When the user's first message is a greeting, a general question or asks how to start,
  the model proposes onboarding in one sentence and tells the user they can type `/kabo:start-with-kabo` at any time to begin, then runs it
  on the spot once the user agrees; when the first message is a specific request, it does the work first and adds one sentence about the
  command at the end. It never starts the flow on the user's behalf, and scheduled or unattended sessions ignore it. The offer is made only
  once: the marker is written to the `CLAUDE_PLUGIN_DATA` directory the host provides (falling back to `~/.kabo` when it is absent), and if
  the marker cannot be written the hook stays silent, so that it does not interrupt every session.
- The packaging rules change accordingly: `hooks/` is no longer listed as a forbidden component, but it is still not a package component.
  It is read only when Claude Code installs from this repository, the release ZIP does not contain it, and the OpenAI package check still
  rejects `hooks/`; the "no lifecycle hooks" wording in `AGENTS.md`, the README, INSTALL.md and the Skills spec is rewritten to match.

## 1.0.43 (2026-11-12; GitHub Release)

- `diagnose-reach-drop`: numbers the user supplies (their own creator analytics, a specific post they name) can be entered as questions carrying their own `source` and placed in the same plan as the imported public data. Previously the plan accepted a single source and explicitly forbade merging, so the user's data could not enter the analysis (production session on 11-10). Only attaching user numbers to the default public source is rejected; one comparison uses only one source; when there is only one group it is handed over as an observed value, with no claim of change and a note that a comparison is missing; the report labels each item by source, and user-supplied items are marked "user-supplied, not verified". Delivery still forwards the full report; anything the assistant adds stays within the report and is marked as a suggestion. An approximate figure the user gives for a whole group ("about 60% before") is recorded as one `approximate` value, no longer split into per-item exact values, and the report marks it as approximate; when a field inside a group is wrong, the error points to that specific group (#163).

## 1.0.42 (2026-11-12; GitHub Release)

- `verify-platform-rule`: a claim backed by a quotation can additionally carry an `inference`, which states what follows from the evidence but is not written on the page; it may only be phrased as possible, never as a definite effect. The report labels it separately after the quotation as "Our inference, not the platform's own words". Previously the structure did not allow a quotation and an inference to coexist, and the model, in order to deliver an action, merged steps the page does not mention into already-confirmed claims (production session on 11-10). A step the user proposes stays a separate claim, and is marked `no_official_text` when the page does not mention it; validation rejects only an empty inference, and a multi-line inference is rendered as one paragraph. Delivery still attaches the full report verbatim; anything written outside the report stays within the report: "the pages I read don't say so" must not be turned into "the platform has no such thing", and action advice the user asked for is marked as our suggestion, not the platform's (#162).

## 1.0.41 (2026-11-12; GitHub Release)

- `remake-viral-video` supports **local** videos and photos supplied by the user (mp4/mov/m4v/webm up to 200 MB, JPEG/PNG up to 10 MB): `upload-call` generates the
  `upload_file` input (the file name is derived from a content digest; the user's file name is not sent out) -> `upload` sends the bytes to the signed storage URL returned by `upload_file` (one POST
  opens a resumable session, one PUT sends everything; only the signed headers are forwarded) -> `upload_file` is called with just the `file_id` to verify, yielding `kabo-file:<id>`, which can be used in any of the reference, own-video,
  photo, reference-video and reference-image link positions. Depends on kabo#2184 (`/mcp-pub` adds `upload_file`; `start_remake_video` / `start_video_project`
  accept `kabo-file:` references); `contracts/directory-mcp` is re-pinned to kabo da94908. Adds `references/local-files.md`, and Skills spec KS7.3 gains this upload network path.
- Acceptance: end-to-end test with Codex 0.163 on Pre: local photo + local video -> step-by-step project -> free trim -> delivered MP4 passes; local reference + local own video ->
  full remake through to waiting_script, and the brief (including the reference clip's raw ASR text) is written to disk and passes.

## 1.0.40 (2026-11-12; GitHub Release)

- `start-with-kabo` restores locally proposed pillars, and after the creator confirms, **syncs the whole set to Kabo once**; Kabo becomes the only place pillars are stored:
  - Flow: opening -> ask once before binding -> bind -> call `prepare_creator_profile` once in passing (without waiting for it; it only lets Kabo start generating the profile too; when write permission is missing or a niche is needed,
    handle as before) -> `collect_account_history` reads the posts -> `collect_video_media` reads up to 8 transcripts -> the assistant proposes 2-4 pillars
    (`propose-pillars`) -> if `get_creator_profile` (with `pillars: true`) already holds Kabo's main content, it is shown as a "What your numbers show..."
    reference -> the creator confirms (`save-pillars`) -> `update_content_preferences` with `declare_pillars` once (`declare-request` generates the input,
    `record-sync` records the result) -> today's picks -> scheduled tasks -> four-line closing.
  - The pillar shape matches the backend: `name` (1-60 characters), `definition` (1-200 characters), `search_phrases` (1-3 entries, each 1-60 characters), at most 4 pillars, names unique ignoring
    case; the script pre-checks these rules first and has the assistant shorten anything over the limit. The previously hard-coded "median views >= 0.8x, second pillar >= 20%" rule is now only a reference number (per-group post count,
    median views, share); the script no longer rules on whether to recommend, and does not present it as a Kabo statistical conclusion.
  - Sync: first read `get_creator_profile` to get `preferences.version` (0 if absent), then replace the whole set; on a version conflict, re-read and retry once; for other failures (missing write permission,
    the host or Kabo not recognising this action, network), tell the creator honestly that "pillars are only saved on this computer for now", and the local library is marked unsynced; the next time `start-with-kabo` runs,
    or the creator manually runs `review-new-posts`, a sync is attempted once if writing is possible (scheduled runs do not write).
- When `review-new-posts` refreshes pillars it reads `get_creator_profile` with `pillars: true`, with source priority: pillars declared by the creator (`declaredPillars` non-empty) ->
  Kabo's main content -> none. Declared pillars have no id and are aligned by name (ignoring case); posts whose pillar was renamed are set to uncategorised; when unsynced local pillars exist they are not
  cleared by the backend result. Hosts that do not keep files build the library with the same priority.
- The three Skills speak only everyday language to the creator: no tool names, field names, status codes, failure codes, Skill ids or file paths; all script copy that gets paraphrased (opening, waiting and
  failure prompts, sync results, review and recap limits, the closing line of the picks) is rewritten, and failure codes remain only in fields meant for the assistant. The SKILL.md Ground rules gain
  an "internal term -> what to say to the creator" table; next-step suggestions are written as actions (Break it down / Write my version / Remake it with me in it / review it after
  24 hours), and Skill ids are kept for the assistant only. A test scans the script's fixed copy, the actual output of each branch and the quoted example sentences in SKILL.md, and none may contain a forbidden word.
- `start-with-kabo` again ships `build_public_snapshot.py` (identical to the copy in the account review) and the data-fetch allowlist (`collect_account_history`,
  `collect_video_media`); `allowed-tools` adds back `collect_account_history`, `collect_video_media`, `get_research_data_download` and
  `get_research_data_job`; `review-new-posts` adds `update_content_preferences` (used only to catch up on sync in manual runs). `pick-daily-viral-videos`
  is unchanged (it fetches only `get_for_you_videos`, and the relative threshold is still 10% of the top item in the window).
- Depends on kabo#2185 (the `declare_pillars` action, and the `pillars` input / `declaredPillars` output of `get_creator_profile`). `contracts/directory-mcp/`
  is re-pinned at kabo `dd614f5` using the command in `pin.json` (`tools-list.json` is byte-for-byte identical to the backend golden; `annotations.md` and
  `data-tool-bindings.json` are unchanged), and the inputs and length limits agree with the script's pre-check.
- Fixes after testing on real hosts (Codex, production, three accounts):
  - The idempotency key for binding an account is generated by the script (new command `connect-request`, to be used as is): `library:<platform>:<lowercase handle>:<bindingVersion of the binding being replaced,
    or new for a first binding>`, at most 119 characters (the contract limit is 128). Previously the key depended on the account alone, so "bind A -> switch to B -> switch back to A" sent different requests with the same key, and the backend
    rejected them permanently as a conflict (observed with `@MrBeast`). The binding result is turned into plain language by `connect-result`, and the backend's own wording remains only in `reported`; when binding fails, the flow still reads posts,
    proposes pillars and saves them locally.
  - Numbers shown to the creator are formatted by the script: view counts are rounded with thousands separators (`1,231,293,530`), and multiples have at most two decimals; the "What your numbers show" reference block and each proposed
    line are supplied directly by `say_line` of `profile-pillars` / `propose-pillars`, and the model is no longer asked to put `share_of_posts` and `medianMultiplier` into words
    (observed outputs included "about 32% of its sample" and "1.48 times its comparison baseline").
  - "I read N of your videos..." is said only once, when the posts have been read (`posts --tell`), and is not repeated when posts are listed again afterwards.
  - What is said while waiting for picks or the profile is at most two sentences and never repeated: say it once on entering the wait (with "may take a few minutes" for picks), add "Still working on it." on the 3rd call,
    and the remaining poll outputs carry `say_to_creator: false` (in the observed run "Kabo is still preparing today's picks for you." was sent 6 times).
  - Picks are described only as returned by Kabo, without saying "chosen by the pillars you just confirmed" (after pillars are saved, Kabo may still return the set generated before saving).
  - The copy guard adds: sample / baseline / reference groups must not appear, nor `\d+.0 views` nor integers of 8 or more digits without separators.
- Acceptance: `@leohuan.fang` (Instagram) and `@veritasium` (YouTube) went through local proposal -> `declare_pillars`
  save (version 0 -> 1) -> `get_creator_profile` (`pillars: true`) read-back identical verbatim, on Codex with production `/mcp-pub`; `@MrBeast` could not be bound at the time because of the idempotency-key collision, and has not been retested since the fix.
  The remaining gaps are the same as in 1.0.38.

## 1.0.39 (2026-11-12; GitHub Release)

- `start-with-kabo` restores the niche line when confirming pillars: when `creator_library.py` reads the niche it first reads the top-level `niche` of the `get_creator_profile` result
  (the niche inferred by `prepare_creator_profile` or stated by the creator is written there), and falls back to `diagnosis.insight.niche` and
  `diagnosis.accountReview.sections.niche` only when it is empty. Previously only those two places in the diagnosis were read, so a newly bound account without a review diagnosis had no readable niche (observed on Codex: YouTube
  `@veritasium` had top-level niche "Science education", yet the `niche` output by `profile-pillars` was null, and the proposal lacked the niche line).
  The library build and pillar refresh of `review-new-posts` use the same function, so the niche in the library is filled in too. Other behaviour is unchanged (the views threshold for picks is still 10% of the top item in the window).
- Acceptance: offline tests only (niche at top level, top level takes priority over diagnosis, only diagnosis has one, neither has one, library build and refresh); not yet rerun on a real host after the fix.

## 1.0.38 (2026-11-12; GitHub Release)

- Adds three Skills that make up the creator's daily flow (originals of this repository; total Skills 18 -> 21; #160):
  - `start-with-kabo`: the first conversation. Two short opening messages plus one question; ask first, then bind one public Instagram / TikTok / YouTube account
    (`connect_public_account`); `prepare_creator_profile` has Kabo infer the niche and generate the profile (polled with a cap per `retry_after_seconds`: after the first call,
    at most 8 more checks and 480 seconds of total waiting; when no niche can be inferred, ask the creator only once and retry with their own words as `niche`; occasional failures wait for the backend to rerun automatically; when write permission is missing, prompt to re-authorise),
    `get_creator_profile` reads out the niche and pillars for the creator to confirm, and rename / delete / merge are saved back to Kabo with `update_content_preferences`; when there are no pillars,
    say so honestly and continue. Then give today's picks, propose three host scheduled tasks (daily picks, 24-hour review of new content, daily account recap), and close with four lines.
  - `pick-daily-viral-videos`: three a day, taken only from Kabo's backend daily picks `get_for_you_videos` (with `include: ["author_id"]`). The plugin only applies display
    restrictions: first 7 days, then 30 days, then 24 hours; each window takes only items whose views are at least 10% of the top item in that window; it skips items shown before, the creator's own, a second item from the same author, and duplicates across
    windows; it does not pad the list. Evidence uses only the backend basis (views, rank within the window, backend reason). While generation is in progress it waits with a cap (after the first call at most 3 more checks, 600 seconds of total waiting),
    and `not_eligible` / `failed` are explained in one sentence and end the run, with no polling and no fallback. Can run unattended.
  - `review-new-posts`: a once-a-day 24-hour review of new content (compared against equal-age readings of the creator's own earlier posts) plus an account recap. The first run builds the library itself; each run
    refreshes pillars from `get_creator_profile` (aligned by profile item id: a rename keeps ownership, a merge assigns to the merged item, a delete sets posts to uncategorised; if it cannot be read, the existing pillars are kept and the limits note says so);
    with no pillars the review and recap still run as usual. Can run unattended.
  - All three share `creator_library.py` (three byte-identical copies, guarded by a test). The plugin keeps no profile derivation or pick retrieval that duplicates the backend. When the host has no persistent files,
    picks cannot be deduplicated across days and each review starts from a fresh reading; the Skill says so plainly. How to write host scheduled tasks is in `start-with-kabo/references/host-schedules.md`;
    scheduled tasks run only the picks and the review and do not call write tools.
- **Permission scope widened: the first authorisation adds `workspace:write`.** The `defaultScopes` in `host-auth.json` changes from `data video workspace:read` to `data video workspace:read workspace:write`, and the package check is updated to match. Reason: the first conversation
  has to bind an account, trigger profile generation and save pillar changes, all of which need write permission;
  testing on real hosts showed that Codex authorises per `defaultScopes` and does not top up permissions from a 403 challenge. **Already-installed users need to log in once more** (Codex:
  `codex mcp login kabo --scopes openid,profile,email,offline_access,data,video,workspace:read,workspace:write`; on other hosts, disconnect and reconnect);
  old authorisations are covered by each Skill's missing-write-permission handling.
- The `/mcp-pub` contract (`contracts/directory-mcp/`) is re-pinned to kabo `80e7d5263` using the command recorded in `pin.json` (79 tools, adding
  `get_for_you_videos` and `prepare_creator_profile`; `tools-list.json` is byte-for-byte identical to the backend golden), and both go into `runtime-contract.json`.
- Adds `INSTALL.md`: installation steps written for an AI assistant to follow (for hosts without a plugin installer, such as Grok Bot and Muse). `host-schedules.md` now says that, to prove a scheduled task
  will be delivered, temporarily moving the daily task is preferred; any extra temporary task must tell the creator how to turn it off, and must be deleted as soon as the proof is seen, with the task list read back to confirm (in a real run Grok Bot was told
  "run 5 times" and the task still ran 137 times). The README corrects the duration limit of `remake-viral-video` from 90 seconds to 10 minutes (consistent with that Skill).
- The files of the 18 existing Skills are unchanged; the three new Skills do not declare `metadata.version` and are not listed on any channel, so Web publishing skips them.
- Acceptance: the non-interactive flow of the three Skills was run with two accounts on Codex 0.167 with production `/mcp-pub`; Claude Code, Grok Bot, Muse, interactive sessions, scheduled tasks
  running at their due time, new installs getting write permission by default, a successful profile after a classification retry, and YouTube channel-name display have not been verified.

## 1.0.37 (2026-11-11; GitHub Release)

- `develop-content-ideas`: the content-ideas report is validated by the script and written to a final file, displayed verbatim through the host's existing `emit_block(path)`, with the model adding at most one lead-in sentence and no longer retyping or rewriting the report in the conversation (I20 incomplete, report shortened). The request is first normalised by code: language tags such as `es-ES` are unified, and interface text in Chinese, English, French, Arabic and Spanish is supplied by the program; 1 idea and 15-20 ideas are supported; a same-style continuation checks that the core mechanism of the original input is retained (S094). When validation passes, the SHA-256 of the request and of the ideas content is recorded, and an export whose hashes do not match errors out instead of being delivered. Follow-up routing that picks from or expands an existing list is not fixed in this version (#144).

## 1.0.36 (2026-11-10; GitHub Release)

- `review-creator-account-deep`: for each watch-video request, `plan_media_jobs.py` lowers the keyframes from 60 to 12 and explicitly carries `sampling: duration_scaled` (same as video analysis). Downstream reads only the frames within the first 3 seconds of each video (`watch_media.py` shows the model at most 5 frames, and the author package lists only frames within 3 seconds); under the backend's duration-adaptive sampling, the frames within 3 seconds among 12 frames (6 at the start + 2 in the body + 4 at the end) are identical frame for frame to those among 60 frames, and the other 48 frames only make the combined result larger and frame extraction slower (#157).

## 1.0.35 (2026-11-10; GitHub Release)

- `analyze-content-video`: the measurement-basis line of the report no longer always reads "viewing unverified" (or its Chinese counterpart). The frames had reached the model and the report cited them one by one, yet creators read it as "the footage was never viewed" (group feedback on 11-06); now it states only the number of frames extracted, the number of frames the report cites, and the sources of the transcript and backend data. Results generated before 1.0.32 still replay with the old wording accepted.

## 1.0.34 (2026-11-10; GitHub Release)

- Same content as 1.0.33; only the three Skills that declare `metadata.version` are bumped one version: `optimize-creator-brand` 0.3.24, `plan-content-calendar` 0.1.27 (including the `candidate_skill` constant in the schema), and `price-creator-brand-deals` 0.4.14. #152 changed `static_host.py`, which 15 Skills share, so the content checksums of these three changed, and Web publishing requires the declared version to be higher than the online one, which is why 1.0.33 could not be published to Web.

## 1.0.33 (2026-11-10; GitHub Release)

- `research-instagram-trends`: before the Gate score sheet, each lane keeps at most 30 items, taking items inside this week's window first, then items without a publish time, and items outside the window last; previously a lane had 90-100+ items for the model to score one by one, and the model wrapped up without scoring, and described the step it had not run as "metrics completion did not finish" (Web inspection on 11-07). Patterns that have a single citation and no outlier / top-quartile evidence are removed, rather than being forced through by changing the stage label; a step that did not run is reported honestly as not run, without blaming upstream (#153).
- Addendum: when all media fails, `review-creator-account-deep` degrades to continuing with catalogue numbers only instead of exiting with 1, and the watch-video handoff is a mandatory step (#152); it was released with the v1.0.32 tag.

## 1.0.32 (2026-11-10; GitHub Release)

- `analyze-content-video`: once the frame-reading call has displayed the images, the frames count as viewed, and saving and staging frame by frame is no longer required (the report lists frames by the keyframes envelope and does not need the frame bytes); previously on Web, 59 frames meant 59 staging steps, which exceeded the per-turn step limit, and the run stopped right after reading the frames (two production regressions on 11-07). `collect_media.py`: "N tasks still running" is on its own line, so the second-round handoff is also recognised by Web hosts; the resume argument is now `--id=<id>`; the run that was entered with `cd` is the one used (same as the deep review in 1.0.30). Fixes the KS2.2 lint error in `evidence-reading.md` (#149).
- `analyze-content-video`: when only the transcript is exported, metadata is not fetched and the request has no `content_id`, so `build_content_evidence.py` used to exit with `content_ref needs a content_id`; it now takes it from the original link (#151).
- `review-creator-account-deep`: an audio name or author is metadata and does not represent how it sounds; for sound that was neither heard nor measured, do not comment on genre, mood or whether it fits (review N0685, #149).

## 1.0.31 (2026-11-09; GitHub Release)

- `remake-viral-video`: re-pins the directory contract per kabo#2136; polling `get_remake_video` now carries `words: true`, the transcribe result carries per-word timing, cuts are made on word boundaries so the same stretch of the original is not placed twice, and the step notes of trim / concat flag this (#145).

## 1.0.30 (2026-11-09; GitHub Release)

- `review-creator-account-deep`: the watch-video handoff of `watch_media.py` is rewritten so that Web hosts can complete it themselves (same as the video analysis in 1.0.25): slot lines carry numbers, the resume command has no `KABO_STATIC_RUN_DIR=…` prefix and uses the run that was entered with `cd`, "N tasks still running" is on its own line, and the second-round handoff is also recognised by the host; the resume argument is now `--id=<id>`, so a result id starting with "-" is no longer rejected as an option (#140).
- `recommend-publish-timing`: the title or summary must state the recommended time as HH:MM and must not state hours outside the recommended window; when a single hour is the answer, the body no longer reports the winning segment of the chunk vote (previously "recommend 18:00" appeared alongside "06:00-09:00 performed best"); when the creator's time zone was not obtained, the model writes `creator_view.clock_note` in the creator's language (these hours are not confirmed to be local time), rendered below the answer (#141).

## 1.0.29 (2026-11-09; GitHub Release)

- `remake-viral-video`: requests where the creator does not appear on camera (animation, product images, editing their own video, voice-over) use the single-step path directly, with no frontal face needed; when sound is needed and no recording exists, ask once before starting the project for a link to a talking video or a stock voice and wait for the answer, without choosing for the user; an already-confirmed script can be made as an on-camera-free voice-over (tts of the exact words + visuals + mux); when the material is clearly not the creator speaking, first ask the user which kind they want (#142, matching creator-remake-web 0.1.48/0.1.49).

## 1.0.28 (2026-11-08; GitHub Release)

- Same content as 1.0.27; the `metadata.version` of `plan-content-calendar` is bumped to 0.1.26 (#133 changed that Skill's content, and Web publishing requires the declared version to be higher than the online one, which is why 1.0.27 did not reach Web).

## 1.0.27 (2026-11-08; GitHub Release)

- `review-creator-account`: comparisons align observation windows of equal length, and conclusions on conversion rate and missing order data follow the measured sample (#132).
- `develop-content-ideas`: supports 15-20 content ideas at a time, with count, continuation and calendar intake filled in (#133, migrated from creator-skills#165).
- `review-creator-account`: account-growth forecast calibration; probabilities and ranges are based on the computed inputs, and gaps are stated when inputs are insufficient (#134, split out of #106).

## 1.0.26 (2026-11-07; GitHub Release)

- `develop-content-ideas`: reuses context visible in the conversation (the mechanism already chosen, same-style variants, the sequel source) without rewriting the user's original request; keeps diagnostic information (#89).
- `create-script-and-packaging`: for continuations / sequels, first confirm the published source before writing, keep the citations and media delivery requirements, and check continuity before delivery (#94).
- `review-creator-account`: the report carries the evidence time and sample basis, sales / conversion conclusions are narrowed to the measured sample, and observation windows are aligned (#110).
- Reel routing and personal facts: requests for talking-head originals go to script packaging; unconfirmed personal facts such as names and years of experience are no longer written into scripts (#129).

## 1.0.25 (2026-11-07; GitHub Release)

- `analyze-content-video`: the handoff of `collect_media.py` is rewritten to the same form as `connector_driver.py` in other Skills: slot lines carry numbers (`result 01  (fallback file…)`), and the resume command has no `KABO_STATIC_RUN_DIR=…` prefix (the run is found from the current directory). Web hosts recognise a handoff in this form, call `collect_video_media` themselves, write the result into the slot and resume, so the model no longer handles staging. Previously the host did not recognise it and the handoff fell to the model: the Instagram Reel diagnoses in pre M3b, M4c and M5a all failed at the staging step, and M5a gave up after failing once without delivering a formal report.

## 1.0.24 (2026-11-06; GitHub Release)

- `analyze-content-video`: the final number check now treats timestamps with fractional seconds (`0:07.866`,
  `0:08.366–0:09.366`) as a whole timestamp. Previously only `0:07` was stripped, and the leftover `.866` was treated as a
  number that could not be found in the evidence, so the whole report was rejected. The Web pre retest (M4c) and the plugin
  retest of an Instagram Reel diagnosis both stopped at this step; with the fix, the same run directory passes the final
  check in full.

## 1.0.23 (2026-11-06; GitHub Release)

- `analyze-content-video`: when `collect_media.py` cannot find this round's media result on resume, the error now adds a
  line: a host that passes the result in as an evidence reference should first run `static_host.py stage` on the result of
  the last `collect_video_media`, then run the same resume command. In the Web pre retest (M3b) the model fetched the media
  and resumed without staging it first; the error mentioned only the result number and saving to a file, the model gave up
  immediately, and no formal report was delivered.

## 1.0.22 (2026-11-06; GitHub Release)

- `analyze-content-video`: only `collect_media.py` may write the arguments of `collect_video_media`; the model no longer
  assembles this call itself, and on failure it no longer switches to fetching media item by item or checking the job
  (#125). In 12 runs on production Web with 0.14.31, most first assembled the call themselves and were rejected by the
  schema, then bypassed the script, fetched data item by item and answered freely, and never reached `finish_diagnosis.py`.

## 1.0.21 (2026-11-06; GitHub Release)

- `remake-viral-video`: a voice-over reference is no longer treated as unsupported, with the user asked for a face photo,
  just because the creator's video has no face on camera; a voice-over uses only the creator's voice (found by local plugin
  gates C4/C5, historical wording). The body text is compressed by an equivalent amount, to 20,999 characters.
- `remake-viral-video` (pre t17 acceptance): after a cancel, wait until the job is no longer running before replying; if
  that does not happen, say "cancel requested, stopping"; the `bg` estimate is now about $0.02/second (consistent with the
  runner's pricing, and no longer filed under "costs little or nothing"); when the message of `quota_exceeded` says another
  step is still running, wait for it to finish and resubmit with the same key, and do not describe it as quota used up; the
  total spend after an edit is read from `project.spend_usd` (kabo now counts post-delivery steps and edits in it).
- `remake-viral-video`: post-delivery edits and atomic projects (cross-repo contract v1–v1.4, 2026-11-04; content rewritten
  from `skill/references/atoms.md` of remake package V2-r87, changed from "run cr commands" to "call /mcp-pub tools").
  - Local edits after delivery (change a line, subtitle color/size, replace the background of one segment, overlay an image,
    insert a new shot) go through `edit_remake_video`, change only the parts the user named, produce a new revision, and keep
    the old one; time ranges are taken from `lines` in `get_remake_video` (`project: true`); details are in
    `references/edits.md`.
  - A new video within the five categories is still a whole remake by default; anything outside the five categories uses an
    atomic project: `start_video_project` → several `make_video_step` calls → `finish_video_project`; write the plan first,
    and tell the user what will be done and the approximate cost before paying; face-touching rules (redraw as little as
    possible, prefer real footage, degraded does not block delivery but must be explained); details are in
    `references/atoms.md`.
  - Gap-list items addressed: after a whole remake rejects a "no-person-on-camera reference", route to a project instead
    (the reference goes into `--reference-video`, reuse the reference footage and splice the creator's own segments back, G1);
    a generated video that does not contain the creator uses only faceless steps (G5); when the creator's video has nobody
    speaking, ask for a recording first, and only if there is none let the user pick a preset voice (G3); when the user asks,
    cancel a stuck job with `cancel: true` of `get_remake_video` (G6); the description is narrowed to trigger only when a
    finished video is wanted or an existing one is to be changed, and not for script writing, breakdowns or account
    diagnosis (G8).
  - Contract v1.5 (G4): when the user has no footage of themselves at all, `persona` can be used to create a fictional AI
    on-camera person (a studio portrait plus a preset voice), after which atoms are used as usual; it must be a fictional
    character that does not point to any real identifiable person, it is not used when the user has their own footage and the
    two are never mixed, and on delivery the user is told it is an AI-generated fictional person. `step-call` validates the
    description (≤600 characters, no @account or link) and seed_images (≤4 images, not creator/ handles).
  - `scripts/static_host.py`: `project-call` (0–4 creator video segments, photos, a reference video, reference images, or
    `--job-id` to append to an existing project), `step-call` (including trim / mux / extract_audio / voice_change, and tts
    preset voices), `edit-call` and `finish-call` are checked against strict shapes, accept only workspace handles, and use
    the idempotency key `<skill>:<run directory>:<tool>:<input digest>:a<sequence number>`; `fetch-step` and `fetch-revision`
    download only the signed links given in tool results (size, sha256, type, file header), and the latest revision is saved
    separately as `remake-<id>-r<N>.mp4`.
  - Contract v1.6 (kabo `e6ecd21b`): four tool-level atoms `retime` (speed / loop / bounce / hold), `crop`, `inpaint_text`
    and `layout` (composite multiple layers by box and time, optionally keeping only near-white/near-black strokes), executed
    locally, $0, never touching faces; `lipsync` gains `sync_mode` (only for sync-lipsync) and `tts` gains `speed` (0.5–2).
    Only tools are added, not scene-specific steps or recipes; the host composes the atoms for a scene. `step-call` validates
    on the same basis as the server (the ratio box is non-empty and inside the frame, the mode of retime matches
    speed/duration, sync_mode matches the model), and first checks that the layers of `layout` correspond one-to-one with
    handles.
  - To free up body length, error handling moved to `references/tool-errors.md` and handling of a returned script moved to
    `references/script-returned.md`, with the content unchanged.
  - The routing judgment is aligned with the web client creator-remake-web 0.1.40 and the local remake package (AGENTS.md /
    atoms.md): in the body, "Which path" is replaced by "Choose what to make" — five general principles (keep everything not
    asked to change; never redraw a face if the real pixels can be kept; use existing footage before asking; ask only what
    only the user can decide or know; a whole remake is a shortcut for "shoot another one with this structure", not a
    fallback) plus a capability catalog organized by "what to keep / what to change" (each item marked as to whether it
    redraws the face). The same shot with the same action in the original goes through `replace` → `lipsync`; changing words
    or language in the creator's video goes through `tts` → `lipsync`; what a whole remake did not do (B-roll, close-ups) is
    added after delivery with steps or edits. Project steps and edits start work right after stating the plan and
    approximate cost, and ask first only when exceeding what the user has agreed to (previously they waited for the user's
    nod). `motion` no longer treats a full-body photo as a prerequisite (extracting frames from the creator's footage is
    enough); when an edit needs an image, first check whether the finished video, the materials or the reference clip
    already have one. To stay within 21,000 characters, several phrasings in steps 1 and 2 and in "What this covers" were
    compressed, with the rules unchanged.
- Contract v1.7 (remake package V2-r95): the op of `make_video_step` gains `first_frame` (edit one image to produce a new
  still frame, redraws the face, paid, accepts only three tested-tier models), `still_video` (turn an image into a segment,
  with optional slow push) and `audio_edit` (volume/loudness/fade in-out/speed/length, local $0); `frame` accepts
  `at: first|last` (mutually exclusive with `t`); `refvideo` goes up to 30 seconds with Kling v4; `talking` accepts
  `prompt`; `captions` accepts `max_words` / `upper`; a delivered remake additionally has the handles `master.mp4` (the
  current picture without subtitles), `broll_bNN.mp4|png` (B-roll segments and their still frames) and `frame_sNN.png` (the
  first frame of a talking segment). `step-call` validates on the same basis as the server.
- Contract v1.8 (remake package V2-r96): `make_video_step` gains `transcribe` (what a video / audio clip says, with times;
  local $0, produces no file), with the result in `last_step.transcript`; a step that produces an image / video additionally
  has `last_step.output.preview` (a JPEG of ≤1280 px and ≤200 KB; for video, a four-frame contact sheet). `fetch-step` saves
  the preview separately as `<handle>.preview.jpg` and gives `preview_path` for the model to open and look at, and saves the
  transcript as JSON and hands it back as is; `step-call` validates the `language` of `transcribe`.
- Contract: `tools-list.json` is replaced wholesale by the official export from the data layer (commit `21a97d65` on the
  kabo#2022 branch `yutian/remake-atoms-launch`, after syncing kabo main `6677ce0f`; after kabo#2022 was merged into kabo
  main it was re-exported on merge commit `8c8cfc0d`, the three files are byte-for-byte identical, the sourceCommit of
  `pin.json` is re-pinned to `8c8cfc0d`, and it contains all tools of `4c0b966e` pinned in 1.0.17 (including
  `collect_video_media`); the golden is byte-for-byte identical, 77 tools; the `start_remake_video` description and the
  transcript limits change with kabo#2022 to a 10-minute reference clip, 1500 segments / 60000 characters), and `pin.json` is
  re-pinned. Relative to the version pinned in 1.0.17 (73 tools): added `start_video_project`, `make_video_step`,
  `edit_remake_video` and `finish_video_project` (permission video, added to the required tools); `get_remake_video` gains
  `project: true` (project state) and `cancel: true`, with its annotation changed to not read-only; `start_remake_video`
  carries `creator.photo_urls` / `voice_preset` from kabo#2011. The inputs / params of `make_video_step` are only objects in
  the public schema, and the server validates strictly key by key per op; the local strict validation in the plugin's
  `step-call` is kept as the first line of defense. kabo#2022 was merged and deployed to production on 2026-11-06. The
  originally planned version number 1.0.18 was already taken on main, so this change ships as 1.0.21.
- The `remake-viral-video` description incorporates contract v1.7 (same text as the web client creator-remake-web 0.1.41):
  the capability table adds `first_frame` (edit one frame / photo of the creator to produce a new still frame, redraws the
  face), `audio_edit` and `still_video`; principle 3 names the `master.mp4`, takes, B-roll and first frames of a delivered
  remake; for step notes, when a given box lands on on-screen text or a face, drop the box and redo it or tell the user;
  `atoms.md` adds the `at` of `frame`, `refvideo` up to 30 s, `talking.prompt`, `captions.max_words` / `upper` and prices.
- `remake-viral-video` route simulation (local t19) follow-up: principle 4 now states that lines are also taken by the agent
  from the transcript of the reference clip or the creator's video, and are not written by the agent itself; principle 3
  states that `frame` / `crop` are checked on the result before being used, a different moment is tried if it is unclear,
  and the user is asked only as a last resort; the start of "1. Collect the inputs" notes that it applies only to a whole
  remake (previously it pulled "replace a shot of the original" and "change the language of the creator's video" back into
  whole remake), "What this covers" is renamed "What a whole remake covers", and the run directory is reserved "per video".
  Steps 5 and 6 and the wording of "What a whole remake covers" are compressed by an equivalent amount, with the rules
  unchanged (body 20,995 characters). Same text as the web client creator-remake-web 0.1.42.
- The `remake-viral-video` description incorporates contract v1.8 (same text as the web client creator-remake-web 0.1.43):
  principle 4 "take the exact words from the transcript" points to `transcribe`, and the capability table adds a row;
  principle 3 "look before using" is changed to looking at the preview of each step (the `preview_path` printed by
  `fetch-step`, four video frames); `atoms.md` adds a `transcribe` row and the preview / transcript output of `fetch-step`.
  The body is compressed by an equivalent amount (20,998 characters).
- The `remake-viral-video` body is pressed back to within 21,000 characters (previously 21,195, which made `skills:lint`
  KS3.1 report an error): several phrasings in steps 1, 2, 3 and 8, and in the cancel and scope notes, are compressed by an
  equivalent amount, with the rules unchanged (body 20,996 characters).
## 1.0.20 (2026-11-06; GitHub Release)

- `analyze-content-video`: the final number validation accepts large counts rounded or truncated to significant digits (for
  example 18,067,177 written as "18 million" or "1.8 ten-million" and 2,689,000 written as "2.6M+"), and recognizes the
  magnitudes thousand / million / ten-million; small numbers and spellings with only one significant digit are still
  blocked by the original rule. On production Web, video analysis was rejected at the last step because of this (#120).
- `analyze-content-video`: local measurement runs as a separate command with a time limit (#115).
- `diagnose-reach-drop`: when only public snapshots exist, gives an approximate decline judgment by post age (#119).
- Publishing to Web: publishing to the pre test account (`target=test`) no longer applies the production hold list
  `PLUGIN_WEB_HOLD`; `PLUGIN_WEB_TEST_HOLD` can be set separately (#121).

## 1.0.19 (2026-11-06; GitHub Release)

- Publish-to-Web flow: when SKILL.md declares `metadata.version`, it is used as the Web version (must be higher than the
  online version), and probe packaging no longer compares versions; the declared versions of the three new Skills are
  raised above the online versions (brand 0.3.23, calendar 0.1.25, pricing 0.4.13), so 1.0.18 could not be published to Web
  (#117). The Skill content is the same as in 1.0.18.

## 1.0.18 (2026-11-06; GitHub Release)

- Three new Skills: `optimize-creator-brand` (brand naming, bio, brand pack), `plan-content-calendar` (a reviewable content
  calendar) and `price-creator-brand-deals` (brand-deal pricing), ported from creator-skills (#97).
- Syncs creator-skills fixes made after the port and before the freeze point `6f8ef681f` (#114): for competitor / reach-drop
  / publish-timing, TikTok image posts and videos get separate baselines and the original links are kept; account review
  hands the "includes today" maturity cutoff to the report writer; content ideas can use plain conversation text as a
  continuation source (`--conversation-context`); script packaging distinguishes creative drafts from native packages, keeps
  the upstream SelectedIdea, hands the finished video to the host's media capability, and treats the duration suggested by
  the assistant as an estimate only.
- Production regression: pending.

## 1.0.17 (2026-11-06; GitHub Release)

- `analyze-content-video`: transcript, frame extraction and measurement (plus metadata for Instagram / TikTok) become a
  single `collect_video_media` background call, handed off and awaited by the new script `collect_media.py`; once everything
  is in a terminal state, each item is written to disk as `snapshot/envelope-NN.json` and the evidence build parameters and
  a single frame read are given; the model no longer submits and polls media jobs one by one (#112, requires kabo#2050).
  Codex production regression: 3/3 runs of the same YouTube video produced a report.

## 1.0.16 (2026-11-06; GitHub Release)

- `create-script-and-packaging`: when the user gives the direction themselves, the script that records the direction prints
  the next step, and the model goes on to write the script package, validate it and render `SCRIPT_PACKAGE.md`, instead of
  answering directly at this step (#107).

## 1.0.15 (2026-11-05; GitHub Release)

- `review-creator-account`: after the report is rejected by the validator, delete the report that failed validation, fix the
  synthesis and re-run the same command to produce the report; when the failure message does not involve the author field
  (system errors such as files or permissions), the report is flagged and the run stops (#104).
- `review-creator-account-deep`: `--workspace` first claims a run in this workspace that was just reserved and has not
  started (exclusive claim, started ones are skipped), and one request reserves only one run and records usage only once
  (#104).
- The three ported Skills drop the outdated `metadata.version`, so the Web side can accept these packages (#98).
- Production regression: pending.

## 1.0.14 (2026-11-05; GitHub Release)

- Handoff now passes a result number (#83): a data-fetch result carries a short number, the model only fills the number into
  the resume command, and the script downloads by number, checks length and sha256 and then writes to disk, no longer
  relying on the model to write the result to a file; results without a number are still saved the old way. On the same 30
  rounds of input as 1.0.10, model-written saves dropped from several to 0.
- `review-creator-account-deep` (#79): the catalog fetch hands off a single `collect_account_history`, and the metadata,
  subtitles and frame extraction for watching the videos hand off a single `collect_video_media`; both handoffs pass result
  numbers; the creative basis is bound by run name and relative path.
- Every per-use-billed Skill calls `start_skill_run` once after reserving the run directory (Kabo records one usage per
  skill and does not double-count the same run); when the quota is used up the Skill stops and hands the billing link to the
  user, and when the tool is missing it continues as usual. `remake-viral-video` uses only the video quota and does not
  declare it (#95).
- The catalog contract is re-pinned to the deployed kabo `096d598ba` (73 tools, including `start_skill_run`,
  `get_credit_balances`, `get_credit_tasks`, `claim_credit_task`, `collect_video_media`).
- `verify-platform-rule`: judging something a "rumor" requires official original text that contradicts it, and silence in the
  official text does not count as a rebuttal; paraphrases only translate and do not summarize; the description names rumors
  about threshold changes and the registration page (#88).
- `diagnose-reach-drop`: traffic-source groups can carry their own calendar windows; the generic window goes by post age
  only (#92, #96).
- `plan-platform-monetization`: keeps the country declared by the channel; the description covers questions where the user
  gives numbers and questions with no account (#85, #86).
- `analyze-content-video`: report labels in the Chinese view are localized locally and no longer fall back to the backend
  analysis (#87).
- The spec document keeps only the English version `docs/skills-spec.md` (#93).
- Production regression (Codex, OAuth connected to `kabo.sh/mcp-pub`, test account, installed `#stable` = `4e9343a`):
  `review-creator-account-deep` (@mkbhd YouTube) delivered a creator_report, with 1 `collect_account_history` for the
  catalog and `collect_video_media` for watching the videos, all 10 videos watched, all handoffs using result numbers, and
  model-written saves at 0; `review-creator-account` (@veritasium YouTube) delivered a creator_report, with 1
  `collect_account_history`, handoff by result number, model-written saves at 0, and `start_skill_run` recorded once each
  and not rejected by the quota. Leftover issues (not blocking release): on the first run of account review, the report
  validation blocked it because the model wrote a provider in the limitations note; after rewriting, the re-run of the
  already-delivered path reported "report does not match the source" and could not be rescued, and a second re-run delivered
  normally; in the deep review round two run directories were reserved, and `start_skill_run` recorded twice.

## 1.0.13 (2026-11-05; GitHub Release)

- `remake-viral-video`: the talking-head model choice is understood by meaning (same as web client kas#320 /
  creator-remake-web 0.1.39): the confirmation wording no longer requires "reply with a number / reply OK" and becomes "tell
  me which one to use; if you want to start right away use the default tier; nothing is generated or charged before you
  confirm"; if a reply selects a tier by meaning (a number, a name or a description, in any language), that tier is used; if
  the user clearly wants to start but selects none, the default (the first tier) is used; if it cannot be told or the answer
  is off-topic, ask once more briefly and do not start work; still never choose for the user.
- Offline check (Codex, no Kabo calls, reusing an archived script-gate task): "the second one", "use Wan", "use the cheapest
  one" and "go ahead" each select the corresponding tier (go ahead uses the default Vivix), and a weather question gets only
  a brief re-ask without writing any video parameters, 6/6 passed; the first message does not require replying with a number
  or OK.

## 1.0.12 (2026-11-04; GitHub Release)

- `remake-viral-video`: a video can also be produced when the creator has only photos: `start-call --creator-photo` (1–4
  public JPEG/PNG links, at most 4 together with videos) goes into `creator.photo_urls`; with only photos, first ask the user
  for a video of themselves speaking, and only if there really is none let the user pick among 4 preset voices
  (`--voice-preset`). The rules are in `references/creator-photos.md`, consistent with web 0.1.35. Depends on kabo#2011
  (server-side safe image fetch for `/mcp-pub`) and runner V2-r72.
- Production regression (Codex, OAuth connected to `kabo.sh/mcp-pub`, test account, runner V2-r74 series): photos plus the
  creator's own video (job `dadcaedf`) and photos only (job `e76090ba`) were both delivered. With photos only, it first asks
  "do you have a public 10–30 second video of yourself speaking", and only after the user says no does it list the 4 preset
  voices by number; after the user picked number 3 it produced the video with Male calm, and the final note told the user
  truthfully that "the appearance comes from the photos and the voice is a preset"; all plugin-side checks passed. On the
  runner side: when photos and a video are both given, all appearance references are taken from the video, and the delivery
  note did not mention the photo source either (handed to the runner to follow up).

## 1.0.11 (2026-11-04; GitHub Release)

- `remake-viral-video`: the description is narrowed to "use only when a finished video is wanted", same as web client
  creator-remake-web 0.1.36 (creator-skills #955): writing a script using a reference's structure, breaking down
  editing/sound effects/format, account diagnosis, growth advice and content ideas do not trigger a remake (in production, a
  script-writing / breakdown / diagnosis request had wrongly loaded the remake skill).
- Routing check (Codex, no Kabo calls, a package of fifteen Skills): 6 requests for script writing / breakdown / reach-drop
  diagnosis / growth and content ideas did not load the remake skill, and 2 requests for a remake and for producing a video
  from a script both loaded it, 8/8 passed.

## 1.0.10 (2026-11-03; GitHub Release)

- Recommendations for the last seven days on the three platforms now independently check content language; only candidates
  that qualify on both domain and language enter ranking, and when the language does not match or the evidence is
  insufficient the gap is left honestly.
- When the user explicitly agrees to add a given language, the allowed set is expanded; when the user agrees to any
  language, the language restriction is lifted for this request. The authorization takes precedence over the account
  default, and the profile is not rewritten; domain, time window and detail validation continue to apply.
- Cross-language search uses search terms in the permitted languages within the existing call budget, and the report states
  the coverage; YouTube can pass a search language preference per query.
- The combined YouTube fetch can optionally return the audio language declared by the platform; a conflicting audio
  declaration cannot be overridden by an English title or description. TikTok reads the text per the field mapping of the
  original caption, and Instagram reads the original caption.text.
- Original-text evidence and a short reason are kept, distinguishing platform-declared, copy-inferred and unconfirmed; an
  older domain judgment cannot be used directly as the result of the new language review. When language is unrestricted,
  unknown spoken language is not passed off as verified either.
- The fifteen Skills and the existing MCP/OAuth connection are kept. The GitHub Release, the stable update and the OpenAI
  store review for this change, plus all cross-host acceptance, are recorded separately.

## 1.0.9 (2026-11-03; GitHub Release)

- Short-window recommendations on Instagram, TikTok and YouTube first judge the domain from the full candidate text and then
  rank by popularity; each item keeps its judgment and a short reason.
- Instagram's last seven days goes through the Search collector (experiment B): at most two intents, one page each, with an
  original-post detail budget of 24; only candidates whose details are complete, whose views are known and whose original
  post date falls within the exact time window take part in ranking.
- The popularity layer for TikTok and YouTube re-checks the 30-day boundary locally; the report states the number excluded
  and the missing data, and when there are not enough slots, the gaps are honestly kept.
- The talking-head script production and delivery notes published in 1.0.8 are fully kept; this package also contains the
  fifteen Skills already merged into main, the backend aggregated fetch and the compatibility fix for media operation names.
- This release focuses its acceptance on the three-platform recommendation changes; the full cross-host acceptance of the
  fifteen Skills and the OpenAI store review are still recorded separately and cannot be replaced by this GitHub Release.

## 1.0.8 (2026-11-02; GitHub Release)

- `remake-viral-video`: produce a video from a confirmed talking-head script (no reference video). It reuses the same chain
  as a remake: `start-call --script-file` carries the script verbatim (exactly one of it and `--reference-url`),
  `check_documents.py copy-drafts` writes the runner's four drafts verbatim into submission files, and only line breaks may
  be changed; model choice, production, final-review relay and failure handling are shared with remake. The script-writing
  rules are ported from the approved-script flow of creator-remake-web 0.1.32 (`references/approved-script.md`). Depends on
  kabo#1925 (`start_remake_video` gains an optional `script`).
- `remake-viral-video`: when run inside a subagent, the main thread relays the subagent's final result to the user in full
  (path, cost, final review).
- Production regression (Codex, OAuth connected to `kabo.sh/mcp-pub`, default Vivix A1, runner V2-r71 series `a028b1a9`): a
  confirmed 54-word talking-head script (job `5dfe48ee`, 20.7 seconds, $0.46) was delivered, with a word-by-word check
  showing 54/54 identical; the approved-script path, `--script-file` carrying only `script`, `copy-drafts` writing verbatim,
  the default Vivix, and not fabricating a conclusion when the final review is empty all passed. The main thread dropped the
  cost when relaying, and the wording is corrected in this version.

## 1.0.7 (2026-11-02; GitHub Release)

- `remake-viral-video`: reference video limit raised from 60 seconds to 90 seconds (kabo#1826, runner r62).
- `remake-viral-video`: after the finished video is delivered, use `include: ["review"]` on `get_remake_video` (kabo#1825) to fetch
  Kabo's final review verdict and delivery note: tell the user each `failed` item in plain language, say that some checks could
  not be measured for `incomplete`, and do not mention the review result for `measured` or null; never say the video
  "passed final review"; paraphrase the delivery note in one or two lines.
- `remake-viral-video`: both the reference video and the creator's footage accept TikTok links (kabo#1836): long links are normalised to
  `https://www.tiktok.com/@user/video/<id>`, and `vm.`/`vt.` short links keep their trailing slash as-is, matching the server's format so the
  idempotency keys line up; image posts, http links and other platforms are rejected before any paid call.
- `remake-viral-video`: the description and body state that the finished video is generated by the Kabo server from the user's own footage (the person
  on camera is normally the user), and that the host is not generating a face or voice itself, so the host must not refuse
  "remake the video onto yourself" as impersonating a real person (one host refused before calling the tool).
- `remake-viral-video`: the final-review paraphrase goes through the `failed` list item by item and ignores `status` (production once returned `measured` with `failed [framing]`); `framing` added;
  the self-check numbers in the delivery note are not paraphrased. The paraphrase rules moved to `references/final-review.md`, and the step 8 details moved to `references/when-it-does-not-finish.md`.
- `remake-viral-video`: supports picture-in-picture (cutting to a screen recording or screenshot during the talk) and physical-product (showing the product while talking, cutting to product close-ups) reference videos,
  ported from `talking-with-screens.md` and `talking-with-product.md` in web creator-remake-web 0.1.32 (creator-skills `f74df60a`);
  the runner detects the type automatically. For the product type, the talking shots are bare-handed by design; the skill tells the user up front and does not promise a hand-held product.
  Depends on kabo#1896 (`/mcp-pub` allows these two types and quotes the talking model for all three talking types), runner V2-r66.
- `remake-viral-video`: model options now use `talking_model_choices` returned by `get_remake_video` with `all_models: true` (kabo#1899,
  all tiers, the first tier is the default); an older server that only has `talking_models` still uses that as before. Wan 3.0 is an optional second tier; the default is still Vivix A1
  (user decision on 10-31, kabo#1911, same as web kas#294).
- `remake-viral-video`: the original author's self-introduction is rewritten in the creator's voice where possible instead of being deleted wholesale; if what remains after deletion is under half the reference duration, tell the user in one sentence before choosing a model
  how short the finished video will be and why (in a production regression run, a 73-second reference shrank to 13 seconds).
- Production regression (Codex, OAuth to `kabo.sh/mcp-pub`, default Vivix A1, runner V2-r70 `fdcd2d10`, product type retested separately on V2-r71 `087045c1`):
  talking (Instagram 72.8 seconds, job `22cb0fcd`), picture-in-picture (TikTok, job `f3dbe111`) and product (YouTube Short, job `3b4c83e2`) were all delivered,
  and all plugin-side checks passed: model options had Vivix as the first tier and the default render used Vivix; picture-in-picture / product read the matching format files and the product type announced bare hands up front; the final-review paraphrase was complete.
  Most of the talking reference was the original author's professional self-introduction while the creator is a gardening creator,
  so the script was cut to about 15 seconds and the user was told before the model choice.
  Known runner visual issues (no worse than r67, tracked separately by the runner): picture-in-picture screen recordings are cropped and subtitles cover the recording; product-type desktop products are incomplete and some inserted shots were replaced by generated stills;
  the original white-background title of the talking video is lost and subtitles cover the hands.
- Merged into main (1.0.5 / 1.0.6 were already released from main and include the narration reference): narration and the three talking types coexist, with the reference limit unified at 90 seconds.
  The merged package was smoke-tested in production (picture-in-picture TikTok, job `20964b79`, runner V2-r71, 73.3 seconds, $1.22): it read the picture-in-picture format file, `all_models` returned
  `talking_model_choices`, the default render used Vivix, and the final-review verdict (framing) was paraphrased item by item; all passed. Narration references were not tested in this round (released with 1.0.5 / 1.0.6 from main).
- `contracts/directory-mcp/` re-pinned to kabo `d1dcf9b09` (64 tools, including `all_models` / `talking_model_choices` on `get_remake_video` and `script` on `start_remake_video`).
- Four new Skills, all ported from creator-skills `8fc3371e6` and adapted per KS1-KS8 (ported from this fixed version; differences from later upstream versions will be reconciled before launch):
  `diagnose-reach-drop` 0.4.10, `recommend-publish-timing` 0.5.15 (`2947e5ea`, including the fix for magnitude-word numbers on the evidence side), `plan-platform-monetization` 0.7.13,
  `verify-platform-rule` 0.18.23. `manifest.json`, `agents/` and the scripts that read host session transcripts were removed; data fetching now uses `/mcp-pub`
  tool names + `delivery:"download"` + `static_host.py`; data files over the KS3.2 limit were split, or fields that neither the scripts nor the body read were removed.
  `recommend-publish-timing` fixes an inconsistency between the upstream validator and the engine in judging confidence for hour-level recommendations (the validator recomputed it from the metric agreement rate, while the engine used same-row corroboration);
  previously most hour-level recommendations failed at the validation step.
- `verify-platform-rule` depends on `official_page_render_page`, which `/mcp-pub` restored (kabo#1817, merged and deployed); `contracts/directory-mcp/`
  re-pinned to the merge commit `d1dcf9b09` on kabo main (64 tools; also includes the input/output updates made on kabo main in the meantime to the remake tools, `analyze_content_video` and
  `tiktok_list_account_posts`).
  The four new Skills were tested on a local Codex against production /mcp-pub: publish timing and monetization were delivered; the platform rule check awaits the kabo#1817 deployment.
- `analyze-content-video` synced to creator-skills 0.14.29 and `create-script-and-packaging` synced to 0.2.27 (frozen commit `a9514ba30`): local video frame extraction now uses hashed file names, 720px, capped at 90 frames / 12 MiB, and writes the start and end first; `--measure-signals` measures cut points and pauses into `media.probed`; host machine transcription uses `--origin speech_recognition` to be recorded as "heard"; a healthy job waits about 3 minutes within the same turn; handling for measurements, long-video text, image posts and edit requests that cannot be obtained is written into `references/evidence-reading.md`; the script's `video_analysis_sources` only accepts `video_analysis.json`; for a sequel, first verify the previous episode. Neither SKILL.md body grew.
- review-creator-account-deep synced to upstream 0.3.52: when there is no standard-edition analysis, `fetch_catalog.py` fetches one page of the post catalog within this run (at most 4 catalog calls per run, failed calls are recorded with `--failed`, and Feed failures are not retried); when a later step is missing input it exits with code 2 and gives the two entry points of step 1; the standard-edition reuse notes moved to `references/standard-inputs.md`.
- `develop-content-ideas` synced to creator-skills 0.1.31 (`a9514ba30`): prep returns `needs_correction` uniformly for all kinds of input problems (non-JSON / non-UTF-8 / missing files, non-verbatim topics, wrong language tags), merges all independently verifiable problems in the first round, and allows only one correction; supports "10 more in the same style" follow-up rounds (`--previous-ideas` binds the previous round's `idea_set.json`); report languages other than zh/en/fr/ar use the translated UI labels listed by `report_language.py --labels` and validate each item. `remake-viral-video` was compared against upstream 0.1.34 and needs no change (TikTok links are handled by #20, Wan 3.0 is not in the current `/mcp-pub` contract, and the fixed tween values were already merged in #40); only the provenance record was updated.
- `review-creator-account` synced to creator-skills 0.5.53: TikTok image posts (photo) and videos get separate baselines; `build_public_snapshot.py` recognises `tiktok_photo`/`tiktok_video` from the original post URL or the platform-declared media type, records anything undeterminable as unknown and excludes it from same-format comparison; when duplicate records are merged, the original post URL is kept.
- `analyze-creator-competitors` synced to creator-skills 0.5.89: `report` first normalises synonyms of the synthesis `status` (completed/done/ok/success, incomplete, failed) to complete/partial/blocked, and other invalid values get a fixable hint at the compose entry instead of failing only at validation. `review-creator-account` stays pinned to upstream 0.5.50, whose changes (`--export-report` and handoff only accepting `.json`) belong to the delivery mechanism of the web host; the plugin version has no handoff export and `ACCOUNT_REVIEW.md` is already a locally delivered file, so they are not ported.
- Three trends Skills: item-by-item review of the account-profile series (#914, #915, #918, #920, 15 commits) between creator-skills `92824da5b` and `a9514ba30` (the freeze point); scripts and references are fully covered by #32, #33 and 1.0.6, so no further porting is needed; the source recorded in `skills.lock.json` is changed to IG 0.3.115 / TT 0.1.105 / YT 0.1.103 (`a9514ba30`).

## 1.0.6 (2026-11-02; GitHub Release)

- Recommendation delivery gains a unified fallback: videos that were already selected are not lost because synthesis left them empty; when the normal recommendations are empty, at most three videos collected in this round are shown as references, clearly labelled as matched or insufficient data, with no fabricated metrics. The original Gate and quota are not rewritten, and no extra data or model calls are added. If YouTube coverage is still insufficient after one re-search, the report continues with the existing candidates instead of aborting.

- The three trends Skills fix the off-topic rules and boundary holes found in the #1866 retest: queries no longer force a historical profile seed,
  and the Gate always judges relevance against this run's Request.niche; with zero signature categories a reliable base profile is still kept.
  Analysis explicitly records all selected videos (including those not matching a signature category), the report shows only the selected evidence, and the Composer and Validator share the selected-scope check.
  The historical seed quota check and its unused parameters are removed; the profile-less filter expansion is withdrawn, and author de-duplication is still handled by the existing allocation step.
  Query semantics are still judged by the host; no new target files, model stages or recommendation policies are added, and the search budget, thresholds and backend API are unchanged.
- Repository rules enter CI: `scripts/repo-rules.test.mjs` is restored (vendor names, host-specific mechanisms, case numbers, provenance docs, bytecode), with two new rules: Skill Markdown must not contain version code names or dates; Skills with scripts must state at the start of the body that a foreground sub-agent executes them (KS2.4). The references of `analyze-creator-competitors`, `research-instagram-trends` and `research-youtube-trends` drop measurement / observation dates, with conclusions and numbers unchanged. CodeRabbit gains three judgment rules: do not put execution rules in the description, put the delivery contract first, and do not add exceptions to the body that can be handled by a validation script.
- Convention cleanup (no behaviour change): the titles of `create-script-and-packaging` and `develop-content-ideas` drop their V3/V4 version history; the `analyze-content-video` format notes and the `review-creator-account-deep` waiting notes drop their history and dates and keep only the conclusions.
- `analyze-creator-competitors` synced to creator-skills 0.5.88 (`c414fac55`): a duplicate competitor keeps the first entry and no longer fails the whole report, and profile tab links are accepted per account;
  a missing `competitor-eligibility.json` (or a wrong file name) or a missing intents file returns `needs_correction` without closing the run; when the Gate misses at most 1/20 rows in a long table, 0 scores are filled in and noted;
  `popular_topic` gives only the category lane; a YouTube `@handle` is first resolved to a channel id via `youtube_get_channel` using `subject --platform youtube --handle`, and a bare `@handle` is no longer silently treated as Instagram;
  evidence and replies give posting frequency per account (a lower bound is written as "at least N posts"), the YouTube subject history fetches 50 posts at once, and after the backup accounts are classified `content` no longer inherits `--placed`;
  the reply states the number of accounts the user asked for and the automatic-discovery cap of 6 per run, and still lists the key content when there is no pattern; `content --comments` fetches comments in one call, `comments` is kept as an alias, and the schema is printed compactly before large evidence blocks.
- Skills that use `static_host.py`: `stage` rejects a result whose "status is complete but has no `data`" (the host dropped `download` when saving the download result, leaving only a digest) and points back to saving the full result and then running `fetch`. Previously such a digest was staged as evidence and only a later script reported an error, and the full result downloaded afterwards was never read.
- `review-creator-account` synced to upstream 0.5.49: a first `report` that passes (never returned needs_revision) is the final step, and `verify-report` no longer runs;
  running `verify-report` before `report` directly prompts to run `report` first; the YouTube channel bio and subscriber count enter the identity;
  a rejected YouTube handle now prompts to use `--channel-id`; `fetch` prints the compact schema before printing the input. `review-creator-account-deep`
  step 1 likewise recognises `report` as the final step and prints `creator_report:`.
- TikTok competitors (`analyze-tiktok-competitors`) synced to creator-skills 0.1.72: a duplicate competitor account keeps the first entry and no longer fails the whole report; display translations are matched by id and only `text` is read, header fields may be omitted, and a single non-compliant translation falls back to the source text and is listed in `kept_source_text` (the driver forwards it) instead of failing the whole report; `search_query` states two to five words.
- Skills that download Kabo signed links with `static_host.py fetch`: when Python's default trust store does not exist (python.org Python on macOS that has not run Install Certificates), `fetch` now uses certifi or the system's own CA bundle, with certificates still validated as usual. Previously every download on such machines failed with a certificate error and the model had to download with curl itself and then `stage`.
- Three trends Skills: when Compose/Validate rejects the synthesis at the `report` stage, the run is restored and `needs_correction` is returned (exit 0), allowing one fix within the same run; the second rejection ends it. Synced from creator-skills `4231cfa36` (#902, upstream IG 0.3.108 / TT 0.1.98 / YT 0.1.96). Only this one fix was ported, and `derivedFromVersion` in `skills.lock.json` is unchanged.
- Three trends Skills: when no region or language is specified, the Gate scoring table header gains `locale_fit_rule`, stating that the language of the question only determines the reply language and that `locale_fit` must not be lowered because of the content language. Synced from creator-skills `e4b807f4` (#906, upstream IG 0.3.109 / TT 0.1.99 / YT 0.1.97).
- Three trends Skills: `locale.region` / `locale.language` take only the market or content language the user explicitly named; the language of the question only determines the reply language, and both fields stay empty when nothing is named. Synced from creator-skills `77dd6179` (#909, upstream IG 0.3.110 / TT 0.1.100 / YT 0.1.98), written into each Skill's references with no growth in the SKILL.md body.
- Three trends Skills: `discover` gains `--question-file` (`-` reads the user's verbatim words from standard input); when `locale.region` / `locale.language` is non-empty, `locale.named_in_ask` must quote the fragment of the original words verbatim, otherwise `needs_correction` is returned with only one chance to correct. Synced from creator-skills `92824da5` (#919, upstream IG 0.3.111 / TT 0.1.101 / YT 0.1.99).
- Three trends Skills: the remaining applicable changes between creator-skills `d2de2e4e` and `92824da5` (#919, IG 0.3.111 / TT 0.1.101 / YT 0.1.99) are brought in (#879, #889, #891, #892, #894, #898). When there is no pattern, the report lists the top five items before "Test this first" (Featured posts; multiples are shown only when the same-account sample has at least 5 posts); a small rise in TikTok search popularity is no longer shown as 1.0x; when the question within seven days is "which ones beat their own norm" or any other same-account multiple, it stays in the Workflow (`--policy user_named_span`); when the IG audio chart needs per-track ideas, one idea per track is given in chart order with de-duplication; when more rows are requested than the chart has, one sentence states the chart's row count and no re-pull is done (IG, TT); under a single TikTok snapshot, `current_high_performance` must cite content at at least 1.5x its own norm or in the top quarter of public metrics, otherwise use `recurring_pattern`; the `content_key` of IG supplementary fetches carries the `instagram:` prefix, and when rejected it is resent once as-is and then `rank --placed`; the Gate scoring notes state that without a named market or content language `locale_fit` is not lowered because of language; the IG description states that beating one's own norm within a topic belongs to this Skill. The rules are written in references (the TikTok opening rules are split into the new `references/synthesis-openings.md`), and the IG SKILL.md body does not grow. The later account-profile series upstream (#914, #915, #918, #920) was already ported into main by #32 and #33 and is not repeated here; host-related changes such as cwd wording and the manifest are not ported.

## 1.0.5 (2026-10-30)

- Effective profile and per-person edits for account profiles (the three trends Skills and `review-creator-account`):
  - `contracts/directory-mcp/` re-pinned to the main merge commit `927b75c47` of kabo-sh/kabo#1875, tool count 62 -> 63:
    `get_creator_profile` gains the optional boolean input `effective` and the gated output `effectiveContentProfile`, and a new write tool
    `update_content_preferences` (`workspace:write`, without `idempotency_key`) is added; `requiredTools` in `runtime-contract.json`
    gains the write tool. tools/list is byte-identical to the golden of that commit.
  - The provider has fixed the empty-array schema of `effectiveContentProfile.formats` with `maxItems: 0`; the temporary workaround in the meta-schema validation is removed,
    and all pinned tool inputs and outputs pass draft-07 meta-schema validation.
  - Manually ported creator-skills `feat/reco2-trends-effective-profile` (kabo-sh/creator-skills#920, `12b91ffef`): when the profile file contains
    `effectiveContentProfile` and its literals are recognised, it is read, otherwise fall back to `contentProfile` v1; Request gains `excluded_topics`,
    `market_region`, `own_content_ids` and `profile_basis`; plan validation, eligibility filtering and the Gate all enforce excluded topics; signature items rank first;
    the market serves only as the default search region (TikTok search, YouTube collect, not used for Instagram); switching profile files in the middle of a run is an error. This repository's MCP envelope unwrapping,
    non-printing of audience counts, and `--without-include` handoff stay unchanged.
  - Reading the profile uses `effective: true` and, if rejected, resends once without it. The `allowed-tools` of the four Skills gains `update_content_preferences`
    and `compatibility` gains `workspace:write`; the write rules are in the new `references/profile-edits.md` (identical text in four copies), following the confirmation rules in kabo CONTRACT §16.6
    (kabo-sh/kabo#1869); on 409 re-read first, and on `insufficient_scope` ask the user to approve the extra permission and retry once.
  - New effective-profile fixtures (three TikTok ones taken from the vectors of the kabo `effective-content-profile-v1` golden) and matching tests; the README and submission materials
    are updated. Before launch the directory review must be run again and the plugin acceptance redone.
- The three trends Skills (`research-tiktok-trends`, `research-instagram-trends`, `research-youtube-trends`) receive the backend account profile:
  S1-S3 of creator-skills #918 (`feat/reco-trends-allocation`, `e6fd8cfe7`) manually ported. When a user asks about trends for their own bound account,
  first `list_connected_accounts`, then `get_creator_profile` (`include: ["content_profile"]`), save the full result as-is to a file and hand it to
  `drive.py start --profile`; `--profile` is mutually exclusive with `--video` / `--post`. With a profile, the retrieval intent carries seed terms of the signature content,
  TikTok search carries `include: ["content_signals"]`, Instagram collect carries `include: ["media_signals"]`, candidates first pass the eligibility filter,
  the Gate gains a signature content id column, quotas are allocated by signature content weight, and the report cites at least one item per signature content category. The rules are in each Skill's
  `references/signature-content.md`. Language is only a retrieval label, not a hard filter, and is not written into `locale`.
  - Differences from how creator-skills reads it: the profile file may be a full `get_creator_profile` result (unwrap the MCP envelope first, reject on `isError`) or its
    `structuredContent`; `start` no longer prints audience counts (they stay only in the Request for the eligibility filter); this host does not fetch data for scripts, and when `include`
    is rejected the handoff prompt tells the model to rerun the same stage with `--without-include`, dropping `include` only from the calls of that round that carried it and handing them in once more.
  - When reading the profile is rejected, the tool is unavailable, `workspace:read` is missing, there is no matching account or `contentProfile` is null, no profile is used and the calls handed out are byte-identical to before
    (pinned by `scripts/mcp-pub-sync.test.mjs`). New `scripts/trends-profile.test.mjs` and synthetic fixtures `scripts/fixtures/creator-profile/`.
  - Depends on kabo #1849 (connector `include`) and #1851 (`include` on `get_creator_profile`). `contracts/directory-mcp/` re-pinned to
    kabo main commit `48d5ee773` (tool count still 62, byte-identical to the tools/list golden of that commit; `annotations.md` and
    `data-tool-bindings.json` are byte-unchanged). While the server has not yet launched these two items, reading the profile is rejected or returns null,
    and the Skills run as "without a profile".
- Remake (`remake-viral-video`) supports narration reference videos (nobody on camera, voice-over matched to visuals): ported from web creator-remake-web 0.1.30
  (creator-skills PR #896, runner V2-r63). On-screen text visuals are written by the agent as motion (composition; images needed in it are generated with
  `make.images`); after writing the script, first `render_remake_video` + `preview` to render paged visuals, save them locally with `fetch-preview` to inspect the images,
  and iterate until satisfied before rendering; before the final video the runner pauses once with a sentence-by-sentence comparison image, which is saved with `fetch`, then a `beat_review` is written and `--beat-review` is used to rework,
  redoing only the sentences that are not right. Narration has no talking model to choose.
  Depends on kabo `mark/remake-preview-review` (`/mcp-pub` allows narration, `render_remake_video` gains `preview` and
  `beat_review`, and the preview result and the sentence-by-sentence comparison image live in the brief envelope); `contracts/directory-mcp/` has been re-pinned to its commit
  `cf290a6cf` (only the inputs and descriptions of the two remake tools changed, outputs unchanged); after it is merged it must be re-pinned to the commit on kabo main.
- The step 8 "did not finish" details moved to `references/when-it-does-not-finish.md` (the SKILL.md body is back under 20,000 characters).
- New `scripts/remake-narration.test.mjs`: narration visual checks, preview / review parameters, and paged download (no network).

## 1.0.4 (2026-10-28; GitHub Release)

- `remake-viral-video`: when the reference video is judged to be a type other than pure talking head (handling a physical object while talking, screen recording / picture-in-picture, narration), tell the user which type it was judged to be,
  and state that the web version supports it (#16; for the server-side reason see kabo#1819).
- `remake-viral-video`: once both inputs are present, start directly, no longer requiring a check of bound accounts, OAuth or workspace data (#17).
- `remake-viral-video`: when another remake for the same account is already running at script-submission time, the server returns `quota_exceeded` (`reason: in_flight`,
  kabo#1822), and the skill waits for that one to finish and resubmits with the same parameters (#17).
- Video analysis (#14): a dot after a word (such as `obs.14`) is no longer treated as a decimal starting with a dot.
- `remake-viral-video`: on rejection, tell the user both which type it was judged to be and that the web version can remake this type; the first-remake opening notice must also be given first when the first message already carries both inputs,
  and listed item by item (what is remade, which cases are rejected before generation without charge, and that edge cases may work poorly).
  Production regression (Codex `gpt-5.6-luna`, OAuth to `kabo.sh/mcp-pub`, kabo-api image `bd4c6798`, runner `sha256:103d39d8…`):
  a normal talking video was delivered (job `fe1d0da5`, about 21 minutes, $0.55, 8-frame frame-by-frame check passed; at 27 seconds the subtitles covered a raised hand, which the runner's quality check did not report);
  a physical-product reference video was rejected before generation with `unsupported_type` three times (`e04da234`, `b5d74607`, `cd8d2432`), with the reason stating "showing or handling a physical object while talking"
  and noting that the web version supports it, with no rendering and no cost; the fixed version relays "the web version supports it" to the user. Known: GPT still often omits the "no charge on rejection" sentence in the opening notice.
  Not covered in production: the second submission after a script is returned once, and the in_flight rejection of #1822.

## 1.0.3 (2026-10-28; GitHub Release)

- New eleventh Skill `remake-viral-video`: remakes a viral pure-talking video of up to 60 seconds into a finished video (MP4) with the creator on camera.
  Ported from the script-writing gates of web creator-remake-web 0.1.23 (creator-skills `2206478d`) (pronunciation proofreading, four rewrite slots,
  on-screen text and inheritance ledger, source rules, four documents), pure talking only; screen recording / picture-in-picture, physical product, narration and web-specific mechanisms are not ported.
  Depends on the new `start_remake_video`, `get_remake_video` and `render_remake_video` in `/mcp-pub` (kabo#1777);
  the three tools were re-pinned into `contracts/directory-mcp/` with kabo#1777 (62 tools, also including two new TikTok topic tools and eleven personal-asset tools added on kabo main),
  and `requiredTools` in `runtime-contract.json` has been updated. The pinned source is the merge commit `005fcbc6d` of kabo#1777.
  On the first remake request, first explain in two or three sentences which reference videos are supported and which are rejected (same as web 0.1.26).
  Production acceptance: Codex 0.164 installed this package via OAuth, connected to `kabo.sh/mcp-pub` and ran one pure talking video through (job `ed76cc05`, runner r56,
  about 19 minutes, $0.53, frame-extraction check of the finished video passed); Claude Code and other hosts were not tested.
  Regression after the production runner was switched to r58q (fast opening pre-screen): a normal talking video was let through at the opening pre-screen and delivered (job `b04218cd`); a reference video with two people in frame
  was rejected as `out_of_scope` by the opening pre-screen within 30 seconds, with no paid generation done (job `0d1575bb`). The delivery result contains no final-review verdict, so
  the skill no longer claims the finished video "passed final review" and instead recommends that the user watch it in full before publishing.
- Video analysis (#12): a source that itself writes a number with a magnitude word such as "27B / 27 billion" is no longer treated as fabricated and no longer aborts the diagnosis.
- Personal-asset tools (#11): after workspace permission is granted, they can read bound accounts, creator profiles, social connection status, scripts and the video library,
  save or update scripts, and bind public accounts; `review-creator-account` and `create-script-and-packaging` use them as needed.

## 1.0.2 (2026-10-27; GitHub Release)

- Video analysis: when the server extracts fewer frames than the sampling plan (for example 120 requested, 119 returned), report generation is no longer interrupted, and `data_note` states
  "119 extracted frames of 120 requested"; more frame records than planned are still rejected.
- Frame-extraction requests for video analysis and deep review are capped at 60 frames (previously the default hit the server cap of 120): `static_host.py job-call` fills in `max_frames` per each Skill's
  `FRAME_CAPS`, and explicit values above the cap are rejected; the density of the first three seconds is unchanged, only the body sampling is thinned.
  Not measured on a real host or in production; the speedup was not timed.
- README adds installation and update instructions for the MCP and the Skills.

## 1.0.1 (2026-10-27; GitHub Release)

- Supports installing the ten Skills separately with the skills CLI (`npx skills add kabo-sh/kabo-mcp-plugin#stable`): the README explains installation,
  adding the `/mcp-pub` connection separately, and versions and updates; the `stable` branch points only to released tags and serves as the update channel for `npx skills update`.
  Each SKILL.md gains `license: MIT`, the license is distributed with separately installed Skills, and the package check requires it to match `plugin.json`.
  Install completeness and Codex 0.164 recognition were verified; login and end-to-end runs await acceptance.
- Repository collaboration conventions (AGENTS.md) changed to English, with commit messages and PRs in English.

## 1.0.0 (first released 2026-10-23; re-released 2026-10-27 with the public repository)

- Re-released on 2026-10-27: the repository became public and the development history is not published with the public repository; the ZIP was rebuilt from a new commit and the old ZIP is void.
- The plugin adopts the MIT license: a root `LICENSE` is added and packed into the ZIP, and `plugin.json`, `.claude-plugin/plugin.json` and `package.json` declare `MIT`;
  `.claude-plugin/plugin.json` explicitly declares the privacy policy link, and `claude plugin validate --profile directory` no longer reports directory submission problems.
  The license covers only this repository's content; the kabo.sh service remains governed by its terms of service.
- Cleanup before the repository went public: 1.x/2.x historical migration records were deleted, docs and code comments no longer reference issues, PRs and design docs of non-public repositories,
  and the README drops the installation requirement of private repository read access.
- The externally published version is unified as `1.0.0`, replacing the earlier development-stage package version numbers; this is not a rollback to old code.
- Keeps the ten fixed Skills of the latest main branch, the `/mcp-pub` connection, full evidence download, host adaptation and packaging fixes;
  deep uses only the validated output of the ordinary account review already completed in this conversation.
- Syncs the portable / Claude Code manifests, the npm root package and lock file, unpack tests, release copy and install migration notes; the build artifact is `kabo-1.0.0.zip`.
- Unified English experience: deep review defaults to English, the fixed notes in the catalog digest and comment evidence are now English, and report singular/plural forms are fixed; the README provides English install and troubleshooting notes, and explicit Chinese output and original source text are kept.
- The value `1.0.0` is lower than the earlier `3.x`, so old installs must refresh the marketplace and confirm the version actually loaded; the host is not assumed to downgrade automatically.
- The business versions, dependencies and schema versions of the source Skills are maintained independently.
- A GitHub Release does not change production acceptance or marketplace review status; acceptance must still be redone bound to this commit and ZIP.

## Old numbering (3.x and earlier, development phase)

Only the facts needed when upgrading are kept below; they are not the currently released versions.

- 3.1.1 (2026-10-22): frame reads now go through `delivery: "download"`, and the script writes images to the run directory, no longer depending on the host
  session directory; the ten Skills require the sub-agent to run in the foreground, so that reports are not lost when `claude -p` exits. Updating from 3.0.1 or later does not require re-authorization.
- 3.1.0 (2026-10-22): adds the Claude Code marketplace manifest `.claude-plugin/marketplace.json` (plugin ID `kabo@kabo-mcp-plugin`),
  the Codex marketplace name is still `kabo-plugin-openai`; the icon changes to the rounded K Fold icon; the ten Skills are adapted per `docs/skills-spec.md`;
  data tools by default download via GCS signed links valid for 10 minutes, and `static_host.py fetch` checks size and sha256 before writing to disk.
  `/mcp-directory` has been removed from the server; updating from 3.0.0 or earlier requires re-authorizing for `/mcp-pub`.
- 3.0.1: the connection and OAuth resource are unified under `/mcp-pub`; after updating from an older version, re-authorization is needed for the new address.
- 3.0.0: ten fixed Skills ship with the package and execute on the host; dynamic Skill download, signed package cache and lifecycle hooks are removed.
