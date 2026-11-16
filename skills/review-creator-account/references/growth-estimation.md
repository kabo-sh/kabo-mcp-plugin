# Conditional growth calculations

Use this procedure for a forecast or its continuation. A complete account review additionally
reads [growth-review-workflow.md](growth-review-workflow.md); do not start that review merely
because a forecast lacks data.

## 1. Keep the requested target and measurement

For a continuation, inspect the last completed user request and its answer. Extend that one
account or post; a change of time horizon does not request both. Resolve a pronoun through that
answer, not an older account table. Name the selected target first. Clarify only genuinely
ambiguous scope. Earlier assistant forecasts are claims to correct, never source observations.

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

Run `scripts/forecast.py` with the command in `SKILL.md`. It writes `forecast_scope.json` (the
target, the verbatim request and its reference) and one calculation input per metric from the
flags, so every input carries the same target and contract. It chooses the method from what was
supplied: two or more dated counts give `observed_pace`; one dated count plus `--rate` gives
`assumed_pace`; views/likes/comments of new content use `content_scenario` on `--snapshot`
(the most captured format unless `--format` names one; the captured pace unless `--posts` names
the items). Anything missing returns `needs_input`, which asks only for the missing records.
Never write these input files by hand or edit them after the command.

`estimate_growth.py` and `compose_forecast_reply.py` remain the calculators behind it; call them
directly only for a creator-stated publishing frequency (`plan` with `period`, see
[growth-calculation-inputs.md](growth-calculation-inputs.md)). An invalid input is a correction
to make, not permission to bypass the calculation.

The final reply is the complete text between `KABO_FORECAST_REPLY_BEGIN` and
`KABO_FORECAST_REPLY_END`; translate fixed labels if needed. Keep values, target, dates, sources,
formula, assumptions, missingness and limits. Do not replace it with another numeric scenario,
historical reference table or promise. Missing-input results are a complete answer to what can
be calculated now; no invented forecast is needed to fill a table.

Inside a complete review, retain the review/funnel findings and use the separate handoff rules
in [growth-review-workflow.md](growth-review-workflow.md), including `needs_input` stock results.
