# Diagnosis runtime

Read this whole before the first analysis command in `SKILL.md`. Part 1 holds what each command
depends on; Part 2, *Reading the evidence*, covers frames, transcript, metadata and cover for every
mode. For a diagnosis, every step before `finish_diagnosis.py` leaves it unfinished; only the final
validated report closes it.

## 1. The request

`begin_analysis.py` (analysis step 2 in `SKILL.md`) writes `analysis/video-analysis-request.json`
for a link or an attached file exactly as `prepare_link_request.py` does, from the same arguments:
it preserves the creator's original link, the chosen ownership state and confirmation, and leaves
an unresolved post ID null. For a public link, `<platform>` is the link's platform (read from the
link when the support list knows it), and `--mode` (the mode from *Which question is this*) sets
the call ceiling for that mode. The request on its own, outside a begin step:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/prepare_link_request.py --url '<link exactly as given>' --platform <platform> --subject-state <chosen-state> --mode <mode> --confirmed-by-user --output analysis/video-analysis-request.json
```

Write the request by hand from `references/video-analysis-request.schema.json` only for a local
file (`references/local-file.md`).

Use the linked-media helper **only when an input actually declares
`schema_version: linked-media-evidence.v1`**, directly or inside its `linked_media` field. A normal
connector envelope (`schema_version: 1.0`) does not qualify, and never call the helper to find out.
`<chosen-state>` is the ownership state from analysis step 1 (`--max-connector-calls <n>` replaces
the mode's default ceiling when the creator approved another):

```sh
cd '<run directory>' && python3 <skill directory>/scripts/prepare_link_request.py --envelope snapshot/<file>.json [--envelope ...] --subject-state <chosen-state> --mode <mode> --confirmed-by-user --output analysis/video-analysis-request.json
```

Omit `--confirmed-by-user` unless that confirmation exists. Do not manufacture a linked-media
packet from connector fields.

**Platform of a file.** An attached or local file names no platform, and its platform only shapes
format expectations (how long the opening has, short-form or long-form pacing). When the creator has
not named one, never stop to ask: use the one the conversation already establishes (the selected
account, an earlier link or answer); without one, choose the platform whose format fits the file (a
short vertical clip as short-form, a long horizontal video as YouTube long-form). Say in one
sentence, before the report or answer, which platform's format the analysis assumed and that the
creator can name another.

A video the creator attached in Kabo chat (`kabo-file:<id>`) has no packet; the media tool reads the
stored file. `<platform>` is the one it was posted on or is made for, as the creator says, else as
*Platform of a file* above says; any ownership state may apply:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/prepare_link_request.py --file-ref 'kabo-file:<id>' --platform <platform> --subject-state <chosen-state> --mode <mode> --confirmed-by-user --output analysis/video-analysis-request.json
```
 A transcript does not establish the content ID: take it from
metadata already read or from the packet, and keep a missing identity missing, never a guessed
short-link ID. A summary of the video written by someone else is not a frame set or evidence.

## 2. Building the evidence

Every response this request produced must be staged and persisted into this run's `snapshot/`
before the builder runs. With `--snapshot-root`, the builder binds this run's staged images to
canonical frame IDs by SHA256 and writes matching copies under portable filenames in `analysis/`.
Read the paths in `ContentEvidence`, not the staging filenames. Build the evidence once: in a run
begun with `begin_analysis.py` the observation's last command builds it from every envelope then in
`snapshot/` and prints the brief. It builds again only with `--replace` (as the observation prints
it), when an envelope or a per-run flag below comes in after that build; then prepare the brief
again.

Per-run flags, on the evidence-building command only:

- `--viewer snapshot/whole-video.json` when the observation printed it: the whole-video result,
  already reduced to its timestamped notes and transcript. Its notes become `viewer_observations`
  (cited by their ids) and its transcript fills the transcript only when none was fetched.
