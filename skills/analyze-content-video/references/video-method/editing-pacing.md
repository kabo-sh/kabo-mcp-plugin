# Editing and pacing

Deeper method for the default card's `pacing` and `duration`, and for how cuts carry `structure`.
Use it when the creator asks about the edit, the rhythm, whether it drags or feels rushed, jump
cuts, transitions, or what to trim.

## Measure first, judge after

Put the countable things down before any opinion, each with the measure it came from:

- **Cuts and shot lengths**: `media.probed.shots` (cut times, each shot's duration). Compute the
  cut count per section (opening, body, close) rather than one average: a fast opening and a slow
  middle average out to "fine".
- **Dead air**: `media.probed.silence` spans under the speech floor, especially a silent lead-in and
  a trailing silence.
- **Held pictures**: `media.probed.freeze` spans. A freeze that overlaps a silence at the end is a
  still-logo or end-card ending.
- **Information per span**: from cues and frames, what new thing each span adds.

Pacing is the rate of new information, not the rate of cuts. A fast cut that repeats the same
picture adds nothing; a long take of a hand doing something difficult can be the best span in the
video.

## Standards

| Strong | Weak |
|---|---|
| Each cut arrives when a thought or action completes | Cuts on a timer, mid-gesture or mid-word |
| Pauses kept where they sell a reveal or a joke | A pause before every sentence |
| Shot length follows what the shot carries | Every shot the same length regardless of content |
| Visual change carries information (an insert of the noun, the step, the result) | Zooms and shakes added for movement alone |
| The rhythm changes at the turn (slows into a reveal, speeds through setup) | One rhythm from start to end |
| Ends on the payoff | A tail of freeze, logo or silence |

## What to cut, what to keep

General practice for short talking videos (not measured from this video):

- **Cut**: false starts (keep the clean take), repeated takes of the same line, filler words,
  breaths before lines, pauses longer than about a second that carry nothing, wind-ups before the
  point, a recap of what was just shown.
- **Keep**: short natural pauses between sentences, a pause before a reveal or punchline, a
  reaction that tells the viewer how to feel, a hold long enough to read proof or text.
- **Jump cuts** in a talking video are accepted and keep it moving; a jump cut that leaves the face
  in nearly the same place reads as a glitch. A slight reframe (punch-in) between takes hides it.
- **Audio leading or trailing the picture** (the next line starting before the cut, or a sound
  carrying over it) smooths a cut. These can be heard, not seen: claim one only from viewer notes
  or measures that support it.
- **Transitions**: a hard cut is the default. A designed transition (whip, mask, match on action)
  earns its place when it connects two shots by motion or meaning; a stock wipe between
  unrelated shots slows the video down.

## Common failures

- A slow body after a fast opening: measured shot lengths jump after the hook window.
- Dead air at the start (the first sound after a silent lead-in) or a long tail after the payoff.
- Proof or on-screen text cut away before it can be read.
- Speed applied evenly: setup and payoff given the same time.
- Over-cutting a story: a moment that needed to land is chopped into pieces.

## Fixes

Each fix names the span, what to remove or move, and what stays:

- "Trim 0:12–0:15 (the pause and 'so basically'); start the next shot on 'the trick is'."
- "Hold the result at 0:27 for about a second longer so the number can be read."
- "Cut the end card after 0:48; end on the reveal."
- "Punch in between the takes at 0:20 and 0:24 so the jump reads as intentional."

## Evidence this needs

- The measure (`media.probed.shots`, `silence`, `freeze`). Without it, say the cuts were not
  measured; place each visible change between the two frames that bracket it and mark the spans
  between frames unconfirmed.
- Never count cuts or measure shot lengths from viewer observations or prose descriptions of
  frames: they arrive per observation, not per cut.
- Cues for false starts, filler and repetition.

## Do not claim

- Exact cut counts or shot lengths without the measure.
- That cuts land on the beat: cut times are not beat times.
- That pacing caused viewers to leave: no retention curve here.
