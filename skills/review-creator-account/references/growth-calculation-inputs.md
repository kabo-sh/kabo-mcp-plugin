# Growth calculation inputs

Use only after resolving the target and checking evidence under `growth-estimation.md`.
The calculator accepts these existing contracts; missingness is not permission to invent rows.

Direct calculation inputs use top-level `schema_version: growth-input.v1`, positive `horizon_days`, and `scope: {platform, account, metric, semantics}`. Each row carries the same scope and a `source` pointing to its persisted evidence or the supplied record. Timestamps include a timezone. Missing values are null, observed zero remains zero. Never mix accounts or metric definitions; window totals are not cumulative stock observations. Public totals do not measure private conversion.

For a named-post stock calculation, put the resolved post identifier in `scope.account` (for
example `creator/post-1`, or its canonical URL), and use that exact scope for every observation.
An account handle alone would mislabel a post calculation as an account-wide result.

Choose one method:

- `observed_pace`: for dated follower/subscriber or other cumulative stock observations. `scope.semantics` is `cumulative_stock`; `observations` contain `observed_at`, `value`, `source`, `scope`. The script uses first-to-last net change divided by actual elapsed days and exposes intermediate interval rates. Explain reversals or short/old windows before interpreting the unchanged-pace scenario; missing dates are not zero. Mock records are not real observations.
- `assumed_pace`: uses the existing limited Chinese/English day/week quote binding, not arbitrary
  rate-language interpretation. Same observation fields, at least one dated baseline, plus `assumption: {amount, period: "day" | "week", origin: "user", quote}`. Use only an assumption explicitly supplied by the user. A cadence or scenario name is not a rate. Negative net change is allowed; linear values crossing zero are flagged.
- `content_scenario`: for views/likes/comments, with semantics `per_content_cumulative`. `samples` contain `content_id`, `published_at`, `observed_at`, `format`, `value`, `source`, `scope`. Supply `cohort: {format, age_min_days, age_max_days}` appropriate to the user's comparison; use the same account and keep the chosen age band visible. The script filters format and observation age, preserves missingness and multiplies the available sample median by a publication plan: `plan: {posts, origin: "user", quote, binding}` for an explicit total count; add `period: "day" | "week"` when `posts` is the user's count per period. Interpret the user's language into the source-bound contract below: the script derives the equivalent item count as `posts × horizon_days / period_days`. Keep a fractional equivalent count as a rate scenario, not a rounded calendar schedule. Or use `plan: {origin: "observed_cadence"}` with `--snapshot` to continue the captured pace. The latter derives `(captured same-format posts - 1) / elapsed publication days` from at least two dated posts; do not supply `_snapshot_cadence`. Report the actual observed ages returned by the script, not the broader selection band. This is a conditional total for new content at that observation age, not account-wide growth, a confidence interval or a guaranteed total by the plan's end. Do not use it for subscribers. A tiny or selective sample can be computed but needs that limitation in the interpretation.

Build each observation only from a real source row. The contract above supplies field names,
not example measurements to copy. When requesting a missing export, use placeholders such as
`[measurement date, cumulative count]`; do not attach illustrative dates or counts to this account.

```bash
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/estimate_growth.py' growth_input.json --output growth_estimate.json
```

Use this skill's absolute script path from the run directory. A narrow estimate requires no synthesis or public handle. When public samples are needed, use the existing public review fetch contract; keep fetched facts in persisted artifacts and include their references in the calculation input. Do not claim that daily follower history or owner analytics are connected just because storage exists elsewhere in the platform. No tool of this Skill provides them: request a dated export rather than inventing a tool or substituting another creator's pace.

For `content_scenario` from the review's `public-content-snapshot.v1`, omit `samples` and add `--snapshot snapshot.json` to the command. The script binds the matching creator and metric directly, preserves unavailable values, and retains snapshot item references; do not retype those facts into samples. Keep the snapshot's coverage and source limitations in the interpretation. The native result is described by `references/growth_estimate.schema.json`.

For user inputs, pass `--question-file` pointing to the original request as plain text. Public review fetch retains it as `question.txt` in the printed run directory; use `--question-file question.txt` there. Add `--snapshot snapshot.json` only for `content_scenario`; stock modes must not receive `--snapshot`. For a publication plan, interpret the request's meaning first, then supply `quote` as the complete original request (excluding surrounding whitespace) and `binding`:

- Explicit total: `{"posts": 4, "origin": "user", "quote": "If I post 4 long videos in total next month, how many views will I get?", "binding": {"quantity_kind": "total", "quantity_quote": "4"}}`.
- Frequency: `{"posts": 3, "period": "week", "origin": "user", "quote": "3 videos per week", "binding": {"quantity_kind": "cadence", "quantity_quote": "3", "period": "week", "period_quote": "per week"}}`.

The model interprets total versus frequency and maps the user's language to `day`/`week`; the script does not claim to understand arbitrary prose. It checks that the whole request is retained, the numeric source matches `posts`, the period evidence occurs separately in the source, and the normalized fields agree. It then calculates the equivalent publication count without rounding. Do not invent evidence or turn a frequency into a model-calculated monthly total. Missing interpretation, truncated quotes, absent evidence or unsupported periods return `needs_input`; clarify when the request cannot be interpreted confidently. Structural consistency cannot prove that the model's semantic interpretation is correct. Read compatibility remains only for a complete old explicit-total short form such as `6 videos` (or `publish 6 videos`), not a number excerpted from arbitrary prose.

The new `binding` contract applies only to publication plans. `assumed_pace` retains its pre-existing stock-rate input reader for compatibility; it recognizes the existing Chinese/English forms rather than providing a new multilingual rate interface: `assumption.quote` is an exact source excerpt containing the signed net amount and day/week period, such as “20 subscribers per week” (a Chinese excerpt with a per-day or per-week net amount is read the same way). Never relabel an assistant suggestion as a user assumption. Relay computed values, formula, assumptions and missing inputs together; preserve the same limits under follow-up pressure.