- `--song snapshot/song.json` and `--comment-summary snapshot/comment-summary.json` when the
  observation printed them: the one song recognition call of a find-the-song request or of a
  diagnosis of a link, and the one comment summary call of the `audience-response` card, as they came
  back (or why they did not). A diagnosis names a recognised track only in the report's closing line,
  which the final step adds.
  They become `song_identification` and `audience_response`; a call that brought nothing is a
  limitation line, never a failure to retry.
- `--pending <operation>=<job id>` or `--deferred-incomplete <operation>=<job id>` for a deferred
  job without a terminal result (see *When to stop waiting* in Part 2 below).
  Persist only a job's terminal envelope.
- `--owner-metrics <file>` with the `owner_metrics` block read from the creator's own export, on an
  owned video.
- `--published-at` when the creator states a publish time the metadata lacks.
- `--limitation` for a gap the envelopes do not show.
- On a local file, `--local-media analysis/local-media.json` and, where the creator supplied one,
  `--local-transcript analysis/local-transcript.json`. An unpublished draft is read by the local
  scripts, never by a tool, and the request must still name the platform it is made for
  (*Platform of a file* above).

Never write or edit `ContentEvidence` fields yourself. The builder derives the read-only
`data_note` from recorded source, sampling and citation facts; it never treats extraction or
citation as viewing.

Before writing the judgment, read `analysis/content_evidence.references.json`. Its `evidence_id`
and `evidence_sha256` bind it to that evidence; use its exact `evidence_refs` for observation
citations, never guessed paths or staged filenames. It lists legal references, not observed facts:
read each cited value and its availability; missing or null remains unavailable. Creator-view
cards cite `observations.<observation_id>`.

**Still-image posts.** Open the available `ContentEvidence.images.items[].path` files in `index`
order. Cite their `image_id` with observation `basis: image`, leave `t_start_s` / `t_end_s` null and
name the slide position in prose. Missing positions and unknown completeness stay missing or
unknown. Still images have no audio timeline: do not fetch video frames or invent seconds for them.

Use source moments only at recorded precision, not as exact cut boundaries. `prepare_analysis.py`
passes `source.subject_state` from the request to `compute_deterministic.py`: `own_unpublished`,
`own_published`, `third_party` or public-only `unknown`, as chosen in analysis step 1.

## 3. The judgment

The judgment schema in section 7 of the brief (the rules the run names: `references/diagnosis-rules.md`
for a diagnosis, with any topic cards the brief prints, otherwise `analysis/rules.md`) projects the
model-authored fields from the final analysis schema. Read it whole and write only this partial
judgment, using its shapes and enums. Keep `revisions` empty for `third_party` and `unknown`, and
cite exact refs from the reference index. The composer supplies evidence lineage, completeness and
the unchanged `deterministic.json` block.

After saving `analysis/video_judgment.json`, run `--check-judgment-refs` (a read-only step).
Advance only on `status: ready`. For `needs_correction`, read the named evidence values, correct
only those citations once and rerun the check once. If still not ready, stop and report the gap.
Never guess aliases, fetch to fill a citation or reopen a closed run. Index, hash, I/O and
execution errors are fatal, not input corrections.

On `ready`, read `grounding_review` through `packet_end`; the same output carries `view_contract`
for the creator view (section 4). It places the referenced frames, images
and literal speech beside the authored judgment; it does not certify pixel interpretation. Compare
each objective observation and report-bearing judgment with the images already displayed. A cue
start does not establish first visual appearance; a legal frame ID does not prove the described
object. If a statement is unsupported, use the **same one correction opportunity** to narrow or
remove it and rerun the check once — never a separate loop; use the `view_contract` of that last
check. If that opportunity is spent, stop or keep the gap explicit rather than invent a claim.
After this review, keep the saved judgment unchanged.

## 4. The creator view

