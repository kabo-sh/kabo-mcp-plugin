# Default video diagnosis

The method for every diagnosis and content read. On its own it gives a complete, general diagnosis;
a topic card, when one is loaded, goes deeper on one aspect inside the same structure. The output
contract decides the shape of what you write; this card decides what you look at, how you judge it
and what comes first.

## 1. Fix three things before judging anything

1. **Who it is for.** The viewer this video is built to stop: a beginner with a problem, a fan of
   the creator, a buyer comparing options, someone scrolling for a laugh. Infer it from what is
   said, shown and written, and say it is inferred.
2. **What the opening promises.** The first frame, first line and first text together make one
   promise: a result, an answer, a story, a laugh, a reveal. Write it down in one sentence, with
   the ids it rests on.
3. **What the video actually delivers.** Where (or whether) that promise is paid, and what else
   the video spends its time on.

Every later judgment is measured against these three. A gap between 2 and 3 is usually the
biggest finding in the video.

**Judge the video by its own genre.** Each kind needs different evidence before you may call it
working:

| Genre | It works when | Evidence that shows it |
|---|---|---|
| Skit, short drama | setup is instantly readable, escalation, a turn the viewer did not see coming | frames of faces and action, the line that lands the turn |
| Tutorial, how-to | the result is shown, the steps are followable, the result is checked | the result on screen, each step visible or spoken |
| Product, sales | a problem the viewer has, a trigger-to-result demonstration, one clear offer | the product doing the thing in one continuous sequence |
| Personal story, vlog | a want, an obstacle, a change, told by someone the viewer can read | face and voice at the turn, the line that names the change |
| Commentary, explainer | a claim worth hearing, support for it, a takeaway | the claim's wording, what supports it on screen |

Do not mark a skit down for having no proof, or a tutorial for having no twist. A deliberate joke,
exaggeration or staged opening is a device: judge whether it bridges into the content, not whether
it is literal.

## 2. Three kinds of statement, kept apart

- **Seen or heard** — a frame shows it, a cue says it, a measure counted it, a viewer observation
  noted it. Cite the id.
- **Claimed by the speaker** — prices, income, results, endorsements, safety, "this works".
  Attribute them: "she says the cream cleared it in a week". A money overlay is a graphic, a
  testimonial is a claim, an interface montage shows a feature exists, not that it works. Call
  something a demonstration only when the action and its result are visible in one sequence.
- **Your inference** — why something may work, who it may reach, what the viewer may feel. Label
  it, and say what would confirm or kill it.

**Evidence ids.** Every judgment cites what it stands on: a `frame_id`, `transcript.cue[i]`, a
`media.probed.…` measure, `content_metadata.caption`, a metric name, or a viewer observation id
(`viewer_observations.items[].id`, as listed in the evidence index). Viewer observations are timestamped notes from a whole-video viewing. Use what
they report seeing or hearing, at their time span; ignore any evaluative word in them
("engaging", "effective", "great"), which is a note, not a verdict. A note spanning the whole video
locates nothing. Typography, framing and exact on-screen wording need a frame; cut timing needs a
measure.

## 3. Mechanisms, not adjectives

"The opening is strong" says nothing. A mechanism names three things:

1. **The moment** — a time and what is on screen or said there.
2. **What it answers in the viewer** — a curiosity (what happens next, how did they do that), an
   emotion (recognition, amusement, tension, envy, relief), or a need (fix my problem, save me
   money, help me decide).
3. **The behaviour it may drive** — stop scrolling, keep watching, save or share, comment, buy or
   click. Keep these apart: what stops a scroll rarely earns a save. A comment-for-the-link ask can
   capture leads; it does not show satisfaction, organic sharing or extra distribution.

Never say a moment improved retention, completion or conversion: nothing here measures that.
"Gives a viewer who made the same mistake a reason to wait" is a mechanism; "boosts retention" is
a claim.

## 4. Trace the whole video

Before diagnosing any one part, walk the progression once:

- Does each section add something new (a step, a complication, proof, a turn), or restate the
  promise? Before calling it **repetitive**, name the repeated idea and locate both occurrences.
- Before calling something **missing**, check the whole video for it — frames, cues and viewer
  notes across the full length. A brief glimpse is not an understandable demonstration; say which
  you found.
- Does the payoff match the promise in kind and size? A "3 tricks" opening paid with one trick, or
  a "watch till the end" with no end reveal, is a broken promise.
- How many asks are there? Follow, save, comment, link and "part 2" in the same close split
  attention; count every requested action, including alternatives at the end.
- Unseen spans stay unconfirmed: sampled frames are not the whole video.

## 5. The seventeen dimensions in four stages

Use these keys verbatim as dimension names. They are where to look, not a walkthrough to write: the
diagnosis is the two or three that change the edit. A dimension with no evidence is unavailable,
never guessed. Each entry: what to look at, strong against weak, how it usually fails, the fix.

### Opening — does it stop the right viewer and make a promise?

Judge over `frames.sampling_plan.hook_window_s`: about three seconds on a short, fifteen to thirty
on long-form.

