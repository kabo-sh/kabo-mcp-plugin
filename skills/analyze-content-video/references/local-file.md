# When the video is a file on this machine

Read this file whole when the video is a file on the creator's own machine (`source.acquisition`
is `local_file`). Everything in `SKILL.md` still applies; this is what differs.

A creator asking about a cut they have not published has no link to give, and that is the ordinary
case for the question they most want answered: is this ready. The file is right there and this
package reads it.

**Whose file.** `unknown` is the public-link-only scope, so a file on this machine is never
`unknown`: take `own_unpublished` or `own_published` from the creator's statement, or `third_party`
for someone else's video, and ask when nothing says which. A file has no caption, counts or
comments: when the creator asks how the video performed, ask once for its published link.

1. **Ask what the machine has, before committing to it.**
   `cd '<run directory>' && python3 <skill directory>/scripts/probe_media_tools.py --require ffmpeg,ffprobe`. Exit 3 means the tools are not
   installed: **say so and install nothing.** Hand the creator the one line the script printed and
   carry on with whatever evidence the run does have — a subtitle file, what they told you, the
   platform they are making it for. A run that stops dead because a tool is missing has done less
   for them than one that names the single command that would fix it. Pass each `gaps[].limitation`
   through to the builder with `--limitation`.
2. **Read the file.**
   `cd '<run directory>' && python3 <skill directory>/scripts/extract_local_frames.py --media <absolute path> --out-dir analysis/frames
   --artifact analysis/local-media.json --hook-window-s <3 for a Short, 15–30 for long-form>`
   (sound is measured in step 5, not here). It samples by the connector's plan
   (120 frames at most: the first 50 seconds densest, a frame just after each cut, and the dense
   windows the method cards put in `analysis/method.json`) and writes the same frame shape, so
   everything in *Frame sampling* in `references/evidence-reading.md` applies unchanged — `frames.origin`
   and each frame's `source` included. It also writes **contact sheets**: four frames to an image, two
   by two in time order, each tile at near the frame's full detail, listed under `contact_sheets` in its
   summary with the seconds they span (each tile is captioned with its second where this machine's
   ffmpeg can draw text; otherwise `frames.contact_sheets[].tiles` in the artifact maps each tile, by
   `row` and `col`, to its frame and second). **Read every sheet: the sheets are the frames.** Then
   open a single frame from `frames.items[].path` wherever a detail on a sheet is unclear — small text,
   a number, a face — and before quoting it. When the summary has `frames_not_on_a_sheet`, the sheets
   stopped early (the byte cap or the time ran out): open the frames after the last sheet one at a
   time. Cite the frame, never the sheet. **Locally sampled frames are real pixels and are read exactly like any other frame:
   open them, quote what is on them, cite them the same way.** Nothing in the analysis branches on
   where a frame came from; the ledger records that, and the ledger is not the report.
3. **Measure, in a command of its own**, whenever the question touches pacing, cuts, pauses or the
   ending: `cd '<run directory>' && python3 <skill directory>/scripts/extract_local_frames.py --media <the same absolute path>
   --artifact analysis/local-media.json --signals-only`. Frames place no cut shorter than their
   spacing and hear no pause; the measurement does both with the connector's own thresholds and adds
   them to the artifact step 2 wrote, landing in `media.probed` exactly as a published video's would.
   **Never fold it into the frame command.** Sharing a command means sharing its time, and a
   measurement that runs out or fails on its own leaves the frames already written untouched.
4. **Get the words** — see the three tiers under *Getting the words* below. A local file is read
   here only: it is never uploaded, and no Kabo tool sees it.
5. **Measure the sound** — always for a diagnosis, and for any question that touches sound, music,
   voice or pacing: `cd '<run directory>' && python3 <skill directory>/scripts/measure_audio_local.py --media <the same absolute path>
   --artifact analysis/local-media.json`. Run it after steps 2 and 4: it adds `media.audio` to the
   artifact step 2 wrote (a later frame command replaces that artifact, so measure again after one),
   reads the cuts that step found, and reads `analysis/local-transcript.json` to tell speech from
   other sound. Nobody listens to a local file whole, so this is the sound evidence: loudness over
   time, silences, where words are and what sits under them, a pulse, whether cuts land on onsets.
   See *A local file's sound* below for how to use it.
6. **Then build**, with `--local-media analysis/local-media.json` and, where there is one,
   `--local-transcript analysis/local-transcript.json`.

### A local file's sound

`media.audio.findings` are the only sound claims a local file supports, and each one already
cleared the threshold printed beside it. **State the measurement first, the inference second**:
"the first 2 s are 9 dB quieter than the rest, so the opening leans on the picture", never the
inference alone. A measure with no finding stays a number: do not round it into a claim.

`media.audio.listen_check` is a separate list for the creator, never findings: what the music is
and whether it fits, which track it is, whether it is trending or licensed, how the voice sounds,
whether an effect is any good, and anything the measurement flagged as ambiguous (words that may
be sung, a stretch with no recognised words that moves like speech). Hand these over as questions
to listen for, in one short list after the findings. A diagnosis report already carries one line,
written by the result builder, that asks the creator to listen: do not write another into the view.

