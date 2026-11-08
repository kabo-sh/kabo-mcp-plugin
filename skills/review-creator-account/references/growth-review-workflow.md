# Growth inside a complete public account review

Apply the target, evidence and probability boundaries in [growth-estimation.md](growth-estimation.md) first. This workflow requires the actual saved public snapshot; a prior chat summary is not that snapshot.

In a public review, use `drive.py growth` for the report's single content slot. Choose a listed
choice, save `review_growth_input.json` with the user's quantity/wording, and rerun before synthesis.
Its metric/horizon follow the question (views/30 days by default). `drive.py report` binds the
input to the retained snapshot, analysis and question, recomputes it, and carries its measurement,
formula, ages and limits in `ACCOUNT_REVIEW.md`. Use the standalone path below for other results.

Inside a complete public review, `drive.py growth` and the composed `ACCOUNT_REVIEW.md` currently
support one `content_scenario` in one growth slot. Once `review_growth_input.json` exists,
another `drive.py growth --metric ...` reads it rather than switching metrics. Do not overwrite it
or place stock figures in that schema. For each additional metric or stock estimate (including a `needs_input` result),
use the standalone interface in the same run with distinct input/output filenames. Extra content
calculations use the same saved snapshot, question and validated `content_scenario` contract;
never substitute one metric's rows for another's. Keep all requested metrics independently gated.
Compose the review with only its selected growth-slot result, then append each other calculator's
Markdown handoff before `creator_report:`. Preserve its values, dates, sources, formula, assumptions
and limits; translate labels only, without a new forecast. These separate Markdown artifacts are
not part of validated `ACCOUNT_REVIEW.md`; identify them when files are requested. No schema
extension or repeated user request is needed, and missing inputs never block supported work.

## Evidence → choice → answer

For a public snapshot assessment, use top-level `schema_version`, `scope`, positive `horizon_days`, and `metrics` drawn from subscribers/followers/views/likes/comments. Only `platform` and `account` belong in `scope`; replace the example account with the snapshot's identity:

```json
{"schema_version":"growth-review.v1","scope":{"platform":"youtube","account":"creator"},"horizon_days":30,"metrics":["views"]}
```

Run:

```bash
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/estimate_growth.py' request.json --assess --snapshot snapshot.json --output growth_evidence.json
```

The script binds actual snapshot rows, groups formats, retains missingness/coverage and sample ages, and calculates the conditional median-performance scenario at captured publication pace for each supported content metric. It marks stock-growth inputs separately. These continuation assumptions come from the evidence; the user need not invent a publishing count. Select the relevant format and explain why its observed performance is a useful reference. All captured items are a transparent default, not proof of a representative or age-matched sample. If a narrower comparison is justified, use the direct method below and explain the selection.

In the answer, keep the number's measurement and deadline comparison together, so later turns can reuse the result without changing its meaning. For content scenarios, `estimate.time_basis` separates the publication window from the actual sampled content ages. Start with the supported comparison: the planned batch matching historical per-item performance at those ages. The deadline total itself is not identified: staggered publication dates give different ages on the deadline, and one cumulative snapshot supplies no age-performance trajectory. Its direction is `lower` when the samples' median observed age exceeds the publication window, since no item published inside the window can be older than the window at its end; say it is usually lower, without a number, probability or size of the gap. Otherwise the direction is `not_identified`; say it may be higher or lower. A follow-up about the deadline uses this field, not a new judgement. Dated trajectories and a publication schedule would support a separate deadline calculation.

If subscriber history is absent, ask for dated net gains; other requested metrics can still be answered. Correct unsupported earlier assistant numbers rather than adopting them as evidence. Targets may use historical performance with an explicit rationale, but neither a target nor user pressure supplies evidence for attainability or likelihood.
For dated stock records or an explicit user rate/count, calculate directly. `needs_input` identifies the minimum missing inputs. Do not translate a scenario into odds, manufacture a conversion rate, or add an uncomputed outcome range.

For a rough range, use the calculated sensitivity choices: the same captured cadence, with each new item's performance set to the observed lower quartile, median, or upper quartile. Explain the changed per-item assumption; these are neither the batch's predicted quantiles nor bounds covering a known probability. A prior assistant's uncalculated range is not another scenario. Keep subscriber/follower gaps separate rather than assigning conversion numbers to complete a table.