**`first_frame_promise`** — what the first frame alone tells a scrolling viewer.
- Look at: the first one or two frames, sound off: do they read as a situation, result or question?
- Strong: one readable subject with a visible tension or result. Weak: a context-free face.
- Fails: a logo, a greeting, a blank wall, a slow establishing shot.
- Fix: open on the strongest frame already in the cut (name its time), or show the result first.

**`visual_hook`** — movement and change in the opening seconds.
- Look at: whether something happens or is about to before the first second ends.
- Strong: an action in progress, a reveal starting, motion toward the lens. Weak: a static setup.
- Fails: the picture settles before anything happens; a pattern interrupt unrelated to the topic.
- Fix: start mid-action; cut the wind-up; let the first cut arrive when the first thought ends.

**`spoken_hook`** — the first words.
- Look at: the first cue in the hook window and when sound starts (`media.probed.loudness`).
- Strong: a specific problem, claim or question in the viewer's words. Weak: "so today I…".
- Fails: a greeting or context before the point; a question with an obvious answer.
- Fix: start from the sentence that states the point, often said later; quote its time.

**`text_overlay`** — what on-screen text says, in the opening and wherever it carries the point.
- Look at: whether text adds the stakes, number or "for who", and makes the promise sound-off.
- Strong: one specific line the speech then expands. Weak: text transcribing speech word for word.
- Fails: text and speech promise different things; a generic headline ("watch this").
- Fix: rewrite the text as the one-line promise, with the specific noun or number.

### Middle — does it keep paying the viewer to stay?

**`structure`** — the order of beats.
- Look at: the beat map (setup, complication, proof, turn, payoff, ask) with times.
- Strong: each beat changes what the viewer knows or wants; beats link by "but" and "so".
- Fails: context dumped before the point; a flat list; the best item first, nothing to wait for.
- Fix: move the strongest beat to where interest dips; merge or cut beats that restate.

**`pacing`** — the rate of new information, not the rate of cuts.
- Look at: shot lengths and cuts (`media.probed.shots`), silence and freeze spans, idea per span.
- Strong: time on an idea matches what it carries. Weak: one idea held long after it landed.
- Fails: dead air, false starts, a pause before every line; or cuts too fast to read the point.
- Fix: name the span to trim and what stays (an emphasis pause before a reveal stays).

**`proof`** — what makes the claim believable.
- Look at: the result, before/after, demonstration or source: visible and understandable?
- Strong: trigger and result in one continuous sequence. Weak: the speaker's word alone.
- Fails: proof flashes by too fast to read; a montage stands in for a demonstration.
- Fix: one continuous trigger-to-result shot; hold it long enough to read; attribute the rest.

**`delivery`** — how the person performs.
- Look at: energy and its variation, eye-line, whether face and voice change at the turn.
- Strong: intensity rises at the point that matters. Weak: one flat level throughout.
- Fails: reading off-screen; energy that drops right after the hook.
- Fix: re-record the turn with a pause before it; cut to a tighter shot where energy should rise.

### Close — does it pay off and ask for one thing?

**`payoff`** — the moment the promise is kept.
- Look at: where it lands against the promise-payoff result in the deterministic results (the
  anchored promise and candidate payoff cues; never compute a distance yourself), and whether it
  matches the promise in kind and size.
- Strong: shown, not only said, soon after the build. Weak: smaller than promised.
- Fails: it arrives after the ask, or is buried under the next topic.
- Fix: move it before the ask; show it; cut what sits between promise and payoff.

**`cta`** — the requested action.
- Look at: every ask, spoken, written and in the caption; whether it follows from the payoff.
- Strong: one action tied to what the viewer just got. Weak: an ask before any value.
- Fails: follow, save, comment and link at once; an ask that fits no viewer of this video.
- Fix: keep one ask, give its exact line, place it right after the payoff.

**`duration`** — whether the length fits the content.
- Look at: total length against beats that add something; tails after the payoff
  (`media.probed.freeze`, `media.probed.silence`).
- Strong: ends when the payoff lands. Weak: a recap of what was just shown.
- Fails: a trailing still, logo or silence; a second ending.
- Fix: cut to the end of the payoff; name the span.

### Craft — can the viewer see, read and hear it?

**`framing`** — where the camera is and whether the subject is in the shot.
- Look at: shot size, headroom, placement on a vertical screen, `media.probed.framing` (fill, bars).
- Strong: the thing being talked about is in frame and large. Weak: a small subject in a wide room.
- Fails: the object discussed never shown; letterboxed horizontal footage in a vertical feed.
- Fix: a tighter shot or an insert of the noun; reframe to fill the screen.

**`text_placement`** — where text sits and whether it can be read.
- Look at: size, contrast, time on screen, overlap with face, product or platform buttons.
- Strong: read in one glance, clear of the edges. Weak: thin text over a busy background.
- Fails: text under the caption/button areas; text gone before it can be read.
- Fix: move it up and in from the edges; add a box or stroke; hold it longer.

**`audio`** — what sound is doing.
- Look at: original voice or an existing track (`audio_attribution` is metadata, not hearing);
  sound in the first second; whether music energy broadly rises at the payoff.
