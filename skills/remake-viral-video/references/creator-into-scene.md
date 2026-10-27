# Putting the creator into the viral video's own scene (route B)

**What this route is**: keep the viral video's **content and setting**, and put **the creator** in
it. They appear in that scene, saying that script. (A different method, route A, keeps only the
viral video's structure and films the creator in their own settings; this Skill does not use it.)

**The price of admission**: on this route **the whole face is generated**. It is not a real frame of
the creator with a new background behind it. Identity similarity is measurably lower than on route
A, and that is inherent, not a bug you can tune away.

> Host edition: sections 0, 2 and 7 of the route-B manual. The hosted runner runs every command
> named here (`cr ...`); take only the writing rules. Where this file says `analysis.json`, read
> the reference part of `brief/work/brief_input.json`; where it says the content library, read
> the creator lines in the same file.

## 0. The script: the reference's lines, four slots rewritten

Route B keeps what the reference says. **Every line stays the reference's own, in its order, except
four slots.** Know which line does what from the beats in the brief before you change anything.

### 0.1 Design the opening first, then the body

The first picture is the reference's own (rebuilt with the creator in it), so opening candidates
differ in the **first line** and the **first-frame text**. Write **2-3 candidates**. The reference's
own opening may be one of them (`"original": true`); keep it when it already gives the viewer a
reason to stay and does not need the creator's experience to be true -- do not rewrite a working
opening for its own sake. A candidate must not contradict the fixed first picture, and it must
lead into the topic the kept body actually delivers: the body stays the reference's, so an opening
about the creator's own subject that the body never returns to breaks the video.

Pick candidates from the material you actually have; these are prompts with the condition under
which each holds, not a pattern library:

| Material on hand | Opening to try | Holds only when |
|---|---|---|
| A visible action or result in the first shot | Say what is being shown, as it happens | The action is in the first frame, not later |
| A concrete number, name or object in the reference's script | Lead with it | It is sourced (kept reference line or the creator's own lines), not invented |
| A contrast (before/after, two options, two numbers) | State both sides at once | Both sides are in the script and the picture can carry them |
| A counter-intuitive claim or a "don't" | Say the conclusion flat, first word carries it | The body really supports it |
| A list, framework or steps | Name the list and its size | The body delivers that many items |
| A phenomenon worth naming | Name it as the first-frame text | The name is accurate to the content |

Run the opening-review pass 1 (`opening-review.md`) on each candidate, **choose one yourself** -- do
not hand the choice to the user -- and record it in the opening review with `"route": "B"`,
`candidates[]` (`first_line`, `first_frame_text`, `original`, `assessment`), `chosen` (index) and
`choice_why`. The runner's opening check requires these fields on a route-B review.

### 0.2 The body: four slots, nothing else

| Slot (`rewrite.slot`) | What it covers | Default | User may set |
|---|---|---|---|
| `author_claim` | The original author speaking about themselves: experience, credentials, clients, income, a freebie promise ("comment X and I'll send..."), an ad | Replace with something **the creator has really said** (cite their lines); the replacement has to make sense in the reference's scene. Nothing fits -> delete the line. Never invent their experience | Delete rather than replace, or the reverse |
| `opening` | The first line(s) and first-frame text | The candidate chosen in 0.1 (if that is the original, the line is simply kept) | -- |
| `summary` | **One added** line before the sign-off, closing in the creator's voice | A quote of theirs close in meaning (`basis: "creator_quote"`, cited); else one line in their persona (`basis: "persona"`, no new facts; persona rules of `rewrite-and-sources.md` section 4) | "Only their own words", "persona", or no summary at all |
| `cta` | The sign-off / call to action | Their recurring sign-off, found in their own videos (`basis: "creator_habit"`, cited); else a plain platform follow prompt (`basis: "platform_generic"`) | The exact text (`basis: "user_given"`) |

