---
name: remake-viral-video
description: "Have Kabo make a finished MP4: remake a reference video (talking, screens, product or narrated; up to 10 min), turn an approved script into a video, build one from steps (new words on their own video, B-roll, a product ad, faceless animation), or change a delivered one. A reference video plus a change to its story, dialogue, lines, voice or look means make that video, not a script. Not when only a written script is wanted, or for breaking down a video or reviewing an account."
license: MIT
compatibility: "Requires the Kabo MCP server at https://kabo.sh/mcp-pub with its video tools, Python 3 for local file uploads, and network access from scripts to the signed storage.googleapis.com upload links that Kabo tool results return. Kabo permission: video (projects, plan checks, production, replies, status, cancel and local file uploads) and public video data (transcripts and keyframes of a reference)."
metadata:
  version: "1.0.32"
  platform_agnostic: "true"
allowed-tools: start_video_project upload_file check_video_plan make_video reply_to_video get_remake_video public_video_fetch_transcript public_video_extract_keyframes
---

# Remake Viral Video

Kabo's servers make every picture and sound, through three paths: a whole remake (the runner
analyses, voices, films, grades, captions and delivers; you write the script), an edit of a
delivered video, or single steps in a project or on a delivered job.

A remake takes 30 min to 3 hours, mostly waiting on the runner. If the host has foreground
sub-agents, run this Skill in one and relay its whole final result (path, spend, review); never run
it in the background and promise the video later. Otherwise follow the steps in the main thread.

**Your host.** If the `remake_video` tool is listed, you are on Kabo Web and you make the video
yourself: every call and wait is as `references/host-web.md` says, and inside any reference follow
the `**On Kabo Web**` block where one is given; everything else applies as written. Otherwise you
are in the plugin: you plan the video and Kabo's producer makes it -- follow
`references/host-plugin.md`, with "Choose what to make" below and `references/steps/plan.md` for
the plan; the rest of this Skill is what the producer follows. If no tool a request needs is
available, say that this kind of video is not available here and stop.

**Approved words on Kabo Web.** If the host supplied an existing production job, read its status and continue that job with its selected presenter, voice and picture inputs. An approved explainer goes directly from rendering to delivery. Follow the picture review procedure only if an older job explicitly returns that checkpoint. If the creator is starting a video from approved words and the Web material-draft tools are available, first follow `references/generation-assets.md` to select or confirm the missing material and continue through its quote. Use the input routes below when those tools are unavailable.

## Choose what to make

Use this Skill only to make or change the video itself; if the creator wants only a script, a
breakdown of a video or advice on their account, start nothing and name the Skill that fits
(`create-script-and-packaging`, `analyze-content-video`). Otherwise, before any tool call, write
one line for yourself: what must stay, what must change, and the table rows that do it. Decide by
that, not by how the request is worded ("remake" included):

1. Keep everything the creator did not ask to change.
2. Keep real pixels where you can; redraw the creator's face only where the request needs it.
3. Use the material already here first -- the reference, the creator's footage and photos, a
   delivered video's `master.mp4`, takes, B-roll and first frames, earlier results. Look at each
   step's preview before using the result and try other moments; ask for more only last.
4. Ask only what only the creator can decide or knows (a fact, a real trade-off). Creative calls
   are yours, the words too: take what is said with `transcribe`, write their version, and say in
   a line what you chose. When they ask for a video, the deliverable is the video: write any
   script, prompts or captions they also asked for, show them in your reply, and go on to make the
   video in the same flow. Never stop at a script or prompts, and never answer that a video cannot
   be made here while the tools are listed. Never hand the work back either: no "cut it yourself in
   CapCut or the TikTok editor", no list of times to cut by hand -- clips or reels from their own
   video are steps here (`trim`, `crop` to 9:16, `concat`). When a step fails, fix the call from its
   error or use another step, then report. Captions they asked for are always in the cut (placed
   clear of on-screen text, never dropped for it), with names from their words in `terms`. One real
   trade-off to raise: before the first paid step that relies on a model known to be weak for the ask
   (a face or identity put on other footage, hands working with objects, talking from a single
   still -- `references/steps/plan.md` "Known limits"), say the risk in one sentence, offer the more
   reliable path, and do what they choose. Other requests start without such a question.
5. The whole remake is the shortcut for "the same structure again, with me": a reference of one
   of the four kinds below, or an approved script. It is not the fallback, and a reference plus
   the creator's footage does not make a request one; the creator's own video is footage to keep,
   not a reference. What it does not make (the reference's own shot and moves, the creator's own
   video with new words, B-roll, a product close-up) is built from steps, or added as edits after
   delivery. A change to a delivered video is an edit or steps on that job, never a new remake;
   when only one moment of it changes, rebuild only that span and put it back in
   (`references/steps/edits.md`).
