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

**The frame.** When the creator names TikTok, Reels or Shorts (or asks for a vertical video), plan
every picture and clip at 9:16 from the start (`aspect` on the steps that take it); never deliver
those as landscape. Never lay a landscape source full width on a black 9:16 frame (`layout` with
`fit: "contain"` on a solid colour): the picture ends up a third of the screen. Reframe it with
`crop` (the writing is kept whole); `deliver` fills such letterboxed stretches itself and says so.

**Several videos in one request** (ten styles of one story, five episodes, one per product):
write every video asked for into each video's storyboard as `series` -- one entry per video in the
creator's order, with what is particular to it (its style, topic or product) in the creator's words
and its `job_id` once its project exists -- and keep it there whenever you save the storyboard
again. Later turns read the list from the plan; never ask the creator to send it again.

Every request carries a new idempotency key (a UUID). Repeat the same key only to retry the same
request after an unknown outcome.

## Read what you were given first

- **Listen before you assign.** Run `transcribe` on every clip the creator sent that has sound
  before deciding which clip is which language, speaker or role; never infer language or role from
  upload order or file names. If the clips do not match what the creator described (e.g. "three
  languages" but two clips are English), say in one line what you heard and make what the creator
  asked for: a missing language version gets its own voice and captions in that language, not the
  uploaded clips cut together again.
- **Screenshots are references, not shots.** A screenshot, phone capture, chat or post capture
  (status bar, app chrome, black bars) the creator sent as an example shows the idea, the look or
  the words: draw new pictures from it, never open on it or cut it in as it is. Show such a capture
  as a shot only when the creator asks to show that screen. Screens of the creator's own app or
  product are the product itself: show them where the plan shows the product.
- **"Not on camera" holds for the whole video.** When the creator says they will not appear (no
  face, voice only, a preset voice), plan every shot without a person: hands, product, places or
  illustration -- no upper body, partial face or stand-in person -- and say so in every picture
  step's prompt.
- **The real interface or product.** When the video shows the real app, website or product (a
  demo, a walkthrough), use the screen recordings or photos the creator gave. If there are none,
  make illustrative cards for those screens, say in your plan message that a screen recording
  would replace them, and go on; do not stop to wait for one.

- **The project receipt says what each upload holds.** It lists what each uploaded clip says (its
  language and first words, "no speech heard" when silent) and marks uploads that are screen
  captures (status bar, clock, battery). Plan languages, speakers and versions from that, never
  from the upload order or file names; a capture it marks is a reference for the idea, the look or
  the text -- animate one as a shot only when the creator asked to show that screen.

## Break the reference down first, then keep its form

Before the first paid step of any video made like a reference:

1. `frame` with `shots: true` on the reference: one contact sheet of all its shots with their
   time spans, and the shot count and cut times in the notes (which cuts are dissolves, and
   whether the picture sits in black bars). Look at it (and a `frame` or two
   up close) and write, shot by shot, what the picture is: the subject kind (a person in
   close-up, a statue, an object, a scene, a chart, a character), shot size, motion, any text
   on it; plus the sound (voice, music, effects) and captions.
2. Write its style (step 0 of `motion-graphics.md`: `medium`, `look`, `cast`, `avoid` ...) and
   pick the motion style whose `medium` matches in `../motion-catalog.md`.
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

The storyboard is one JSON object (its exact field shapes are in `params.md`): at the top `form` (settings, shot count and pace,
captions, voice, music and sound), `style` (the look, in one place: "The look: one style card" below), `total_s`, `target_s`, and, when the video has recurring characters,
`characters`: one entry per character, `{name, look}` -- a short name used for them everywhere in
the storyboard, and the fixed look every picture of them follows (build, face, hair, clothes,
colours, props). `sheet` is filled in during production ("The same people in every shot" below);
a plan handed to Kabo's producer to make leaves it out.
When the reference plays in clear segments (an opening hook, a setup, the turns, the payoff, a
call to action), add `skeleton` at the top: each segment with its job, its share of the length and
its shots, every shot in exactly one segment, in order (fields in `params.md`). Leave the sound
levels (`audio_plan`) out: the defaults duck the music under the voice.
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
`characters`. (The style card's `cast` says what kind of figures appear at all; it is not
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

Write the prompt yourself from `picture`, `form` (`avoid`), the `look` of each
character in the row's `on_screen_cast`, and the style
card, as step 4 above says, and save it into the row when you save the storyboard again.

## Length, actions and who does them

**Length.** Set `target_s` on the storyboard to the length the video must have -- the user's stated
length (a range: its middle), else the reference's length -- and make the shots' `t0`/`t1` add up
to it. A spoken row is at least as long as its words take to say (~2.5 words/s narration, ~3
words/s brisk dialogue). If the save notes say the rows miss the target, fix the rows, not the
target. For narration and voice-over, give every shot its own line (`tts` + `mux` with
`params.shot`) and join with `concat` `params.shots: "all"`; never lay one voice track over the
whole cut -- the join then fits each shot to its share, a pause after its line.

**What the creator asked to see.** Put what the creator explicitly asked to see in
`storyboard.asked` as short phrases ("cutting the noodles", "plating the ramen"); every item gets
its own shot. A save that leaves one out comes back with a note naming it.

**Opening and narration.** Open on a moving shot. Narration states each fact once and never asks
a question the video has already answered (listing the costs, then asking "how much did it cost?").

**A revision** keeps the last version's length and what worked in it. "Make it fun / livelier /
better" means new shots, new sound or new pacing, not only new on-screen text; the delivery receipt
says when a version is much shorter than the last or only changed text.

**One action per shot.** A row's `motion` is ONE action by ONE subject (or several subjects acting
at the same time). Never "X, then Y", "first ... then ...", "near the end ..." in one row -- split it
into consecutive shots, each with `start` (its first frame) and `end` (its last frame, = the next
row's `start`). Steps that change an object's state (cut, cooked, poured, plated) each get their
own shot.
The story's last step is in the cut: when the creator's beats or the reference end on an outcome
(the dish plated and served, the box opened, the finished result), that outcome gets its own
last shot whose still already shows it (the food on the plate, the result in hand), so the cut
ends on it even when the clip's motion falls short.

**Who does it.** Give each row `actor` (the character card's exact name) -- or
`actions: [{"actor": "<card name>", "does": "<one action>"}]` when two characters move at the same
time. Write the action with the card name, not a pronoun that could mean another character
("RightFox touches RightFox's own cheek", not "touches its face").

**Props.** One card per object whose look or state matters across shots (each ingredient, the
plate, the pan); don't lump a kit into one card. Say the object's state in `start`/`end`.

**Speaking shots.** When someone on screen speaks, `camera` is medium or closer, and the
`picture`/`prompt` text must not name a wider size ("Wide shot", "full body") -- describe the
speaker from the waist or chest up.

## The look: one style card

Put the look in ONE place: a top-level `style` object on the storyboard (`description`,
`keywords`, `avoid`, `palette`, `fonts`, `motion`, `refs`). `form.medium` and `form.look` are for
people; the runner does not read them. Each row's `prompt` and each sheet prompt say only what is
in the picture, what happens and how it is framed -- no look words (photoreal, 3D, anime,
watercolor ...). To keep the reference's look, put reference frames in `style.refs` (e.g.
`input/style_ref_01.png`).

Changing only the style: a new `style` (give the whole card) -> redraw the sheets and places the
reply names with `sheet_for` -> `still` by `shot` -> `animate` / `talking` by `shot` -> `concat`
`shots: "all"` and the finishing steps. The voice, the storyboard and the card descriptions stay.

## The same people and places in every shot: cards first

Every character seen in more than one shot goes in the storyboard's top-level `characters`, every
place seen in more than one shot in `environments`, and every object that recurs or matters to the
story in `props`, each `{name, look, sheet}`: `name` is used the same way everywhere (rows'
`on_screen_cast`, `speaker`, `location`, `props`) and `look` is the one fixed appearance (for a
place, written by direction: "window on the north wall, sofa against the east wall", so every
angle agrees). When the plan is saved, Kabo keeps these as the project's cards; from then on a step
only names them and Kabo adds their sheets and looks to the picture. Write only the names in
prompts: a look copied into a prompt drifts.

A character who changes clothes or look between scenes gets one card per look ("Tomas (street)",
"Tomas (florist)"), each with its own sheet, and each row names the look's card: one card that
describes several looks makes a clip switch outfits mid-shot. A prop a still names that has no
picture yet is drawn once as a plain product picture on a plain background and kept as its card
first (Kabo does this by itself). A product with brand marks (a logo, an engraving): those exact
marks are allowed in the picture and close shots get enlarged crops of them as references; never
write "no text" or "no logo" for a branded product.

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

## Shots that continue one another

When a shot carries on from the one before (the same moment, the same things in it), write on its
row `start` (the first frame: the pose, where each prop is and its state -- spilled, knocked over,
open) and `end` (the state in the last frame), and put the small details that tend to vanish
(an accessory, a bow, a collar) in `keep`. Where time jumps or the place changes, write
`continues: false`. Make every shot's still before any `animate`. Write motion prompts with the end
state said positively ("holds the mug upright", never "not tipping it"): the video model acts out a
verb even when it is negated.

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