Every other line is kept **word for word and in order**; only fix obvious ASR errors and drop filler
words. Rewording kept lines into the creator's style, swapping examples for their own stories or
reordering is not this route. Facts about third parties in kept lines remain the reference's
content: mention any you doubt when you report the result.

**Preferences are your calls, not questions.** Apply the defaults in the table above unless
something in the material gives you a better reason, and record each of the three
(`summary_source`, `cta`, `author_claims`) as a choice in the decisions record (section 0.5):
`by: "default"` when you applied the default, `by: "agent"` when you made a different call (say
why), `by: "user"` when the user already said what they want.

### 0.3 The record

```json
{
  "route_b": {
    "dropped": [{"text": "<the deleted reference line>", "slot": "author_claim",
                 "beat": 4, "why": "<why it was deleted>"}],
    "inherit": [
      {"element": "<what carries the hook on screen>", "role": "hook", "ref": {"beat": 0},
       "decision": "keep"},
      {"element": "<what a cutaway shows>", "role": "cutaway", "ref": {"shot": 3},
       "decision": "drop", "why": "<why it cannot be kept>"},
      {"element": "numbered list 1-3 with icons, lit up as each point is spoken",
       "role": "on_screen_text", "ref": {"beat": 1}, "decision": "adapt",
       "why": "icons not visible in the brief; one emoji per spoken item",
       "ref_form": "emoji_icon", "layout": "vertical-left"}
    ]
  },
  "overlays": [
    {"kind": "title", "text": "<the reference's title sticker>", "t0": 0, "t1": null},
    {"kind": "list", "layout": "vertical-left", "x": 0.05, "y": 0.30,
     "items": [{"label": "1.", "icon": "<emoji>", "t": 2.1, "line": 2},
               {"label": "2.", "icon": "<emoji>", "t": 9.4, "line": 4}]}
  ],
  "lines": [
    {"text": "<chosen opening line>", "viral_role": "b0",
     "rewrite": {"slot": "opening", "why": "<candidate and reason>", "replaces": "<original>",
                 "basis": "<what it rests on>"}},
    {"text": "<reference line, unchanged>", "viral_role": "b2",
     "claims": [{"phrase": "<the whole line>", "ref": "viral_line"}]},
    {"text": "<their line>", "viral_role": "b6",
     "claims": [{"phrase": "<their line>", "src": {"video": "<video>", "field": "transcript",
                 "t0": 41.2, "t1": 43.0, "quote": "<their words>"}}],
     "rewrite": {"slot": "cta", "basis": "creator_habit", "why": "<where they use it>",
                 "replaces": "<the reference's sign-off>"}}
  ]
}
```

The top-level `route_b` object is what switches the route-B rules on; keep it. The runner copies
your recorded choices into `route_b.preferences` when it closes the decisions record.

**On-screen graphics are inherited in their own form.** The draft already writes the title
sticker and any numbered list into `overlays` with the reference's measured position and row
spacing, and adds the matching inherit row. Fill in the text and icons and leave the coordinates
and each reveal `t` as drafted; the runner moves each overlay off faces, hands and props as little
as possible and keeps captions off it. Changing icons into text (`out_form`) or moving the list
(`out_layout`) is an `adapt` with a `form_why` about the viewer; the runner rejects reasons about
rendering, fonts or effort.

**Every reference sentence has to be accounted for**, word by word: kept in an unchanged line,
named in the `rewrite.replaces` of the slot that replaced it (an `opening`, `author_claim` or `cta`
that takes the place of a reference line must carry `replaces`), or recorded in `route_b.dropped`.
That includes the end of the reference -- a dangling last line or the original sign-off is replaced
by `cta` (`replaces`) or dropped, never just left out. Cutting the author's self-mention out of the
middle of a line that is otherwise kept is allowed, but the cut-out words go into `dropped` as a
fragment (`"text": "<the words removed>"`); the rest of the line stays a `viral_line`.
`dropped[].beat` marks a beat as deleted on purpose only when the entry removed every sentence of
that beat; a fragment whose sentence is still partly kept does not drop the beat.

