# Diagnosis report shape

Read this file whole before writing `analysis/creator_view.json` on a diagnosis. It is the card
shape, the field caps and the change-instruction rules the delivery gates check.

## Result shape

Everything in this file is the **diagnosis** shape. Nothing here overrides it for a craft
teardown: a craft teardown has no fixed shape on purpose — see `craft-teardown.md`, and do not
carry these titles into one.

A summary, then three cards with fixed titles, three lines in each, paired straight down. This is
a three-card cut of a tested six-section layout, minus two of its sections; the
reason a creator can read it fast is that the titles never move, so they know where the answer
lives before they start reading.

| Position | What it answers | What it holds |
|---|---|---|
| summary | — | The judgement, in a sentence or two, before anything else |
| Card 1 | what is working | The mechanisms that are working |
| Card 2 | what holds it back | What holds each of them back |
| Card 3 | what to do about it | What to do about each, with the line to say |

**The order is fixed; the headings are yours to write.** Give each card a heading in the creator's
language that says what it answers, and do not give two cards the same one. A validator checks the
order, the pairing and the evidence — not the wording, because wording that can only be one
language is wording no localized report can use.

Each `cards[].why_for_you` is one JSON string containing exactly three nonempty lines,
encoded with `\n`. The same line index pairs mechanism → evidence-supported weakness → next
change across the three cards. Missing evidence remains unknown: do not invent a weakness to
fill the shape, or prescribe a change that depends on an unconfirmed weakness. A problem with
no change belongs in the structured observations; a change answering no stated problem is a guess.

