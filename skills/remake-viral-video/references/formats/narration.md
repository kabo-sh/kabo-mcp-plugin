# Format: narration (the creator is heard, never seen)

**When this applies**: the brief's `brief_input.json` (the result's `reference_type`) has `reference.type: "narration"`, or the waiting-script
message says the run is narration-led. The reference is carried by a voice over pictures --
a screen recording, an animated or drawn explainer, stock or live-action scenes, kinetic type --
and nobody talks to the camera for more than a moment. The runner measured this from the video;
you do not decide it.

The creator's cloned voice reads the reference's script; every picture is re-made. Nobody is put
on camera, so there are no plate or anchor prompts.

## The script

The script, the four rewrite slots, sourcing, the opening record and the proofread are exactly as
in `talking-head.md` and `../creator-into-scene.md` section 0, with two differences:

- **Call to action only where the reference has one.** A reference that ends on its payoff keeps
  ending there: record the `cta` choice as "none, the reference ends on its payoff". Where the
  reference does sign off (usually promoting its own author), replace it with the creator's
  recurring sign-off from their own lines, or a plain follow prompt.
- `route_b_jobs` is not used: send it as `{"jobs": []}`. There are no plate or anchor prompts,
  so the hair and outfit wording rules do not apply.

## The picture plan (in `decisions`)

`decisions.draft.json` carries three extra fields. Fill all three; the runner checks them before
anything is paid for.

**See the reference before you plan its pictures.** At `waiting_script` you are shown none of
the reference's pictures, only its words -- and a plan written from the words alone misses how
the pictures are drawn (one pre run planned a reference of 3D vectors as `dimension: flat`,
another a white page of stick figures as "cream background, icons"; both came out unlike the
reference). Two things show it: `reference.line_looks` in the brief measures each line's
picture (background colour, `light` or `dark`, how much of the frame is drawn on), and every full
`preview` ends with pages headed `REFERENCE`: the reference's own frame while each line is heard.
So write a first plan, preview it, then read `reference_style` and every row's `grammar` (and
`reference`) off those pages and the LEFT frames of the strips, correct the plan and its `make`s,
and preview again before `start`.

0. `reference_style` -- the reference's style for the whole cut, read off its keyframes once, a
   short phrase each, before any picture row. Hard (a difference is a different picture):
   `medium` -- the medium and render tier, one of `live_action` (filmed, stock, photos),
   `screen_capture`, `photoreal_cg`, `game_render` (real-time engine look), `stylized_3d` (toy,
   clay-like, cartoon 3D), `flat_2d` (vector, motion graphics), `hand_drawn_2d` (cel, painted,
   ink), `collage`, `stop_motion`, `pixel_art`, or `mixed: a + b`; `look` -- overall colour and
   light, contrast, saturation, surface and texture (outlines, toon or realistic shading, grain,
   era); `cast` -- who or what recurs and how it is drawn (`none` when nothing does). Followed
   where the run has a choice: `frame` (full bleed, letterbox, a card on a background, split
   screen), `edit` (how long shots hold, cuts or transitions), `sound` (voice, music, effects),
   `captions` (none, phrases or word by word; font, case, position, highlight). And `avoid` --
   the neighbouring looks it must not drift into (a reference that looked like a game render was
   once made as cinematic photoreal CG because nothing named its medium). Every picture is made
   in it: a generated still's prompt names the medium and light and what to avoid; a component or
   composition takes the motion style whose `medium` matches (`../motion-catalog.md`). When the
   brief's `pictures.look` is the creator's own drawn look, the cut follows that look -- say so
   in `picture_system`. Left out, the run writes placeholders and says so in the delivery notes;
   it does not stop.
1. `picture_system` -- one paragraph before the lines: what kind of picture the reference is and
   how it moves (an app or a page on screen, drawn or animated, live action, ...), the look you
   make yours in (`pictures.look` in the brief: whose frames, and why), and the one way every
   line is made so the cut reads as one piece. Decide how each picture is made by what the
   reference's picture is drawn with, not by the word "diagram": exact geometry or words that
   must read (axes, vectors, grids, charts, formulas, an interface) is a component or a
   composition; drawn figures (stick figures, people, animals, a tree or chart of drawn figures,
   a hand-drawn scene with arrows) are generated stills in the look frames -- markup cannot draw
   them and turns them into icons and dots.
2. `pictures` -- one row per line or per group of neighbouring lines that stay in one scene:

```json
{"lines": [3, 4],
 "reference": "what the reference shows while these lines are heard, and what kind of picture it is",
 "grammar": {"dimension": "flat | 3d | mixed", "shot": "...", "layout": "...", "palette": "...",
             "type": "...", "elements": "...", "motion": "..."},
 "plan": "how yours is made, the same kind of picture, with the same grammar",
 "evidence": false,
 "needs": [],
 "make": {"kind": "composition", "markup": "...", "style": "...", "script": "..."}}
```

