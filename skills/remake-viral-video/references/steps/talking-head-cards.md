# Cards over the creator's own finished talking video

Use this when the creator gives one talking video they have already edited (an upload, a link to
their reel, or a video delivered here) and asks for number cards, callouts or motion on top of it,
with the picture, the sound and the length left as they are. It is a branch of "a re-edit of
their own video": no whole remake, no new pictures. The job is mostly judgement: which moments get
a card, what it says, when it lands and where it sits. The picture is one `motion_graphics` step
(`motion-graphics.md`) with the video as `inputs.base`.

Not this route: a new video, B-roll, cutting or tightening, a re-voiced or translated video, or
captions alone (`captions`). If the creator also wants captions or cuts, do those first and put the
cards on the finished cut: editing moves every word, so cards timed on an earlier cut land wrong.

## 1. Material and words

1. Start a project with the video as the creator's own video (`project.md`; a link is fetched
   first as under "Links" there). A video delivered here takes the steps on its own job.
2. `transcribe` the video. Its segments carry word times (`words`: `w`, `t0`, `t1`); every card is
   timed from them, never from the sentence's start or end. Speech over about 3000 words comes back
   with `words_truncated`: transcribe the spans you will use (`trim` first) to get their words.
3. `frame` with `shots: true` once, for the cut times.

Transcript word starts can be early: a word that follows a pause sometimes takes the pause into
its own span. When a short word (a number, a name) spans far longer than it takes to say, put its
moment near the end of that span rather than at its start.

## 2. Choose the moments (three passes)

Read the whole transcript three times before settling, because numbers are the easy ones and hide
the rest:

