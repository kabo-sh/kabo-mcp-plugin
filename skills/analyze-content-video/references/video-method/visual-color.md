# Visual and colour

Deeper method for the picture: the default card's `framing`, `visual_hook` and the visual side of
`delivery_quality`. Use it when the creator asks about the look, the framing, the lighting, the
colour, the grade, or why the video looks amateur or premium.

## What to look at

1. **Subject and size.** Is the thing the video is about large in the frame when it matters? Shot
   size should follow importance: wide to place, close to read a face, an insert to show an object
   or a step.
2. **Composition on a vertical screen.** Subject placement (eyes around the upper third in a
   talking shot), headroom, and whether key action falls where a feed's buttons and caption sit.
   `media.probed.framing` gives the delivered aspect, screen fill and bars: horizontal footage
   letterboxed in a vertical feed fills only part of the screen.
3. **Background.** Does it support the topic (the kitchen for a recipe, the desk for a setup) or
   compete with the subject (clutter, bright windows, moving people)?
4. **Light on the subject.** Is the face or the product lit and readable? Backlight from a window,
   top light leaving eyes in shadow, mixed colour temperatures across the face.
5. **Consistency across shots.** `media.probed.brightness.per_shot` shows shots much darker or
   brighter than the rest; frames show white balance jumping between shots (a cool shot cut against
   a warm one) and skin that changes colour.
6. **Colour as intent.** A consistent palette or grade that fits the mood (warm and soft for a
   personal story, clean and neutral for a tutorial, high contrast for energy) against colour that
   is simply uncorrected.
7. **Visual variety that carries information.** Inserts of the noun being spoken, the step being
   done, the result: new pictures that add meaning, not motion for its own sake.

## Standards

| Strong | Weak |
|---|---|
| The subject fills the frame when it matters | A small subject in a wide, busy room |
| Even, readable light on face or product | Silhouette against a window, eyes in shadow |
| Shots match in brightness and colour | One shot noticeably darker, colder or greener |
| Full-screen vertical delivery | Bars, or horizontal footage shrunk into a vertical frame |
| Inserts show what is being talked about | A talking head while the object stays off-screen |
| A deliberate look that fits the mood | A heavy filter that hides skin tone or the product |

## Common failures

- The object of the video never shown close enough to see.
- Lighting that changes between takes recorded at different times of day.
- A first frame that is dark, blurry or mid-transition.
- Colour filters that turn skin orange or grey.
- Letterboxed footage that wastes most of a phone screen.

## Fixes

- "Add a close insert of the product at 0:09 while she describes the texture."
- "Lift the shot at 0:21–0:26; it is much darker than the shots around it."
- "Reframe 0:00–0:05 to fill the vertical screen instead of the bars."
- "Face the window rather than having it behind you; the face is in shadow from 0:00."
- "Match the white balance of the 0:30 shot to the rest; it cuts from warm to blue."

## Evidence this needs

- Frames. Every claim about framing, light or colour needs a frame; cite it.
- Measures: framing (fill, bars) and per-shot brightness, when present.
- Viewer observations only for what moves between frames, never for a colour or composition claim.

## Do not claim

- The camera, lens, focal length, exposure settings, the grade's settings or a named filter or LUT:
  none of these can be read off a frame.
- Exact colour values or temperatures unless measured.
- That a look caused performance, or that a "premium" look is what this audience wants.
