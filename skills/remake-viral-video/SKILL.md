---
name: remake-viral-video
description: "Make a finished remake video of a viral talking-head reference (60 seconds or less) with the creator in it: the reference's scene and lines, the creator on camera, a few lines rewritten in their voice, rendered by Kabo and saved as an MP4. Use when someone asks to remake, recreate or copy a viral video onto themselves or a named creator. Needs a reference link and the creator's Instagram profile or video links. For only a script, use script writing; for only a teardown, use video analysis."
license: MIT
compatibility: "Requires the Kabo MCP server at https://kabo.sh/mcp-pub with its remake tools, Python 3, read and write access to a local workspace, and network access from scripts to the signed storage.googleapis.com download links that Kabo tool results return."
allowed-tools: start_remake_video get_remake_video render_remake_video
---

# Remake Viral Video

Kabo's hosted runner does every deterministic step of a remake: analysis of the reference and the
creator's footage, speech, first frames, talking video, grading, captions, review and delivery. You
make the creative calls at one point only, the script, and keep the user informed. Everything runs
through `start_remake_video`, `get_remake_video` and `render_remake_video`. If those tools are not
available on this connection, say that video remakes are not available here and stop; never draw,
record or assemble a video another way.

A remake takes about half an hour, most of it waiting on the runner. When the host supports one,
run this Skill in a foreground sub-agent and wait for its final result before replying; never run
it in the background and tell the user the video will come later. Without a foreground sub-agent,
follow the same steps in the main thread.

## What this covers

- A reference of **60 seconds or less** where **one person talks to the camera** for most of the
  video, at any distance, seated or standing, anywhere, with a fixed or slightly handheld camera.
  This version remakes only this talking-head kind. References that cut to screen recordings or to
  a product the speaker shows, and voice-over references, are not remade yet.
- Refused by the runner before any video is generated (`out_of_scope`): references over 60
  seconds, walking, vehicle or first-person vlogs where the camera keeps moving, dialogues between
  several people, references with nobody speaking on camera, references where the speaker is on
  camera less than about half the time, and references that are mostly other footage. So are
  creator videos with no clear frontal view of the creator's face.
- The creator is framed as the reference frames its speaker, shot by shot; the reference's other
  shots (cutaways, inserts, other people) are reused from its own footage. The reference's speaker
  never appears in the result.
- One method: the reference's content and setting are kept and the creator is placed into it
  (route B). Four kinds of line are rewritten in the creator's voice (the opening, the original
  author's claims about themselves, one closing summary and the call to action); the rest of the
  reference's lines are kept, or dropped with a reason. The whole face is generated, so likeness is
  lower than real footage of the creator.
- The final video has no on-screen label, notice or watermark. Never say it carries one.
- Only the model that makes the talking footage can be chosen, and only from the options
  `get_remake_video` returns once the script gate is reached (step 6). Voice, images and editing
  use one fixed production setup. If the user asks for any other model (for example Veo, HeyGen or
  ElevenLabs), say in one line that the talking footage can be made with one of the offered
  options only and the rest cannot be changed, then carry on.

## Set up one run

`<skill directory>` is the folder holding this `SKILL.md`. Reserve exactly one run per remake:

```sh
python3 '<skill directory>/scripts/static_host.py' init --workspace '<user-workspace>'
```

It prints the run directory. Run every later command from it with `KABO_STATIC_RUN_DIR` set to it,
in the same command (`cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 ...`):
many hosts do not keep environment variables or the working directory between commands. Paths such
as `host-results/...`, `brief/...` and `script/...` are relative to the run directory; `scripts/...`
and `references/...` live in `<skill directory>` and are called by that absolute path. Quote
filesystem paths in commands. Every command below is complete as written: do not run a script
with `--help`, read its source or search other Skills.

**Saving a tool result.** When a step says to save a result, write the complete
`get_remake_video` or `render_remake_video` result (the host's result export, or the result
unchanged) to `host-results/<NN>-<tool name>.json`, numbered in call order. These results are
small: they carry download links, never the brief or the video itself. Never retype the brief or
rebuild a file from what was displayed.

## 1. Collect the inputs

A remake needs both of these. Check them before any paid call:

1. **One reference video**: the viral video to remake, as a YouTube or Instagram link, 60 seconds
   or less, one person talking to camera.
