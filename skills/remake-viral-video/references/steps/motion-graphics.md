# Code-animated videos (`motion_graphics`)

For a video made mostly of code animation (an explainer, a chart or data piece, product photos in
motion, an illustrated story, callouts over a clip). The step's inputs and params are in
`atoms.md`; style cards, components and exemplar pages are in `../motion-catalog.md`.

**Marks on a moving subject in a clip** (a reticle on a knee, a label on a hand, a line between
two joints): first take `frame` of the clip with `grid: true` at the moment the marks start and
read each point's x / y off its grid -- never guess positions, never from an unmarked frame. Then
use `tracked_overlay` (the marks follow those points as they move) with the clip as `base`. Own
markup or `hud_callout` puts marks at fixed screen positions that do not follow anything; use them
only for things that stay put.

0. **With a reference (a video or images to make it like), write its style first** (this applies to
   every video made like a reference, code-animated or generated) -- a short
   phrase each, read off its frames (`frame` at a few moments), before the shot list. The whole
   video: `medium` (the medium and render tier: `live_action`, `screen_capture`,
   `photoreal_cg`, `game_render`, `stylized_3d`, `flat_2d`, `hand_drawn_2d`, `collage`,
   `stop_motion`, `pixel_art`, or `mixed: a + b`), `look` (colours, light, contrast, surface and
   texture), `cast` (who or what recurs and how it is drawn), `frame` (full bleed, letterbox, a
   card, split screen), `edit` (how long shots hold, cuts or transitions), `sound` (voice, music,
   effects), `captions` (none, phrases or word by word; font, position) and `avoid` (the
   neighbouring looks it must not drift into: a game render is not photoreal CG, flat vector is
   not 3D). Each shot of the list: `dimension` (flat, 3D or mixed), `shot` (size and camera
   angle), `layout`, `palette`, `type` (font and how much text), `elements` (axes, charts, icons,
   characters, photos, UI) and `motion` (in the frame and the camera). Everything after follows
   it: the style card is the one whose `medium` matches, every `still` prompt carries the
   medium, light and `avoid` (and the card's `prompt words`), and components are chosen by
   whether they can draw the shot's dimension, layout and elements. After each shot renders, put
   a frame of it beside the reference's frame at the same moment: a different medium, look, cast,
   dimension, layout or elements is re-made (once); the rest is a note.
1. **Shot list first, then shot by shot.** Before any call, write one row per shot: its time
   span, the component or exemplar page (or own markup), the content of its fields or what the
   markup shows, where the picture comes from (`code`, `still`, or `animate`), and the style
   card. One style card for the whole video. When there is a voice, make it first (`tts`) and
   take the spans from its timing. Then make each shot with its own `motion_graphics` call and
   join them with `concat`: a video of several ideas is several shots (a contrast, a curve, a
   flow, a closing line), never one long page of titles and labels.
2. **Style.** Read the style card table in `../motion-catalog.md` and choose by its
   `medium` column first (the reference's medium), then light and texture, then `suits`. A style
   the creator names comes first. When no card fits, write the colours
   from the creator's description as a colour object.
3. **Components first.** Read the component table in the same file; it lists each component's
   required and optional fields and whether it needs `refs` or `base` (each component's fields in
   full: `../motion-catalog-fields.md`). Use a component whenever
   one fits the shot (photos of a product, a contrast, a number, a flow, callouts over a clip):
   it is tested and renders first time. When none fits, use an exemplar page (spec C,
   `{"exemplar": "<name>", "fields": {...}, "style": ...}`; the exemplar table in
   `../motion-catalog-fields.md` says which shot each suits and lists its fields): the runner renders the finished page with
   your words, and drops the parts you leave out. Only when no exemplar fits either, write your
   own HyperFrames markup (spec A) to the standard of the closest exemplar's description: every
   animated element has its own `id` and `class="clip"`; a clip's own `display` is set by the
   renderer, so put flex or grid on a box inside it; times use fixed numbers or `DUR`.
   **Caption band:** keep the bottom fifth of the frame (y > 0.80) free of content in your own
   markup too; components and exemplars already do, and captions go there by default.
4. **Numbers.** Only numbers the creator gave or that are in their material. Without them, the
   shot shows something else (a contrast, a flow, a picture) -- never invent figures. You may ask
   for them once when they matter, but by default go ahead without.
5. **Heavy picture, light code.** When the subject needs a real-looking or drawn picture (a
   realistic scene, a storybook, history, a quote over an image), make the pictures with `still`
   first, then move them with a parallax component (`storybook_parallax`, `product_parallax`)
   via `refs`, or with `animate`.
6. **Positions on a clip.** For targets over a video (`tracked_overlay`, `hud_callout`), take a
   `frame` of the base at the moment the targets start with `grid: true` and read each point's
   x / y off the grid; never estimate positions from an unmarked picture (see "Marks on a moving
   subject" above).
7. **Errors.** A missing field, a wrong component name or a render error comes back as one error
   listing every problem, the legal names or fields and an example. Fix them all and send the call
   again straight away (no need to ask the creator). Mechanical slips are corrected by
   the runner and reported in `notes` as `fixed: ...` (markup with no `class="clip"` gets one
   root clip, common colour-key names are mapped, a font the renderer lacks falls back to its
   sans) -- still write them right next time.

Then join the shots (`concat`), add the voice and music (`mux`, `music`), captions if wanted, and
deliver. Before delivering, check the result against what you told the creator you would make
(music, voice, captions, which parts changed): add what is missing, and describe the delivered
video as it is, not as planned. The old keys `style_css` / `script_js` and the four old `preset`
names are still read for compatibility; use `spec` as above.
