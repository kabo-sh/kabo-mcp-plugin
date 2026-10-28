# Opening design and review

Read this when you write the opening record at the script gate. It is a method for using the
current footage, not a new account style guide, an external dependency or a claim that any
opening will go viral.

## Evidence before a pattern

The brief gives you the reference's opening as sentences, shots and beats with timings, plus the
creator's own opening and closing lines. State what makes someone continue: what they see, what
they hear, and what the two say together. Cite the source (the brief field and the interval).
Compare with the creator's own **same-format** openings where the brief has them; record the
sample size and what is missing. If those examples are unavailable, say so. Plays alone do not
establish retention or cause.

Default: preserve the reference's narrative job and express it using the creator's measured habits
and available material. An explicit creative brief from the user overrides style suggestions, but
does not waive factual provenance.

When considering a pattern, write its intent, picture, sound, their relationship, conditions under
which it fits, and the samples you actually inspected. Name a counterexample or an uncertainty.
Candidates worth inspecting include a visible demonstration, a question the picture helps answer,
a contrast, an evidence insert and a cold open into an action. These are search prompts, **not a
validated pattern library**. Do not manufacture sample IDs, performance evidence or platform rules.
An external pattern library, if the user supplies one, can suggest candidates; its personal-account
rules and claimed sample count do not become evidence for this creator.

## Candidates: write several, choose one yourself

On this route (`creator-into-scene.md` section 0.1) write 2-3 complete candidates and run pass 1 on
each. The reference's own opening may be one of them. Choose one yourself and record
`candidates[]`, `chosen` and `choice_why`; do not ask the user to pick. The picture is fixed by the
reference, so candidates differ in the first line and the first-frame text, and the review carries
`"route": "B"`.

## Three passes, one decision record

1. **Script (yours, at the gate):** before refining the body, state the first picture, first
   audible event, opening line and the viewer's reason to continue. Check their relationship and
   the factual sources. Silence, a still picture, no title or a delayed voice can be intentional;
   explain the intended effect.
2. **Shots (the runner):** the first frame and first shot are checked against the promised action,
   prop or evidence, and captions are kept off important subjects.
3. **Final (the runner):** the opening is checked for unintended black or blank frames, unwanted
   silence, text introduced by generation, clipping and sync.

Record pass 1 in the opening review, in this shape (`"stage": "script"`, `"route": "B"`):

```json
{
  "stage": "script",
  "route": "B",
  "intent": "<reason the viewer continues>",
  "picture": "<what the first shot shows, from the brief>",
  "sound": "<first audible event and its timing>",
  "relationship": "<what picture and sound communicate together>",
  "creator_fit": "<same-format habit, sample size and any deviation>",
  "conditions": "<when this choice fits; uncertainty or counterexample>",
  "evidence": [{"source": "<brief field and interval>", "observation": "<what it shows>"}],
  "checks": {
    "picture_sound": {"status": "pass", "basis": "<your judgment and what it rests on>"},
    "first_frame": {"status": "unavailable", "basis": "keyframes are not in the brief"}
  },
  "candidates": [
    {"first_line": "<line>", "first_frame_text": "<text>", "original": true, "assessment": "<what it does, what it rests on>"},
    {"first_line": "<line>", "first_frame_text": "<text>", "original": false, "assessment": "<...>"}
  ],
  "chosen": 0,
  "choice_why": "<why this one over the others>",
  "verdict": "limited"
}
```

Use `fail` for a defect, `unavailable` for missing evidence and `not_applicable` with a reason.
`ready` cannot conceal failed or unavailable checks. `limited` states missing evidence; it is not
permission to ignore an unresolved defect. The runner's opening check verifies completeness and
contradictory states; **it cannot see the video or judge its quality**.

## Defaults and user choices

Do not ask the user to pick a pattern, font, first-sound timestamp or caption height. Use the
reference mechanism, the creator's habits and any brief the user gave to propose one coherent
opening, and explain the choice when you report the result. Reuse decisions already made in the
conversation.

## No universal personal-account prescriptions

Title at frame zero, speech at exactly zero, a particular word count, font or colour, language,
loudness target, hand gesture or camera motion are **contextual choices**. Compare them with the
creator and the reference; do not fail an arbitrary creator for another person's preference.
Caption placement keeps its priority: avoid faces, hands, props and graphics, then match the
creator's habit.