2. **The creator's own talking footage**, separate from the reference: their Instagram handle or
   profile link, or one to four YouTube or Instagram links to videos where they talk to camera. It
   decides how much the result looks like the creator.

Uploaded or local video files are not supported in this version, and neither are TikTok links:
say so and ask for a YouTube or Instagram link instead. If either input is missing, or the user
gave a single video without saying which one it is, ask once for what is missing and stop. Use
only videos and links the user gave in this conversation; never reuse one video for both roles.
If a length you can see (the user states it) is over 60 seconds, say references are limited to 60
seconds and ask for a shorter one.

Whenever you stop before `start_remake_video` has accepted the job (something is missing, a video
is refused, the inputs are refused), tell the user that nothing was started, nothing was charged
and it does not count toward the daily remake limit.

`--creator-name` is a short ASCII name for the creator (letters, digits, `.`, `_`, `-`); with an
Instagram handle it defaults to the handle. Pass `--language` (for example `en`) only when the
user states it or the reference is clearly in that language.

## 2. Start the job and wait for the script gate

Before the first paid call, tell the user in one or two sentences what will happen: the method
above and that it takes about half an hour in total (do not say the result carries a label or
mark). Do not wait for a reply unless the user asked to approve first. Then build the arguments:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' start-call --reference-url '<reference link>' --instagram-handle '<handle or profile link>'
```

For creator video links, pass `--creator-video '<link>'` once per link (one to four) instead of
`--instagram-handle`. Add `--creator-name '<name>'` and `--language '<code>'` only as step 1 says.

It checks the links and prints `{"tool": "start_remake_video", "arguments": {...}}`. Call
`start_remake_video` with exactly those arguments. A refusal from the script is an input problem:
relay it and ask for a corrected input; nothing was started.

- The `idempotency_key` is stable for the same inputs in this run. On a timeout or lost response,
  call again with exactly the same arguments; the key returns the same job instead of creating and
  charging another. Never create a second job for the same request.
- `fetching_inputs` means the videos are still being fetched (`job_id` is null). Tell the user in
  one line, then call `start_remake_video` again with the same arguments after `retry_after_s`
  seconds (wait with the host's own sleep or wait facility); the same fetches are picked up.
- An error result (reference over 60 seconds, a link that cannot be fetched, no usable reels, the
  same video in both roles) means nothing was charged and the daily limit was not used: relay the
  reason and ask for a different video instead of resubmitting. At the daily limit, say no new
  remake was started, nothing was charged and another can start tomorrow. When another remake is
  still running, say one remake runs at a time. A key conflict means the inputs changed: build the
  arguments again with `--attempt 2`.

Once there is a `job_id`, call `get_remake_video` with `{"job_id": "<id>", "wait_s": 30}` until the
status is no longer `preparing`. Analysis takes about ten minutes. Tell the user the current stage
in one line when it changes; do not repeat yourself on every call.

**Talking head only.** As soon as a result shows a `reference_type` that is set and is not `talking`, stop: say
that this version of the plugin only remakes talking-head videos (one person talking to the camera,
without screen recordings, product close-ups or voice-over), that no video was generated, and the
spend the result reports, if any. Do not call `render_remake_video`.

A final status at this point (`out_of_scope`, `failed`, `timed_out`) is handled as in step 8; when
it comes from `start_remake_video`, its reason is in `message`.

## 3. Save the brief

At `waiting_script` the result carries `brief.download`, `gate_message` and `talking_models`.
Save the result as above, then fetch the brief at once (the link is short-lived):

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch --input 'host-results/<NN>-get_remake_video.json'
```

It downloads the bundle, checks its host, size and sha256, and writes the four brief files under
`brief/work/`. When it says the link expired or the download was refused, do what it prints: call
`get_remake_video` again (that re-signs the link; nothing is re-run), save that result and fetch
again. If this host blocks scripts from the network, say that the remake cannot continue here; never
rebuild the brief from what was displayed.

## 4. Write the script (the only creative gate)

Read `references/script-gate.md` whole, then the references it names for the judgement in front of
you. In short:

- Proofread the reference's sentences and record it in the script as `proofread`.
- Keep the reference's lines word for word and in order; rewrite only the four slots, each with
  `slot`, `why`, `replaces` and `basis`; source every fact in a rewritten line to the creator's own
  lines or mark it as an inference; never invent the creator's experience.
- Keep the reference's on-screen title and numbered list; record every inherited element in the
  ledger, with a reason for each adapt or drop.
