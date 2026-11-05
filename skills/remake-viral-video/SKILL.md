---
name: remake-viral-video
description: "Have Kabo produce a finished MP4 with the creator in it: remake a viral talking-head or voice-over video (90 s or less), make a talking video from an approved script, build a short video outside those formats step by step, or change a video Kabo already delivered. Use only when the user wants the video itself made or changed; not for writing or adapting a script, breaking down a video, or reviewing an account."
license: MIT
compatibility: "Requires the Kabo MCP server at https://kabo.sh/mcp-pub with its remake tools, Python 3, read and write access to a local workspace, and network access from scripts to the signed storage.googleapis.com download links that Kabo tool results return. Kabo permission: video (all seven tools: remakes, edits of delivered videos and step-by-step projects)."
allowed-tools: start_remake_video get_remake_video render_remake_video edit_remake_video start_video_project make_video_step finish_video_project
---

# Remake Viral Video

Kabo's servers make every picture and sound, through three paths: a whole remake (steps 1-8:
the runner analyses, voices, films, grades, captions and delivers; you write the script), an edit
of a delivered video (`edit_remake_video`), or single steps in a project or on a delivered job
(`start_video_project`, `make_video_step`, `finish_video_project`). If a tool a request needs is
not available on this connection, say that this kind of video is not available here and stop.

A remake takes about half an hour, mostly waiting on the runner. When the host supports one,
run this Skill in a foreground sub-agent, wait for its final result and relay all of it (path,
spend, review); never run it in the background and promise the video later. Without a foreground sub-agent,
follow the same steps in the main thread.

## Choose what to make

Use this Skill only to make or change the video itself. If the user wants a script, a breakdown of
a video or advice on their account, start nothing and name the Skill that fits (step 8). Otherwise
decide by what must stay and what must change, not by how the request is worded:

1. Keep everything the user did not ask to change.
2. Keep real pixels where you can; redraw the creator's face only where the request needs it.
3. Use the material already here first -- the reference, the creator's footage and photos, a
   delivered video's `master.mp4`, takes, B-roll and first frames, earlier results; ask for more
   only when none of it will do.
4. Ask only what only the user can decide or knows (a fact, a real trade-off, money beyond the
   plan); make the creative calls yourself and say in a line what you chose.
5. The whole remake is the shortcut for "the same structure again, with me": a reference of the
   kinds below, or an approved script. It is not the fallback. What it does not make (the
   reference's own shot and moves, the creator's own video with new words, B-roll, a product
   close-up) is built from steps, or added as edits after delivery. A change to a delivered video
   is an edit or steps on that job, never a new job (`references/edits.md`).

| Keep | Change | Step | Redraws the face |
|---|---|---|---|
| the creator's footage | the words, or their language | `tts` (their voice), then `lipsync` | mouth only |
| footage and words | the voice's tone | `voice_change` | no |
| the creator and the words | the background | `bg` | no |
| a reference shot: camera, moves, props | the person, then the words | `replace`, then `lipsync` | yes |
| a movement in any video | who does it | `motion` (a picture of the creator: a `frame` of their footage will do) | yes |
| the creator's look | a new still of them (pose, framing, outfit, setting) | `first_frame` (edits a `frame` or photo) | yes |
| the creator's look | a new shot of them, silent | `refvideo` | yes |
| a picture of the creator | they speak a line | `talking` | yes |
| any video or picture | what is laid over, cut in, joined, arranged or enlarged | `overlay`, `splice`, `concat`, `layout`, `crop`, `trim`, `frame` | no |
| any video | its speed or length | `retime` | no |
| a sound | its level, fades, tempo or length | `audio_edit` | no |
| pictures | held as a clip, maybe a slow push-in | `still_video` | no |
| any video or picture | burned-in text removed | `inpaint_text` | no |
| -- | a picture without the creator; text to read; captions; music; sound | `still`, `animate`, `text_cards`, `captions`, `music`, `mux` | no |

