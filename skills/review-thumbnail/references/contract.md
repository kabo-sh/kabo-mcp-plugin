# File contract v2

Input `request-input.json` contains exactly:

```json
{"images":["thumbnail.png"],"context":{"title":"A pottery lesson","target_aspect_ratio":"16:9"},"language":"en"}
```

Use 1–3 distinct local static PNG/JPEG/WebP images, paths relative to the input file. `language`
is en or zh. `context` may be empty; allowed nonblank strings are title, video_url, video_summary,
source_reference, channel_reference, peer_reference, source_disclosure, audience, target_aspect_ratio.
The target ratio must use positive integer `W:H` syntax. A supplied URL alone is not topic evidence.
`prepare` produces immutable hashed A/B/C originals and small images and a v2 request.json.

Author `review.json` with exactly these fields:

```json
{
  "schema_version":"review-thumbnail.review.v2",
  "request_sha256":"<sha256 of exact request.json bytes>",
  "candidates":[{
    "id":"A",
    "items":{
      "topic_match":{"verdict":"pass","reason":"The clay pot matches the lesson title.","fix":"","basis":"observed"}
    },
    "priorities":[],
    "suitable":true,
    "suitability_reason":"A clear subject and finished layout suit this topic."
  }],
  "comparisons":[],
  "recommendation":{"candidate_id":"A","reason":"The subject and topic are immediately clear."}
}
```

The example abbreviates `items`; real reviews require all ten IDs from rubric.json exactly once,
in every candidate. All objects reject extra fields (including scores). Candidate order is A/B/C.
Each item has `verdict: pass|fail`, one nonblank `reason`, `basis: observed|missing_context`, and
`fix` (nonblank for fail, empty for pass). A missing-context item must fail. With no topic evidence,
topic_match must fail for missing context; with no target ratio, resolution_aspect must do likewise.
A measured ratio mismatch over 1% must fail resolution_aspect. This tolerance allows pixel rounding;
it is not a quality score. The host still judges sharpness and whether dimensions suit the use.

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
