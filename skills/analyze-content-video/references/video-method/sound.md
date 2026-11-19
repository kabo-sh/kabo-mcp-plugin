# Sound

Deeper method for the default card's `audio` and `audio_mix`, and for sound's part in the opening
and the payoff. Use it when the creator asks about the music, the voice, the mix, sound effects, or
whether the sound fits.

## Where sound evidence comes from

Judge sound only from what was heard or measured for this video:

- **Measured**: `media.probed.loudness` (lead-in silence, first audible time, mean and range of the
  momentary loudness), `media.probed.silence` spans, and the file's encoding block when present
  (integrated loudness, true peak, loudness over spans). Measures say when and how loud, never what.
- **Heard**: viewer observations about sound (music present, its character and energy, speech,
  sound effects). Notes, not verdicts: use what they heard, not their adjectives of quality.
- **Declared, not heard**: `audio_attribution` (original sound or not, a track's title and artist).
  It says which track was used, never how it sounds or how it sits in the mix.
- **Transcript origin**: words with `transcript.origin` `speech_recognition` on a video using an
  existing track, or where no one is seen speaking, may be lyrics.
- **Measured on this machine** (a local file): `media.audio`. Its `findings` are measurements that
  cleared a threshold -- level against the feed target, true peak, a weak opening, level jumps,
  silences, wordless stretches, a bed under the voice or none, ducking, a pulse and its tempo, cuts
  on onsets. Its `listen_check` is what no measure settles. See *A local file's sound* in
  `references/local-file.md`.

A transcript is heard words only. With neither a measure nor a heard note, say the music and mix
were not analysed and stop there; the words may still be used as words.

## Measurement first, inference second

Say the measured fact, then what it implies: "integrated -27.9 LUFS, so the platform will lift it
about 14 LU and the room tone with it", not "the audio is too quiet". A measure that did not clear
its threshold supports no claim, however suggestive the number.

**Listen-check, never findings.** Genre, mood and fit; which track it is, whether it is trending or
licensed; voice timbre; how good a sound effect is. No measure here can settle them: when the
creator needs them, list them as things to listen for, separate from the findings.

## Six questions

1. **Original sound or an existing track, and what is it buying?** An existing track borrows
   recognition and a mood the audience already knows; an original voice carries the creator's
   personality. Whether a track is trending needs usage data, which is not available here.
2. **Is sound working in the first second?** A silent lead-in or a slow fade-in leaves the opening
   to the picture alone. Check the measured lead-in; on a short, a fraction of a second of silence
   at the start is already noticeable.
3. **Does energy rise where the video pays off?** A broad match or mismatch between the music's
   development and the video's turn is judgeable from listening notes. An exact second is not.
4. **When speech carries the point, does the music stay under it?** Music that competes with words
   is the fix, whatever the track. General practice: music under speech sits well below the voice
   (a common starting point is around 15–20 dB under speech peaks), rising in gaps.
5. **Do sung words compete with on-screen text or speech?** Only when it was actually heard that a
   song with vocals plays under talking or reading.
6. **Does the end sound like the start, on a video meant to loop?** Only when it was heard clearly;
   do not judge loop seams from impressions.

## Mix and delivery

- **Loudness cliff**: a track that ends before the video does leaves a quiet tail; it shows in
  loudness over spans or as a trailing silence span.
- **Trailing silence** after the last line or the payoff: the video ends on nothing.
- **Overall level**: general practice for feed delivery is around -14 LUFS integrated with true
  peak no higher than about -1 dB. A true peak above zero distorts after the platform re-encodes.
  The momentary-loudness mean is a summary, not integrated loudness; compare only the integrated
  figure with a target.
- **Sound effects**: one at a reveal or a transition directs attention; one on every cut becomes
  noise. Judge only effects that were heard.
- **Voice quality**: room echo, wind, distortion, a voice much quieter than the music. From heard
  notes only.

## Standards

| Strong | Weak |
|---|---|
| Sound starts with the picture, or a silence is clearly deliberate | A silent or slowly ramping first second |
| Speech always on top when it carries the point | Music competing with words |
| Music's energy broadly develops toward the payoff | Energy flat, or peaking somewhere unrelated |
| Track chosen for a reason the video uses (recognition, mood, a lyric moment shown on screen) | A track that would fit any video |
| Ends cleanly with the last beat | A cliff, a cut-off note, or silence at the end |

## Fixes

- "Duck the music under the voice from 0:03 to 0:20 and bring it back up for the reveal at 0:21."
- "Trim the 0.6s of silence before the first line, or open on a sound."
- "Extend or loop the track to the end, or fade it out with the last line at 0:44."
- "Put one sound hit on the reveal at 0:12 and remove the swooshes on the other cuts."
- Aligning a specific cut with an audible hit is a valid suggestion: it is a change, not a
  measurement.
- Recommend a different track only with the problem it solves (mood mismatch heard at a time,
  vocals competing with speech).

## Signs a judgment did not come from listening

- It would be equally true of any video using a track with that title.
- It names a genre or mood no heard note describes.
- It places a cut on or off the beat from an impression.
- It recommends swapping the music without naming the problem the swap solves.

## Do not claim

- **A song, artist or remix identified by ear.** A title comes from metadata, on-screen text or
  speech, and is cited as that.
- **Lyrics**, quoted or paraphrased, anywhere in the answer. Sung words are not the video's
  message.
- **That cuts do or do not land on the beat**, unless a beat measurement exists for this video
  (`media.audio` finding `cuts_on_sound`). Cut times are not beat times, and no finding is not "off
  the beat".
- **An exact second where the energy changes**, from listening notes alone.
- **That a sound is trending** or helped distribution.

These were the claims that came out differently when the same video was listened to twice.