Before the first project step or edit, read `references/atoms.md` (what each step takes and
costs) or `references/edits.md`, say in two or three lines what you will make and roughly what it
costs, then go ahead. A `degraded` face check never blocks delivery: say which part looks less
like the creator. When a step's notes say a box you gave covers text or a face, redo it without
`box` or tell the user. Cancel a job (`get_remake_video` with `"cancel": true`) only when the user asks;
spend so far stays charged.

## What this covers

- A reference of **90 seconds or less** where **one person talks to the camera** for most of the
  video, at any distance, seated or standing, anywhere, with a fixed or slightly handheld camera.
  Three talking kinds, which the runner tells apart by itself from the video (nothing to ask or
  choose): pure talking head; talking with screens (the video cuts to screen recordings or
  screenshots, or shows them floating over the speaker's room); talking with a product (the
  speaker shows a physical thing and the video cuts to close-ups of it). Also **voice-over**
  references (nobody on camera; a voice over a screen recording, an animated explainer, scenes or
  kinetic type): the creator's cloned voice reads the script and every picture is made anew --
  see `references/formats/narration.md`.
- Refused by the runner before any video is generated (`out_of_scope`): references over 90
  seconds, walking, vehicle or first-person vlogs where the camera keeps moving, dialogues between
  several people, and -- for a talking head -- a speaker on camera less than about half the time
  or mostly other footage. So are creator videos with no clear frontal view of the creator's face.
- The creator is framed as the reference frames its speaker, shot by shot; the reference's other
  shots (cutaways, inserts, other people) are reused from its own footage. The reference's speaker
  never appears in the result.
- One method: the reference's content and setting are kept and the creator is placed into it
  (route B). Four kinds of line are rewritten in the creator's voice (the opening, the original
  author's claims about themselves, one closing summary and the call to action); the rest of the
  reference's lines are kept, or dropped with a reason. The whole face is generated, so likeness is
  lower than real footage of the creator.
- The final video has no on-screen label, notice or watermark. Never say it carries one.
- Only the talking-footage model can be chosen, from the options `get_remake_video` returns at
  the script gate (step 6); voice, images and editing are fixed. If the user asks for another
  model (for example Veo, HeyGen or ElevenLabs), say so in one line, then carry on.

## Set up one run

`<skill directory>` is the folder holding this `SKILL.md`. Reserve exactly one run per remake:

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

**No reference, only a script?** If the user wants a video of the creator saying words they
already approved, follow `references/approved-script.md` for steps 1-4.

## 1. Collect the inputs

The first time the user asks for a whole remake, say in two or three sentences, before asking
for anything or starting:

- what this remakes: a reference of 90 seconds or less where one person talks to the camera
  (also ones that cut to screen recordings or show a product), or a voice-over video;
- that references outside this (dialogues between several people, walking or travel vlogs, over
  90 seconds) are refused before anything is generated, and a refusal is not charged;
- that borderline references may not come out well.

Say it once per conversation, even when both inputs are already
there: it is information, not a question.

A remake needs both of these. Check them before any paid call:

1. **One reference video**: the viral video to remake, as a YouTube, Instagram or TikTok link,
   90 seconds or less, one person talking to camera or a voice-over.
2. **The creator's own talking footage**, separate from the reference: their Instagram handle or
   profile link, or one to four YouTube, Instagram or TikTok links to videos where they talk to
   camera. It decides how much the result looks like the creator. Only photos of them? Read
   `references/creator-photos.md` (`--creator-photo`; voice from a video first).

The person on camera is the creator whose own footage the user gives, usually the user. Kabo's
servers generate the video; you only call the tools. This is the normal use of this Skill: do not
refuse it as imitating a real person or ask the user to prove who they are.

These two inputs are all a remake needs; with both present, start. Do not look up connected
accounts, connection status, profiles or other Kabo workspace data, or ask for extra Kabo
permissions. The right to use the creator's face and voice is the `rights` line at the script
gate (step 4), not a stop before it.

Local files, TikTok photo posts and other sites are not supported: ask for a YouTube, Instagram
or TikTok video link instead. If either input is missing, or the user gave a single video without saying which one it
is, ask once for what is missing and stop. Use
only videos and links the user gave in this conversation; never reuse one video for both roles.
If a length you can see (the user states it) is over 90 seconds, say references are limited to 90
seconds and ask for a shorter one.