The ready reference check's `view_contract` holds the author fields, the current canonical
observation references and the display-column limits (`build_creator_result.py
--print-view-contract --observations-from analysis/video_judgment.json` prints the same contract
on its own; it is not a step of a run). Read it completely; what the fields should say is
`references/diagnosis-report.md`, which section 7 of the brief already
carries whole, so it needs no read of its own. Omit the read-only `data_note` and `listen_note`. Every figure in the view, including
next-edit timings, must trace to the composed analysis or evidence; rounding and magnitude notation
are allowed and clock times are not numeric claims. For a new duration that is editorial advice,
give a qualitative instruction anchored to a verified moment. Never add observations or alter the
saved judgment to manufacture grounding. Write `analysis/creator_view.json`, then run
`finish_diagnosis.py --check --finish-if-ready`: it runs every gate of the final step on scratch
copies and lists each violation with its field and limit. A gate that fails does not hide the
gates after it: every later gate whose input exists still runs, and `gates_not_run` names any that
could not, so the one correction sees everything at once. It exits 3 on `needs_correction` (not a
failure) and writes nothing; never chain it to another command with `&&`. Correct the view once
for all of the violations and run the same command once more. This is the view's one correction,
separate from the judgment's; the judgment stays as saved. On `ready` the same call runs the final
step (section 5) and prints what it prints. A failure no view edit can fix (a derived line that
cannot be derived from the evidence, a disagreeing measurement basis) is `failed` with exit 1:
report it as a failed step and do not spend the correction on it. `--check` alone checks without
finishing and says `ready`; the final step alone is the same command without `--check`.

## 5. Finishing

`finish_diagnosis.py` (run by the ready `--check --finish-if-ready`) runs these six commands in
order and stops at the first failure. It renders
the report beside its final name and moves it into `report/` only after every gate passed, so a
failed finish leaves no report file. Do not run them yourself, and do not call the result builder
on its own after writing the view:

```sh
cd '<run directory>' && python3 <skill directory>/scripts/compose_video_analysis.py --judgment analysis/video_judgment.json --evidence analysis/content_evidence.json --deterministic analysis/deterministic.json --request analysis/video-analysis-request.json --output analysis/video_analysis.json
cd '<run directory>' && python3 <skill directory>/scripts/validate_video_analysis.py analysis/video_analysis.json analysis/content_evidence.json analysis/video-analysis-request.json
cd '<run directory>' && python3 <skill directory>/scripts/build_creator_result.py --creator-view analysis/creator_view.json --analysis analysis/video_analysis.json --evidence analysis/content_evidence.json --request analysis/video-analysis-request.json --output analysis/creator-task-result.json
cd '<run directory>' && python3 <skill directory>/scripts/render_video_report.py analysis/creator-task-result.json report/VIDEO_DIAGNOSIS.md
cd '<run directory>' && python3 <skill directory>/scripts/validate_creator_shape.py analysis/creator-task-result.json analysis/video_analysis.json analysis/content_evidence.json
cd '<run directory>' && python3 <skill directory>/scripts/validate_creator_report.py report/VIDEO_DIAGNOSIS.md --emit-report
```

The final step adds no fetch, judgment, correction or retry. The final check prints the report body;
read the report file only if that body is truncated. Any failure ends the run: report the failed
step and the missing deliverable. Do not retry, rewrite the judgment to force a gate, or edit
`video_analysis.json` / `creator-task-result.json`, which are script outputs.

`validate_video_analysis.py` enforces the schema enums, that every evidence reference resolves,
that a stated frame total matches the evidence, that every acquisition entry says which kind of
step it was, and the rules for whose video it is.

## The delivered object

`analysis/creator-task-result.json` is the delivered `CreatorTaskResult`
(`schema_version: creator-task-result.v2-final`, with `result_id`, `task`, `status`, `details`,
`evidence_index`, `interaction` and `creator_view`). `build_creator_result.py` writes the envelope
and its fixed task value; never write or rename it yourself. Every card carries `title`,
`why_for_you`, `action` and `evidence_refs` — a card that proposes nothing is an observation.

