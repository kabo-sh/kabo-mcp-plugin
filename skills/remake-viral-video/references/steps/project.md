# A project: composing a new video from steps

A project is a workspace with the creator's material and any reference material, in which single
steps (`atoms.md`) are made one at a time and one result is delivered as the video. Plan it first
(`plan.md`). A delivered remake job can also take steps (for example a new shot to `clip` into
it); a change to a delivered video is an edit or steps on that job (`edits.md`), not a project.

## What goes into a project

0-4 of the creator's own videos, up to 8 of their photos, and optionally reference videos (a
dance to copy, an original to recast, a reference to reuse) and reference images (product shots,
a place, a background). The creator's own recordings -- a screen capture, a product or pet video,
anything they shot to appear in the new video -- are their videos, never reference videos: a
reference is only a video whose form is copied, and its footage is not delivered. The creator's
material becomes `creator/...` handles and is what every face step is checked against; reference
videos become `input/ref_NN.mp4`, reference images `input/img_NN.<ext>`. More material can be
added to a `ready` project later.

**Without the creator.** No face is needed; never ask for it. A project with no creator footage or
photos uses only steps that draw no face (`still`, `animate`, `motion_graphics`, `text_cards`,
`music`, `tts` with a preset voice, and editing); a face step is refused with
`no_creator`. Never present a generated person as the creator or as any real person.

**An invented AI presenter (`persona`).** Only when the creator has no footage or photos of
themselves at all and wants someone on screen: offer an invented presenter and, once they agree,
make one `persona` step first, for example
`{"op": "persona", "inputs": {}, "params": {"description": "an invented woman in her thirties, short dark hair, warm smile, casual denim shirt", "count": 3}}`.
It makes two to four portraits of the same invented person (`creator/persona_NN.png`); after that
the face steps work as usual and are checked against those pictures, and the voice is a preset
voice ("No voice to clone" below). `inputs.seed_images` may add up to four style pictures (handles of
pictures that show no real person, never `creator/...`). The project then reports `persona: true`.

- The persona is always fictional. Never describe, name or imitate a real, identifiable person (a
  celebrity, a public figure, someone the creator names, or the creator); refuse such a request
  and offer an invented person instead. No handles or links in the description.
- Never mix: a project with the creator's real footage or photos cannot get a persona, and a
  persona project cannot take creator footage later. When real footage exists, use it instead.
- At delivery, say plainly that the person on screen is an AI-generated fictional presenter.

**No voice to clone** (no creator material, or no speech in it, or a picture of anyone or
anything that should speak). `tts` reads lines in the creator's cloned voice by default; with
nothing to clone it is refused with `no_voice`. Never stop to ask about the voice. A voice the
creator named (a recording they sent, a preset number, "a calm male voice") is used as given.
Otherwise -- they said to use a preset, or said nothing about the voice -- choose the preset
yourself by the role: the narrator's or character's gender, age and tone, and the reference's
voice when there is one (a story told calmly: a calm, professional voice; an upbeat young host: a
young, energetic or bright one). Pass it as `tts` `voice` (or the character's card `voice`), say
in one line which voice you chose and that a 10-30 s recording of theirs or another preset switches
it, and go on in the same reply. Say at delivery that a preset voice was used.

## The face

Steps that draw the creator's face (`refvideo`, `motion`, `replace`, `lipsync`, `talking`,
`first_frame`) are measured against the creator's own material automatically; the result carries
`face: {verdict, median, p10}` (`pass` or `degraded`).

- Draw the face as few times as possible: every generation moves it further from the creator.
  Prefer steps that keep real pixels (`lipsync` on real footage over `talking` from a still, `bg`
  over drawing the creator into a new scene) over drawing the person again, and chain two face
  steps only when the chain is the point (`replace` then `lipsync`); look at the result after each.
- `degraded` does not stop anything: keep the result, try another approach (or another listed
  model) once if a better one exists, keep the better take, and tell the creator plainly at
  delivery which part looks less like them.
- When the provider refuses an input, the runner tries the step's fallback model once by itself
  (`fallback_from` in the result); mention it when you report the step. If it is refused again,
  say so and suggest other material.
- In a project without the creator's material, steps that draw the creator are refused; ask for
  their footage, or offer a fictional persona only if they want one. Never put a real person who
  is not the creator into the result, and never reuse a reference's speaker on screen. `still`
  and `animate` must not show the creator (that would be a face step without the check).

## Status, limits and errors

While a step runs the project reads `working`; when it can take the next step, `ready` (it can
also be `delivered`, `failed` or `cancelled`). `last_step` carries the last step's outcome
(`spend_usd`, `model`, `fallback_from`, `face`, `error`); an image or video result also comes with
a small preview (four frames of a video) to look at before using it.

- `quota_exceeded` that says another remake or step is still running: not a limit; wait for it,
  then send again with the same key.
- Any other `quota_exceeded`: a daily limit or the spending safety stop was hit -- nothing was
  called; tell the creator. Do not split the step to get around it.
- `workspace_expired`: a workspace is kept for 14 days; offer to start again.
- `no_creator`: a face step in a project without the creator. `no_voice`: nothing to clone (above).
  A `persona` refused because the project has creator material: use that material instead.
- A step that ends `failed`: relay its error in plain words and the spend, if any; try another
  listed model once if it was a refusal or a provider failure, otherwise stop and ask the creator.

## Delivering

Deliver makes a handle the project's video. Tell the creator what you made (step by step, in two
or three lines), the total spend the status reports, every `degraded` face check or step that fell
short, any fallback model or preset voice used, and for a persona that the presenter is an
AI-generated fictional person. A degraded result is delivered with that said, never hidden. Do not
claim views, retention or likeness that nobody measured.

## Host mechanics

**On Kabo Web** (the `remake_video` tool is listed):

```
remake_video {request:{action:"project", idempotency_key, creator_videos:[...], creator_name, creator_photos?:[...]}}
remake_video {request:{action:"add_inputs", job_id, idempotency_key, ...}}
remake_video {request:{action:"atom", job_id, idempotency_key, op, inputs:{...handles...}, params:{...}}}
remake_video {request:{action:"deliver", job_id, idempotency_key, handle:"aNN.mp4"}}
```

Read the project with `status` and the `job_id`; every `atom` returns a new handle. The preset
voices are the ones the host lists (`tts` `voice` takes its id). `deliver` saves the video like a
remake's final video and shows it as a file card.

**Links.** When the creator gives a link to a video for steps (their own reel to re-edit, a reel
whose pictures should change, a clip to follow), fetch it yourself before asking for a file:
run the host's data connector `creator-remake-materials`, operation `prepare`, with
`params:{url:<the link exactly as given>, include_source_video:true}` (no other params), follow
its job until it finishes, and pass its `source_video` material as
`{kind:"material", job_id, index}` in `project` or `add_inputs` (as the creator's video when it
is theirs, otherwise as a reference video). Ask for an upload only when that fetch fails, and
then say the link could not be fetched.
