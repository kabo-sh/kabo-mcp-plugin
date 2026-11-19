# Workflow: a narrated video built from steps

A voice carries the video over pictures and nobody talks to the camera: an explainer, a picture
book, a history or science story, kinetic type. Use this workflow when such a video is built from
steps -- made like a narrated reference the creator has nothing of their own for (no clip, photo or
recording; a preset voice), or the creator's script read over pictures in a reference's form, or a
narrated video from the creator's request alone. The whole narration remake (the creator's own
voice cloned from their material) is `../formats/narration.md` instead. Characters who speak their
own lines on screen are `character-drama.md`.

The stages run in this order. **Stop and wait for the creator only at the two points marked STOP**:
end your reply there and make nothing paid until they answer. Everything between the stops runs
without asking; the checks in each stage are yours (look at the results, re-make what fails), not
questions for the creator. A plain go-ahead ("ok", "go", "looks good") at a stop means continue.
How each step is called, the storyboard's fields and saving the plan are in `../steps/plan.md` and
`../steps/atoms.md`; this file says what comes when.

## 1. Break the reference down (free)

`frame` with `shots: true` on the reference (and a `frame` or two up close), `transcribe` of it.
Write two things, kept in the analysis you will save:

- **The style card** (step 0 of `../steps/motion-graphics.md`): `medium`, `look`, `cast`, `frame`,
  `edit`, `sound`, `captions`, `avoid`, and the style card from `../motion-catalog.md` whose
  `medium` matches.
- **Reference notes**: the opening (what it shows and says in the first 2-3 s to hold attention);
  the **pacing skeleton** -- the video cut into its 3-6 segments (hook, setup, turns, payoff, call
  to action ...), each with its job and its share of the length; how many shots and how long they
  hold; captions and on-screen text (kind, font, position, which words are stressed); voice,
  music and effects, and how loud the music sits under the voice.

**STOP 1 -- the style.** Tell the creator in a few short lines what you will make it look and
sound like: the medium and look, the captions, the voice and music, and the segments with their
share of the length. Ask whether that is the style they want. Nothing has been paid for.

## 2. The narration script

Write the script by segment, following the skeleton. When the creator gave the words, keep them
exactly and only split them into segments; otherwise write them yourself in the reference's
manner. In each segment mark the **key words** (stressed in captions), the **cut points** (where
the picture changes; about as many as the reference's shots) and the **effect points** (a whoosh,
a pop, a page turn).

## 3. The storyboard, saved

Write the storyboard from the script as `../steps/plan.md` says: one row per cut point, its
`words`, `picture`, `how`, `prompt`, `on_screen_text`, `captions` and `sound` (the effect points),
`form.captions` by its mode name, and `characters` / `environments` / `props` for anything that
recurs. Save the analysis (style card + reference notes) and the storyboard with `plan` (free).

**STOP 2 -- the script and the storyboard.** Show the script by segment (key words marked) and
the storyboard as a short table (shot, seconds, what is seen, how it is made), with the quote your
host gives. Changes here cost nothing: change the storyboard, save the whole of it again and show
it again, as often as the creator wants. Make nothing paid until they say go.

## 4. Voice, timed by the word

`tts {params:{shot: N}}` for the rows (a batch), in the voice agreed at STOP 1. The voice sets the
length: take each line's timing from the result's notes (word times: `transcribe` of the joined
voice) and move the rows' `t0` / `t1` to them; save the storyboard again when the times moved.

## 5. Pictures, checked by you

Character and place sheets first (`../steps/plan.md`, "cards first"), then `still
{params:{shot: [...]}}` in batches. Put the first still beside the reference's frame before the
rest. Check every still yourself: the medium and look match the style card, the people in it are
the row's `on_screen_cast` and no more, no garbled text. Re-make a failing still once; the rest is
a note.

## 6. Motion, text and captions

Per row as its `how` says: `animate {params:{shot: N}}` for a generated picture that moves,
`motion_graphics` for words, numbers, charts and interfaces (`../steps/motion-graphics.md`),
`text_cards` for text to read, `still_video` for a held picture. Captions come from the script in
the mode of `form.captions`, the key words stressed.

## 7. Sound

`concat {params:{shots: "all"}}`, the voice under it (`mux`), `music` with `duck: true` so it steps
back under the voice, `sfx` at the effect points. Listen to the result's notes: the voice must be
clearly louder than the music.

## 8. Join, final check, deliver

`captions`, then look at frames of the whole cut against the style card and the storyboard: every
row made, in order, each line heard in full, captions in the reference's mode. Re-make only the
rows that fail, then deliver as your host file says.
