# Projects: building a video step by step

A whole remake (steps 1-8 of `SKILL.md`) is the tested path for a talking, talking-with-screens,
talking-with-product or voice-over reference, and it stays the default for those. A project is the
same kinds of steps one at a time, for a new video those formats do not cover. Kabo runs every
step on its servers; you decide what to make, in what order and with which words, and call the
tools. Never draw, record or assemble a picture yourself.

Tools: `start_video_project`, `make_video_step`, `finish_video_project`, and `get_remake_video` to
read the project (its `handles`, `last_step` and status).

## When to build a project

Build one only when the request is a new video outside the remake formats, for example:

- the creator doing the moves of a video (a dance, a workout, a trend);
- the creator doing something without speaking, under long text cards and music;
- a short product ad made from stills and the creator's footage;
- the creator's own footage placed somewhere else, or with new words.

A request that fits a remake format is remade whole even when parts could be built step by step. A
change to a video that was already delivered is an edit (`references/edits.md`), not a project.

## Pick the step by what must stay and what must change

| The request | Step (`op`) | Why |
|---|---|---|
| The creator's own footage saying other words | `tts` for the new line in the creator's cloned voice, then `lipsync` (video + that audio) | real pixels, new mouth |
| The creator's own footage somewhere else | `still` for the background plate (no person in it), then `bg` (video + plate) | real pixels, new background |
| The creator doing the moves of a video | `motion` (a picture of the creator + the movement video) | the movement comes from the video, the person from the picture; likeness is modest. Default model draws full-body motion; `fal-ai/kling-video/v3/pro/motion-control` keeps the face better but keeps the picture's framing, so it needs a standing full-body picture |
| A new shot of the creator doing something without speaking (a reaction, a scene with props) | `refvideo` (1-10 pictures + what happens in words; optionally `ref_video` to follow a motion) | the model draws the shot from the pictures; it is checked against the creator |
| A still of the creator speaking a line | `tts`, then `talking` (picture + line audio) | a talking take from one picture |
| A reference shot frame for frame with the creator in it | `replace` (shot + picture of the creator), then `lipsync` for the creator's words | keeps the shot, props and gestures; the words stay the original's until `lipsync`. Small moving text can garble |
| B-roll, a scene, a product shot (no creator) | `still`, then `animate` to move it | no face is drawn |
| Words that must be read on screen | `text_cards` on a base video | real text; never ask a generated picture to contain words |
| Background music | `music` with a mood | from Kabo's royalty-free library; if the step says it is not available, leave music out and say so |
| Captions in the creator's style | `captions` | |
| A picture laid over a time range, a clip spliced in, clips joined | `overlay`, `splice`, `concat` | |
| A still from a video (to use as a picture, or to look at a moment) | `frame` | cheap; also how you see a video |

Pictures of the creator come from the creator's own videos: take them with `frame` at moments where
the face is clear and frontal (and, for `motion`, the whole body when there is such a moment). This
version cannot take photos or files from the user's computer, and a project holds only the
creator's own videos: if the request needs another video (for example a dance to copy that is not
in the creator's footage), say that it cannot be added in this version and offer what can be made
from the creator's footage instead. Never use the creator's footage as the movement source when
the user asked for someone else's moves.

## Rules for the face

- `refvideo`, `motion`, `replace`, `lipsync` and `talking` redraw the creator's face. Kabo checks
  each one against the creator's own footage and reports `face.verdict` `pass` or `degraded`.
- Redraw the face as few times as possible: every pass moves it further from the creator. Prefer
  steps that keep real pixels (`lipsync` on the creator's real footage over `talking` from a still;
  `bg` over drawing the creator into a new scene). Chain two face steps only when the chain is the
  point (`replace` then `lipsync`), and look at the result after each.
- A provider refusal is retried once on Kabo's side with another tested model; the result names it
  in `fallback_from`. Mention it when you report the step.
- A `degraded` result is kept, never a reason to stop. You may try the step once more with another
  listed model (new `--attempt`, or a `model` param); keep the better take and say in the delivery
  what fell short.
- Never put anyone other than the creator on screen, and never the speaker of a reference video.
  `still` and `animate` must not show the creator (that would be a face step without the check).

## Plan before spending

Before the first paid step, write `project/plan.json` in the run directory and tell the user in two
or three lines what you will make, which steps, and roughly what it costs. Wait for a go-ahead
unless the user already asked you to go ahead.