`ContentEvidence` is written by `build_content_evidence.py`, `VideoAnalysis` by
`compose_video_analysis.py` and the `CreatorTaskResult` by `build_creator_result.py`. What you write
as JSON is the pair those read: `analysis/video_judgment.json` and `analysis/creator_view.json`. Do
not write a throwaway Python file to emit them; write the objects as files. A craft teardown writes
none of these; see `references/craft-teardown.md`.

## Local-file scripts

`scripts/probe_media_tools.py` reports which media tools the machine has and never installs one,
`scripts/extract_local_frames.py` probes the file and samples frames from it, and
`scripts/read_subtitle_file.py` reads a subtitle file the creator supplied. They produce the same
shapes the tool path produces. When and how to use them is in `references/local-file.md`.

# Part 2: Reading the evidence

Shared by every mode. Read *When to stop waiting* before the first data call of a run.

## Frame sampling

The request asks for at most 120 frames with `"sampling": "duration_scaled"`: twice a second through
the first 50 seconds (a dense window every request carries) and through the closing two, one a second
after that, the body spread out evenly once a longer video would exceed the cap. It also asks for a
frame just after each detected cut (`include_shot_starts`) and for the dense windows the selected
method cards name (`dense_windows`, from `analysis/method.json`, sent before the default one, three at
most). The opening, the closing and shot starts come first; the windows then take at most half of
what is left unless the rest of the video needs less, and are thinned by a whole factor to fit (on a
video past about a minute the first 50 seconds are sampled every second, not every half second); the
body fills only the time outside the windows. `observe_video.py` adds all of these, so never write them yourself and
never pass `fps`: it applies only to `evenly_spaced`, is capped at 2, and a higher value is rejected
as invalid input. Each frame's `source` says why it is there (`hook`, `closing`, `body`, `shot_start`,
`dense_window`); a server that does not take the cut and window options yet returns the standard
plan, the frames carry no `source`, and the script says so: then no frame sits at a cut on purpose.
Read the frames 15 to a call, as the script prints the reads.
On a video longer than 50 seconds the request also asks for the **overview** (`overview`): low-resolution
sheets of every second of the whole video, tiles in time order left to right and top to bottom, listed
under `frames.overview` with the seconds each sheet spans (the script prints a legend before the reads,
and the sheets come first). The body then has no even grid: the high-resolution frames past the opening
are chosen where the picture or the on-screen text changes (`source` `change`, with `reason`
`picture_change` or `text_change`) and, where a gap is still over ten seconds, at its middle (`anchor`).
Look at every sheet first: they are the only view of the seconds between frames, so a moment seen only
on a sheet is cited by its second as seen at low resolution. Small text on a sheet is not readable;
quote on-screen text from a frame. A server that does not make the overview yet returns the plan above,
and the script says so.
`sampling_plan` records requested sampling, not verified decoded timestamps or viewing coverage; even `t_seconds` may be a nominal requested point. Without verified actual decode
records, never state a planned interval as actual spacing in judgment or creator cards. Describe it
only as a planned/requested sampling limitation. Judge the hook over `frames.sampling_plan.hook_window_s`
rather than a fixed three seconds — a Short lives or dies in about three, long-form has fifteen to
thirty. When `body_degraded` is true, name the planned `body_interval_s` as a coverage limitation:
shorter cuts may be missing. Before a change depends on an element being absent, inspect the
available evidence for the relevant span. Sampled frames are not full-video or viewing coverage;
an unseen span remains unconfirmed. Denser requests add potential evidence, not a walkthrough.

On some videos no frame can be retrieved at all, and the evidence instead carries timestamped
descriptions of what a model saw. `frames.origin` says which you have. When it reads
`model_observation`, the pixels were read by a model on the supplier's side rather than fetched
here — **and on YouTube that is the ordinary path, not a rare fallback**, so a rule written as if
it were rare would fire on most videos.

