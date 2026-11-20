# Craft teardown

Read this file whole when the creator asks how a video was made — see *Which question is this* in
`SKILL.md`. It is this mode's workflow and what it may not claim; the shot method itself is the
`craft-shot-description` card in `references/video-method/`, which the analysis brief carries.

A creator watched something and wants to know how it was made. Answer the question they asked, in
the shape that question has. Everything `SKILL.md` and `references/evidence-reading.md` say about
evidence holds here: frame sampling, transcript handling and when to stop waiting are shared. What
differs is what the evidence is read *for*, and that there is no fixed layout waiting at the end.

**The diagnosis pipeline does not belong to this path.** A teardown writes no `video_analysis.json`,
no `VIDEO_DIAGNOSIS.md` and no `CreatorTaskResult`. Its fixed steps are observing, building the
evidence and preparing the brief. Write `report/craft-teardown.md` yourself; there is no renderer
to look for.

## Workflow

1. **Write `analysis/craft-request.json` before retrieving anything**, following
   `references/craft-request.schema.json`. It carries the creator's question verbatim and whether
   a video was named. Written first, it records what this run was asked; written last, that can
   only be guessed from what the run produced.
2. **Get the evidence before forming an opinion**, with the observation and evidence steps of
   *Analysis* in `SKILL.md` (mode `craft_teardown`). A video whose transcript never arrived is a
   video whose argument was never read.

   For a public URL with no ownership statement, record `subject.whose=unknown` in the craft
   request and `source.subject_state=unknown` in its evidence request. Keep `owner_data` null,
   `owner_metrics` skip and no account baseline; unknown does not mean third party. Do not hold
   public evidence or a transcript export while asking about ownership. A local file keeps the
   state the creator declared.

   **Then look at the frames.** They arrive as references — an id, a second, a checksum — and a
   reference is not a picture. Read the frames with `read_research_data_artifacts` as *Reading the
   frame bytes* in `references/evidence-reading.md` says, and look at the images: the ones the read
   shows you, or the fetched files you open. Framing, shot size, camera movement, type, colour and where the eye
   goes all live in the picture. Read only the words and you have written what the video *said*,
   filed under a question about how it was *made*.
3. **Measure before you claim.** The media call's `measure` operation measures in one job: shot
   boundaries and how long each runs, per-shot brightness, where the track goes quiet, loudness
   every tenth of a second, held frames including a trailing still, and the real frame size with
   its bars and the share of a phone screen actually filled. Measurement is its own readiness
   question, answered by the run's one `get_research_capabilities` check. When it is not
   available, say the numbers were unavailable and carry on from frames and transcript.
4. **Prepare the brief and write.** `prepare_analysis.py --mode craft_teardown` puts the shot
   method (the `craft-shot-description` card: the five points per shot, organising around the
   question, ranking, what one person can do alone, and the two levels of sourcing), any topic card
   such as `sound`, and the rules below into `analysis/brief.md`. Read it whole, then write the
   report.
5. **Check and deliver.** End the report with one line, in the creator's language, saying what it
   rests on: how many frames and at what spacing, whether the transcript and the measurements
   were there, and whether the sound was heard. Then run
   `python3 <skill directory>/scripts/validate_creator_report.py report/craft-teardown.md --emit-report`
   from the run directory: it refuses internal names and prints the report to deliver; on an
   error, fix the report and run it again.

## What may not be claimed in a teardown

- **No performance, no prediction.** Not how this video did, not how the creator's next one will
  do, not what a change is worth in views. This mode holds no metrics and no baseline. A creator
  who wants both asked a diagnosis question.
- **Give the craft whole: the tool, the setting and the command.** Encoding, bitrate, loudness
  target, frame size, the program that does it — these are the trade, not incidental detail.
  `H.264 at 10–12 Mbps, audio 192 kbps AAC, loudness to -14 LUFS` is what a creator needs to act;
  "export at a good bitrate" helps no one. Source every figure: read off this video, or visibly
  general practice.
- **Name the feature; do not invent the click path.** "CapCut calls these text templates" is
  stable. Which tab or sub-menu is not known here and moves between versions.
- **Admit the gaps.** Gear to buy, phone shooting technique and editor presets have no source in
  this Skill. Answer what the video supports and say which part is general practice. A guessed
  menu path costs the creator an afternoon.
- **Borrow the mechanism, never the wording.** Say which pass transfers to someone with no
  audience and which only works because that creator already had one. A teardown is not a repair
  order for somebody else's published video.
- **Do not rewrite the question.** `analysis/craft-request.json` carries the creator's own words.

### When no video was named

"What should I buy first", "how do I light this with one phone" — answer from general practice and
say plainly that no video was read. Do not go and find a video to look at: footage nobody asked
about is not evidence about their question.

### Before delivering

No validator checks this report. Hold two things yourself: every figure says where it came from,
and no number is stated about this creator's own results that nobody measured.

## What this mode writes

`analysis/craft-request.json` before retrieval and `report/craft-teardown.md` at the end. The
answer is the prose, shaped by the question rather than by a schema, closed by the one line on
what it rests on and checked by `validate_creator_report.py` before it is delivered.
