# Diagnosis runtime

Read this whole before the first analysis command in `SKILL.md`. It holds what each command
depends on. For a diagnosis, every step before `finish_diagnosis.py` leaves it unfinished; only the
final validated report closes it.

## 1. The request

Prepare `analysis/video-analysis-request.json` with `prepare_link_request.py` before building
evidence; it preserves the creator's original link, the chosen ownership state and confirmation, and
leaves an unresolved post ID null. For a public link, `<platform>` is the link's platform, and
`--mode` (the mode from *Which question is this*) sets the call ceiling for that mode:

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

A video the creator attached in Kabo chat (`kabo-file:<id>`) has no packet; the media tool reads the
stored file. `<platform>` is the one it was posted on or is made for, as the creator says; any
ownership state may apply:

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
Read the paths in `ContentEvidence`, not the staging filenames. Build the evidence once.

Per-run flags, on the evidence-building command only:

- `--viewer snapshot/whole-video.json` when the observation printed it: the whole-video result,
  already reduced to its timestamped notes and transcript. Its notes become `viewer_observations`
  (cited by their ids) and its transcript fills the transcript only when none was fetched.
- `--pending <operation>=<job id>` or `--deferred-incomplete <operation>=<job id>` for a deferred
  job without a terminal result (see *When to stop waiting* in `references/evidence-reading.md`).
  Persist only a job's terminal envelope.
- `--owner-metrics <file>` with the `owner_metrics` block read from the creator's own export, on an
  owned video.
- `--published-at` when the creator states a publish time the metadata lacks.
- `--limitation` for a gap the envelopes do not show.
- On a local file, `--local-media analysis/local-media.json` and, where the creator supplied one,
  `--local-transcript analysis/local-transcript.json`. An unpublished draft is read by the local
  scripts, never by a tool, and the request must still name the platform it is made for.

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

The judgment schema in section 7 of `analysis/brief.md` projects the model-authored fields from
the final analysis schema. Read it whole and write only this partial judgment, using its shapes and
enums. Keep `revisions` empty for `third_party` and `unknown`, and cite exact refs from the reference
index. The composer supplies evidence lineage, completeness and the unchanged `deterministic.json`
block.

After saving `analysis/video_judgment.json`, run `--check-judgment-refs` (a read-only step).
Advance only on `status: ready`. For `needs_correction`, read the named evidence values, correct
only those citations once and rerun the check once. If still not ready, stop and report the gap.
Never guess aliases, fetch to fill a citation or reopen a closed run. Index, hash, I/O and
execution errors are fatal, not input corrections.

On `ready`, read `grounding_review` through `packet_end`. It places the referenced frames, images
and literal speech beside the authored judgment; it does not certify pixel interpretation. Compare
each objective observation and report-bearing judgment with the images already displayed. A cue
start does not establish first visual appearance; a legal frame ID does not prove the described
object. If a statement is unsupported, use the **same one correction opportunity** to narrow or
remove it and rerun the check once — never a separate loop. If that opportunity is spent, stop or
keep the gap explicit rather than invent a claim. After this review, keep the saved judgment
unchanged. The view-contract command reads the saved file, so never run it before the file exists
or in the same call as the check it depends on.

## 4. The creator view

`--print-view-contract` prints the author fields, the current canonical observation references and
the display-column limits. Read it completely, then read `references/diagnosis-report.md` whole for
what the fields should say. Omit the read-only `data_note` and `listen_note`. Every figure in the view, including
next-edit timings, must trace to the composed analysis or evidence; rounding and magnitude notation
are allowed and clock times are not numeric claims. For a new duration that is editorial advice,
give a qualitative instruction anchored to a verified moment. Never add observations or alter the
saved judgment to manufacture grounding. Write `analysis/creator_view.json`, then run
`finish_diagnosis.py --check`: it runs every gate of the final step on scratch copies, writes nothing
and lists each violation with its field and limit. It exits 0 on `ready` and 3 on
`needs_correction` (not a failure), so never chain it to the final step with `&&` and read the
status. Correct the view once for all of them and check once more; advance only on `status: ready`. This is the view's one correction, separate from the
judgment's; the judgment stays as saved. A failure no view edit can fix (a derived line that
cannot be derived from the evidence, a disagreeing measurement basis) is `failed` with exit 1: report
it as a failed step and do not spend the correction on it.

## 5. Finishing

`finish_diagnosis.py` runs these six commands in order and stops at the first failure. It renders
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
