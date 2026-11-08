# Conditional growth calculations

Use `<skill directory>/scripts/estimate_growth.py` with actual evidence or a user export, never
manufactured rows. It saves evidence JSON and a Markdown handoff, also printed. `computed` means
arithmetic succeeded, not that future performance is known.

## Final forecast-only reply

After resolving the scope and preparing one valid input per requested metric/horizon, compose
the final reply in one command. Include supported and missing-input results for that same target:

```sh
python3 '<skill directory>/scripts/compose_forecast_reply.py' --scope-file '<run directory>/forecast_scope.json' --input '<first-input.json>' --input '<next-input.json>' --question-file '<original-question.txt>' --output '<run directory>/FORECAST_REPLY.md'
```

The scope file records `platform`, `target`, `request_quote` and `reference` from the scope-resolution
step. Each input must match that same platform/target. This checks consistency, not whether the
model interpreted the conversation correctly: resolve the most recent user focus first.
Use one `--input` when only one is requested; add others as needed. Add `--snapshot` only for
content inputs bound to that original saved snapshot. Add `--correct-prior` only when the history
actually contains an unsupported forecast. The command recomputes the inputs; it never trusts
model-written result JSON. Relay the text between its reply markers, with fixed-label translation
when needed. Do not append another table, numeric scenario, historical substitute or promise.
An invalid input is a correction to make, not permission to bypass this final handoff. When the
scope has no calculator contract, explain that limitation directly rather than mislabelling it.

Missing-input path: run the matching supported calculator contract on the evidence actually
available, retaining missingness. For a stock with no dated observations, use `assumed_pace`
with `observations: []` when the explicit user rate passes its quote binding; ask only for the
missing dated baseline. Otherwise use `observed_pace` with `observations: []`. Both return
`needs_input`; never invent rows. Relay that handoff for the resolved target and stop the forecast.
Do not append offers of unsupported ranges or probabilities. If the metric/scope has no supported
contract, explain that gap directly; never relabel it merely to run a script.

## Decide whether the requested forecast is identifiable

Resolve the target from context, honoring any user change. Use the current horizon, inheriting
the previous one only when unchanged. A post's single lifetime observation cannot define its
future trajectory. Without a valid user rate, correct earlier invented odds, ask for that post's
dated observations and stop its numeric forecast. A dated baseline plus an explicit rate that
passes `assumed_pace` can support conditional arithmetic. Do not substitute a channel-content
scenario to fill a post's monthly table.

A historical per-post median times a posting cadence estimates a batch at the sampled posts'
observed ages. It is not a monthly deadline series, and adding it repeatedly to today's account
stock does not make it one. Keep this distinction even under a "conditional" label. Engagement
combining likes and comments is not a like rate; never use it to compute future likes.

Check each metric independently. Calculate supported ones with the script; ask for the others'
missing dated records or supported explicit assumptions, without suggesting invented rates.
Correct an earlier estimate only if it actually exists. When no metric is supported, end after
clarification: no forecast, table of unknowns, different-target forecast or promise of later odds.
Missing forecast inputs never block supported calculations or the rest of a complete review.

## Require source rows, not reconstructed summaries

A report's median, quartiles or cadence supplies context, not the required dated rows or a
validated calculation. Request missing rows or the saved snapshot. Never reconstruct samples
from aggregates or bypass `estimate_growth.py` with mental arithmetic or a custom calculator.

Preserve the source's date meanings. A sampling window describes selection, not necessarily when
metrics were observed. Relative post ages without an explicit observation timestamp do not supply
publication or measurement timestamps. Never assign the window endpoint as `observed_at`, subtract
relative ages to invent `published_at`, or add dates inferred from a previous assistant to make an
incomplete export pass. Ask for actual dated rows or the original snapshot instead. A source that
explicitly supplies the required timestamp can be used with its stated precision and limits.

Resolve the continuation's referent before selecting a calculation. If "the same" could mean an
account, new posts or a named existing post, ask which one instead of filling all three with
numbers. A content batch at historical observation ages answers a different question from a
calendar-month trajectory; only offer that alternative with its changed measurement explicit,
and do not produce its table until the user chooses that alternative.

