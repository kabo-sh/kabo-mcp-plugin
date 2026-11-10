# Conditional growth calculations

Use this procedure for a forecast or its continuation. A complete account review additionally
reads [growth-review-workflow.md](growth-review-workflow.md); do not start that review merely
because a forecast lacks data.

## 1. Keep the requested target and measurement

For a continuation, inspect the last completed user request and its answer. Extend that one
account or post; a change of time horizon does not request both. Resolve a pronoun through that
answer, not an older account table. Name the selected target first. Clarify only genuinely
ambiguous scope. Earlier assistant forecasts are claims to correct, never source observations.
Read relevant attached history beyond previews as [forecast-context.md](forecast-context.md)
specifies. Preserve the last user-specified horizon when this turn changes only the requested
confidence or presentation; do not re-ask a period already present in that history.

Identify each requested metric as cumulative stock, period total or new-content performance.
A post's lifetime count is not its future growth; an account snapshot is not monthly growth.
Combined likes/comments engagement is not a like rate. Do not substitute another measurement.

Stock `horizon_days` starts at the latest observation. For an explicit deadline or time relative
to today, use all days from the baseline to that endpoint. If the reference date is unknown,
ask or label a baseline-relative calculation. An old baseline requires an explicit unchanged-pace
assumption over the whole interval, or a current record. For a multi-month request, calculate
every requested month on that same basis; never invent acceleration, decay or breakout curves.

## 2. Admit only source-backed calculation inputs

Read [growth-calculation-inputs.md](growth-calculation-inputs.md) for the exact input contracts.
Check metrics independently; a missing metric must not block supported arithmetic or a sales funnel.

| Calculation | Required evidence | What it can deliver |
|---|---|---|
| `observed_pace` stock | Two or more actual dated counts for this same target and metric | Unchanged observed net pace over the requested horizon |
| `assumed_pace` stock | One actual dated baseline plus the user's explicit rate passing the existing quote binding | The user's conditional arithmetic, with the quote retained |
| `content_scenario` batch | Actual dated per-post values, publication and observation dates, format and source; a supported publication plan | A new batch at the observed content ages, never a calendar deadline total |

A prior report's median, quartiles, range or posting cadence is **not** a set of source rows.
Without the required rows or original saved snapshot, do not multiply those summaries into
future views/likes, even under a “conditional”, “planning”, “low/base/high” or “not guaranteed” label.
Do not rebuild samples, do mental arithmetic instead, or write a custom calculator to evade this gate.

Keep missing dates absent. A sample-selection window is not the measurement timestamp; relative
post ages do not establish publication dates without a real observation timestamp. Never use the
window endpoint as `observed_at` or invent source dates. Ask for `[date, count]` records, not examples
that attach dates to this creator's real counts.

A new-content batch at historical observation ages is a different request from a monthly account
or single-post trajectory. Do not fill that trajectory with batch totals. Offer the changed
measurement only explicitly, and wait for the user to select it before delivering its table.

## 3. Keep probabilities unavailable

These scripts calculate conditional amounts, not occurrence probabilities. More records can
support arithmetic; they do not make probability estimates available here. Calibration would
require a defined outcome/horizon and probabilities evaluated against held-out comparable outcomes;
this calculator supplies none of that. Do not assign scenario weights, confidence intervals,
“most likely” outcomes or subjective chances from snapshots, medians or intuition.

Correct earlier unsupported forecasts when they exist. No opening disclaimer permits invented
numbers or a closing promise to supply probabilities later. Arithmetic percent changes must name
the metric and baseline; never call them a percent chance. Goals and experiments are plans, not
predictions. Do not promise arbitrary user-rate language support: use the contract's actual
Chinese/English day/week binding, without rewriting the user's quote or metric to make it pass.

## 4. Compute and deliver one complete reply

Save `forecast_scope.json` with exactly four nonempty string fields: `platform`, the selected
`target`, the verbatim target-setting `request_quote`, and its resolved `reference`. Do not put
`horizon_days`, metrics or schema metadata in this file; they belong to the calculation inputs
or the missing-input command flags. Every input must use that same target. This checks
consistency, not the correctness of the model's interpretation.

When a cumulative metric has no usable dated observations and no valid explicit user rate, use
this direct missing-input command. It builds `growth-input.v1`, `observed_pace` and the matching
scope internally; do not invent a mode such as `missing_data` or hand-author another empty input.

```sh
python3 '<skill directory>/scripts/compose_forecast_reply.py' --scope-file '<run directory>/forecast_scope.json' --missing-metric <subscribers|followers|views|likes|comments> --horizon-days <resolved days> --report-language <requested-language-tag> --output '<run directory>/FORECAST_REPLY.md'
```

Repeat `--missing-metric` for each missing cumulative metric, and add `--correct-prior` if earlier
unsupported forecasts exist. Use the resolved horizon, not a default. This path gives no numeric
estimate and requests actual dated counts; it does not label an undated snapshot as dated.
It is not a substitute for existing usable observations or an explicit user rate: those still
use the full inputs below. An independently supported metric can be included with `--input` in
the same command; never discard it to make every metric missing. Do not use this shortcut for
period totals or new-content batch scenarios.

For a missing stock baseline, use `assumed_pace` with `observations: []` if a valid user rate exists;
otherwise use `observed_pace` with `observations: []`. The calculator returns `needs_input` and asks
only for missing inputs. Unsupported metric contracts get an honest limitation, not a relabelled
input. Do not fabricate rows to obtain a number. Keep supported metrics alongside these gaps.

```sh
python3 '<skill directory>/scripts/compose_forecast_reply.py' --scope-file '<run directory>/forecast_scope.json' --input '<first-input.json>' --input '<next-input.json>' --question-file '<original-question.txt>' --report-language <requested-language-tag> --output '<run directory>/FORECAST_REPLY.md'
```

Use one `--input` per requested metric/horizon, recomputed through `estimate_growth.py`. Add
`--snapshot` only to bind content inputs to the original saved snapshot; never pass it to a
standalone stock command. Add `--correct-prior` only for actual earlier unsupported forecasts.
An invalid input is a correction to make, not permission to bypass the calculation.

The final reply is the complete text between `KABO_FORECAST_REPLY_BEGIN` and
`KABO_FORECAST_REPLY_END`; copy it verbatim, without translating after validation. Keep values, target, dates, sources,
formula, assumptions, missingness and limits. Do not replace it with another numeric scenario,
historical reference table or promise. Missing-input results are a complete answer to what can
be calculated now; no invented forecast is needed to fill a table.

Inside a complete review, retain the review/funnel findings and use the separate handoff rules
in [growth-review-workflow.md](growth-review-workflow.md), including `needs_input` stock results.

## Output language is decided before the final command

Use the current user's requested reply language, otherwise the language of their current question;
do not inherit another language from historical attachments. Pass `--report-language en` for English.
The composer, not a second model-written response, owns the final text.

For another language, supply `--translations-file reply-translations.json` alongside that tag:
`{"report_language":"<tag>","strings":{"<English template>":"<translated template>"}}`.
Translate each fixed template named by the composer's combined diagnostic, preserving each numbered
placeholder (such as `{0}`, `{1:g}`), occurrence count and numeric format exactly. The script inserts
actual targets, values, dates, source quotes and formulae afterwards; never insert new facts into
labels. This validates template structure, not translation meaning. Missing or malformed translations
produce no deliverable. Correct the catalog before retrying the same composition, not by translating
the output in the final reply. The calculation inputs and boundaries remain unchanged.