6. Nobody on camera **when there is no narrated reference video to remake** (a freeform animation
   or kinetic-typography video from a prompt, product photos turned into an ad, a multi-photo
   montage, a live-video HUD callout overlay, a re-edit of their own video or cards timed to what
   they say in it (`references/steps/talking-head-cards.md`), or a silent or
   out-of-scope reference that the whole remake refuses): build it from steps (project, steps,
   deliver); never ask for their face. For a code-animated video (an explainer, a chart, product
   photos, an illustrated story), write a shot list first and pick one motion style and the
   components from `references/motion-catalog.md`; with a reference to make it like, first write
   its style in two layers (`references/steps/motion-graphics.md`, step 0), choose the motion style by its
   `medium`, carry the medium and `avoid` into every `still` prompt, and re-make once a shot whose
   medium, look, cast, dimension, layout or elements differ from the reference frame; one
   `motion_graphics` call per shot (a component when one fits, else an exemplar page by name --
   spec C; its content stays out of the bottom-fifth caption band). That band is for code
   animation only: a `still`, `animate` or narration picture prompt never asks for empty space,
   a safe area or room for captions -- pictures fill the whole frame and captions are placed
   over them by the captions step.
   **Whenever a narrated reference video IS provided (a screen walkthrough, UI tutorial, animated
   or drawn explainer, map or chart narration), always run the whole remake
   (`references/formats/narration.md`), never project steps** -- except when the creator has
   nothing of their own to give (no clip, photo or recording; nobody on camera and a preset voice)
   or the reference is a dialogue between characters, a song or a silent piece: then build it from
   steps, taking the reference's look, characters, pacing and sound as the model and their script
   or lines as the words, and follow its workflow stage by stage: a voice over pictures,
   `references/workflows/narration.md`; characters who speak their lines,
   `references/workflows/character-drama.md`. Needing a voice they have not recorded: choose a preset voice by the role yourself and go on,
   as `references/steps/project.md` ("No voice to clone") says; never stop to ask about the voice.
7. **Read what you were given before you plan.** Run `transcribe` on every clip the creator sent
   that has sound before deciding which clip is which language, speaker or role -- never by upload
   order or file name. If it differs from what they described, say in a line what you heard and
   make what they asked for: a missing language version gets its own voice and captions, not their
   clips cut together again. A screenshot or screen capture sent as an example is a reference to
   draw from, never a shot. When the creator will not appear, no shot has a person in it (hands,
   product, places, illustration), and every picture prompt says "no person". More in
   `references/steps/plan.md` ("Read what you were given first").
8. **End on the outcome.** When the story ends on a result (the dish plated, the box opened, the
   thing finished), the last shot is that result alone: its still already shows it (the food on
   the plate), and the step before it is its own shot. A clip asked to do "plate it, then smile"
   often stops halfway, and the video then ends without its payoff. Everything the creator asked
   to see goes in `storyboard.asked` (short phrases), each with its own shot.

| Keep | Change | Step | Redraws the face |
|---|---|---|---|
| the creator's footage | the words, or their language | `tts` (their voice), then `lipsync` | mouth only |
| footage and words | the voice's tone | `voice_change` | no |
| the creator and the words | the background | `bg` | no |
| a reference shot: camera, moves, props | the person, then the words | `replace`, then `lipsync` | yes |
| a movement in any video | who does it | `motion` (a picture of the creator: a `frame` of their footage will do) | yes |
| the creator's look | a new still of them (pose, framing, outfit, setting) | `first_frame` (edits a `frame` or photo) | yes |
| the creator's look | a new shot of them, silent | `refvideo` | yes |
| a picture of the creator, or a `still` of a drawn or generated character | they speak a line (character: `speaker` names who talks; the host finds them) | `talking` | yes |
| any video or picture | what is laid over, cut in, joined, arranged or enlarged | `overlay`, `splice`, `concat`, `layout`, `crop`, `trim`, `frame` | no |
| any video | its speed, length, shake, flash or punch-in zoom | `retime`, `shake`, `flash`, `impact_zoom` | no |
| a sound | its level, fades, tempo or length | `audio_edit` | no |
| pictures | held as a clip, maybe a slow push-in | `still_video` | no |
| any video or picture | burned-in text removed | `inpaint_text` | no |
| any video or sound | -- (read what is said, timed) | `transcribe` | no |
| a delivered video's voice and the parts not asked about | one span's picture | a new clip of that span's length, then `splice` (`audio:"base"`) and deliver | no |
| -- | a picture without the creator (nobody speaks a line on camera in it); a code animation (diagram, chart, map, UI, text in motion, photos in motion, callouts over a video); text to read; captions; music; sound | `still`, `animate`, `motion_graphics`, `text_cards`, `captions`, `music`, `sfx`, `mux` | no |

