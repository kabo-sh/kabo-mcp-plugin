# File contract v3

Input `request-input.json` contains:

```json
{"images":["thumbnail.png"],"context":{"title":"A pottery lesson","target_aspect_ratio":"16:9","target_aspect_source":"user"},"language":"en"}
```

Use 1–3 distinct local static PNG/JPEG/WebP images, paths relative to the input file. `language`
is the creator's BCP 47 tag. `en`, `zh` (Simplified), `zh-Hant`/`zh-TW`/`zh-HK` (Traditional), `pt` and
`es` tags use the built-in labels in `labels.json`; any other language also needs `labels`: exactly the
keys of the `en` entry, each one nonblank line in that language, keeping every `{placeholder}`.
`context` may be empty; allowed nonblank strings are title, video_url, video_summary,
source_reference, channel_reference, peer_reference, source_disclosure, audience,
target_aspect_ratio and target_aspect_source. The target ratio must use positive integer `W:H` syntax
and needs `target_aspect_source`: `user` (the creator named the ratio or size) or `format` (the
standard ratio of a format the creator named). A supplied URL alone is not topic evidence.
`prepare` produces immutable hashed A/B/C originals and small images and a v3 request.json, and
prints the script's `measurements` (and `title_length` when there is a title).

Author `review.json` with exactly these fields:

```json
{
  "schema_version":"review-thumbnail.review.v3",
  "request_sha256":"<sha256 of exact request.json bytes>",
  "candidates":[{
    "id":"A",
    "observations":{"capture":"original","visible_text":["CLAY INTO A POT","AI generated"],"ui_text":[],"main_subject":"Hands shaping clay on a wheel.","disclosures":["AI generated"]},
    "items":{
      "topic_match":{"verdict":"pass","reason":"The clay pot matches the lesson title.","fix":"","basis":"observed"}
    },
    "priorities":[],
    "suitable":true,
    "suitability_reason":"A clear subject and finished layout suit this topic."
  }],
  "title_review":{
    "title":"A pottery lesson",
    "clarity":{"verdict":"pass","reason":"It names the lesson plainly.","fix":""},
    "pairing":[{"candidate_id":"A","verdict":"pass","reason":"The pot shows the result the title promises.","fix":""}]
  },
  "comparisons":[],
  "recommendation":{"candidate_id":"A","reason":"The subject and topic are immediately clear."}
}
```

`observations` is written per candidate before any judgment: `capture` is `original` or `screenshot`
(platform interface such as a duration badge, video title, channel name or view count around or over
the cover); `visible_text` lists each cover text exactly as written (empty list when the image has
none); `ui_text` lists the platform interface text of a screenshot (empty for an original); text
printed on the cover that the interface repeats belongs in both; `main_subject` is one sentence, and
`disclosures` lists source/AI/cloned-voice/financial disclosure labels, each of which must also appear
in `visible_text`. Any quoted text (straight, curly, guillemet or CJK corner quotes) in an item reason, suitability reason,
comparison, recommendation or title review must appear in the relevant candidate's `visible_text` or in
the title; quoting text that is only in the interface is rejected. A reason or fix may not ask
to remove or hide a recorded disclosure. Suggested new wording belongs in `fix`, which is not checked
against `visible_text`.

The example abbreviates `items`; real reviews require all ten IDs from rubric.json exactly once,
in every candidate. All objects reject extra fields (including scores). Candidate order is A/B/C.
Each item has `verdict: pass|fail`, one nonblank `reason`, `basis: observed|missing_context`, and
`fix` (nonblank for fail, empty for pass). A missing-context item must fail. With no topic evidence,
topic_match must fail for missing context. `prepare` prints `review_template` (and writes
`review.template.json`): the exact shape for this request with `request_sha256` filled.
The script owns the ratio. Per candidate it measures the size and gives a ratio status: `fail` (over 1%
from the target: resolution_aspect must fail), `pass` (within 1%), `no_target` (no target ratio),
`screenshot` (capture is a screenshot) or `nonstandard_size` (a size within 2% of no common thumbnail
ratio, unless the creator named the target). The last three leave the ratio unjudged: the row needs
`basis: observed`, fails only for blur, and a passing row is rendered as "to confirm" with the
script's explanation, never as a failure or a first change. The resolution_aspect reason and fix judge sharpness and detail only and
may contain no ratio notation or percentage other than the target itself; the report appends the
script's measurement sentence. The 1% tolerance allows pixel rounding; it is not a quality score.

`title_review` is null without a title. With one it has `title` (exactly the context title), `clarity`
(`verdict`, `reason`, `fix`) and `pairing`: one row per candidate in order with `candidate_id`,
`verdict`, `reason` and `fix`, judging whether title and cover complement each other. Fix is nonblank
for fail and empty for pass. The title length row is measured by the script: over 100 characters
(YouTube's limit) or over 70 display columns (wide characters count two) fails.

`priorities` is an ordered array of distinct failed item IDs: 2–3 when at least two items fail,
one when just one fails, empty if none fail. Suitability is an explicit editorial boolean plus
reason, not calculated from a count. Missing-context or all-fail candidates cannot be suitable.

For two candidates `comparisons` has A/B; for three it has A/B, A/C, B/C in that order.
Each object contains exactly `pair: ["A","B"]`, `winner: A|B|tie|neither|insufficient`, and `reason`.
Only members of that pair may win; a winner must be suitable, a tie requires two suitable images,
and two unsuitable images require neither. Explain both sides. A recommendation must be suitable
and consistent with every comparison involving it; otherwise use null and explain the uncertainty.
When all candidates are unsuitable, the rendered conclusion explicitly recommends none.

`deliver` removes stale final artifacts before validating and atomically writes FINAL_REVIEW.md
and delivery.json. The receipt binds request/review/report hashes and returns the absolute path.
Do not edit inputs, files or the report after successful validation; re-run deliver after changing
a review. Validation proves contract compliance, not visual correctness or real-host emission.
