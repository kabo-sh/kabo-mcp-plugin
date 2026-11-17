# Narration: writing a composition

Part of `narration.md` (a row whose `make` is `kind: "composition"`).

The runner puts your three strings into a 1080x1920 page sized to the lines' length:

- `markup` -- the elements, inside the page's root. Every visible element is `class="clip"`; it
  shows for the whole of the row's lines unless you give it `data-start` and `data-duration`
  (seconds) and `data-track-index` yourself. Keep what matters inside the class `safe` box (it
  leaves the bottom third for captions and the right edge for the platform's buttons). Write the
  interface's real words: menu names, button labels, column headings, values.
- `style` -- CSS for those elements: positions, sizes, colours, fonts. Use the fonts the renderer has: "Noto Sans"
  (Latin) and "Noto Sans CJK SC" (Chinese, Japanese, Korean), with sizes that read on a phone (body
  text 34px or more).
- `script` -- lines that add tweens to the paused GSAP timeline `tl`. `cue("word")` is the time
  that word is heard, counted from the start of the row; `DUR` is the row's length. Example:

```js
tl.fromTo("#win", { y: 16 }, { y: 0, duration: 0.35, ease: "power2.out" }, 0);
tl.to("#cursor", { x: -320, y: -90, duration: 0.6, ease: "power2.inOut" }, cue("layout"));
tl.to("#tabular", { backgroundColor: "#cfe6d8", duration: 0.2 }, cue("tabular"));
tl.to(".filled", { opacity: 1, duration: 0.4, stagger: 0.15 }, cue("form") + 0.4);
```

It has to pass the renderer's checks, or the line falls back to a plain card:

- Move with transforms only: `x`, `y`, `scale`, `rotation`, `opacity`, colours. Never animate
  `left`, `top`, `width` or `height`.
- **Never fade the base window, canvas, or map container from `opacity: 0` at `t=0`, and never strip
  surrounding context on later beats.** Keep the main window, canvas, or map at `opacity: 1` from
  `t=0` so the start of each beat is never blank or black (`preview` warns on this). For UI and
  software reconstructions, populate the full surrounding window chrome (titlebar, address or
  breadcrumb bar, sidebar or folder tree, status bar) plus **8-12 realistic surrounding rows, keys,
  or table entries** on every beat (keep the parent window visible behind modal dialogs or
  spinners). For maps, globes, and charts, project real simplified GeoJSON geometry into inline
  `<svg><path d="..."/></svg>` layers or pair a cartographic base in `make.images` with crisp SVG
  routes, rings, and HUD labels across every beat.
- **Math, vector and science diagrams**: prefer the `vector_diagram` component (projection `3d`
  for a 3D reference). Written by hand, keep one stage across the cut -- the same canvas, axes
  and header (title and formula line) on every row; a perspective grid with axes going into the
  screen when the reference draws in 3D; **one origin**: all axes meet at one pixel point and
  every origin-rooted vector starts exactly there (`preview` warns when vector tails sit away
  from the axis crossing); real arrowheads (`<defs><marker>` with `marker-end`, never dots on
  line tips; `preview` warns); a difference or analogy as parallel dashed arrows between the
  tips (a parallelogram), not boxes in a flowchart; labels 34px or more. Fill the frame: a
  sentence or an equation alone on a dark page is a card, not the reference's diagram.
- Give every tween fixed numbers. Never a function that measures the page
  (`getBoundingClientRect`, `offsetLeft`): the renderer's workers seek on their own, so a measured
  value differs between them.
- Nothing from the network: no web fonts, no image URLs (draw icons as inline SVG or text).
  Never paste an image in as `data:`; the runner drops it.
- One timeline: no timers, no `requestAnimationFrame`, no randomness.
- Keep each row's three strings under about 250,000 characters together, so full inline `<svg>`
  street-grid or GeoJSON maps and multi-row interface trees fit directly.

A composition that needs a real-looking image inside it -- the picture an app produced, a photo
on a page, the base of a map -- names it in `make.images` and shows it by name. The runner
generates each one (no text in it, in the creator's look) before rendering, at most six per row:

```json
"make": {"kind": "composition",
         "images": {"result.png": {"prompt": "a watercolor portrait of a young woman, soft light"}},
         "markup": "<div id=\"app\" class=\"clip safe\">... <img id=\"out\" class=\"clip\" src=\"result.png\"> ...</div>",
         "style": "...", "script": "..."}
```

What makes one good:

- **Phone-sized interface density, never a sparse slide**: when the reference shows an app, a web
  page, a spreadsheet, a dialog, a file or registry tree or a settings panel, rebuild the real
  multi-row table, sidebar or toolbar, input fields, keys or dialog controls filling the vertical
  safe frame, with the active row, button or cursor step lit on `cue("word")` -- never a
  three-bullet summary card.
- **Street-grid maps and vector diagrams**: when the reference shows a city or street map or a
  geometric diagram, draw a dense multi-block street grid (`<svg>` roads, intersections, street
  labels, zone polygons, an animated route or pins) or a balanced diagram above with its formula
  below.
- One idea per row, a few things moving at once, the same window and colours across rows so the
  cut reads as one piece, and each element landing on the word that names it.
Fill the vertical frame: show the part of the interface the line is about at phone size -- the
menu, the column, the dialog -- not a whole desktop window shrunk into the middle with black
above and below. Give each scene its own row (a few lines); one composition for the whole video
is slow to render and hard to keep readable.
The captions already carry the narration, so do not spell the line out on screen as well.

What the runner cannot do here: open a real web page or an app, or use the user's own material.
Where the reference shows a real interface, rebuild it as a composition (`evidence: false`) and
keep the line's claim to what the picture can carry. A picture that cannot be made becomes a card
of its line, and the delivery notes say so.

