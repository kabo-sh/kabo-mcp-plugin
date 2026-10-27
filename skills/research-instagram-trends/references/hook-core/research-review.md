# Opening mechanisms in trend research

Use this reference when the synthesis needs an opening mechanism or a practical opening
recommendation. Use the evidence and output fields the Workflow already selected. This reference
adds no discovery, ranking, watching or model stage.

## Decide what the current evidence supports

Titles, captions and untimed transcripts can suggest a topic or writing direction. They cannot
establish the actual first frame, on-screen text timing, first sound, delivery or audiovisual
alignment. Describe an unobserved opening as a proposed production choice, not a finding about
what that video did. A transcript is not a listening observation. Keep existing content citations
attached to observed claims. Do not infer private retention from public plays or a reference's
success.

## Choose a mechanism that the creator can make

`rank` prints the pattern catalog (`hook-context.json`): each mode's ID, name and material
requirements. Read one mode's full details — picture, sound, intended joint effect, material
requirements, applicability and exceptions — only through the script:

```sh
cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/prepare_hook_context.py' --platform instagram --purpose trends --pattern-id <Mxx> --output hook-opening-<Mxx>.json
```

Pass `--pattern-id` up to three times. Never open the pattern data file itself. Select one main
mode; series recognition (M13) and sound emphasis (M15) can overlay it.

- For information-led content, try a concrete proof/result, recognisable problem, comparison,
  demonstration or counterintuitive claim supported by the actual material.
- For action/suspense content, the visible situation can carry the question. Intentional silence,
  no caption and first-person narration are valid choices; do not impose an immediate spoken
  topic or a universal loudness requirement.
- Check the required material before recommending the mode. A proof-led opening needs owned or
  authorised readable proof; a comparison needs both sides; an action-led opening needs the
  action. A public reference link does not give reuse permission or prove the creator has it.

Write a usable suggestion in the existing mechanism, differentiation, direction or recommendation
field: what appears first, what is said or heard (or why silence is intentional), and what the
combination makes the viewer understand or want to find out. Keep it proportionate to the task;
research does not need a full draft or three mandatory variants.

For example, a caption about saving time can support: "Try showing your own before/after timer
first, then explain the one change." It cannot support: "The video opens with a timer." A watched
action with a clearly visible unresolved outcome can support an action-led recommendation
without requiring a title card or speech.

## Keep method context out of current-task evidence

The modes are method, not observations of any video in this run, and the script returns no
historical examples. Use the conditional rules and checks for relevant questions, not a universal
ten-item report or pass/fail score. Account-level repetition still needs the workflow's supporting
videos; a single opening does not establish a repeated account problem. Title/cover promises and a
closing loop are context only when they help judge the opening. Advertising thresholds and
long-video retention examples are not universal short-video cutoffs.

Keep metric/missingness audit notes in the workflow's existing structured fields. Give the
creator the supported mechanism and a concrete production choice, in their language, through
the existing renderer. Do not write a second report, alter rankings or add media retrieval to
make an opening claim.