**When the video is somebody else's**, the sequence stays but the subject moves. This is still a
diagnosis — it is the case the description calls a teardown of someone else's video, and it is not
the craft teardown mode. Their published video is not the creator's to repair, so card 2 reads as
what they would inherit by copying it (its action, labelled "How to avoid it", says how not to
inherit it), and card 3 is what they do differently in their own next video (labelled "What to do in
yours") — never a repair order for a post that is already out. On the creator's own video the three
actions are labelled "How to reuse it", "How to fix it" and "What to change". The renderer adds each
label: start no `action` with one.

`decision` is one word for the editing decision the report stands on. Own video: `keep` (it works;
the changes are small), `recut` (re-edit the footage already shot) or `replace` (needs new footage
or a new version). Someone else's or unknown: `borrow` (use the mechanism in their own next video)
or `skip` (nothing transfers). The view contract prints the values allowed for this run.

Two of that six-section layout's sections are deliberately not reproduced. A single virality verdict is
refused for the reason `composite_score` is fixed to null — hook stage and sustain stage were
observed ranking the same two posts in opposite orders, so one scalar destroys the distinction
that makes the report actionable. Suggested titles belong to Script and Packaging; producing them
here would put two Skills in the same job with no shared contract.

Each line carries the evidence position it rests on: a real second for video or the original slide position for an image post. Never manufacture a timestamp for a still image.

Every card cites at least one `observations.{observation_id}` in `evidence_refs`. That reference
is what keeps the report standing on the analysis instead of restating it from memory — it carries
the dimension, the basis and the confidence behind the card.

## How long each part gets

A report the creator has to read twice has not saved them anything. Each field is capped, because
length pools: three runs of this shape put a median of 613 characters into a single `why_for_you`
— three times the whole report's thesis — while every other field stayed short on its own.

The caps are in **display columns**, not characters: a full-width character counts as two and
everything else as one. A cap counted in characters is a different cap in every script — these
figures were set on Chinese reports, and read as characters they gave a Latin-script report about
a third of the room for the same content.

Run `finish_diagnosis.py --check` after writing the view: it reports every field over its cap and
exits 3 (`needs_correction`) until the view passes, 0 once it is `ready`.

| Field | Columns |
|---|---:|
| `summary` | 480 |
| `cards[].why_for_you` | 480 |
| `cards[].action` | 320 |
| `hooks[].visual_direction` | 240 |
| `data_note` | 240 |
| `hooks[].purpose` | 160 |

These are not a style preference. The tested six-section and four-card layouts
read quickly because each part is one or two sentences; the reason to cap a field rather than cut a card is
that the sequence is what carries the analysis, and dropping a card would drop a reading.

`data_note` is read-only and derived by `build_creator_result.py`, not authored by the model.
It is one measurement line within 240 columns, in the view's language (see below): recorded extraction, canonical frame references cited by these cards, transcript
provenance and owner-metric availability. Requested
`sampling_plan` intervals and possibly nominal `t_seconds` do not establish actual decoded spacing
or viewing. Without verified decode records, describe intervals only as planned/requested
limitations beside the relevant finding. The line states only countable facts; it says nothing
about viewing, so never add that the frames were not looked at when you opened and cited them. The
builder writes it in Chinese, English, Spanish, Portuguese, German, French, Japanese, Korean,
Indonesian, Vietnamese, Arabic or Hindi by the view's `language`; for any other language, the host translates the complete line
for delivery without changing its quantities or uncertainty.
Put claim-specific uncertainty once beside the claim it weakens, not in this measurement line.

## What a change instruction contains

- `time_range` points into the original cut, in seconds as the evidence records them: a span
  `4.03–6.13s` or one moment `5.03s`; the report prints it as m:ss. Whenever it is present, name what is at that moment —
  the on-screen words in `on_screen_text`, or what the shot does in `visual_direction`, or both. A
  bare second is not evidence the creator can check.
- `spoken_line` is a line the creator can read aloud in their own next video. On their own video
  it may quote their own cut — "start from the sentence you already say at 21.2s" is the most
  useful form it takes. On somebody else's video it must be a new line that demonstrates the
  borrowed mechanism, never that creator's own sentence: what transfers is the structure, and the
  wording is bound to a person the audience already knows. The gate compares every line against
  the analysed video's transcript cues and rejects a match.
- To point at footage worth reusing, put that frame's `frame_id` in the card's `evidence_refs`.
  Saying "open on the frame you already have at 4.017s" is only actionable if the frame is named.

### When the change is the opening of a short video

How to choose and write a new opening is the `opening` card (in the brief when it was selected; it
reads `references/hook-core/` through `scripts/prepare_video_hook.py`, never directly). Put it in the
card fields this way:

- `visual_direction`: the first frame and the first sound together, and the question their
  combination raises. Leave `time_range` off: this hook is about the next cut, not a moment in
  this one.
- `spoken_line`: the first words, when the opening is spoken, under the rules above.
- The card's `action`: the material to prepare when the creator has not shown they have it — "a
  screenshot of the result you can actually show" — never written as if they already own it.

When the strongest opening already exists in the creator's own cut, give it its own hook — the
`time_range` and what is on screen there — and let the opening hook say how to bring it to the front.

`finish_diagnosis.py` runs `validate_creator_shape.py`, which enforces the sequence, the pairing,
the observation reference, the timestamp binding and the `spoken_line` rule; do not run it yourself.

## Promise and payoff

`scripts/compute_promise_payoff.py` (run by `prepare_analysis.py`, results in section 4 of the brief)
anchors the promise: the first thing said inside `frames.sampling_plan.hook_window_s`. It will not
locate the payoff. Name the cue you judge pays it off and the script returns the gap; name nothing
and it returns the candidate cues. Do not report a distance the script did not compute.

## What the document does not carry

The schema allows a `source_url` on a card. Do not set one: the creator handed you the video, and
a bare link under a change instruction reads as a stray paste rather than as evidence. The address
lives on `content_ref.permalink` in the structured object, and a moment worth opening is named by
its timestamp and its `observations.{id}`, not by a second copy of the same URL.

## What `details` may hold

`details` is the host's half of the result, not the audit ledger. It must not carry
`calculations`, `reproducibility`, `limitations` or `evidence`: those belong to the `VideoAnalysis`
and `ContentEvidence` objects, which travel alongside and are where anyone checking the work will
look. Keeping them out of the creator's text is *Delivery* in `SKILL.md`; this is a second thing. Copying
them into `details` duplicates the audit layer into the object the App renders, and the two copies
then drift.