1. numbers, names and quotes;
2. structure in the words: enumerations, and any place where the speaker describes one kind of
   person, thing or case and then the other -- often with no "versus" word ("if you are X..., but
   if you are Y...", "some do A, others do B", "most people..., the good ones...");
3. the picture: for every stretch where something other than the speaker is on screen (a screen
   recording, a screenshot, a chart, a document), look at frames and ask whether a spoken word
   points into it.

| What the sentence does | Card | Use it when | Not when |
|---|---|---|---|
| states a number | big number | one number carries the point | the number is already on screen (consider a mark) |
| compares numbers | comparison bars | two or more numbers in one unit | there are no numbers (use two sides) |
| names a person | name and role | the first time the speaker gives a name or introduces someone | the name is already on screen |
| quotes someone | quote | the exact words matter | it is a paraphrase |
| lists items or steps | list (ticks) or steps (numbers) | 2-4 parallel items, each said in at most 5 words (10 Chinese characters) | the video already shows that list; fewer than 2 real items |
| sets two things against each other | two columns | two named sides, each with 1-3 short points said in words | only one side is described; the contrast is numeric (use bars) |
| talks about something in the picture | mark: a drawn ring, underline or frame on it | the thing said is visible but easy to miss among other things (one row of a table, one value on a chart, one button) | it is already highlighted, boxed or circled; it is the only big thing on screen; it moves |

Rules:

- **Every card supports a point.** Skip ordinals and idioms ("one thing", "two ways"); a real
  enumeration behind "first..., second..." is a list.
- **Already on screen means: do not repeat it.** Either point at it with a mark or add nothing.
  Big, alone or already highlighted: nothing. Small or one thing among several, with nothing
  pointing at it yet: a mark. A mark is never decoration: if you cannot say which spoken words it
  illustrates, drop it. A screenshot or screen recording inserted in the video is a target for a
  mark, never a place to lay a card over.
- **Card text states only what was said.** No added numbers, titles or conclusions. Numbers match
  the transcript exactly; tell the creator any you doubt (a homophone, a slip). A name card's role
  line holds only what was said or shown; prefer a spelling shown on screen. A quote is the spoken
  words exactly, its source only when one was given.
- **Two numbers being compared are one bars card**, not two big numbers. The bars are the quantity
  the sentence compares; the other numbers go in the labels.
- **How many.** About 8 seconds between the starts of two cards; a 60-90 second video usually gets
  2-5 cards in all. A mark may follow a card sooner, but two cards are never on screen together.
  Zero cards is a valid result: say why, skip `motion_graphics` (an overlay with nothing drawn
  fails the step) and deliver nothing new.

## 3. Time each card to its word

- **Big number**: the number lands on its final value at the moment the number is said. The card
  opens 0.4-0.6 s before that (the label first, the number on the word). It counts up only when the
  sentence is a process the viewer should follow ("grew to 161 million"); a conclusion number ("only
  3 steps") pops in once. Ranges ("20 to 30%", shown whole as `20-30%`, never one end) and years
  never count.
- **Bars, list, two columns, name, quote** open 0.2 s before their first content. Each bar, list
  row or column point appears when its own words are said. A quote's words surface across the span
  they are spoken.
- **Two columns** open the moment the speaker starts the first side, never after that side has been
  explained; both labels show from the start, the other side's points wait for their words.
- **A list said twice** (a recap) goes on the recap, so the card is never half empty for long.
- **Leaving**: about 0.3 s after the sentence ends. If a cut falls just before or after the first
  content, the card waits for the cut; if one falls in its last half second, it leaves at the cut.
- **Marks** start when the thing is said and stay only while the target holds still.

## 4. Look before placing

Over a `base`, `motion_graphics` checks faces and bodies after rendering: when a card covers the
person, its notes carry a `warning: the overlay covers the person at ...` with the times and the
part of the frame the person never takes; move those cards there and render again. It does not
check text already on screen, and it only warns after the render, so plan the places first:
take `frame` with `grid: true` at each card's start, its landing moment and its end (one a second
across a stretch with a screen or chart on it). From those frames write down, as 0-1 fractions:

- the face box, grown upward by about 60% of its height for hair and a little on each side;
- the hands while the speaker gestures (cards still tend to cover moving hands: prefer the side
  the hands stay away from);
- every piece of text already on screen: burned captions, name plates, slide or chart text,
  watermarks;
- for a mark, the target's box on the frame where it is said.

Then place each card in space clear of all of them for its whole time on screen: above the head
first, then below the face, then a side. Keep at least 5% from every edge (phone buttons sit
there). The bottom fifth is where captions usually are. If a card fits nowhere, shorten it, make it
smaller (not under about 70%), or drop it. A face filling the frame with no free space: ask the
creator where cards may go.

## 5. Look of the cards

Legibility first: text on a solid or near-solid plate, contrast against the plate (or, without one,
against the brightest part of the frame behind it) of at least 3:1, and text at least about 34 px
on a frame whose short side is 1080 px. Then match what is already in the video: the colours of
its captions or titles, its tone (calm or punchy). One look for the whole video. A style card from
`../motion-catalog.md` can set the colours (`palette`), but the card stays a small plate
over the footage, never a page.

## 6. The call

One `motion_graphics` step lays all the cards over the video:

```
inputs: {base: "<the video handle>"}
params: {duration: <the handle's seconds, exactly as status lists it>,
         spec: {markup, style, script, palette?}}
```

- `duration` must equal the video's length: the result is cut to `duration`, so a shorter value
  shortens the video. It is limited to 120 s; for a longer video, cut each card's span with `trim`,
  lay that card over the span, and put it back with `splice` (`audio: "base"`), one card at a
  time.
- Write your own markup (spec A). The page is transparent over a base; the canvas takes the base's
  aspect with 1920 px on the long side (1080x1920 for a vertical video). Components and exemplar
  pages are whole pages and would cover the speaker; only `hud_callout`, `tracked_overlay` and the
  `hud_over_footage` page are made to sit over footage.
- Each card is one positioned element with its own `id` and `class="clip"`, placed where section 4
  found room; its parts (label, number, rows) are clips too. Times are the absolute seconds of the
  video. Give each card `data-start` and `data-duration` (its span in seconds) so it shows only
  then, and fade it in and out within that span.
- Every word is in the markup and every animation is on `tl`. The renderer only seeks the GSAP
  timeline and shows clips by `data-start` / `data-duration`; it never calls a page's own
  `window.render`, `requestAnimationFrame` or `setInterval`, so text drawn that way never shows and
  a fully transparent overlay fails the step. A count-up is a tween on `tl` that writes the number
  into the element on every update; a ring or underline is an SVG path with `pathLength="1"` drawn
  from `stroke-dashoffset: 1` to `0`.

```
markup: <div id="c1" class="clip" data-start="11.4" data-duration="4" data-track-index="2"
             style="position:absolute;left:120px;top:210px;width:840px">
          <div id="c1-label" class="clip">videos posted</div>
          <div id="c1-num" class="clip">0</div></div>
script: tl.fromTo("#c1",{opacity:0},{opacity:1,duration:.25},11.4);
        (function(){var o={v:0},el=document.querySelector("#c1-num");
         tl.to(o,{v:24,duration:.5,ease:"power3.out",onUpdate:function(){el.textContent=Math.round(o.v);}},11.4);})();
        tl.to("#c1",{opacity:0,duration:.2},15.1);
```

The number lands at 11.9 s, the moment "24" is said.

## 7. Check, then deliver

Look at the step's preview, then take `frame` (without grid) at each card's fully shown moment:
the face, the hands and the text already on screen are clear, the number shows its final value,
the text fits its plate, nothing touches an edge, and no person warning is left in the notes.
Fix and re-run once. Before delivering, tell the
creator each card, the words it is timed to, and the moments you left without a card and why.
The result keeps the video's sound and length; the runner writes it at 30 frames a second, so say
so when the video was at another rate.
