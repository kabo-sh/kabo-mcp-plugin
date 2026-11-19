# Workflow: a character drama built from steps

Drawn or generated characters act and speak their own lines: a cartoon sketch, a family drama, a
dialogue between characters. Use this workflow when such a video is built from steps -- made like
a reference with characters who talk (the whole remake refuses dialogues), or from the creator's
script or request. A voice over pictures with nobody speaking on screen is `narration.md`.

The stages run in this order. **Stop and wait for the creator only at the three points marked
STOP**: end your reply there and make nothing paid beyond what the stage says until they answer.
Everything between the stops runs without asking; the checks in each stage are yours, not
questions for the creator. A plain go-ahead ("ok", "go", "looks good") at a stop means continue.
How each step is called, the storyboard's fields and saving the plan are in `../steps/plan.md`
("Characters that talk", "cards first") and `../steps/atoms.md`; this file says what comes when.

## 1. Break the reference down (free)

As stage 1 of `narration.md`: the contact sheet, frames up close and `transcribe`; the style card
and the reference notes with the pacing skeleton. Add for a drama: how many characters there are,
who speaks how often, the rhythm of the dialogue (quick exchanges or long lines, pauses), and
whether captions change colour by speaker.

**STOP 1 -- the style.** As in `narration.md`: the medium and look, the captions, the sound, the
segments. Nothing has been paid for.

## 2. The characters, with their voices

Write the storyboard's first version and save it with `plan` (free): `characters` with each one's
`name`, `look` and `voice` -- `{language, gender, age}` (a preset kind of voice in the video's
language), or `{id: "creator"}` only for the creator's own cloned voice -- and the rows of the
script, each line with its `speaker`. The creator's words stay exactly as they gave them; you only
assign each line to a speaker.

Then make each character's sheet (`still` with `params.sheet_for`, a batch; the host saves each as
the character's sheet) and one short line in each character's voice (`tts` with
`params.speaker`), so the creator can see and hear them. These are the only paid steps before
STOP 2.

**STOP 2 -- how the characters look and sound.** Show each character's sheet and play their line,
with one line each on who they are. Every shot depends on this, so change a look or a voice here
(a new sheet, another voice, saved into `characters`) until the creator is happy.

## 3. The script and the storyboard

Finish the storyboard as `../steps/plan.md` says: every line with its `speaker`, the effect
points in `sound`, one row per shot with `on_screen_cast`, `speaker`, `location`, `camera` (a
talking row at least `medium close-up`) and `how` (a talking row names `talking`). Save it again.

**STOP 3 -- the script and the storyboard.** Show the script with its speakers and the storyboard
as a short table (shot, seconds, who is seen, who speaks, how it is made), with the quote your host
gives. Changes cost nothing: save the whole storyboard again and show it again, as often as the
creator wants. Make nothing paid until they say go.

## 4. Voices, timed by the word

`tts {params:{shot: N}}` for every spoken row (a batch): each line in its speaker's card voice.
Take the timings from the notes and move the rows' `t0` / `t1`; save the storyboard again when
they moved.

## 5. Pictures, checked by you

Place sheets if any, then `still {params:{shot: [...]}}` in batches (the host adds the sheets of
the characters in each row). Check every still yourself: the right characters and no extra
people, each looks like their sheet, the medium and look of the style card. Re-make a failing
still once.

## 6. Talking and moving shots

`talking {params:{shot: N}}` for every row whose words are said on screen (the speaker must be in
the picture; a refusal says what to make first), `animate {params:{shot: N}}` for the rows without
a line on screen.

## 7. Sound and captions

`concat {params:{shots: "all"}}`, `music` with `duck: true`, `sfx` at the effect points; captions
in the reference's mode, coloured by speaker when the reference does it.

## 8. Final check, deliver

Look at frames of the whole cut: in every talking shot the right character speaks and the others
keep still, nobody's look drifts from their sheet, nobody extra appears, every line is heard in
full. Re-make only the rows that fail, then deliver as your host file says.
