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
ahead. What to make follows the storyboard, never the cost. Choose photos, moments, frames and words yourself from the material here (look at each
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
   the line mentions), about as many different pictures as it has shots (within a third; never
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
list), `speaker` (who says the row's words on camera, by its `characters` name; `""` for a
voice-over or when nobody is seen speaking), `how` (the steps that make the row, by step name with
the handles, e.g. "still a05 -> talking (speaker: grandma)" or "still -> animate"; acting and
delivery go in `motion` or `prompt`, not here), `prompt` (the full prompt), `captions`, `sound`,
`transition`. A row whose words are said on camera by its speaker is a talking shot: its `how`
names `talking` (or `lipsync` on a moving clip), never `animate` alone. Every character in a shot's picture
is in its `on_screen_cast`, and the picture never redescribes a character's look differently from
`characters`. (A style card's `cast` in `form` says what kind of figures appear at all; it is not
`on_screen_cast`.) Captions follow the reference: when it has captions, `form` and each row's
`captions` give their style (font, size, position, one word or a phrase at a time); `none` only
when the reference has none or the creator asked for none. Every line of the script has a picture that
shows what it says. A storyboard written before the material is broken down is not the plan.
Each shot is its own picture; a shot whose reference moves (a person or thing acting, a camera
move) is made to move (`animate`, `refvideo`, `talking`, a code animation), and only a shot over
a held picture in the reference becomes `still_video`. Then make it row by row -- every row, in
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

## The same people in every shot: character sheets first

Every character seen in more than one shot goes in the storyboard's top-level `characters`:
`{name, look, sheet}`, where `name` is used the same way everywhere (each row's `on_screen_cast`
lists the names seen in it, and `speaker` uses them too) and `look` is the one fixed appearance
written into every picture of them. Before the shots, make one sheet per character: a `still` with
`params.sheet_for` set to the name and a prompt of their look, full body, front view, plain
background, in the project's look (a planning trial still may be a sheet). Save the handles with
`remake_video {request:{action:"plan", job_id, sheets:{<name>: <handle>}}}`; the whole storyboard
need not be sent again. Then give `params.on_screen_cast` on every `still` with characters in it:
the host puts their sheets first in the references, so a character looks the same from shot to
shot, and a still of a character without a sheet is turned back until the sheet is made.
Stills batched together share their references, so batch rows with the same cast. `animate` and
`talking` start from those stills and keep the look.

## Characters that talk

A drawn or invented character, with or without the creator: make each character with `still`;
voice the lines with `tts` (one call per voice, preset voices); then `talking` (the character's
still + its line) or `lipsync` (an `animate` clip of it + the line) gives a talking shot per line;
each shot takes the per-line audio of that line from the `tts` call of the voice that speaks it
(match the words in that call's notes, not the order of the handles). On a character picture every
`talking` call names the speaker in `params.speaker`, as the storyboard row does (its
`characters` name with its look, e.g. "grandma, the grandmother in the armchair"): the host counts the characters in the picture and, when
there is more than one, makes only the speaker's head and shoulders talk, so the others keep their
mouths shut. A `params.region` [x, y, w, h] you give is used as it is; when the speaker cannot be
told apart the call comes back with each character's box to pick a region from. `talking` and
`lipsync` work on pictures this project generated and on the creator or a `persona`, never on a
real person from an upload or the reference (`no_creator`). For a dialogue, `concat` the per-line
audios in the order spoken into one track (`concat` joins sounds as well as videos), cut the shots
to their lines, `concat` them and `mux` the track under them.