### 0.4 What the runner checks

The runner runs this check when you submit and names a failing field. It:

- looks every `viral_line` phrase up in the reference transcript, **in order** (ordered coverage
  >= 0.9, 1-3 consecutive sentences); numbers in a verified `viral_line` are sourced to the reference;
- requires every line without `rewrite` to be the reference's wording, marked `viral_line`, in the
  reference's order;
- requires `rewrite.slot` to be one of the four with a `why`; `author_claim` replacements, a
  `creator_quote` summary and a `creator_habit` sign-off must cite the creator's own lines; opening
  first, one summary, summary before sign-off, both after every kept line;
- requires well-formed `route_b.dropped`;
- requires `route_b.inherit` (section 0.5): every non-talking shot of the reference (`shots[].kind`
  other than `talking` in the brief) and the opening's hook recorded as `keep`, `adapt` or `drop`,
  with a `why` on every adapt and drop;
- walks the reference transcript and requires every sentence to be accounted for (kept, in a
  `rewrite.replaces`, or in `route_b.dropped`; up to 10% of a sentence's words may be ASR fixes or
  fillers);
- warns when a kept line reads like the author talking about themselves. Resolve it as
  `author_claim`, or say when you report the result that it is not the creator's experience.

Rewritten lines follow the provenance rules of `rewrite-and-sources.md` unchanged, including its
word budget (section 7).

### 0.5 Your calls, recorded once

Work the way a good editor does: **you make the creative calls and say what you decided and why.**
Nothing here is a question to the user except the talking model, which SKILL.md handles.

**Inherited elements are yours, and the default is keep.** Anything the user did not mention is
inherited from the reference: the prop or action that carries the hook, each cutaway (B-roll,
insert, card) and what it shows, a change of setup or angle between beats, on-screen text and
graphics the reference relies on, the scene's key objects. Decide each one and record it in
`route_b.inherit`:

| Field | Value |
|---|---|
| `element` | What it is, in a few words |
| `role` | `hook`, `payoff`, `cutaway`, `setup_change`, `on_screen_text` or `scene_object` |
| `ref` | Where it is in the reference: `{"beat": N}` and/or `{"shot": N}` (lists allowed) |
| `decision` | `keep`, `adapt` (kept in another form) or `drop` |
| `why` | Required for `adapt` and `drop`: the model cannot produce it, it belongs to the original author's identity, a safety issue, ... "Simpler" is not a reason |

Every non-talking shot in the brief and the opening's hook must have an entry; the runner's
script check fails otherwise. Removing something from the reference without an entry here is the
failure this ledger exists to catch: a cut that quietly loses the hook prop or every cutaway no
longer does what the reference did.

**Your calls go in the decisions record**:

```json
{"status": "pending",
 "summary": "<two or three sentences, in the user's language: what you will make>",
 "rights": "<one line, e.g. 'I'm assuming you have the right to use <name>'s face and voice -- tell me if not.'>",
 "choices": [
   {"key": "cta", "applied": "<what you will use>", "by": "default | agent | user",
    "why": "<one line>"}
 ],
 "questions": []}
```

- `choices` always records the three preferences (`summary_source`, `cta`, `author_claims`), and
  any other call worth knowing about (a fact you removed, the output length).
- `questions` is **usually empty**. Add one only for a genuinely ambiguous goal (`ambiguous_goal`),
  a fact only the user knows (`user_fact`), a real value trade-off such as a brand or how the
  creator is represented (`value_tradeoff`), or money beyond the estimate (`spend`) -- each with
  `kind`, `question`, `recommended` and `why`; at most 3. Style, wording, shots, frames and
  inherited elements are never questions.
- The right to use the creator's face and voice is **one line** (`rights`), not a separate stop.

The runner applies your recorded decisions; there is no separate check-in message. Write every
choice into the decisions record with a reason.

