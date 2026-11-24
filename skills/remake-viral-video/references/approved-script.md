# Approved script: a talking video of the creator's own words

Read this when the creator already has the exact words they want to say: pasted here, or a
script written earlier in this conversation and approved (for example by
`create-script-and-packaging`). There is no reference video. Kabo makes a talking video of the
creator saying those words, using the creator's own footage for face and voice. This is the same
remake job as the reference path; only the inputs and the script gate differ, and the rest of
`SKILL.md` (waiting, the model choice, production, delivery, failures) applies unchanged. Use it
only when the creator asks for a video of a script and has footage of themselves for it; a request
to remake a video follows the reference path, and a script with no creator footage (read over
pictures, or to be made in a reference's form) is built from steps (`SKILL.md`, "An approved
script"). Never send a reference with `input_kind:"script"`.

## 1. Inputs

- **The approved spoken text**, exactly as the creator approved it. If more than one script could
  be meant, ask which one. Do not ask for a reference, portrait, topic, rewrite or language: the
  text sets the output language; never translate it to the footage's language.
- **The creator's own footage**: one to four clips of them talking to camera, or their Instagram
  profile. A script may have come from another video; that relationship never makes that video a
  required input or authorizes using its speaker's face or voice. The creator may explicitly
  choose that script's source video as their footage: then it goes in only as their footage,
  never as a reference. Do not operate the camera yourself or claim this tool can record; existing
  footage, a new upload and a recording uploaded by the product are equivalent sources.

**Nobody on camera.** Route by the video the creator asks for. When they want no face, this is not
a talking-video job: build it from steps (`steps/plan.md`) -- `tts` of the exact approved words
(the creator's voice from a recording of them speaking, or a preset voice chosen by the role), pictures
from their material or made with `still` / `animate`, `mux` the narration onto them, then
`captions` or `text_cards`, `music`, and deliver. Keep every word. Clips that plainly are not the
creator talking (nobody on camera, gameplay, scenery, a screen or hands-only tutorial) are not
creator footage: say what they show and offer that narrated version with them as pictures. This
holds for clips confirmed in a form too: the host binds which files the creator chose, not that
they show the creator talking. Send such clips as talking footage only when they may show the
creator talking, or when the creator still wants the talking version after you explained it.

If the host says script videos are not available (`script_video_unavailable`), tell the creator
nothing was started or charged and this input is not available yet. Stop; never substitute a
reference-video remake.

**On Kabo Web** (the `remake_video` tool is listed):

```
remake_video {request:{action:"prepare", input_kind:"script", idempotency_key:<stable UUID>, script:{text:<exact approved spoken text>}, creator_videos | creator_profile, creator_name?}}
```

Upload ids must be listed in this conversation, as for a reference remake (`host-web.md`). Reuse
the key and inputs on retries. Then wait as `host-web.md` says.

## 2. At the script gate: copy the drafts, do not write

The brief's `brief_input.json` has `input_kind` `script`; its `approved_script` is the source of
truth. Do not write the four documents yourself: copy the runner's drafts
(`script.draft.json` -> `script`, `opening_review.draft.json` -> `opening_review`,
`decisions.draft.json` -> `decisions`, `route_b/jobs.template.json` -> `route_b_jobs`),
preserving their receipt fields and SHA. Only where the lines break (segmentation) and each line's
performance direction may change. Never proofread, rewrite an opening or call to action, add
claims, translate or drop a word. The runner checks the words again before anything is generated.
The empty image-jobs document is expected: this mode has no reference scene or inherited inserts.

**On Kabo Web**: read the drafts from the brief (`work/...`) and pass them as the four start files,
with no model (`host-web.md`).

## 3. Model, production and delivery

Show the model options and wait for the creator's choice exactly as for a reference remake
(`SKILL.md` step 4); never preselect or skip the confirmation. At delivery, say the approved script
was used word for word and only the line breaks may differ; do not say you rewrote anything.
Anything else they asked for (B-roll, a close-up) is added before delivery. If the runner rejects
the text check, restore the exact approved text; never change
the words or the snapshot to pass. A change to the words is a new approved script and needs a new
job once the creator approves it.
