# Opening mechanisms in competitor research

Read this whole file before writing an opening mechanism or a practical opening recommendation
into the synthesis. Use the evidence and output fields the synthesis already has; this reference
adds no discovery, ranking, watching or model stage.

## Decide what the current evidence supports

Titles, captions and untimed transcripts can suggest a topic or writing direction. They cannot
establish the actual first frame, on-screen text timing, first sound, delivery or audiovisual
alignment. Describe an unobserved opening as a proposed production choice, not a finding about
what that video did.

- With titles/captions only, keep reference-related findings, including overview and pattern
  labels, about their wording. Label inferred mechanisms as title/caption interpretations: say
  "the titles suggest a demonstration direction", rather than narrating what the creators show or
  do. Reserve action order, visible proof, first frames, text timing, sound and delivery for
  observed media.
- Public performance numbers do not establish why an opening worked; a transcript is not a
  listening observation. Do not infer private retention from public plays or a reference's
  success.
- Keep current-task citations and metrics unchanged and attached to the claims they support.

## Choose a mechanism the creator can make

`synthesis-evidence.json` carries `hook_context.pattern_catalog`: the ids and names of fifteen
short-video opening patterns. Those ids and names are method labels, never an observation of a
competitor's video. Read a pattern's details only through this command, never by opening the
Skill's data files:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/prepare_hook_context.py' --platform tiktok --purpose competitors --pattern-id <Mxx> --output hook-opening-<Mxx>.json
```

Pass one to three `--pattern-id` values. Each pattern specifies picture, sound, intended joint
effect, material requirements and exceptions. Select one main pattern; series recognition (M13)
and sound emphasis (M15) can overlay it.

- For information-led content, try a concrete proof/result, recognisable problem, comparison,
  demonstration or counterintuitive claim supported by the actual material.
- For action/suspense content, the visible situation can carry the question. Intentional silence,
  no caption and first-person narration are valid choices; do not impose an immediate spoken topic
  or a universal loudness requirement.
- Check the required material before recommending the pattern: proof needs owned or authorised
  readable proof, comparison needs both sides, and demonstration needs the actual action or
  workflow. Unconfirmed materials are preparation requirements, not assets the creator already
  owns. A competitor's video is not reuse permission.

Write the suggestion in the existing mechanism or differentiation field as one complete production
choice: what appears first, what is said or heard (or why silence is intentional), and what the
combination makes the viewer understand or want to find out. Keep it proportionate to the task;
research does not need a full draft or three mandatory variants. State the proposed execution as a
recommendation for the creator's next video.

For example, a caption about saving time can support: "Try showing your own before/after timer
first, then explain the one change." It cannot support: "The video opens with a timer."

## Keep method context out of evidence

- Pattern details are method context, not current account evidence, audience-comment needs or
  additional competitors. They supply no viewing or listening evidence.
- Use the conditional checks for relevant questions, not a universal ten-item report or pass/fail
  score. Account-level repetition still needs the selected accounts' supporting videos; a single
  opening does not establish a repeated account problem. Advertising thresholds and long-video
  retention examples are not universal short-video cutoffs.
- Write the production choice in the delivery language. Keep pattern ids, internal labels and the
  helper command in task artifacts, outside Creator-facing prose. Do not write a second report,
  alter rankings or add media retrieval to make an opening claim.