Without numpy, onsets, pulse, cut alignment, stereo width and the syllable-rate test are in
`skipped`; without a transcript the map has no speech in it. Both are unmeasured, not absent. When
`measured_until_s` is present, the sound past that second was not read.

### When the file is long or heavy

Some hosts end a command after about a minute and keep nothing it wrote, so every command above
stops itself at `--deadline-s` (40 seconds after it started, by default) and writes what it has.
A large or high-resolution file can need longer than that, and the output says what was left out:

- **Frames** — the opening and the closing frame are written first, so running out of time thins
  the body; the summary counts the skipped frames and a limitation gives the widest gap left.
- **Measurement** (the signals in step 3 and the sound in step 5) — each reads the file from the start and stops at the deadline. `measured_until_s`
  in its summary names the second it reached, and a limitation in the artifact says the rest was not
  read. Pass that on: past that second, cuts and pauses are **unmeasured, not absent**. Place a
  change there between the two frames that bracket it, as you would with no measurement at all.

Raise `--deadline-s` only where the host lets a command run longer. Rerunning the same command
with the same deadline gets no further.

### Where the file is allowed to be read

**Some hosts deny whole folders, and a denied file looks exactly like a missing one.** A sandboxed
host commonly puts the personal folders entirely out of reach — Documents, Desktop, Downloads,
Pictures, Movies, Music, and external volumes with them — which is precisely where creators keep
video. The path is real, the file is there, and the read fails.

`extract_local_frames.py` and `read_subtitle_file.py` tell the two apart and **exit 4 for a denied
location**, separately from exit 2 for a path that does not exist. Treat them as different answers:

- **Exit 2 — no such file.** Ask the creator to check the path. They may have renamed or moved it.
- **Exit 4 — the host will not read there.** This is not the creator's mistake and not a missing
  file, and telling them the file does not exist sends them hunting for something that is not lost.
  Say the analysis could not open it from that folder, and ask them to put a copy somewhere outside
  those folders — a folder they make in their home directory is enough — and give that path. Then
  carry on with whatever else the run has.

Never report a denied read as an absent file, and never tell the creator to change a setting: this
is the host's boundary, not something they configure.

### A local file is the master, not what viewers received

On this path `media.encoding` is read off the creator's own export. Every platform re-encodes on
upload and normalises loudness to its own target, so the integrated loudness, the bitrate and the
frame size say what was **sent**, not what was **heard or seen**.

Name which one a recommendation is about. "Your master sits at −26 LUFS and the platform will lift
it to about −14, so the quiet passages will come up more than you expect" is usable. "Your video is
at −26 LUFS, too quiet for the feed" is a claim about a file no viewer ever played, and a creator
who tunes to it has tuned to a number that never reached anyone.

**True peak is the exception and travels either way**: above zero is exactly what a platform's own
re-encode turns into audible distortion, so it is worth saying on the master.

## Getting the words

**A file on this machine has no platform captions to fetch, and three tiers in order:**

1. **Platform captions** — only where the same cut is also published and the creator points at the
   post. That is a `public_url` run and the media call's `transcript` operation is the whole path, as *Transcript* in `references/evidence-reading.md` says.
2. **A subtitle file the creator supplies** — `.srt` or `.txt`, read by
   `cd '<run directory>' && python3 <skill directory>/scripts/read_subtitle_file.py --subtitle <file> --artifact analysis/local-transcript.json`.
   **Ask for one before giving up on the words.** A creator who cut with captions already has this
   file, and unlike anything a machine hears it carries their own wording — `transcript.origin` is
   `creator_supplied` and that is what lets you quote a line as what they actually say. Its timings
   were never checked against this cut, so quote the words freely and say once that the timing is
   the file's claim about the video rather than a measurement of it.
   **Where the host can transcribe the attached file itself**, that is the same tier with a machine
   behind it: save the cues it returned, timings unchanged, as `analysis/host-transcript.srt` and
   read that with `--origin speech_recognition` added. The origin is the point — those words are
   what the analysis heard, quotable as heard but never as the creator's exact wording.
3. **Local speech recognition** — only when `probe_media_tools.py` reports `faster_whisper` as
   `available` (the package and its speech model are both on this machine):
   `cd '<run directory>' && python3 <skill directory>/scripts/transcribe_local.py --media <the same absolute path> --artifact analysis/local-transcript.json`,
   adding `--language <code>` when the creator states the language. It writes the same artifact as
   the subtitle reader, with origin `speech_recognition`: quote the words as heard, never as the
   creator's exact wording. When it says it stopped at its time limit, run the same command again
   until it reports `"complete": true`; what it never reached is unread, not silent.
   `no_speech_detected` (music or silence only) is an answer, not a failure. When the probe reports
   it `absent` or `model_missing`, or the script exits 3, **install nothing**: give the creator the
   one install line it printed and carry on without the words. This Skill never runs an install and
   never downloads the model.

When none of the three produced words, say the argument was never read — the same sentence a
connector run says when its transcript did not arrive — and carry on from frames and metadata.
