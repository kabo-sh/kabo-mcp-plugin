# Plan a video made from steps

Which path and which steps follow "Choose what to make" in `SKILL.md`: keep what the creator did
not ask to change, keep real pixels, use the material already here, and keep the whole remake for
"the same structure again". This file is how a video made from steps is planned; what each step
takes is in `atoms.md`, code animation in `motion-graphics.md`, the project itself in
`project.md`, and changes to a delivered video in `edits.md` (all in this folder).

1. **A change to a delivered video**: an edit of that job, or steps on it. Never remake a whole
   video for a local change.
2. **Anything the whole remake does not make**: a **project** of single steps (start the project,
   make steps, deliver one result), or steps on a delivered job.

## Plan first, then make it

Before the first paid step of an edit or a project, tell the creator in two or three lines what
you will make and in which order, with what `SKILL.md` says your host adds before paying. Then go
ahead -- except in a video that follows a workflow in `../workflows/` (a narrated video or a
character drama built from steps): it stops for the creator where that workflow says, and only
there. What to make follows the storyboard, never the cost. Choose photos, moments, frames and words yourself from the material here (look at each
step's preview before using its result; if it is not clear, try another moment) and say what you
chose; ask only what only the creator can decide or knows.

For a video made like a reference, make the form the storyboard needs: one picture per shot,
motion where the reference moves, the voices and talking shots it has. Never merge shots, drop
rows, hold one picture over many lines or turn moving shots into still pictures; such a cut changes
what was agreed, so ask first.

Every request carries a new idempotency key (a UUID). Repeat the same key only to retry the same
request after an unknown outcome.

## Break the reference down first, then keep its form

Before the first paid step of any video made like a reference:

1. `frame` with `shots: true` on the reference: one contact sheet of all its shots with their
   time spans, and the shot count and cut times in the notes (which cuts are dissolves, and
   whether the picture sits in black bars). Look at it (and a `frame` or two
   up close) and write, shot by shot, what the picture is: the subject kind (a person in
   close-up, a statue, an object, a scene, a chart, a character), shot size, motion, any text
   on it; plus the sound (voice, music, effects) and captions.
2. Write its style (step 0 of `motion-graphics.md`: `medium`, `look`, `cast`, `avoid` ...) and
   pick the style card whose `medium` matches in `../motion-catalog.md`.
3. Keep the reference's form and take only the words and topic from the creator's script: the
   same kinds of subject in the same shot sizes (a reference that opens on a person's face opens
   on a person's face -- an invented one, or the person the script is about -- not on an object
   the line mentions; a line said on camera is framed at least `medium close-up`), about as many different pictures as it has shots (within a third; never
   one picture held under many lines), the same pace of cuts, the same caption kind, music when
   it has music. Characters, props or a setting the creator describes replace the reference's.
4. Every `still` / `animate` prompt carries the card's prompt words plus the medium, light and
   `avoid` (a game render is not photoreal CG or film; flat vector is not 3D). Make the first
   `still` and put it beside the reference's frame: a different medium, look or subject kind is
   re-made before the rest, which then go in batches.
5. Exact numbers, words or labels on things (a digit on each step, a sign) are drawn on top
   with `motion_graphics` or `text_cards` timed to the voice, never left to a generated picture.
   Take those times from `transcribe` of the voice as it sits in the cut (after joins, lead-in
   and `retime`), not from the voice clip on its own: a lead-in shifts every word.

## The plan: analysis and storyboard, saved before making

Plan first, as its own stage: break the material down, write the whole storyboard, save both,
then make it. Any project that composes a new video (like a reference or from the creator's
request alone) is planned in full before the first paid step beyond one or two trial stills.
Break the material down first (the steps above: the reference's shots on a contact sheet, frames
at the moments that matter, `transcribe`; every image the creator sent) and write the analysis as
plain text: the shots with their times, for each the subject, shot size, motion and on-screen
text, the medium and look, the layout, the voices and sound, the captions -- what you saw kept
apart from what you infer. Then write the storyboard from it and save both (host mechanics below).
A video takes many turns and the later ones see only the saved plan, not this turn's notes.

The storyboard is one JSON object: at the top `form` (medium, look, settings, shot count and pace,
captions, voice, music and sound), `total_s`, and, when the video has recurring characters,
`characters`: one entry per character, `{name, look}` -- a short name used for them everywhere in
the storyboard, and the fixed look every picture of them follows (build, face, hair, clothes,
colours, props). `sheet` is filled in during production ("The same people in every shot" below);
a plan handed to Kabo's producer to make leaves it out.
`total_s` follows the reference when there is one. Without one (the creator's request and
material only) and with no length asked for, plan the length the format needs, not the fewest
seconds the material fills: a product or brand promo runs about 20-30 s, an explainer or a story as
long as its words take at the voice's pace, one clip with overlays keeps that clip's length. A held
picture lasts about 3-4 s at most, so a few photos become more shots (details, moves, a closing
lockup), not a shorter video. Never shorten the plan to spend less.
Then `shots`, one per shot: `shot`, `t0`, `t1`, `words` (the exact words heard over it), `picture`
(who or what, doing what, shot size; in a talking shot who speaks and who stays silent), `sources`
(the attachments or handles it uses), `keep_change`, `motion` (`"still"` or how it moves),
`on_screen_text`, and optionally `on_screen_cast` (the `characters` names seen in this shot, a
list), `location` (its place, by its `environments` name), `camera` (the shot size, `close-up` to
`wide`, or the camera position on that place: `reverse`, `top`, `low` ...), `positions` (`{name: left | center | right}` for the
characters seen), `props` (the `props` names seen), `speaker` (who says the row's words on camera, by its `characters` name; `""` for a
voice-over or when nobody is seen speaking), `how` (the steps that make the row, by step name with
the handles, e.g. "still a05 -> talking (speaker: grandma)" or "still -> animate"; acting and
delivery go in `motion` or `prompt`, not here), `prompt` (the full prompt: what happens, camera
and framing; it names the characters, place and props and never copies their looks), `captions`, `sound`,
`transition`. A row whose words are said on camera by its speaker is a talking shot: its `how`
names `talking` (or `lipsync` on a moving clip), never `animate` alone. Every character in a shot's picture
is in its `on_screen_cast`, and the picture never redescribes a character's look differently from
`characters`. (A style card's `cast` in `form` says what kind of figures appear at all; it is not
`on_screen_cast`.) The style card describes the picture only. Caption and title styling goes in
`form.captions`, never in `style.description` (words about captions there were drawn into every
picture). Captions follow the reference: when it has captions, `form` and each row's
`captions` give their style (font, size, position, one word or a phrase at a time), and
`form.captions` names the mode by its word: `phrase`, `word`, `highlight` or `reveal` (captions
that grow a word at a time as it is said are `reveal`, never `highlight`); `none` only
when the reference has none or the creator asked for none. Every line of the script has a picture that
shows what it says. A storyboard written before the material is broken down is not the plan.
Each shot is its own picture; a shot whose reference moves (a person or thing acting, a camera
move) is made to move (`animate`, `refvideo`, `talking`, a code animation), and only a shot over
a held picture in the reference becomes `still_video`. One action per shot: a generated shot
shows a single action of about 5 s at most. Never ask one shot to move food or an object from one
container to another (pouring, plating, scooping, handing over); cut from the action to its result
instead (stir-frying in the pan -> cut -> the finished dish on the plate). Animate each shot about as long
as its line (5 s unless the line is longer); a shot `mux` trims the picture to its line. Then make it row by row -- every row, in
batches -- without redesigning the look, the characters or the shot structure, and before
delivering count the rows made against the rows planned; times may follow the real voice, the
form does not change. When a row has to change, change the storyboard and save the whole of it
again (the analysis may be left out to keep the saved one).

**On Kabo Web** (the `remake_video` tool is listed): save both with
`remake_video {request:{action:"plan", job_id, analysis, storyboard}}` (the tool description
lists the fields). Every later `status` of the job returns the analysis and the storyboard. A
storyboard with prompts left for later is not the plan.

### When a row has no `how` or `prompt`

A storyboard may come with only `picture`, `sources`, `keep_change` and `motion` (another host or
the creator wrote it). Then choose the steps yourself, row by row, from the table in `SKILL.md`
("Choose what to make") and `atoms.md`:

- **What stays** (`keep_change`, `sources`): the creator's real footage with new words is
  `tts` + `lipsync`; a reference shot with the creator in it is `replace` (+ `lipsync`); the
  creator somewhere else is `bg`; a delivered video's span is a new clip `splice`d back.
- **Who is in the picture** (`picture`): the creator, or a generated character that speaks a
  line, is a face step (`talking` from a still, `lipsync` on real footage, `refvideo` when silent,
  `first_frame` for a new still of them); anything without the creator is `still` (several in one
  batch); a picture with words, numbers, a chart, a map, an interface or callouts is
  `motion_graphics` (a component or exemplar from `../motion-catalog.md`); paragraphs to read are
  `text_cards`.
- **How it moves** (`motion`): `"still"` over a held picture is `still_video`; a moving subject or
  camera on a generated picture is `animate`; the creator doing a movement from a video is
  `motion`; a code animation moves itself.
- **Sound and joins**: `tts` per voice before the pictures that follow it, `concat` with the
  row's `transition`, `mux`, `music` (`duck` under speech), `sfx`, then `captions` as the row or
  `form` says.

Write the prompt yourself from `picture`, `form` (medium, look, `avoid`), the `look` of each
character in the row's `on_screen_cast`, and the style
card, as step 4 above says, and save it into the row when you save the storyboard again.

## The same people and places in every shot: cards first

Every character seen in more than one shot goes in the storyboard's top-level `characters`, every
place seen in more than one shot in `environments`, and every object that recurs or matters to the
story in `props`, each `{name, look, sheet}`: `name` is used the same way everywhere (rows'
`on_screen_cast`, `speaker`, `location`, `props`) and `look` is the one fixed appearance (for a
place, written by direction: "window on the north wall, sofa against the east wall", so every
angle agrees). When the plan is saved, Kabo keeps these as the project's cards; from then on a step
only names them and Kabo adds their sheets and looks to the picture. Write only the names in
prompts: a look copied into a prompt drifts.

Before the shots:

- **Characters.** One sheet per character: a `still` with `params.sheet_for` set to the name, in
  the project's look: one character sheet on a plain white background, a head-and-shoulders
  close-up on the left and three full-body views of the same person on the right (front,
  three-quarter, back). On Kabo Web the host saves a finished `sheet_for` still as that card's
  sheet in the plan by itself (the result says so); a sheet made without `sheet_for` is saved with
  `remake_video {request:{action:"plan", job_id, sheets:{<name>: <handle>}}}`; the whole
  storyboard need not be sent again.
- **Places.** One picture of the place without people, `params.sheet_for`
  `{kind: "environment", name, as: "ref", view: "wide"}`; then, from it (`inputs.refs`), one
  vertical picture per other camera position the shots use (`as: "ref"` with its `view`:
  `reverse`, `top`, `low` ...). A grid of all angles is only for the creator to check; it never
  goes into a shot.
- **Props** that must look the same: one sheet each, `sheet_for` `{kind: "prop", name}`.

Then every `still` with characters gives `params.on_screen_cast` (`[]` when nobody is in it),
`params.location` and `params.camera`, `params.positions` when more than one character is seen,
and `params.props` when they are seen. `camera` is the shot size (`close-up`, `medium close-up`,
`medium`, `medium wide`, `wide`) or the label of one of the place's pictures; a size frames the
picture even when the place has only its wide picture. Keep the reference's shot sizes, except
for a row whose `how` has `talking`: it is at least a `medium close-up` so the mouth is readable,
and a two-person exchange is a `medium` two-shot or the speaker alone; `wide` and `medium wide` are
only for rows where nobody speaks on camera. In a batch one value per item (a list, `null` for an item
without) or one for all. Leave `inputs.refs` out of shots: Kabo sends at most three pictures (the
characters' sheets and the place's picture from that camera), and more drew worse. A still of a
character without a sheet is turned back until the sheet is made. `animate` and `talking` start
from those stills and keep the look; `animate` must not add a character the still does not show.

## Make the rows by shot number

Store the storyboard (`plan`) before any step that says `shot`. The saved storyboard is also kept in
the project, so steps say the shot instead of pairing rows
with handles: `still {params:{shot: N}}` (a batch: `shot: [3, 7, 10]`) takes the row's prompt and
its characters, place and camera; `animate {params:{shot: N}}` takes the shot's latest picture and
the row's `motion`; `tts {params:{shot: N}}` reads the row's `words` in its speaker's card voice;
`talking {params:{shot: N}}` makes the shot's picture say the shot's voice; `trim`, `retime` and
`mux` take the shot's latest clip; `concat {params:{shots: "all"}}` joins every shot's latest clip
in storyboard order (a talking clip over an animated one over any other). Give a prompt or a handle
only to change what the row says. A refusal names what to make first: `shot_missing` (no picture
or voice for that shot yet), `shot_mismatch` (a handle made for another shot), `shot_no_words`,
`talking_speaker_not_in_picture` (the shot's picture was drawn without its speaker). Pair handles
yourself only for steps outside the storyboard.

## Characters that talk

A drawn or invented character, with or without the creator: make each character's sheet and the
shots' stills as above; voice each row with `tts {params:{shot: N}}` (the row's words in its
speaker's voice; a batch of them in one call); then `talking {params:{shot: N}}` (the shot's
picture with its voice) or `lipsync` on an `animate` clip of it gives the talking shot. Without a
saved storyboard, take each line's audio from the `tts` call of the voice that speaks it (match the
words in that call's notes, not the order of the handles). On a character picture every
`talking` call names the speaker in `params.speaker`, as the storyboard row does (its
`characters` name with its look, e.g. "grandma, the grandmother in the armchair"): the host counts the characters in the picture and, when
there is more than one, makes only the speaker's head and shoulders talk, so the others keep their
mouths shut. A `params.region` [x, y, w, h] you give is used as it is; when the speaker cannot be
told apart the call comes back with each character's box to pick a region from. `talking` and
`lipsync` work on pictures this project generated and on the creator or a `persona`, never on a
real person from an upload or the reference (`no_creator`). For a dialogue, `concat` the per-line
audios in the order spoken into one track (`concat` joins sounds as well as videos), cut the shots
to their lines, `concat` them and `mux` the track under them.