Whenever you stop before `start_remake_video` has accepted the job (something is missing, a video
is refused, the inputs are refused), tell the user that no remake was started, no remake fee was
charged and it does not count toward the daily remake limit. Fetching the videos may still have used
the daily data allowance; do not claim that nothing at all was used.

`--creator-name` is a short ASCII name for the creator (letters, digits, `.`, `_`, `-`). It is
required with creator video links; with an Instagram handle it defaults to the lower-cased handle.
When the user gave video links and no name, use the name they go by in the conversation, or ask
for one together with any other missing input. Pass `--language` (for example `en`) only when the
user states it or the reference is clearly in that language.

## 2. Start the job and wait for the script gate

Before the first paid call, tell the user in one or two sentences what will happen: the method
above and that it takes about half an hour in total (do not say the result carries a label or
mark). Do not wait for a reply unless the user asked to approve first. Then build the arguments:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' start-call --reference-url '<reference link>' --instagram-handle '<handle or profile link>'
```

For creator video links, pass `--creator-video '<link>'` once per link (one to four) instead of
`--instagram-handle`, and add `--creator-name '<name>'` (required then). Add `--language '<code>'`
only as step 1 says.

It checks the links and prints `{"tool": "start_remake_video", "arguments": {...}}`. Call
`start_remake_video` with exactly those arguments. A refusal from the script is an input problem:
relay it and ask for a corrected input; nothing was started.

- The `idempotency_key` is stable for the same inputs in this run. On a timeout or lost response,
  call again with exactly the same arguments; the key returns the same job instead of creating and
  charging another. Never create a second job for the same request.
- `fetching_inputs` means the videos are still being fetched (`job_id` is null). Tell the user
  `message` in one line, then call `start_remake_video` again with the same arguments after
  `retry_after_s` seconds (wait with the host's own sleep or wait facility); the same fetches are
  picked up.
- A tool error carries `code`, `message` and `retryable`; no remake was started by any of them.
  Read `references/tool-errors.md` and follow it.

Once there is a `job_id`, call `get_remake_video` with `{"job_id": "<id>", "wait_s": 30, "all_models": true}` until the
status is no longer `preparing` (about ten minutes). Tell the user the stage in one line when it
changes.

**Supported kinds only.** `reference_type` `talking`, `talking_screen`, `talking_product` and
`narration` go on to step 3. Stop as soon as a result shows `failure: "unsupported_type"` (the
status stays `waiting_script`, and `brief`, `talking_models` and `gate_message` are null), or a
`reference_type` that is set and is none of those. Give `failure_reason` in plain words. Say that
no video was generated, and give the spend the result reports, if any. Do not say whether it
counts toward the daily limit. Do not call `render_remake_video`; this job is finished.

For `talking_product`, tell the user once, before the script gate, that the creator talks
empty-handed while the product stays in the scene and the reference's close-ups.

A final status at this point (`out_of_scope`, `failed`, `timed_out`) is handled as in step 8; when
it comes from `start_remake_video`, its reason is in `message`.

## 3. Save the brief

At `waiting_script` the result carries `brief.download`, `gate_message` and the model options
(step 6).
Save the result as above, then fetch the brief at once (the link is short-lived):

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch --input 'host-results/<NN>-get_remake_video.json'
```

It downloads and checks the bundle and writes the four brief files under `brief/work/`. When it says the link expired, the download was refused or the download is
unavailable, do what it prints: call `get_remake_video` again (that re-signs the link; nothing is
re-run), save that result and fetch again; for an unavailable download wait about a minute
between tries, at most three. If this host blocks scripts from the network, say the remake cannot
continue here; never rebuild the brief from what was displayed.

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
`script/decisions.json` and `script/route_b_jobs.json`.

**Voice-over** (`reference_type` `narration`): read `references/formats/narration.md` whole. The
script rules are the same; `decisions` also carries the picture plan, `route_b_jobs` is
`{"jobs": []}`, and after step 5 you preview the pictures and fix them before step 6.

