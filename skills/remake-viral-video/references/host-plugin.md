# In the plugin: this Skill's tools and scripts

Tools: `start_remake_video`, `get_remake_video`, `render_remake_video`, `edit_remake_video`,
`start_video_project`, `make_video_step`, `finish_video_project`, `upload_file`. Kabo runs every
step on its servers; the scripts in this Skill only build tool arguments, download and check
files. Never draw, record or assemble a picture yourself.

## Set up one run

`<skill directory>` is the folder holding `SKILL.md`. Reserve one run per video (a remake, a
project or its edits):

```sh
python3 '<skill directory>/scripts/static_host.py' init --workspace '<user-workspace>'
```

It prints the run directory. Run every later command from it with `KABO_STATIC_RUN_DIR` set to it
in the same command (`cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 ...`):
many hosts do not keep environment variables or the working directory between commands. Paths such
as `host-results/...`, `brief/...` and `script/...` are relative to the run directory; `scripts/...`
and `references/...` live in `<skill directory>` and are called by that absolute path. Quote
filesystem paths in commands. Every command below is complete as written: do not run a script
with `--help`, read its source or search other Skills.

**Saving a tool result.** When a step says to save a result, write the complete
`get_remake_video` or `render_remake_video` result (the host's result export, or the result
unchanged) to `host-results/<NN>-<tool name>.json`, numbered in call order. Never retype the brief or
rebuild a file from what was displayed.

**Local files.** A video or photo the user gives as a file on this machine (mp4, mov, m4v or webm
up to 200 MB; JPEG or PNG up to 10 MB) works in any role: send it with `local-files.md`, then pass
the `kabo-file:<id>` it gives wherever a link goes (`--reference-url`, `--creator-video`,
`--creator-photo`, `--reference-video`, `--reference-image`). If this connection has no
`upload_file` tool, say local files cannot be sent from here and ask for a link. TikTok photo posts
and other sites are not supported: ask for a YouTube, Instagram or TikTok video link instead.
Fetching the videos may use the daily data allowance even when no remake starts; do not claim
nothing was used.

`--creator-name` is required with creator video links; with an Instagram handle it defaults to the
lower-cased handle. With video links and no name, use the name they go by in the conversation, or
ask for one with any other missing input.

## Start the job and wait for the script gate

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' start-call --reference-url '<reference link>' --instagram-handle '<handle or profile link>'
```

For creator video links, pass `--creator-video '<link>'` once per link (one to four) instead of
`--instagram-handle`, and add `--creator-name '<name>'` (required then). Add `--language '<code>'`
only as `SKILL.md` step 1 says. Photos: `creator-photos.md`. It checks the links and prints
`{"tool": "start_remake_video", "arguments": {...}}`. Call `start_remake_video` with exactly those
arguments. A refusal from the script is an input problem: relay it and ask for a corrected input;
nothing was started.

- The `idempotency_key` is stable for the same inputs in this run. On a timeout or lost response,
  call again with exactly the same arguments; the key returns the same job instead of creating and
  charging another. Never create a second job for the same request.
- `fetching_inputs` means the videos are still being fetched (`job_id` is null). Tell the user
  `message` in one line, then call `start_remake_video` again with the same arguments after
  `retry_after_s` seconds; the same fetches are picked up.
- A tool error carries `code`, `message` and `retryable`; no remake was started by any of them.
  Read `tool-errors.md` and follow it.

Once there is a `job_id`, call `get_remake_video` with `{"job_id": "<id>", "wait_s": 30, "all_models": true}`
until the status is no longer `preparing`. Report each stage change in one line.

**Supported kinds only.** `reference_type` `talking`, `talking_screen`, `talking_product` and
`narration` go on. Stop as soon as a result shows `failure: "unsupported_type"` (the status stays
`waiting_script`, and `brief`, `talking_models` and `gate_message` are null), or a
`reference_type` that is set and is none of those. Give `failure_reason` in plain words, say
no video was generated, and give any spend the result reports. Do not say whether it counts toward
the daily limit. Do not call `render_remake_video`; this job is finished. A final status at this
point (`out_of_scope`, `failed`, `timed_out`) is handled as in `when-it-does-not-finish.md`; when it
comes from `start_remake_video`, its reason is in `message`.

## Save the brief

At `waiting_script` the result carries `brief.download`, `gate_message` and the model options.
Save the result, then fetch the brief at once (the link is short-lived):

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch --input 'host-results/<NN>-get_remake_video.json'
```