`grammar` is the reference shot's visual grammar, a short phrase each, read off its picture at
those lines (the brief's `reference.line_frames`: the reference's frame while each line is heard)
before you choose how to make yours (the check refuses a row without it): `dimension` -- `flat`,
`3d` or `mixed` (3D perspective: a tilted plane or grid, axes going into the screen, depth, an
orbiting camera); `shot` -- shot size (extreme wide to insert) and camera angle (eye level, high,
low, top-down, POV, a flat screen); `layout` -- where the main thing sits, how much of the frame
it fills, header or caption zones; `palette` -- this shot's background and main colours; `type`
-- font feel and how much text; `elements` -- axes, grid, arrows, chart, map, icons, characters,
photos, UI chrome; `motion` -- inside the frame and the camera: builds on one by one, draws
itself, push / pull, pan, tilt, orbit, morph. Hard: `dimension`, `layout`, `elements`. A
reference drawn in 3D perspective was once re-made as flat diagrams because only what it showed
had been written down. **Choose the way of making it by that grammar**: a component only when
it can draw it (its row in `../motion-catalog.md`, including what it cannot do); otherwise a
composition. Never drop the reference's grammar to fit a component; a difference you choose on
purpose goes in `plan` with why.

Nobody runs a tool after the script here, so `make` is what the runner carries out. Choose by two
questions: **does the reference draw a diagram a ready-made component already has, and does the
picture have words in it that must read?**

- **A ready-made diagram -- `kind: "component"`.** Vectors on a grid, a bar chart, numbered
  steps, a route on a street grid, a headline with points, a before/after split, a number over a
  curve: `{"kind": "component", "component": "<id>", "fields": {...}, "style": <motion style id or
  colour object>}`, with the ids, fields and motion styles of `../motion-catalog.md` (the same
  components as the `motion_graphics` step; nothing else is accepted). The component draws the
  geometry itself -- every arrow of a `vector_diagram` starts at one shared origin, bars are
  measured from their values -- and you give only the content. Choose the style (a card id or
  `{bg, fg, accent}` colours) that matches the cut's look; a sentence is not a style. Pictures
  it shows go in `make.images` (at most 4, in order). A component whose fields do not check is an
  error in `preview` and at `start`. A reference drawn in 3D perspective (`grammar.dimension`
  `3d`) with arrows from an origin is `vector_diagram` with `"projection": "3d"`; the flat default
  makes it a 2D chart, and `preview` warns.

- **Words in it -- `kind: "composition"`.** An interface, a web page, a settings dialog, a list,
  steps, a chart, a number, a map with place names, a formula. You write it now as a motion
  graphic (HTML, CSS and an animation), and the runner renders it after the voice, so every word
  is real text and every move lands on the word that names it. Rebuild what the reference shows
  in this form -- an app's window with its real menus and labels, the list item by item -- not a
  screenshot of anything real. An image model cannot write words: every interface it drew in the
  first web batch came out with garbled text.
- **No words -- `kind: "generated"`.** People, places, objects, an illustrated scene. The runner
  generates the still from `prompt` with the cut's look frames as its references and tells the
  image model they set the look: the creator's own frames when their videos are drawn or
  graphic, the reference's own frames when the creator films themself (a room and a face are no
  look for a drawn picture). The brief's `pictures.look` says which and why. So **the prompt
  says what to show, never a look of its own** -- no palette, paper texture or drawing style
  that you have not seen in those frames (a pre run that wrote a look of its own got stills
  that resembled neither video). Give the cut its own characters; the
  reference's narrator character is not the creator's. It asks for no text in the picture.
  **Never copy OCR or transcript speaker prefixes (`Speaker:`, `POAL:`, `[caption]`, timestamps)
  from the reference into `prompt` or ask the image model to render text.**
  **A diagram drawn with characters is generated too**: a family tree of stick figures joined by
  coloured lines, a chart of drawn people -- the prompt says what is shown and how it is laid out
  (who stands where, what joins what, how many generations), the look frames give the drawing
  style and the page colour. With `motion` it becomes a 5-second moving clip; leave `motion` empty only where
  the reference itself holds a still. **When the reference moves, every picture moves.**
  Neighbouring short lines of one scene share one row and one clip.
- `kind: "motion_graphic"` -- a plain card of the line's words on a flat background, and nothing
  else (any fields or style on it are ignored), for a line where nothing better fits. Preview
  shows it as that card. For a diagram use a component or a composition.

### Writing a composition

How to write `markup`, `style` and `script`, what the renderer accepts and what makes one good:
`narration-compositions.md`. Read it before the first composition row.

## Look before you start -- as often as it takes