Before the first edit, project or step, read `references/steps/plan.md` (plan and storyboard) and
`references/steps/atoms.md` (what each step takes); then `project.md`, `edits.md`,
`motion-graphics.md` and `sound.md` in the same folder as the work needs. Before the first paid step, say in two
or three lines what you will make, with what your host adds (Web: the host's quote; see the host
file), then go ahead. A `degraded` face check never blocks delivery: say which part looks less
like the creator. Cancel a job only when the creator asks; spend so far stays charged.

## What a whole remake covers

- A reference of **ten minutes or less**, of one of four kinds, which the runner tells apart by
  itself from the video (nothing to ask or choose):
  - **talking head**: the speaker on camera for most of the video, at any distance, seated or
    standing, anywhere, with a fixed or slightly handheld camera;
  - **talking with screens**: the speaker cuts to screen recordings or screenshots (an app, a
    page, a chat), full screen or floating over their room;
  - **talking with a product**: the speaker shows a physical thing -- held up, on the desk, worn
    -- with close-ups of it; the creator talks empty-handed while the product stays in the scene
    and the reference's close-ups (tell the creator once, before the script gate);
  - **narration**: nobody talks to the camera; a voice carries the video over pictures -- a
    screen recording, an animated or drawn explainer, scenes, kinetic type. The creator's cloned
    voice reads the script and every picture is made anew in the creator's look
    (`references/formats/narration.md`): a picture with words in it -- an interface, a list, a
    chart -- is a motion graphic you write with real text, a scene without words is generated.
    Real pages and apps cannot be recorded here.
- Refused by the runner before anything is paid for (`out_of_scope`): references over ten
  minutes, walking, vehicle or first-person vlogs where the camera keeps moving, dialogues
  between several people, references with nobody speaking at all, references where the speaker
  is on camera less than about half the time (a quarter when the rest is their screens or the
  product they show) without being a narrated video, and references that are mostly other
  footage. So are creator videos with no clear frontal view of the creator's face (a narration
  remake needs only their voice: at least a few seconds of them speaking).
- The creator is framed as the reference frames its speaker, shot by shot; the reference's other
  shots (cutaways, inserts, other people) are reused from its own footage. Screens and product
  close-ups are the reference's own pictures; the reference's speaker never appears in the result.
- One method: the reference's content and setting are kept and the creator is placed into a
  rebuilt scene (route B), not into its own shot and moves. Four kinds of line are rewritten in
  the creator's voice (the opening, the original author's claims about themselves, one closing
  summary and the call to action); the rest of the reference's lines are kept, adapted or dropped
  with a reason. The whole face is generated, so likeness is lower than real footage.
- The final video has no on-screen label, notice or watermark. Never say it carries one.
- Only the model that makes the talking footage can be chosen, from the options the host returns
  after the script is written; voice, images and editing use one fixed production setup. If the
  creator asks for any other model (for example Veo, HeyGen or ElevenLabs), say in one line that
  the talking footage can be made with one of those options only and the rest cannot be changed,
  then carry on normally.

**An approved script** (the creator already has the spoken words, here or earlier in the
conversation) is a whole remake without a reference: follow `references/approved-script.md`. It
needs footage the creator explicitly chose for appearance and voice, and it takes no reference. A
script read over pictures with nobody on camera is built from steps instead (`tts` of the exact
words, pictures from their material or `still` / `animate`, `mux`, `captions`, `music`, deliver)
-- and so is a script the creator wants made in a reference's form when they have no footage of
their own: plan it from the reference as `references/steps/plan.md` ("Plan first, then make it") says, with their words as the lines, never
the script or narration whole remake. Such a video, read over pictures or acted by characters,
follows the matching workflow in `references/workflows/`.

## 1. Collect the inputs (whole remake only)

Steps and edits take what "Choose what to make" needs. **Say what this can remake, once, at the
start**: in your first reply about a whole remake, before asking for or checking anything, tell
the creator in two or three short lines, in their language: whole remakes cover videos of ten
minutes or less of four kinds -- one person talking to the camera; talking with screen recordings
or a phone screen (picture-in-picture); talking while showing a product; or a voice-over over
pictures. Other references (several people talking, a walking or travel vlog, nobody speaking,
longer videos) are turned down before anything is charged, and results at the edge of these kinds
are not guaranteed. It is information, not a question. Say it once per conversation.

