# Changing a delivered video

An edit changes a video already delivered (a remake, an approved-script video, or a finished
project). Only the parts named are redone and the result is saved as a new version of the same
job; earlier versions stay listed (`final_rN.mp4`). Change the smallest part that answers the
request, never remake the whole video for a local change, and never start a new remake or project
for it. Plan as in `plan.md` ("Plan first, then make it"): say exactly what will change and what
stays the same, then go ahead.

## What maps to what

| The creator asks | Edit |
|---|---|
| Other words in a line (a remake or an approved-script video; a project has no script) | `{kind:"lines", lines:[{row, text}]}` -- `row` is the line's index (from 0) in the delivered script's `lines` (in the job's status). The lines are re-voiced in the creator's voice, only the changed span is lip-synced, other takes are reused, and the captions are re-timed. |
| Caption colour or size | `{kind:"captions", color?, size?}` -- colour is a name (white, yellow, red, ...) or `#RRGGBB`; size a multiple of the default (0.5-2). |
| A picture, screen or product shot over a moment | `{kind:"overlay", t0, t1, media, box?:[x, y, w]}` -- make or choose the media first (an `aNN` image or clip, or a creator photo); box is fractions of the frame. |
| Another background for a stretch | first a `still` for the plate (a place, no person), then `{kind:"background", t0, t1, plate}` -- the creator's own pixels are kept, so likeness does not change. |
| Another clip over a stretch (B-roll, a reaction) | make it first (`still` + `animate`, or `refvideo`), then `{kind:"clip", t0, t1, clip}` -- the clip comes from an earlier step; the cut keeps its sound and length. |

Times are seconds from the start of the delivered video. Up to ten edits go in one request. Line
changes are applied first, the rest in your order. The captions are re-drawn in the cut's own
style. A line change re-times the cut: picture changes made in an earlier edit are not carried
over, and the result's `notes` say so -- apply them again in the same request after the line
change. Words that must be read on screen go in an overlay made with `text_cards`, never into a
generated picture.

**Where new pictures and clips come from.** Make them with steps on the delivered job's own
`job_id` (`atoms.md`) and use the handle they return. Look first at what the job already has: a
`frame` or `crop` of `master.mp4`, its takes, B-roll and first frames, the creator's footage or
the reference (a product close-up is often already in it). Look at each `frame` or `crop` before
using it and try other moments; ask for a picture only last.

**Finding the time range.** The job's status lists the delivered video's `lines` with `row`,
`text`, `t0` and `t1`. When the creator names a moment by its words, take that line's `t0` and
`t1`; for "the second half" and the like, use the length of `final.mp4`. Take a `frame` at the
second you chose and look at it before an edit when the moment is not obvious.

**One moment of a delivered project** (an edit is for remake jobs only): change only that span.
Find its `t0` / `t1` (the `tts` timing in earlier `notes`, or your shot list), make a new clip of
length (t1 minus t0) with the step that made it, `splice` it into the current cut
(`inputs:{base:"final.mp4", clip:"aNN.mp4"}`, `params:{t0, t1, audio:"base"}`) and deliver the
result. The voice and the other parts stay as they were; a later tweak to the same span works the
same way on the new cut. Captions are burned into the picture, so a span spliced into a captioned
cut has none: when the delivered video has captions, splice into the cut you captioned (the step
before `captions`) and run `captions` again on the result. Say the captions are unchanged only
when they are.

## Telling the creator

What changed, in one or two lines; whether anything outside the request changed (from the
result's `notes`); the spend the result reports; and the face verdict when a line was re-synced.
A `degraded` face check does not stop delivery: say in plain words which part looks less like the
creator. The earlier version is kept.

## Errors

- `workspace_expired`: the job's working files are kept 14 days and are gone; the video cannot
  be edited any more. Say so and offer a new video.
- Any other validation error: read it (a time range past the end of the video, a handle that
  does not exist), fix the edits and send again.
- `quota_exceeded`: if it says another remake or step is still running, wait for it and send again
  with the same key; otherwise a daily limit or the spending safety stop was hit; nothing was
  changed. Tell the creator.
- A failed edit: relay its error in plain words; the delivered video is unchanged.

## Host mechanics

**On Kabo Web** (the `remake_video` tool is listed):

```
remake_video {request:{action:"edit", job_id, idempotency_key, edits:[ ... up to 10 ... ]}}
```

Steps on the delivered job are `atom` calls on its `job_id` (`project.md`). The host shows the
new version as a file card.

**In the plugin** (this Skill's scripts): use the run directory of the delivered video. Write the
edits as a JSON list to `project/edits/<NN>.json`:

```json
[{"kind": "lines", "lines": [{"row": 3, "text": "the new words for that line"}]},
 {"kind": "captions", "color": "yellow"}]
```

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' edit-call --job-id '<job id>' --edits 'project/edits/<NN>.json'
```

It checks each edit and prints the `edit_remake_video` arguments; call the tool with exactly those.
A refusal from the script is a mistake in the edits file: fix it. On a timeout or lost response,
call again with the same arguments (the key returns the same edit, not a second charge). For a new
edit after this one finished, write a new edits file; a `conflict` error means the key was used
with other arguments, so build again with `--attempt 2` (then 3, ...). A public picture link (a
product, a place) can be added to the job first with `project-call --job-id` and
`--reference-image` (`project.md`). A plain colour name for captions is turned into a fixed colour
by `edit-call`.

The call returns `working`. Call `get_remake_video` with `{"job_id": "<id>", "wait_s": 30,
"project": true, "include": ["review"]}` until `project.last_step.status` is `done` or `failed`.
Save the result and run:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' fetch-revision --input 'host-results/<NN>-get_remake_video.json'
```

It saves the newest revision as `output/remake-<id>-r<N>.mp4` next to the earlier one and prints
`revision_notes` (which parts were redone, whether anything outside them changed, the spend) and
`last_step` (spend, face verdict). Give the user the new local path; the spend of this edit is in
`last_step`, the total with every edit in `project.spend_usd`. Relay the final review as in
`../final-review.md`.