The r30 runs that matched their references rendered every picture two to four times and looked
at it each time; written once, blind, the map and result-image lines came out empty. After the
four documents are written and before production starts,
preview the pictures (host mechanics below). The runner renders every composition and component
row for its lines (a plain-card row as its card; timed to an estimate of the voice) and returns
pages (for a long video an even sample; the note says which): one strip per row with the row and lines, the line, and
four frames, with the reference's own picture at the same line on the LEFT of each strip and
ours on the RIGHT. Judge every strip on `render` (the medium and render tier, look and cast of
`reference_style`) and the grammar keys. Change before `start` each row that differs from the
reference on render, dimension, elements or layout; a difference in shot, palette, type or
motion is yours to weigh -- change it only where it matters. Repeat it freely; you can redo
only some rows. A preview with stills also generates the stills of the `generated` rows -- the
very stills the cut then uses (not made twice) -- but it is paid: run it only after the creator's
go-ahead on the quote, look at the stills, fix any, and then start with the confirmed option.
Check every strip: the words read at phone size, the frame is filled, nothing important
sits in the bottom third under the captions, and the picture shows what the line says. Fix what
does not and preview again -- there is no limit. A strip headed `! FIX BEFORE START` names a
problem the renderer measured (sparse markup, a blank opening, a vector tail away from the
origin, missing arrowheads, a flat make for a 3D grammar): fix it and preview that row again. The
`REFERENCE` pages at the end are the reference line by line: a row whose medium, dimension,
layout or elements differ from its line there is changed before `start`. A row the preview returns with an `error`
instead of a strip is not made as written -- a composition without `class="clip"` elements, for
one, becomes a plain card of each of its lines; the error says why. Fix it and preview again. A preview does not start production or count as
a submission; the creator does not need to be told about it. Then start production as usual.

**On Kabo Web** (the `remake_video` tool is listed):

```
remake_video {request:{action:"preview", job_id, files:{script, decisions}}}
remake_video {request:{action:"preview", job_id, files:{script, decisions}, stills:true, rows:[3, 5]}}
```

The pages are attached to your next message. `rows` redoes only those rows; `stills: true` is the
paid preview with stills.

## One look at the finished pictures

After the cut is made, a narration job stops once more at `waiting_script`, this time with a
review: pages of the per-line sheet (an even sample for a long video; each row: the cut's picture
while the line is heard | the reference's picture where the same line was heard | the line), the
current decisions and `beat_review.template.json`.

**On Kabo Web**: the status carries `review`; the pages are attached and `brief` holds
`work/decisions.json` and `production/review/beats/beat_review.template.json`.


1. Open every page. Copy the template and set `ok: true` for each line whose picture shows what the line says and
   reads at phone size; `ok: false` with a short `note` for the others. For each line with a
   reference picture set its `grammar` keys (`render`, `dimension`, `shot`, `layout`, `palette`,
   `type`, `elements`, `motion`) true or false: does ours match the reference's picture next to
   it? A false `render`, `dimension`, `elements` or `layout` makes the line not ok and its row is
   made again -- this round is its only re-make, so what still differs after it is delivered with
   a note. A false `shot`, `palette`, `type` or `motion` is only written into the delivery notes;
   change that row too only if it matters. Mark what you see: a key set true while the two
   pictures differ (flat against 3D, icons against drawn figures, another page colour) is a
   defect delivered without a note. A line whose template row carries
   `same_picture_as_previous: true` shows the line before's picture while the reference moves on:
   it is re-made even if you mark it ok, so give it its own picture (its own row, or a build that
   lands on its words) now.
2. For every line that is not ok, change its row's `make` in `decisions` (fix the composition,
   give the still a new prompt, or switch its kind) and preview that row.
3. Answer -- not with a new start. **On Kabo Web**:
   `remake_video {request:{action:"review", job_id, decisions, beat_review}}`.

Only the rows of the lines marked not ok -- and rows you changed -- are made again; everything
else is kept. When a line is marked not ok but its row would make exactly the same picture (its
`make` did not change, or changed only in what a plain card ignores), nothing is re-rendered:
the job comes back once more with `review`, its message starting `NOTHING CHANGED` and naming
those rows. Change their `make` (preview them) or mark them ok, and answer `review` again. A changed row
that cannot be made (an `error` in its preview, or a composition that does not render) keeps the
picture it had in the cut you reviewed, so preview every changed row before you answer. There is one
such round; after it the video is delivered as it stands. Tell the creator only that the video
is being finished.

`needs` holds only these words: `[]` for a composition or a component, `["generation"]` for a
generated still or clip -- not "paid generation"; the runner rewrites such a spelling and says
so, but a wrong value elsewhere is named at `start` with the allowed values. The runner works out
what each row costs; choose a row's kind by what its line needs, never by cost.

## Red lines

- Every picture is an illustration unless it shows the real thing: never present a generated
  interface, chart or scene as a real screenshot or as evidence.
- No people who look like real, identifiable persons; no logos or brand marks drawn as if they
  were the creator's.
- Nothing from the reference's pixels goes into the cut. Its frames may only be the image
  model's style references, when `pictures.look` says the look is the reference's.