## 2. The first-frame prompt: four prose paragraphs

Route B has no right source frame -- the picture does not exist yet -- so each plate and anchor
prompt is **four paragraphs of plain descriptive prose**, in this order.

| Paragraph | What it establishes | What goes wrong when it is missing |
|---|---|---|
| **Capture** | What kind of image this is: a still from a phone video shot by this person, the lens, the look, the grade | The output reads as a studio portrait or an illustration, and cuts badly against real footage |
| **Person** | Who the creator is, from the identity references: their hair and outfit held exactly as in those references, and their natural look | The model averages them toward a generic face, and toward tidy straight hair and a plain top |
| **Shot** | Added by the runner from the anchor's measured `framing` field; you leave it out | Left to the writer, the person ends up small and far away (section 7) |
| **Setting** | The scene itself, in concrete nouns: what is behind them, materials, light sources, depth | The model falls back to the reference image's own room and the target scene disappears |

**The identity references.** Each anchor job's `references` already lists half-body frames of the
creator from different videos, then the plate. Say what each image is for ("the first four images
all show <name> and supply only their identity -- face, hair, build and outfit; the fifth image is
the room").

**The Person paragraph, written without seeing those frames:**

- **Hair**: "her hair exactly as in the identity references: the same hairstyle and the way it is
  worn, the same length and colour; not straightened, not smoothed, not tidied" (with the
  creator's pronoun). The runner refuses a person job without that hold clause. Do not name a
  feature you have not seen: a generic "long dark brown hair with curtain bangs" was measured to
  come back as straight salon hair a shade darker than the creator's.
- **Clothing**: "her own outfit from the identity references". Do not invent a plain or
  "unbranded" garment to avoid text: a print that is part of the clothing is the creator's, and
  the no-text rule covers only text the model adds. The runner refuses "unbranded" and similar
  wording on person jobs.
- **The look**: "natural unretouched look". No beautifying words ("softly lit skin", "smooth
  skin", "flawless", "glamour", ...): they pull the face toward a retouched studio portrait, and
  the runner refuses them.

Measured on one creator, same scene and model, n=2: one face crop + generic wording -> face
similarity 0.749 / 0.729, hair darkened and straightened, invented top; four half-body references
+ wording that holds the hair and outfit -> 0.817 / 0.802 (the creator's own frames: median 0.84).

Rules for writing them:

- **Describe, do not instruct.** Prose that says what the picture *is* outperforms commands that say
  what to do with the inputs. The measured pair in section 7 changed nothing else.
- **Leave the framing to the runner.** It measures each host shot of the reference (face size,
  where the head sits, how much of the body is in frame, the posture) and writes a sentence from
  each anchor's `framing` field into the prompt. Do not write a framing of your own, do not change
  the field, and never describe the shot relative to the plate ("as the seat would require",
  "matching that position").
- **Name the target setting in words even though the plate is passed too.** The plate is there so
  the model sees the room; the words are there so it cannot decide to use a different one.
- The plate prompt describes the reference scene with the speaker removed and burned-in text
  cleaned; it has no person in it.

## 7. The one wording that breaks this route

**Do not write an instruction that asks for the person at the size and perspective of a place in
the plate.** A clause of the form "put them there, at the right size and perspective for that spot"
does two things at once: the model adopts the plate's depth and puts them far away, **and the clause
silently cancels the framing sentence the runner adds** -- the measured framing is simply not
applied.

One measured single-variable comparison (same clean plate, same reference frames, same image model;
only the prompt changed):

| First-frame prompt | Face height (share of frame height) | Identity similarity |
|---|---|---|
| Imperative "place him there at the right size and perspective" | 0.052 | 0.686 |
| Four prose paragraphs (section 2) | **0.243** | **0.717** |
| The viral video itself (the target being matched) | 0.278 | -- |

Read it as: **"the person is tiny and far away" is not the model failing to draw them close. It is
the prompt pushing them away.**