It downloads and checks the bundle and writes the brief files under `brief/work/`. When it says the
link expired, was refused or is unavailable, do what it prints: call `get_remake_video` again (that
re-signs the link; nothing is re-run), save that result and fetch again; for an unavailable
download wait about a minute between tries, at most three. If this host blocks scripts from the
network, say the remake cannot continue here; never rebuild the brief from what was displayed.

## Write and check the documents

Write the four documents as `../script-gate.md` says, to `script/script.json`,
`script/opening_review.json`, `script/decisions.json` and `script/route_b_jobs.json`. Then:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/check_documents.py' check
```

It prints `status`, `errors` and `warnings`. Fix every error it names and run it again; apply each
warning that fits. Advance only on `status: ready` (structure only; the runner checks again).

## Choose the talking model and render

Nothing is generated or charged before this step. **Voice-over**: there is no model to choose.
Tell the user the video will be made in their cloned voice with N pictures (M of them moving),
then wait for a go-ahead. After it, preview the stills once (`formats/narration.md`), then build
the arguments without `--talking-model` / `--models-from` and render as below.

For a talking video, show the model options from the waiting_script result
(`talking_model_choices`, else `talking_models`) in their order, each with its label and its
estimated cost (`est_usd`). Each `est_usd` is the whole video's estimated total, rounded up; say
the final charge is usually a little lower. Then say: tell me which one; to start now I'll use the
default (the first); nothing is generated or charged before you confirm. Do not ask for a number or
"OK". Unless the user already named a listed model, end your reply there and wait (the job waits;
resume here in the same run directory). Read the answer as `SKILL.md` step 4 says. Then build the
arguments (this repeats the check):

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/check_documents.py' render-args --talking-model '<id>' --models-from 'host-results/<NN>-get_remake_video.json'
```

It writes `render/render_remake_video.json`. Call `render_remake_video` with that file's content as
its arguments, unchanged; it returns `status: "running"`. On a timeout or lost response call it
again with the same arguments: an accepted render never launches twice. For a `conflict` or
`quota_exceeded` error, read `tool-errors.md`. A result with `failure: "unsupported_type"` is
handled as above. **The runner checks the documents first, after render returns.** If a later
`get_remake_video` shows `waiting_script` again with `gate_message`, nothing paid was spent: follow
`../script-gate.md` ("When the script comes back").

## Production and delivery

Call `get_remake_video` with `wait_s` 30, `include` `["review"]` and `all_models` `true` until the
status is `delivered`, final, or `waiting_script` again: for a voice-over whose `fetch` reports
`"saved": "review"` it is the one look at the finished pictures (`formats/narration.md`, last
section); otherwise the documents were rejected (above). While it is `running`, report the stage in
one line when it changes.

At `delivered`, save the latest result and fetch the video at once:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch --input 'host-results/<NN>-get_remake_video.json'
```

It checks the MP4 and prints its local `path`. A failed download is handled as for the brief. Give
the local path with the rest of `SKILL.md` step 5, the spend the result reports (`spend_usd`), and
what Kabo's final review found: read `final-review.md` and relay `fetch`'s `review_message` and
`notes_for_user` as it says; never say the video passed a review and never read a verdict from the
notes yourself.

## Edits, projects and steps

Edits, projects and steps follow `steps/*.md`, plugin blocks. Before the first paid step, say in
two or three lines what you will make; there is no quote on this host yet: do not estimate a
price; each step's `spend_usd` is what is charged, reported at delivery. Cancel a job
(`get_remake_video` with `"cancel": true`) only when the user asks; spend so far stays charged.
Stopping takes a minute or two: keep calling `get_remake_video` (30 s apart) until the job or
`last_step` is no longer running; if you stop sooner, tell the user the cancel was requested and is
still stopping, not that it stopped.