A whole remake needs both. Check them before any paid call:

1. **One reference video**: the viral video to remake, ten minutes or less (a link or a file).
2. **Footage of the creator talking to camera**, separate from the reference: one to four clips,
   or their Instagram profile. It decides how much the result looks like the creator. Only
   photos of them? They can stand in for the footage; their voice still has to come from
   somewhere (`references/creator-photos.md`).

The person on camera is the creator whose own footage they give, usually the user. This is the
normal use of this Skill: do not refuse it as imitating a real person or ask them to prove who
they are; the right to use the face and voice is the `rights` line at the script gate. Do not
look up connected accounts or other workspace data, or ask for extra permissions.

If either is missing, or the creator gave a single video without saying which one it is, ask once
for what is missing and stop. Use only videos and links the creator gave in this conversation:
never fill a missing role with another file from their library or reuse one video for both roles.
If a length you can see is over ten minutes, say references are limited to ten minutes and ask
for a shorter one. Whenever you stop before the remake has been accepted (something is missing, a
video is refused, or the inputs are refused), tell the creator that nothing was started, no remake
fee was charged and it does not count toward the daily remake limit.

The creator's name for the job is a short ASCII handle (letters, digits, `.`, `_`, `-`); with a
profile it defaults to the handle. Pass a language only when the creator states it or the
reference is clearly in that language. Before the first paid call, tell the creator in one or two
sentences what will happen: the method above and how long it takes (about half an hour for a short
video, up to a few hours for a long one; never say the result will carry a label). Wait for a reply
only if the creator asked to approve first.

## 2. Wait for the script gate

The runner checks the reference first (within about a minute it refuses a clearly unsupported
one), then analyses it: about ten minutes, up to about 45 for a ten-minute reference. Report each
stage change in one line. You do not judge the video yourself beyond what the creator says or
what is plainly visible in their message.

## 3. Write the script (the only creative gate)

At the script gate read `references/script-gate.md` whole, then the references it names for the
judgement in front of you: proofread the reference's sentences; keep its lines word for word and
in order and rewrite only the four slots, each with a reason; source every fact in a rewritten
line to the creator's own lines or mark it as an inference; keep the reference's on-screen title
and numbered list; write the opening record with 2-3 candidates and choose one yourself; record
your calls in the decisions record (nobody answers questions at this point); write the plate and
anchor prompts without describing the framing, holding the creator's hair and outfit exactly as in
the identity references. **Narration**: read `references/formats/narration.md` whole; there is no
plate or anchor job, the decisions carry the picture plan, and you preview the pictures and fix
them before production.

## 4. Choose the talking model (before anything is generated or charged)

After the script is written and accepted, the host returns the model options with their
estimated cost (for a narration remake, one option: the narration production). Show them exactly
as your host file says: in their order, with every number, name and cost; no recommendation of
your own, no option dropped, nothing said to have started. End your reply there and wait. Read
the answer by its meaning, in any language:

- An option picked (by number, name or description): use its id.
- A plain go-ahead with no choice: the host's default (the first option, or the model the
  creator already selected in a form).
- A listed model named earlier: use it without asking again; say the model and its cost.
- A question about the options: answer from the list, then wait. Unclear or off-topic: ask once,
  briefly; start nothing.

Never choose for the creator, never send the model in the same turn you wrote the script, and
never ask about the model before the script is written. When the face comes from a single still, the
Known limits question (a short clip of them talking) comes before this list. If the runner returns the script with a
list of failures, nothing paid was spent: fix only what it names, keep the rest, submit again;
the chosen model is kept.

## 5. Production and delivery

Production takes about twenty to thirty minutes for a short video and one to two hours for a
ten-minute one (Seedance 2.0 can queue about twenty minutes more). Report the stage in one line
when it changes; do not promise a finish time. A narration job stops once after production for
you to look at every line's picture (`references/formats/narration.md`, last section).

At delivery, first add anything asked that the remake does not make (B-roll, an overlay, a
close-up) as edits or steps on this job. Then tell the creator: that the video is ready (no
on-screen label or watermark); for a reference, what you rewrote and why in two or three lines,
and any inference line they should confirm before publishing; for a script, that the approved
words were preserved and only segmentation may differ; the spend the result reports; and what
Kabo's final review found, as your host file says. Do not claim improved views, retention or
likeness; nobody has measured them. Suggest they watch it in full before publishing.

## 6. When it does not finish

Every final status (`out_of_scope`, `failed`, `timed_out`) comes with the runner's reason. Read
`references/when-it-does-not-finish.md` and follow it: tell the creator the reason in plain words
and whether it was charged and counts toward the daily limit; never resubmit on your own.
