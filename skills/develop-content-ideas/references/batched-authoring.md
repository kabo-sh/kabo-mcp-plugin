# Bounded candidate authoring

Prep writes `idea_work_plan.json` and returns the next batch's global numbers, stable IDs,
request SHA-256 and executable `next_command`. Preparation is not a delivery result. Continue
in the same run now; do not offer an unvalidated short list or stop just because prep succeeded.

For each batch, author only its planned candidates, at most ten. Use the `ideaCandidate`
schema for all semantic fields; omit `idea_id` and `rank` because the script fills them.
Keep source, language, mechanism, people/object sets and production restrictions identical
across batches. Review `accepted_titles` before the next batch to avoid duplicates; for same-style
variants preserve the shared mechanism and vary only allowed slots. No new evidence is invented.

Write `batch-N.json` with precisely:

- `request_sha256`: the value returned by prep (binds this run's complete request).
- `batch_id`: the next integer from the work plan.
- `ideas`: the candidate objects for exactly `next_numbers`, in that order.
- `report`: only in the final batch. Author `status`, `overview`, `gates`, `interaction`,
  `evidence_summary` and any needed `evidence_gap_translations`. Review all accepted candidates
  when writing this aggregate report. Set `status` to `ready_for_selection` only when appropriate.
  Recommended IDs use the returned stable IDs, e.g. `idea-001`. Never include `ideas` inside report.

The script supplies only deterministic root fields (`schema_version`, `idea_set_id`, `request_id`,
`created_at`, `task_intent`, `source_mode`, `report_language`). It does not manufacture risk,
evidence, feasibility, translations, recommendations or other semantic judgments.

Execute the returned command, for example:

```sh
cd '<run directory>' && python3 '<skill directory>/scripts/run_ideas_stages.py' batch --run-dir . --input batch-1.json
```

`awaiting_batches` means continue the next batch, not answer the user. Only `ready_for_core`
means all candidates are assembled; still run core, export and exact path-based emission before
answering. Partial batches never produce a deliverable. Replaying identical content is idempotent;
conflicting content, another request's digest, unknown batch IDs or wrong counts are rejected.
Do not overwrite accepted batches. A network replay is not a new creative attempt.

Initial authoring uses `ceil(N / 10)` batch passes. Core then validates the full set once, including
cross-batch constraints and title uniqueness. If it returns `needs_revision`, revise the assembled
`idea_set.json` once to fix all reported errors, then rerun core. Do not submit replacement batches
or reset prep. Log initial authoring submissions separately from the two aggregate validation
attempts; neither counter proves the host's actual model-call count. Keep the same iteration,
output and wall-time budgets. Missing or invalid content never authorizes a short prose substitute.

The complete-file core interface remains compatible with previously authored artifacts, but
new generation uses this batch workflow. Once any batch is accepted, core refuses missing batches
even if a complete file is manually placed beside them. Terminal missing-source requests remain
on their existing terminal path and never get a generation work plan.