## Before answering a forecast or extending one

Resolve the account versus a particular post, the platform, metric definition (net additions,
cumulative stock, period total or new-content performance), baseline date and currently requested horizon.
Use clear prior context; clarify only unresolved scope. Do not silently switch between a top
post and the whole account when a follow-up asks for the same calculation over more months.
Resolve a clear pronoun through the intervening reply before falling back to an older explicit
request. Historical account and post sections do not by themselves request both targets.

Stock `horizon_days` starts at the latest dated observation, not today. For an explicit deadline
or a request relative to today, calculate the elapsed days from that baseline to the requested
endpoint; do not pass only the number of days from today. If the reference date is unclear, ask
or label the result explicitly as baseline-relative, never as a forecast from today. An old
baseline needs a stated unchanged-pace assumption over the entire interval, or a current record.

Audit each input's source. A previous assistant's outcome range, multiplier, conversion rate or
"most likely" number is not an observation or a user-supplied assumption, even if the user asks
to extend it. Correct that earlier overstatement explicitly before reusing the genuine baseline.
A single public snapshot cannot supply a post's growth trajectory, subscriber conversion or
monthly account-wide totals. Keep missing subscriber history separate from available content data.

This Skill computes conditional amounts, not occurrence probabilities. More dated records can
enable unchanged-pace arithmetic, not calibrated odds. Do not give scenario weights, confidence
intervals or "most likely" labels from snapshots, medians or intuition. Neither a subjective
label nor a disclaimer validates them. Calibration needs a defined outcome/horizon and evaluated
probabilities against held-out comparable outcomes; this calculator supplies none of that.

Check the whole reply and its next-step promises. Answer odds requests explicitly: occurrence
probability is unavailable here, even after the requested records arrive. Never offer
"conditional percentages" or a later probability table. Arithmetic percent changes must name
the metric and baseline, not imply a chance of success. Deliver supported amounts with their
assumptions and limits; ask only for missing inputs to the others. An opening caveat cannot
excuse a contradictory closing promise.

For multi-month requests, keep every month on the same explicit measurement and assumptions.
Show monthly values only when the supported calculation can produce them; never invent a decay,
acceleration or breakout curve to fill a table. State the observed window alongside the requested
horizon, explain which assumptions become less dependable farther out, and set a review point
when new dated observations arrive. Do not multiply a new-content scenario into an account total
or the future cumulative total of one existing post. For each unsupported metric, identify the
missing series rather than give a numeric forecast; still calculate independently supported metrics.

When the evidence and assumptions are sufficient, still answer the supported numeric part with
the script: do not turn this boundary into a blanket refusal. Put the formula, changed assumption
and uncertainty next to each conditional result. Controllable goals and experiments are plans,
not promises about what the platform will distribute.

In a public review, use `drive.py growth` for the report's single content slot. Choose a listed
choice, save `review_growth_input.json` with the user's quantity/wording, and rerun before synthesis.
Its metric/horizon follow the question (views/30 days by default). `drive.py report` binds the
input to the retained snapshot, analysis and question, recomputes it, and carries its measurement,
formula, ages and limits in `ACCOUNT_REVIEW.md`. Use the standalone path below for other results.

## Choose the supported output path

A growth-only request or follow-up uses `compose_forecast_reply.py` above, which recomputes
each input through `estimate_growth.py` and returns the complete reply. It can calculate `observed_pace` or `assumed_pace` from their dated
inputs, including one dated baseline plus an explicit user-supplied rate that passes the existing
Chinese/English day/week quote binding. Do not promise arbitrary rate-language support: named
English view/like rates and monthly-rate phrases are not recognized by that legacy reader.
Other compatible forms still use their actual metric and scope; never relabel or rewrite the
user's quote to make validation pass. Unsupported inputs need clarification or dated observations.
A rate is a
conditional assumption, not a measured trajectory or probability.

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

## Calculation inputs and commands

Before preparing any standalone input (including `needs_input`), read
[growth-calculation-inputs.md](growth-calculation-inputs.md) for the exact schemas, commands and
source-bound quantity contracts. Do not invent a shorter input format.
