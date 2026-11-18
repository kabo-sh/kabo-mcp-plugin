# Captions and on-screen type

Deeper method for the default card's `text_overlay` (what the text says) and `text_placement`
(where it sits and whether it can be read). Use it when the creator asks about captions, subtitles
burned into the picture, headline text, fonts, text size or readability.

## Two jobs, judged separately

- **Captions** transcribe speech so it can be followed with sound off. Judge accuracy, timing,
  chunking and legibility.
- **Headline and callout text** adds something speech does not: the promise, the stakes, a number,
  a label for what is on screen. Judge what it says and whether it earns its place.

Burned-in text read from a frame is on-screen text, not a transcript. Platform caption files are
transcript, not on-screen text.

## What to look at

1. **Does the opening text make the promise sound-off?** A viewer with sound off should know what
   the video offers from the first frame's text alone.
2. **Text against speech.** Captions should match the words; a headline should add to them, not
   repeat them or contradict them.
3. **Legibility on a phone.** Size relative to the frame, weight, contrast with what is behind it
   (stroke, shadow or box when the background is busy), and whether it stays on screen long enough
   to read.
4. **Placement.** Away from the face and the product, and out of the areas a feed covers with
   buttons, the account name and the post caption: on vertical feeds, the bottom fifth and a strip
   along the right edge are commonly covered (general practice; exact areas differ by platform and
   app version). `media.probed.framing` gives the delivered frame size and bars.
5. **Chunking and timing** of captions: a few words per chunk for fast speech, never more than two
   short lines; each chunk appears with its words and leaves with them, never ahead or behind.
6. **Emphasis.** Highlighting the key word in a line helps if it is used sparingly; highlighting
   every other word highlights nothing.
7. **Accuracy.** Machine-made captions mishear names, numbers and brand words; one visible error in
   a price or name undermines trust.

## Reading time

General practice, not measured from this video: viewers read roughly 12–15 characters a second on
a phone, so a 30-character line needs about two seconds; a headline that has to be read and
understood needs more. Text replaced faster than that is decoration. Judge against the frames you
have: if a text appears in one sampled frame and is gone in the next, its time on screen is under
the sampling interval, not a measured duration.

## Standards

| Strong | Weak |
|---|---|
| Opening text states the promise in a few specific words | Generic headline, or none on a sound-dependent opening |
| Captions match speech and are chunked by phrase | Long paragraphs, chunks split mid-phrase |
| High contrast on every background in the video | White text on a bright background, no stroke |
| Clear of face, product and feed buttons | Under the caption area, over the mouth |
| One style throughout, emphasis used sparingly | Several fonts and colours with no system |
| Held long enough to read | Gone before it can be read |

## Common failures

- Text that transcribes the speech word for word while also being the headline: no added
  information.
- A headline and a spoken first line making two different promises.
- Key text sitting where the feed's caption and buttons cover it.
- Captions out of sync after a trim, or left with a misheard word.
- Text crowding the frame so the subject is hidden.

## Fixes

- Rewrite the headline as one promise with the specific noun or number; give the exact words.
- "Move the text at 0:00–0:03 up to the upper third; it sits where the post caption covers it."
- "Add a dark box or stroke behind the captions from 0:10; they disappear on the white wall."
- "Split the two-line caption at 0:18 into two chunks of three or four words."
- "Fix the caption at 0:22: the brand name is misspelled."

## Evidence this needs

- Frames. Typography, placement, contrast and the exact wording need a frame; a viewer note or a
  prose description of a frame supports only that some text was there and what it said.
- The transcript, to compare captions with speech.
- `media.probed.framing` for the delivered frame and its bars.

## Do not claim

- A font's name, a size in points or pixels, or a position as a percentage, unless measured from
  the frame; say "large", "upper third", "over the face" instead.
- Reading time as a measured duration when only sampled frames show the text.
- That captions changed watch time: no retention data here.