What that origin costs is narrow. `on_screen_text` on such an observation is text that was *read
off the screen*, so **quote it**. What you cannot do is take timing or rhythm out of prose:
descriptions arrive per observation, not per cut, so counting cuts or measuring a shot's length
from them is inventing a measurement. Attribute the observation as reported rather than as
something this run looked at, and say so once — not on every line. They are still evidence — they
carry a second and they can be cited — but a claim about typography, framing or a specific frame
needs a frame.

**Reading the frame bytes.** A completed keyframe job lists `frames[]` / `artifacts[]` refs. Select
the exact refs you need and read them with `read_research_data_artifacts` (`job_id` plus those
`object_refs`, without `delivery`, as `observe_video.py` prints the reads: the images arrive inline,
which is the working path). If that read shows you the images themselves, they are viewed: do not save or stage them, one by one or at all; the evidence builder lists frames from
the keyframe envelope, not from their bytes. When a host returns a download link instead, save
that small result and run `static_host.py fetch` on it (it is fetched, not persisted). Then open each image's `path` from fetch's output with the
host's own file or image viewer: a file on disk is not yet seen. Only for items fetch lists as
unavailable, or when scripts cannot reach the network, read those refs again without `delivery`
(the images then arrive inline) and stage that result from the host's result export; never rebuild
it from the host's own session folders. A frame list or a queued receipt is not viewing. Reuse that job,
never a new extraction; bind each image's meaning to its `frame_id`, object ref, SHA and nominal
`t_seconds`, never to arrival order. If the bytes cannot be read, keep honest partial coverage;
never invent a path or refetch.

## Transcript

`transcript.cues[]` carries the spoken track with a start second on every cue; on providers that
return no timing it arrives as `transcript.plain_text` instead. Read it.

The retrieved envelope carries each cue's start in **milliseconds**; the evidence object carries
`start_s` in **seconds**. `scripts/build_content_evidence.py` makes that conversion, sets
`granularity: timestamped` and `timestamps_available: true` whenever any cue carries a start, and
uses `plain_text` only for a path that returned no timing at all. Do not fill or correct these
fields by hand: a start pasted across unchanged is off by a factor of a thousand. A video can carry
a full argument in speech and show none of it on screen — the frames of a video with no burned-in
captions are silent. Quote a cue as the evidence for a hook, a promise or a claim the way a frame is
quoted for what was visible, and cite it as `transcript.cue[i]`.

When `transcript.status` is `available` but no cue text and no plain text reached the evidence
object, treat the transcript as unavailable and say so beside the claims it weakens. A segment
count is not a transcript.

When the platform published no captions, the media call's `transcript` job falls back to machine
transcription inside the same job. There is no second tool to reach for: one job is the whole
path. **A file on this machine has no platform captions to fetch**; where its words come from is
under *Getting the words* in `references/local-file.md`.

`transcript.origin` says which arrived — `platform_captions` for the file published with the
video, `provider_transcript` for one the retrieval path supplied, `speech_recognition` for words a
machine heard after the fact. Machine-heard words carry a word error rate: quote them as what the
analysis heard, never as the creator's exact wording, and confirm any proper noun, price or figure
against a frame before repeating it. A video with no burned-in captions whose transcript never
arrived is a video whose argument was never read — say that.

**Exporting the transcript file.** `scripts/export_transcript.py` takes two positional arguments,
the evidence file and the output directory, plus optional `--stem`, `--formats` and `--summary`. It
writes a `.txt` from whichever track arrived, and a `.srt` only where the evidence carries cue
timing. Ends come from the following cue; only the final cue's end is derived, and the summary says
from what. Where the path returned no timing it writes no `.srt` and says so: a subtitle file with
invented timings desynchronises silently. Confirm its actual `written` / `refused` summary, name the
written files in the delivery, and report a refused format as a missing piece. A short caption
excerpt is not a complete export.