- Write the opening record with 2-3 candidates, and choose one yourself.
- Record your calls in the decisions record; nobody answers questions at this point.
- Write the plate and anchor prompts without describing the framing, holding the creator's hair
  and outfit exactly as in the identity references.

Write the four documents as `script/script.json`, `script/opening_review.json`,
`script/decisions.json` and `script/route_b_jobs.json` (a heredoc at the absolute path, or the
host's file tool).

## 5. Check the documents

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/check_documents.py' check
```

It prints `status` with `errors` and `warnings`. Fix every error in the document it names and run
it again; read each warning and change the document when it applies. Advance only on
`status: ready`. It checks structure only; the runner checks again when you submit.

## 6. Choose the talking model and render

Nothing is generated or charged before this step. Show the user the `talking_models` from the
waiting_script result, in their order, each with its label and its estimated cost (`est_usd`), and
say that the first one is the default. Do not add a recommendation of your own, drop options or
change the order. End your reply there and wait for the answer; the job waits at the script gate.
When the conversation resumes, continue here in the same run directory.

- A model from the list, by number or name: use its `id`.
- A plain go-ahead with no choice ("OK", "yes", or the same in their language): the first option.
- A question about the options: answer it from the list, then wait for their choice.

Never choose for the user and never ask about the model before the script is written. Then build
the arguments (this repeats the check):

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/check_documents.py' render-args --talking-model '<id>' --models-from 'host-results/<NN>-get_remake_video.json'
```

It writes `render/render_remake_video.json`. Call `render_remake_video` with that file's content as
its arguments, unchanged. A retry of an accepted render returns the current state and never
launches twice, so on a timeout or lost response call it again with the same arguments.

If `render_remake_video` returns an error that names failing checks, nothing has been spent and the
job is still at `waiting_script`. Fix only what it names, keep the rest of the documents as they
were, run step 5 again and submit again with the same talking model: do not ask about the model
again. A `failure` of `unsupported_type` means the reference is not a talking-head video; handle it
as in step 2.

## 7. Production and delivery

Production takes about twenty minutes with the default model and longer with the others. Call
`get_remake_video` with `wait_s` 30 until the status is `delivered` or final. While it is
`running`, report the stage in one line when it changes. Do not promise a finish time.

At `delivered`, save the result and fetch the video at once:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch --input 'host-results/<NN>-get_remake_video.json'
```

It checks the MP4's host, size and sha256 and prints its local `path`. An expired link is handled as
in step 3. Then tell the user:

- that the video is ready, with the local path (it carries no on-screen label or watermark: never
  say it does);
- what you rewrote and why, in two or three lines, and any inference line they should confirm
  before publishing;
- the spend the result reports (`spend_usd`), when present.

Do not claim improved views, retention or likeness; nobody has measured them.

## 8. When it does not finish

Every final status (`out_of_scope`, `failed`, `timed_out`) comes with `failure` and, when the
runner gave one, `failure_reason`. Always tell the user that reason in plain words, not only that
the remake was refused or stopped (for example: the reference is filmed with a camera that keeps
moving, like a walking or travel vlog, rather than one person talking to the camera). Do not quote
stage names or internal terms. Always say whether it was charged:

- `out_of_scope`: relay the reason. For a reference that is not a short talking-head video, suggest
  one of 60 seconds or less where one person speaks to the camera for most of it. When no clear
  frontal face of the creator was found, ask for links to videos where they talk facing the camera.
  Nothing was charged and the daily limit was not used; say so.
- `failed` with a likeness reason: the generated person did not look like the creator, so the video
  was stopped or not delivered. Say so plainly and ask for clearer footage of the creator facing the
  camera; do not resubmit the same inputs.
- `failed` or `timed_out`: say the remake did not finish, why, and that no video was produced. These
  jobs ran paid steps and count toward the daily limit; do not say otherwise. Do not resubmit on
  your own; offer to start a new remake if the user wants one.
- Any other `failure` value: relay `failure_reason` and the reported spend; do not guess whether it
  was charged.
- A `get_remake_video` call that fails: try once more; if it still fails, say the job is preserved
  and can be checked later with its job id. Never start a replacement job for an unknown outcome.

When the user's next step is outside this Skill, name the Skill that fits -- for example
`create-script-and-packaging` for a script only, or `analyze-content-video` for a teardown of the
reference -- without running it.
