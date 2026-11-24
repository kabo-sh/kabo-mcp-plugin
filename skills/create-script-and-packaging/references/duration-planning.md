# Recommend and fulfill a script duration

A current user-specified duration wins. Reuse a prior user-confirmed duration only
when the same brief, platform and format still apply; a new instruction overrides it. Never default
all scripts to 8–10 minutes. Packaging-only/title edits reuse the existing script
and do not trigger duration research.

Keep an assistant's suggested length as a draft estimate unless the user confirms
it. Asking to develop the same topic does not make every earlier suggestion an
explicit current requirement. In a native intake, set `target_duration_seconds`
only for the current user's explicit target; put an applicable prior confirmed
target in `prior_target_seconds` with `prior_applies=true`. Otherwise omit the
target and let the helper estimate it. A creative draft may propose its own
duration without creating a native request; state that it is an estimate.

Before building a script request with no duration, reuse relevant public duration
fields already acquired for the target creator channel: in the conversation, or in
the JSON output of another Skill in this workspace (for example a
`review-creator-account` run for that channel), preserving provenance and the
target-turn cutoff. This Skill fetches no channel data. If none exists, do not
block: write the duration context with `"samples": []` and
`"research_status": "not_available"` (the helper's defaults) plus the content
inputs below, say that a channel-based estimate needs that account review, and
let the helper use its content estimate.
A failed or unavailable path stays recorded and is not silently replaced. Do not query unrelated accounts
or mix Shorts/Reels with long videos. Source URLs, channel identity, date window,
format and topic relevance are necessary for a meaningful distribution.

Write local duration context with optional `channel_id`, `samples`,
`research_status`, `prior_target_seconds` and `prior_applies`; content inputs are
`complexity: light|medium|heavy`, `steps`, and `demonstration_seconds`. Each sample
has `channel_id`, `platform`, `format: short_form|long_form`, `duration_seconds`,
`published_at`, `url` and `topic_relevant`. Project them from acquired evidence,
not model-invented averages. State why these samples are comparable. The helper
excludes mismatched/missing/duplicate records and, with at least five samples,
excludes durations outside one quarter to four times the median. It reports the
retained n, mean, median, range, date window and exclusions; this is a bounded
channel sample, not a platform-wide statistic.

Run `cd '<run>' && python3 '<skill directory>/scripts/script_duration.py' --request intake.json
--context duration-context.json --output script-package-request.json` before the direct
selection builder or generation. `intake.json` may omit
`content_format.target_duration_seconds`. The prepared native request has an
integer target and reproducible `duration_plan`; ordinary explicit requests
remain compatible. The helper combines comparable median with an explicit
content-workload estimate. Without usable channel data it uses a transparent
short/long-form content estimate, never a fabricated platform average. Explain
that estimate briefly in the creator's language and allow adjustment. Neither a
missing duration nor an unnamed platform/form needs clarification: an unnamed one
takes the default in *Platform shapes format only* in `SKILL.md`. If requested time cannot hold necessary content, explain the
tradeoff instead of silently changing the explicit target.

Write substantive spoken copy and actual production actions to fit the target.
Scripts using a prepared duration plan must include `script.timing` with `pace: normal|deliberate|brisk`
and `non_speaking_segments` (each has a unique `scene_order`, `seconds` and a
concrete `purpose`). Segment time is additional non-speaking time, not time that
overlaps narration. Do not label empty padding as a demonstration. Use contiguous
`MM:SS–MM:SS` scene ranges. The validator estimates spoken words/Chinese characters
using disclosed planning rates, adds justified non-speaking time, and rejects
obvious underlength/overlength scripts and inconsistent structured timelines.
This is an estimate, not a measured performance. Review pace and useful content,
then recommend a read-through before production. Do not add filler to pass.

Planning assumptions are 240 Chinese characters/minute, 300 Japanese kana/kanji
or Korean Hangul/Hanja characters/minute, 130 Arabic words/minute and 160 words/minute
for other space-delimited languages, adjusted by pace. These are explicit
heuristics, not measured language averages. Publication dates accept full
YYYY-MM-DD or ISO date-time values, never truncated invalid suffixes.

Date-only and timezone-free samples use UTC for window ordering; offset-aware
timestamps are normalized to UTC. Report boundaries retain the original source
strings selected by chronological order.

The renderer emits one English set of timing labels. Before delivery, explain this timing basis in the requested language, preserving every estimate, target, sample statistic and the not-measured qualification; never leave an unexplained English fallback for another language. Creative text stays in its original language.

## Several scripts with one requested length

A request for many full scripts at a stated length (fifteen daily Shorts of 2:20–2:30, a week of
one-minute Reels) is met only when every script reaches that length and every requested script is
delivered. Write `batch.json`:

```json
{"target_seconds": {"min": 140, "max": 150}, "requested_count": 15, "pace": "deliberate",
 "scripts": [{"id": "Nov 16", "language": "es", "spoken_text": "<only the words that will be spoken>"}]}
```

`target_seconds` may be one number. `pace` is the delivery the creator asked for (a calm, serene voice
is `deliberate`). List every script written so far, then run
`cd '<run>' && python3 '<skill directory>/scripts/check_batch_durations.py' --batch batch.json`.
It estimates each script with the planning rates above and returns `meets_request` (exit 0),
`needs_revision` with the `short`/`long` ids and how much more copy a short one needs, or
`partial_batch` when fewer scripts than requested are written. On `needs_revision`, extend short
scripts with real content (another example, step or payoff, never filler) and tighten long ones, then
check again. When the full set cannot be written at full length in one reply, deliver the scripts that
fit, say plainly how many remain and continue with the next batch. Never claim the requested length or
count is met unless the check returns `meets_request`; say the estimate is not a measured read-through.