## Where the metadata comes from

**On YouTube, take `content_metadata` from `youtube_get_video`, not from the media call's
`metadata` operation.** The media tool reads a video page from a datacentre
address, and YouTube refuses those: it answers `service_unavailable` on every YouTube URL, and a run
that used it lost title, tags, cover and publish date. `youtube_get_video` is the platform answering
about its own video; it is not a deferred job and carries the same facts plus public counts. Call it
with `{"parameters": {"video_id": "<resolved-video-id>"}, "delivery": "download"}`. Transcript,
frames and measurements come from `observe_video.py` with the original video URL, as `SKILL.md`
says; it builds the arguments.

On **every other platform** (Instagram, TikTok, Douyin, Xiaohongshu, Kuaishou, Facebook, Bilibili)
the media call's `metadata` operation stays the metadata source. On Douyin, Xiaohongshu and Kuaishou
the `keyframes` job brings the metadata and measurements back with the frames; the separate
`metadata` and `measure` jobs answer `unsupported` at no cost, and the builder reads both from the
keyframes result, so that is not a missing source. Douyin and Xiaohongshu publish no public view
count: the builder leaves views out and records that limitation, so never write zero views or
divide anything by views there. A Facebook view count is the page's rounded display; quote it only
at that precision, and a withheld one stays unknown.

Persist the YouTube response like any other, naming its own connector and operation:
`--connector youtube-public --operation get_video`. The builder reads its fields into the same shape.

⚠ **Do not issue both.** Two metadata envelopes for one video are two readings of the same facts,
and the builder picks one — which one is then invisible in the report.

## Cover and tags

`content_metadata` carries what the platform itself declares: `tags` in the creator's own order,
and `thumbnails` by tier, largest first. This is the only part that decides whether the click
happens at all, so a diagnosis of "why did this get no views" that never mentions the cover has
skipped the top of the funnel.

Read `status` before reading the arrays. `available` with `tags: []` is a finding — this creator
published none. `unavailable` means the fetch did not happen, and the two arrive looking
identical. Never report the second as the first.

`thumbnails[0]` is the highest tier. The ordering is the connector's: do not re-sort and do not
re-derive "highest" from the dimensions.

When the fetch did not happen, say so in a limitation that names `content_metadata` by that name.
The gate looks for the field, not for the words "cover" or "tags".

A thumbnail URL is a reference, not an image. No tool here returns cover pixels, so this run has
not seen it: cite that a cover exists, hand the creator the file, and say what the tags declare —
but never describe what the cover *looks like*, and never judge whether it works.

## When to stop waiting

**A call that cannot succeed is not a call to make.** The media jobs run server-side;
**a file on the creator's machine is not reachable by any of them** — not as a `file://` URI, not
by copying it into the run directory. When `source.acquisition` is `local_file`, make no
media call at all and follow `references/local-file.md`. `build_content_evidence.py`
refuses the mixture too.

