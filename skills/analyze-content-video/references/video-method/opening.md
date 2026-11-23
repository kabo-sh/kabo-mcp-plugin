# Opening

Deeper method for the opening stage of the default card: `first_frame_promise`, `visual_hook`,
`spoken_hook` and `text_overlay`. Use it when the creator asks about the hook, the first seconds,
why people scroll past, or wants new openings.

## The opening is one decision

Picture, sound and text arrive together and make one promise. Judge them together:

- **What the first frame shows** with sound off.
- **What is first heard**: a line, a sound, music, or a silence. Check when sound starts
  (`media.probed.loudness` first audible time and silent lead-in); a voice that starts at 1.2s
  leaves the first second to the picture alone.
- **What the first text says**, if any.
- **What the three together make the viewer want to know.** Write that question in one sentence.
  If you cannot, the opening has not made one.

The window is `frames.sampling_plan.hook_window_s`: about three seconds on a short. Long-form has
fifteen to thirty seconds to establish the promise and different tools (a cold open, a preview of
the payoff, a stated agenda); do not apply short-video patterns to it.

## What to look at, in order

1. **Who the first frame is for.** Can the intended viewer recognise their situation, problem or
   interest within a glance? A specific scene ("a cracked phone screen in a hand") selects a
   viewer; a generic one ("a person talking in a room") selects nobody.
2. **Is something happening.** Action in progress, a result on screen, a contrast, a face reacting
   to something we cannot see yet. A setup that waits for the first line to make sense loses the
   sound-off viewer.
3. **The first sentence.** Does it state the point, the problem or the surprising claim, or does it
   introduce, greet or give context? Find the sentence in the cut that states the point; on the
   creator's own video it often already exists at a later time.
4. **Text and speech agree.** The headline and the first line should be the same promise from two
   angles, not two promises and not a transcript of each other.
5. **The bridge.** How the opening connects to the body. A strong device (a joke, a staged
   situation, a shocking image) that never connects to the content stops viewers and then loses
   them. Keep the device; fix the bridge.
6. **The promise is paid.** Note what the opening commits to and check the payoff stage of the
   default card for whether it is kept. An opening is only as good as the promise it can honour.

## Strong against weak

| Strong | Weak |
|---|---|
| Result or tension visible in the first frame | Logo, title card, greeting, establishing wide |
| First line names a specific problem, number or claim | "Hey guys", "so today", backstory first |
| Text adds the stakes or the "for who" | Text repeats the speech word for word |
| Motion or change before the first second ends | A static frame that settles before anything happens |
| The question it raises is answered later in the video | A question the video never answers |

## Common failures

- **Slow start**: the point arrives at second four, after a greeting and context.
- **Wrong promise**: the opening promises drama, the body is a calm tutorial (or the reverse).
- **Over-promise**: "this will change your life" paid with a modest tip; the viewer feels tricked.
- **Hook unrelated to the topic**: a pattern interrupt or meme that stops the scroll and then has
  to be abandoned.
- **Sound-off failure**: everything depends on the first words and nothing is on screen.
- **Answer given away**: the opening states the payoff so completely there is nothing to wait for.

## Fixes

- **Move the strongest moment forward.** Name its time and what is on screen there, and say how to
  bring it to the front: cut to it at 0:00, then rewind ("here's how I got here").
- **Cut the wind-up.** Name the cue where the point starts; everything before it goes.
- **Rewrite the first line** as one sentence the creator can say: specific, in the viewer's words,
  under ten words where the format allows. On someone else's video, write a new line that shows the
  mechanism, never their wording.
- **Rewrite the headline** to carry the stakes, the number or the viewer it is for.
- **Add a first sound on purpose**: a line, a sound effect, or a deliberate silence, not a slow
  ramp.

## New openings from the opening method

`references/hook-core/` holds a catalogue of short-video opening patterns and the material each one
needs. It is method, never evidence about this video. Do not open those files directly:
`scripts/prepare_video_hook.py` reads them (once for the catalogue, then once with one to three
`--pattern-id` values for the patterns that fit). Use it only for a short video's opening.

- **Choose by material.** A pattern whose material the creator does not have (a result to show, a
  comparison pair, a prop, a series format) is a preparation task, not an opening. Say what to
  prepare.
- **Write each new opening as one decision**: the first frame, the first sound and the question
  their combination raises, plus the first words when it is spoken.
- **On their own video**, prefer an opening already in the cut. **On someone else's video**, the
  pattern is the mechanism that transfers; the opening is for the creator's next video.
- Pattern ids and names stay internal; describe the opening, not the catalogue entry.

## Evidence this needs

- Frames across the hook window (sampled densely there by default). Typography and framing claims
  need a frame.
- The first cues and the loudness lead-in. Without a transcript, say the spoken hook was not read.
- Viewer observations inside the hook window, for motion and sound between frames.

## Do not claim

- Where viewers left, or that the hook "held" or "lost" viewers: no retention curve here. A skip
  rate or average view duration bounds the story; it does not locate it.
- That a pattern from the catalogue is what this video did, or why it performed.
- A first-frame judgment from a thumbnail address: no cover pixels are seen.
