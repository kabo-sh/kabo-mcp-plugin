# Line-by-line rewriting and sourcing: rules, number checks, what you may change

**Bottom line first**: a rewrite passes on two conditions -- **every beat still does its job**, and
**every factual statement can be traced back to the creator's own material**. The second one is
decided by the runner's script check, not by good intentions. Measured across a test set, this rule
took "specific claims that have a source" from 0-4 out of 7 up to 7/7 through 16/16, and it held for
every case. Face similarity on the same cases was flat or better, so the gain does not come at the
expense of another metric.

| Case | Sourced claims (with the rule / without it) | Face similarity (with / without) |
|---|---|---|
| 1 | 11/11 / 2/10 | 0.897 / 0.838 |
| 2 | 14/14 / 0 | 0.790 / 0.727 |
| 3 | 7/7 / 4/7 | 0.894 / 0.900 |
| 4 | 10/10 / 0/6 | 0.827 / 0.830 |
| 5 | 8/8 / 1/6 | 0.824 / 0.708 |
| 6 | 9/9 / 0/2 | 0.889 / 0.789 |
| 7 | 16/16 / 0/6 | 0.834 / 0.817 |

> Host edition. The runner built the creator's material from their videos (transcripts with
> timings) before the gate; the brief carries it as `creator.own_lines` and, when present, library
> items with ids. Take only the writing rules from this file.

## 1. Where sources come from

The creator's own lines in the brief are verbatim transcript fragments with the video and the time
window they were said in. A claim that cites them uses `src`:
`{"video": "<video>", "field": "transcript", "t0": <start>, "t1": <end>, "quote": "<verbatim words>"}`.
`quote` must be a verbatim fragment of what was said in that window: the runner back-checks it
against the window and a quote attributed to the wrong window fails (measured word coverage 0.25
and 0.29 against 1.0 for the correct window).

**On conflict, on-screen text and the post caption win** over speech recognition. Conflicts are not
rare: a number written two ways (words vs digits), a dropped or inserted quantifier, and a
near-homophone that changes a number -- the dangerous one, because nothing flags it. When a number
or noun in a creator line looks misheard, do not build a claim on it.

## 2. Per-line annotation: `text / viral_role / claims`

Every script line is one entry. (The line and the ids below are **invented**.)

```json
{"text": "this one tool cut my prep time in half.",
 "viral_role": "b3",
 "claims": [{"phrase": "cut my prep time in half",
             "src": {"video": "EXAMPLEVID1", "field": "transcript", "t0": 12.4, "t1": 15.0,
                     "quote": "it cut my prep time in half"}}],
 "rewrite": {"slot": "author_claim", "basis": "their own result, said in EXAMPLEVID1",
             "why": "replaces the original author's income claim", "replaces": "<reference words>"}}
```

The kinds of claim:

| Claim | Meaning | Constraint |
|---|---|---|
| `"src": {...}` | The creator's own words | Verbatim, in the cited window |
| `"ref": "<library item id>"` | A library item from the brief | The item must exist in the brief |
| `"ref": "scene"` | Describes the setting **of this video's own picture** | Not a claim about the world, so it needs no source |
| `"ref": "viral_frame"` | Reuses the viral video's sentence frame with its nouns swapped, no fact attached | May carry a sentence frame only, never a number |
| `"ref": "inference"` | A new judgement or number that is not in the creator's material | Only on lines with `"origin": "inferred"`, and the line must start with a hedge |
| `"ref": "viral_line"` | The reference's own sentence, kept as is | Looked up in order in the reference transcript; numbers in it count as sourced to the reference |

No claim has `ref: null`. Basis names (`persona`, `platform_generic`, `creator_quote`,
`creator_habit`, `user_given`) are never a `ref`.

> ### `viral_frame` IS NOT AN ESCAPE HATCH
>
> It exists for exactly one thing: the half of a sentence that is the viral video's structure
> rather than anybody's claim. **A number, a name, a place, a specific event, a product, a claim
> about an effect -- all of it still needs real provenance.** Marking fact-bearing wording as a
> frame is fabrication with a provenance label stuck on it, and it is worse than leaving the claim
> unsourced, because an unsourced claim fails loudly while this one passes quietly.

## 3. Number checking (the thing that goes wrong most often)

Rule: **every number in a rewritten line must appear in the verbatim text of one of the sources
that line cites**. The checker converts English number words (zero...ten, sixteen, thirty) to
digits before comparing, but deliberately excludes "one" (it is usually a pronoun).

Measured: altering a sourced number by one digit was reported at once as a number without a source.
So **look the number up in the creator's lines before you write it**, rather than writing the line
first and hunting for a source afterwards.

## 4. May you change the original wording

These apply to the creator's own words inside a rewrite slot. Kept reference lines stay word for
word (`creator-into-scene.md` section 0.2).

| Situation | Allowed? | Notes |
|---|---|---|
| Reorder, shorten, drop filler words | **Yes** | `quote` only has to be a verbatim fragment of the cited window; the line itself can be tighter |
| Turn "what I did to myself" into "you go do it" | **Yes** | The fact is unchanged; only who it is aimed at moves |
| Swap one keyword (a call to action) | **Yes** | Reuse their own frame with the keyword swapped |
| Change a number | **No** | See section 3 |
| Merge facts from two of their videos into one line | **Yes** | `claims` must list both sources; number checking runs against the union |
| Add a conclusion they have never stated | **Only as an inference** | See section 5 |
| Jokes, reversals, attitude, tone | **No source needed** | As long as it hangs off their established persona -- a fixed character or stance they show in their own videos |

## 5. Inferences

The default is reuse: only facts the creator has actually stated. A new judgement, number or result
that their material does not contain is an inference: the line has `"origin": "inferred"`, it must
start with "I think", "My guess", "Probably" or "Maybe", it carries `"ref": "inference"`, and you
flag it to the user as needing their confirmation. An inference line must not be published before
the creator confirms it.

## 6. Beat-by-beat review (mandatory after rewriting)

When the rewrite is done, put the script and the reference's beats side by side and confirm, beat
by beat:

1. `viral_role` covers every beat of the original; no beat has been merged away or dropped without
   a `route_b.dropped` entry.
2. **The energy gap and the direction of heightening are unchanged**: the heightening beats still
   escalate attitude rather than piling on quantity.

## 7. Word count and duration budget (locked down while writing)

Duration is set by the voice-over. You do not have to match the viral video's duration, but stay
within **+30%** of it. Estimate it from the creator's own speech rate in the brief
(`creator.speech_rate_median`, words per second) and leave headroom: the same text can differ by
2 to 2.5 seconds between two voice takes. A first draft measured at +36% needed two trimming rounds
to land inside +30%. Every rewritten line adds words; a summary line is optional.

## 8. Common failures and what to do

| Failure | Symptom | Countermeasure |
|---|---|---|
| Writing lines first and finding sources afterwards | Numbers have no source | Invert it: pick the creator's lines first, then fit them to the slot |
| Using a speech-recognition mishearing as a fact | A number or a noun that fits nothing else the creator says | Do not build a claim on it |
| An inference line with no hedge | The check reports an unhedged inference | Start the line with "I think" or "My guess" |
| `phrase` is not a substring of the line | The check reports phrase not in text | Cut `phrase` straight out of `text` instead of retyping it |
| Sources are right but it does not sound like them | Everything reads as written prose | Prefer their verbatim lines; reuse their catchphrases -- the recurring line they use to open, react or sign off |