A retrieval path that has not answered is not evidence that arrives later. Give each tool one
retry, and treat a call that comes back with neither an envelope nor a job id as failed at once.
Such a result is also what `static_host.py fetch` and `stage` refuse ("MCP error contains no terminal
connector evidence"): record it with `--limitation` on the evidence-building command and carry on.

The media jobs (transcript, frames, measurements) are deferred and take minutes. The backend waits
for them inside `collect_video_media`; `observe_video.py` prints the same call again while any is
still running, and nothing is queued or charged twice. A whole-video viewing has no server-side
wait: the script waits between its readings itself. The whole observation has one deadline, 330
seconds from the first call, the same on every host. Each printed call waits inside its tool, so
near the end the script prints only calls whose wait still ends inside the deadline (fewer, or with
a shorter `wait_s`) and then none; a fallback starts only while enough of it is left to finish. Keep making the printed calls within this turn until the script reports its status:
ending the turn to wait throws the jobs away. A job or viewing still running at the deadline did not
arrive in time: a job comes back as `--deferred-incomplete <operation>=<job id>` for the evidence
builder (recorded `deferred_incomplete`), never as `failed`, with one limitation line naming what
did not arrive; it carries no media evidence and keeps the affected stages unassessed. Say plainly
that it did not arrive in time; never call it a backend error or `service_unavailable`.

When the window closes with frames still outstanding, deliver; a reply that only says the analysis
is still processing is not a delivery. With no keyframe envelope the builder records `frames.status` as `not_attempted`; list the visual dimensions in
`unavailable_dimensions[]`, and say in one sentence beside the affected claim that this reading
rests on speech and metadata alone. A report that arrives without the frame track beats a report
that never arrives.

## Long videos in two steps

- **Quick first read, by default.** A diagnosis, content read or craft teardown of a link asks the
  media jobs for a quick sample of any video over 3 minutes: a small set of frames at fixed moments
  across it, cuts and sound measured over the first minute, and, where the platform has no captions,
  speech heard for the first 3 minutes. The evidence marks each part (`frames.sampling`,
  `transcript.coverage`, `media.probed.coverage`) and section 3 of the brief states what was seen
  and heard, with its rule for the rest. A diagnosis report closes with one paragraph that says so
  and offers the full analysis, its time and its one more video credit; a content read or craft
  teardown ends with the same paragraph, word for word from the brief; its credit note is the one
  mention of credits a reply makes. Offer it nowhere else. A
  shorter video, a transcript export and an uploaded file always get the full pass.
- **Consent.** Only a reply that accepts that offer ("yes", "full analysis", in any language), or a
  host message saying the deep analysis is ready, starts the full analysis. Never start it on your
  own, for a video of 3 minutes or less, or a second time.
- **The deep run.** Begin again from analysis step 1 as a new run (with `start_skill_run` where
  available: this is the one more credit), with the same link, ownership, mode and the creator's
  original words, `--duration-s` from the first result and `--depth deep`. Its jobs are keyed by
  the link and the day, so running it again replays the jobs already queued, never pays twice.
- **`deep_pending`.** When the full pass cannot arrive inside the observation deadline, the
  observation stops waiting and prints `status: deep_pending`, a `deep_analysis_pending: {...}` line
  for the host, and what to tell the creator: in their language, in one or two sentences, that the
  full analysis is still running, about how many more minutes, and that they can say "continue"
  later (or, when a host note says the result will be posted automatically, that). Write no report
  or answer about the video in that turn. When they say continue, run the one command it printed:
  the same run picks up the same jobs, with no new credit, and goes on like any observation.

## When part of the media is out of reach

- **No measurement.** When the `measure` result is missing or says the media could
  not be retrieved, and no keyframe result carries `signals`, say the cuts were not measured because
  the platform refused the download, never that the video cannot be analysed. Place each visible
  change between the two frames that bracket it ("between 1:03 and 1:05"), read the on-screen text
  of every frame with its second, and mark the spans between frames unconfirmed.
- **No words on a long video.** For a published video, a quick transcript lookup that returns none
  is not the final answer: the media call's `transcript` operation falls back to machine
  transcription inside the same job, before saying the words were not read. A local file never
  goes to the media call; its words come from the tiers in `references/local-file.md`. When a
  whole-video reading is capped by length but accepts segments, read the opening window and the
  spans the question names, deliver, and only then ask for timestamps.
- **Photo and carousel posts.** Metadata naming a photo or slideshow post, or a video reading that
  answers `source_not_video`, makes it a still-image post: make no further video call. Read its
  slides where the post images can be fetched, quote the caption as the platform's text, and ask the
  creator to paste text only when both came back empty. After a share link resolves, use the
  canonical URL it returned for every later call.
- **Edit requests.** This Skill diagnoses; it does not edit, mix or render video. Asked to edit, add
  sound or export, say so in one sentence and deliver the timed edit plan in its place.
