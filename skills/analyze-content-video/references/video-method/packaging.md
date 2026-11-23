# Packaging

Deeper method for what decides the click and frames the viewing before it starts: the title, the
post caption, the cover, the tags, and how they match the video's own opening. It extends the
default card's `first_frame_promise`, `text_overlay` and `cta`. Use it when the creator asks about
the title, caption, cover, thumbnail, hashtags, or why the video got no views at all.

No dimension is called packaging: file a statement about the promise a title or caption makes
under `first_frame_promise` or `text_overlay`, and one about its ask under `cta`.

## Where packaging lives

- **Feed-first platforms** (vertical feeds that autoplay): the first frame and its text are the
  packaging. The post caption is read by viewers who already stopped.
- **Click-first surfaces** (a search result, a channel page, a recommended list): a title and a
  cover are seen before the video plays and decide whether it starts at all.

A diagnosis of "why did this get no views" that never looks at the packaging has skipped the top of
the funnel.

## What to look at

1. **Read the metadata status first.** `content_metadata` with `available` and an empty tag list
   means the creator published none; `unavailable` means the fetch did not happen. They look the
   same; never report the second as the first.
2. **Title and caption against the opening.** Do they make the same promise as the first frame and
   first line? A title promising one thing and an opening showing another breaks trust in the first
   second.
3. **Specific against generic.** A title or caption with the specific subject, number, or viewer
   ("3 mistakes first-time renters make") against one that could caption any video ("you need to
   see this").
4. **Front-loading.** The first words of a caption and title carry most of the weight: feeds and
   search results truncate them.
5. **The ask in the caption.** Does it repeat the video's ask, or add a competing one?
6. **Tags.** What the creator declared, in their order. Judge only relevance to what the video
   shows; their effect on distribution is unknown here.
7. **The cover.** A cover address is a reference, not an image: no cover pixels are seen here. Say a
   cover exists and hand it over; do not describe what it looks like or judge whether it works. On
   feed-first platforms, judge the first frame instead.

## Standards

| Strong | Weak |
|---|---|
| Title, caption and opening make one promise | Three different promises |
| Specific subject, number or viewer in the first words | Generic curiosity bait unrelated to the payoff |
| The payoff honours the title | Title over-promises; the video under-delivers |
| One ask, matching the video's | A caption ask competing with the spoken one |
| Tags describe what is shown | No tags, or tags for topics the video never touches |

## Common failures

- A clever title that hides the topic, so the right viewer never recognises it.
- A caption that retells the video instead of adding a reason to watch or act.
- Hashtags unrelated to the content.
- Key words pushed past the truncation point by emoji or greetings.

## Fixes

- Write the new title or caption opening line itself, grounded in what the video actually shows;
  never invent a claim, result or endorsement for it.
- Align: "the caption promises a recipe, the opening shows a kitchen fail; open the caption on the
  fail, then the fix."
- Cut the competing ask from the caption, or make the caption carry the one ask.
- Replace tags with ones naming what is on screen.

## Evidence this needs

- `content_metadata` (title, caption, tags, cover references, status). Without it, say the
  packaging could not be read, naming `content_metadata`.
- Frames of the opening, to compare packaging against the first frame.

## Do not claim

- Click-through rate, impressions or how the packaging performed: none is measured here.
- What the cover looks like, or whether it works.
- That a tag, a keyword or a caption length affects ranking.