- Strong: sound carries part of the hook or the turn. Weak: a track that would fit any video.
- Fails: silence or a slow ramp at frame zero; energy peaking away from the payoff.
- Fix: name the problem a change solves; never recommend swapping music for its own sake.

**`audio_mix`** — whether the levels serve the point.
- Look at: `media.probed.loudness` and `media.probed.silence`, viewer sound notes.
- Strong: speech clearly on top. Weak: music competing with words.
- Fails: a silent lead-in; a loudness cliff where a track ends early; a trailing silence.
- Fix: duck the music under speech; trim the lead-in; extend or fade the track to the end.

**`delivery_quality`** — the file itself.
- Look at: bars, low screen fill, dark or uneven shots (`media.probed.brightness`), loudness range.
- Strong: fills the screen, even exposure, steady level. Weak: one shot much darker than the rest.
- Fails: a frozen ending; very low or clipped loudness.
- Fix: the exact correction: re-export without bars, lift the dark shot, trim the freeze.

### Numbers — `performance`

Statements about the metrics, not the content. Public counts describe what was observed, never
why:

- Views are plays, not unique reach, and not retention. Likes divided by views is not an engagement
  rate. A public heatmap is relative attention within that one video.
- Null means unavailable, not zero. Give each count its platform and snapshot date; a
  cross-platform view total is not one platform's views.
- No outlier or "above average" claim without the creator's own comparable baseline. No account
  average, ranking weight or cause of high views is known here.
- A comment-to-receive ask inflates comments with requests; do not read them as praise, and do not
  compare comment and view counts whose scopes differ.
- Why it may have performed is a hypothesis; say what would test it.

## 6. Sound: what may be said

From heard or measured sound only. Broad, stable observations are fine: music or not, its general
character and energy, speech present and whether music drowns it, sound effects used. Never:

- **Name a song, artist or remix** from listening. A title comes only from metadata, on-screen text
  or speech, and is cited as that.
- **Quote or paraphrase lyrics** anywhere. Sung words are not the video's message; when the
  transcript may be lyrics (an existing track, nobody speaking on screen), build on frames, text
  and caption instead.
- **Say cuts land on or off the beat** unless a beat measurement exists for this video. Cut times
  alone are not beat times. Suggesting a cut on an audible hit is a fix, not a measurement.

These three were the claims that changed between repeated readings of the same video.

Words and music are separate evidence. A transcript, captions or machine-heard, is heard words:
use it for what is said or sung, under the rules above. The music and the mix (character, energy,
levels, a silent lead-in) need a measure (`media.probed.loudness`, `media.probed.silence`) or a
whole-video note about sound; a transcript says nothing about them. With neither, say the music and
mix were not analysed, and still use the words.

## 7. What comes first in the answer

- **Lead with the strongest insight.** Connect the viewer's desire, the creative device and the
  payoff into a plausible reason someone would watch or act. Then name the main opportunity. Do
  not lead with a fact-check, a plot retelling or a feature list.
- **A strength says what to keep and why.** The moment, the mechanism, and what an edit must not
  break. Write strengths plainly; put a needed caveat once, where it matters, not after each one.
- **A fix says where, why, and exactly how.** Where: time and what is on screen or said. Why: where
  the viewer gets stuck (confused, bored, unconvinced, unsure what to do). How: what to cut, move,
  show, or the line to say. Rank by impact.
- **Rank substance before cosmetics.** Promise and payoff, proof, repetition and the clarity of the
  ask come before captions, zooms and transitions, unless a cosmetic issue really is the
  bottleneck.
- **Never invent a problem to fill space.** Two real fixes beat three. Never recommend cutting the
  strongest existing hook; improve its bridge instead.
- **Someone else's video.** Their post is not yours to repair: say what transfers as a mechanism
  and what depends on their audience, and turn fixes into what to do in your own next video.
  Borrow the structure, never the wording.
- Times in prose as m:ss.

**Weak and useful, from other videos (reasoning only, never their facts):**

- Weak strength: "Creative opening that hooks viewers."
  Useful: "At 0:01 the burnt pan is on screen before she says what went wrong. Anyone who has
  burnt one has a reason to wait for the cause; keep the result-before-explanation order."
- Weak fix: "Improve the CTA to boost engagement."
  Useful: "The close asks for a follow, a save and a comment at once (0:41–0:47). If the aim is
  leads, end on one line, 'Comment PLAN and I'll send it', right after the plan is shown."
- Weak diagnosis: "The demo proves the app works."
  Useful: "The screen montage at 0:08–0:15 shows the feature exists, but the tap and its result
  never appear in one sequence. Replace the repeated benefit line at 0:16 with one tap-to-result
  shot; keep the earnings claim attributed to the speaker."

## 8. In a content read

The same first two steps, without the diagnosis: who it is for, what it promises, what it shows,
says and writes, and what it is about or asks for. Keep seen, heard and claimed apart, with a time
beside each point. Apply the sound rules (sung words are a track, not the message). No dimensions,
no strengths or fixes, no judgment of quality.