## 5. Check the documents

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/check_documents.py' check
```

It prints `status` with `errors` and `warnings`. Fix every error in the document it names and run
it again; read each warning and change the document when it applies. Advance only on
`status: ready`. It checks structure only; the runner checks again when you submit.

## 6. Choose the talking model and render

Nothing is generated or charged before this step. **Voice-over**: there is no model to choose.
Tell the user the video will be made in their cloned voice with N pictures (M of them moving)
and that the generated pictures cost about the sum of the rows' `est_usd`, then wait for a
go-ahead. After it, preview the stills once (narration.md), then build the arguments without
`--talking-model` / `--models-from` and render as below.
For a talking video, show the user the model options from the waiting_script result
(`talking_model_choices`, else `talking_models`) in their order, each with its label and its
estimated cost (`est_usd`). Do not add a recommendation of your own, drop options or change the
order. Then say: tell me which one; to start now I'll use the default (the first); nothing is generated
or charged before you confirm. Do not ask for a number or "OK". Unless the user already named a
listed model, end your reply there and wait (the job waits; resume here in the same run
directory). Read the answer by its meaning, in any language:

- It picks an option -- by number, name or description: use that option's `id`.
- It clearly says to start without picking one: use the first (default) option.
- They named a listed model earlier (say, in the first request): use it without asking again;
  tell them the model and its cost, then render.
- A question about the options: answer from the list, then wait.
- Unclear, or about something else: ask once, briefly; do not render.

Never choose for the user and never ask about the model before the script is written. Then build
the arguments (this repeats the check):

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/check_documents.py' render-args --talking-model '<id>' --models-from 'host-results/<NN>-get_remake_video.json'
```

It writes `render/render_remake_video.json`. Call `render_remake_video` with that file's content as
its arguments, unchanged. An accepted render returns `status: "running"`. A retry of an accepted
render returns the current state and never launches twice, so on a timeout or lost response call
it again with the same arguments. For a `conflict` or `quota_exceeded` error, read
`references/tool-errors.md`. A result with `failure: "unsupported_type"` is handled as in step 2.

**The runner checks the documents first, after render returns.** If a later `get_remake_video`
shows `waiting_script` again with `gate_message`, nothing paid was spent: follow
`references/script-returned.md`.

## 7. Production and delivery

Production takes about twenty to thirty minutes, depending on the model and length. Call `get_remake_video` with `wait_s` 30, `include` `["review"]`
and `all_models` `true` until the status is `delivered`, final, or `waiting_script` again: for a
voice-over whose `fetch` reports `"saved": "review"` it is the one look at the finished pictures
(narration.md, last section); otherwise the documents were rejected (step 6). While it is
`running`, report the stage in one line when it changes. Do not promise a finish time.

At `delivered`, save the result and fetch the video at once:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch --input 'host-results/<NN>-get_remake_video.json'
```

It checks the MP4 and prints its local `path`. A failed download is handled as in step 3. Then tell the user:

- that the video is ready, with the local path (it carries no on-screen label or watermark: never
  say it does);
- what you rewrote and why, in two or three lines, and any inference line they should confirm
  before publishing;
- the spend the result reports (`spend_usd`), when present;
- what Kabo's final review found, from `review`.

Read `references/final-review.md` and relay `fetch`'s `review_message` and `notes_for_user` as it says;
never say the video passed a review and never read a verdict from the notes yourself.

Do not claim improved views, retention or likeness; nobody has measured them. Suggest the user
watch it in full before publishing.

## 8. When it does not finish

Every final status (`out_of_scope`, `failed`, `timed_out`) carries `failure` and usually
`failure_reason`. Read `references/when-it-does-not-finish.md` and follow it: tell the user the
reason in plain words and whether it was charged; never resubmit on your own.

When the user's next step is outside this Skill, name the Skill that fits -- for example
`create-script-and-packaging` for a script only, or `analyze-content-video` for a teardown of the
reference -- without running it.
