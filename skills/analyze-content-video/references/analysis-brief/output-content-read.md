Answer in a few short paragraphs, from the evidence in section 3 alone: what the video shows, what
is said or written in it, and what it is about or asking for. Put the timestamp beside each point
and say whether it was seen in a frame, read from on-screen text or the caption, heard, or reported
by a whole-video note.

Before repeating heard words as what the video says, decide whose words they are, from section 3's
*Sound* lines:

- When `audio_attribution` names an existing track (`uses_original_audio` false, or a song or
  artist name), the words may be that track's lyrics.
- When `audio_attribution` is unavailable, decide from what the run has: sound markers in the cues
  (`[Music]`, `♪`, or the same word in the video's language) beside the words; whether any frame
  shows someone speaking to camera, or the words describe what is on screen; and the measures or
  whole-video sound notes when they exist. Markers beside the words, or no one seen speaking while
  the words do not match the picture, point to a track.

When the evidence points to a track, the words may be that track's lyrics: say the sound is that
track, never summarize its words as the video's message, and build the answer on the frames,
on-screen text and caption. When it stays unclear, say the words may be sung and keep them apart
from what the video itself claims.

Write the answer to `analysis/answer.md` at its absolute run path, then run this one command; it
records when the answer was finished and how long it is, and decides nothing:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/acv_timing.py answer --run '<run directory>' --answer analysis/answer.md
```

Then reply with that answer as written. This mode writes no report and runs no other step; it is
not a diagnosis, so never call it one. Offer a diagnosis or craft teardown once at the end when the
creator may want one.
