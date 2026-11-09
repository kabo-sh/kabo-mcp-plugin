# Delivery state

Track the structured stage and status, not a successful tool call or process exit alone.

| Last stage result | Work still required | Can send the completed idea report? |
| --- | --- | --- |
| prep / ok / ready_for_generation | Write the whole IdeaSet using the schema, then run core | No |
| core / needs_revision | Correct every listed issue in the same IdeaSet; run core once more | No |
| core / ok | Run the final export command in SKILL.md and display its returned file | Only after that check |
| not_met, failed or unreadable result | State the specific limitation without a completed idea list | No |

Large batches need the same per-candidate fields as small ones. Do not save only title, hook and
making direction: read the `ideaCandidate` required fields and definitions before authoring.
If a field error repeats across candidates, stdout groups it with every affected zero-based index;
fix every listed candidate. `revision_brief.json` retains the full original error list. Grouping
does not waive a field, shorten the requested batch or grant extra generation attempts.
Use JSON-aware updates at the named paths, then read back the changed fields before rerunning core.
Do not use blind text substitutions that silently match no fields or alter unrelated statuses.

Preserve the original input, evidence and attempt count. A runnable `needs_revision` is an action
to complete now, not a reason to skip the correction and provide a shorter unvalidated answer.
If execution truly cannot continue, disclose the incomplete validation and stop; do not call it
the completed Skill result. The final reply must keep every candidate's opening and filming
direction, including those later in a larger batch.
Do not shorten away the opening lines after successful validation. The title, opening line and
making direction are separate fields: all three must remain visible for every candidate.