```json
{"goal": "one line: what the user asked for",
 "steps": [{"op": "frame", "why": "a clear picture of the creator", "est_usd": 0},
           {"op": "motion", "why": "the creator does the moves", "est_usd": 4.0}],
 "est_usd_total": 4.0}
```

Rough provider prices per second of output, for the estimate only (the result's `spend_usd` is
what is charged): `motion` about $0.17-0.40, `refvideo` about $0.20-0.24, `replace` about $0.30,
`lipsync` about $0.08 (or about $0.20 per call up to 40 s with `fal-ai/latentsync`), `talking` from
under $0.01 to about $0.30 depending on the model. `still` is a few cents per picture; `tts`,
`frame`, `bg`, `overlay`, `splice`, `concat`, `text_cards`, `music`, `captions` and `face_check`
cost little or nothing. A project has a budget (about $20); a step that would go over it is
refused with `quota_exceeded` before anything is generated.

## Run it

Use one run directory as in `SKILL.md` ("Set up one run"). Every command below starts with
`cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py'`,
written here as `static_host.py`.

1. **Start the project** with the creator's own footage (the same inputs as a remake):
   `static_host.py project-call --instagram-handle '<handle>'` (or `--creator-video '<link>'` one to
   four times with `--creator-name '<name>'`). Call `start_video_project` with exactly the printed
   arguments. `fetching_inputs` is handled as in `SKILL.md` step 2. Then call `get_remake_video`
   with `{"job_id": "<id>", "wait_s": 30}` until the status is `ready`. Its `handles` lists the
   files you can use (`creator/...` are the creator's videos).
   A delivered remake's `job_id` can be used as a project directly; its handles include
   `final.mp4`, each talking take `take_sNN.mp4` and each voiced line `line_NN.wav`.
2. **One step at a time.** Write the step as `project/steps/<NN>-<op>.json`:

   ```json
   {"op": "frame", "inputs": {"video": "creator/clip1.mp4"}, "params": {"t": 2.5}}
   ```

   Then `static_host.py step-call --job-id '<id>' --step 'project/steps/<NN>-<op>.json'`. It checks
   the step against the op's inputs and params and prints the `make_video_step` arguments; call the
   tool with exactly those. A refusal from the script is your mistake in the step file: fix it.
   Inputs are handles only, never paths or links.
3. **Wait and look.** `make_video_step` returns `working`. Call `get_remake_video` with `wait_s` 30
   until `last_step.status` is `done` or `failed` (the project is `ready` again). Save the result to
   `host-results/<NN>-get_remake_video.json` and run
   `static_host.py fetch-step --input 'host-results/<NN>-get_remake_video.json'`. It saves the
   step's file under `project/outputs/` and prints its `path`, handle, spend, model, fallback and
   face verdict. Open pictures with the host's own image viewer. You cannot watch a video: take a
   `frame` or two of it at the moments that matter and look at those.
4. **Same step again.** The idempotency key is stable for the same step file: a retry after a
   timeout returns the same result and is not charged twice. To make a new take of the same step on
   purpose, add `--attempt 2` (then 3, ...). A `conflict` error means the key was used with other
   arguments: use the next `--attempt`.
5. **Finish.** `static_host.py finish-call --job-id '<id>' --handle '<aNN.mp4>'`, call
   `finish_video_project` with the printed arguments, poll `get_remake_video` until `delivered`,
   save the result and run `static_host.py fetch --input 'host-results/<NN>-get_remake_video.json'`
   for the local path.

## Errors

Errors from `start_video_project` are read as in `references/tool-errors.md`.

- `validation_error`: read `message`. With `details.reason` `workspace_expired`, the job's working
  files are gone (they are kept 14 days); say so and offer a new project.
- `quota_exceeded`: the step would go over the project's budget or a daily limit; nothing was
  generated. Tell the user; do not split the step to get around it.
- A step that ends `failed`: relay `error` in plain words and the spend, if any; try another listed
  model once if the error is a refusal or a provider failure, otherwise stop and ask the user.
- Never call a step again in a tight loop; wait at least half a minute between status calls.

## Delivering

Tell the user: the local path; what was made, step by step, in two or three lines; the total spend
(`spend_usd` of the job, or the sum of the steps); each face verdict, and in plain words which part
looks less like the creator when a step was `degraded`; any fallback model used. A degraded face
check never blocks delivery. Do not claim views, retention or likeness that nobody measured, and
suggest the user watch it in full before publishing.
