# What each step takes

Plan first (`plan.md`). Choose a step by what the storyboard row needs -- a picture that moves is
made to move, a line that is spoken is spoken, words that must read are laid out -- never by which
step is quicker or cheaper.

**Exact parameter shapes** -- which fields each step takes, their types, lists or objects, and
ranges -- are in `params.md` in this folder, generated from the host's own schema. Write every
request and the storyboard by it; where a sentence here reads differently, `params.md` is right.

## Files are handles

Steps never take paths or links, only the handles the job lists in its status (`handles`):

- `creator/<name>` -- the creator's own videos and photos (or a persona's portraits);
- `input/<name>` -- reference videos and images given to a project, and a delivered remake's
  reference (`input/reference.mp4`);
- `aNN.mp4` / `.png` / `.wav` -- the output of an earlier step;
- `final.mp4` -- the current delivered cut; `final_rN.mp4` -- each earlier version (r0 is the cut
  as first delivered);
- on a delivered remake also `master.mp4` (the current cut without captions), `take_sNN.mp4`
  (each talking take), `frame_sNN.png` (each take's first frame), `broll_bNN.mp4` / `.png` (each
  B-roll) and `line_NN.wav` (each voice line).

Read the job's status to see them before planning; use only handles it lists. For a delivered
remake the status also lists the script's `lines` (`row`, `text`, `t0`, `t1`): the `row` is what a
line edit takes. Look at these before asking the creator for material.

## Sending steps

- **One step at a time, but one step can be a batch.** An account runs one video step at a time.
  Send one step, read its result (read the status until it is done), then send the next; never
  send several steps together -- the extra ones are refused (`in_flight`), which is not a limit.
  Pictures for the same video go in one batch step instead: one `still` with `prompts` (2-8) or
  one `animate` with `images` (2-8) makes them all at the same time, each into its own new handle
  (`last_step.handles`, in order), which is much faster than one step per picture. If some items
  fail, the made ones are kept and the notes say which failed -- send only those again.
  Other single steps that do not depend on each other go together as `op: "batch"` with
  `params.steps` (2-8 `{op, inputs, params}`; `inputs` of the batch itself empty): the per-shot
  `trim` / `retime` / `mux`, one `talking` per line, one `tts` per voice, the `motion_graphics`
  shots. Each step is checked as a single call would be and they run one after another in one
  call, far faster than one call each. A step cannot use another step's output from the same
  batch -- chain those in the next call. `refvideo`, `motion`, `replace`, `persona`,
  `face_check` and `transcribe` stay single calls; `still` / `animate` batch with their own
  `prompts` / `images`.
- **Keep it moving.** On Kabo Web only a running step brings the conversation back by itself:
  never end a reply while nothing is running and the video is not delivered -- send the next step
  (a refused one fixed), or tell the creator what is left and ask.
- **A refused or failed editing step is fixed and sent again at once, without asking.** When a
  step that draws nothing new (`motion_graphics`, `text_cards`, `still_video`, `concat`, `mux`,
  `captions`, `trim`, ...) is refused or does not render, its error says what is wrong, the legal
  values and an example (`expected` gives the step's whole shape): fix the call and send it again
  in the same reply, and tell the creator in a line what you changed. Ask first only when the fix
  changes what was agreed with the creator (another look, other content, dropping a shot). A
  result's `notes` starting `fixed:` say what the runner corrected by itself; read them and keep
  going.
- **The reference is the model, not the footage.** Make the new video's pictures yourself
  (`still`, `animate`, `refvideo`, `motion_graphics`). Do not deliver the reference's own footage
  re-voiced, re-timed or re-captioned as the new video; if the step that would make the pictures
  fails, try another way to make them or tell the creator, never fall back to the reference.
  Never copy its account name, handle, logo, watermark or platform badge into a picture, a
  prompt, on-screen text or the captions; when a reference frame shows them, describe the
  picture without them.
- **Read each result's notes.** When they say a box you gave covers on-screen text or a face,
  redo the step without `box` so it is placed automatically, or tell the creator; never ignore it.

## The steps

| Need | op | Notes |
|---|---|---|
| A new shot of the creator (or anything in photos) doing something without speaking; a scene with props | `refvideo` | 1-10 reference images, optional `ref_video` for a motion or camera to follow, optional `first_frame` / `last_frame`; `prompt` says what happens. Silent unless `sound`. Up to 15 s; up to 30 s with `model` `kling/v4/reference-to-video`. To put product photos in motion with their exact pixels and text, a code animation (`motion_graphics` with `refs`) usually keeps them better. |
| A new still of the creator: another pose, framing, outfit or setting | `first_frame` | `image` (a `frame`, a photo or `frame_sNN.png`) + optional `refs` (0-3) and `prompt`. Draws the face; needs the creator's material. |
| The creator doing the moves of a video (a dance, a workout, a trend) | `motion` | a picture of the creator + the movement video. A `frame` of their own footage will do; a standing, full-body one keeps the moves best. Look at the movement video first: a talking clip is not a dance reference. Likeness is modest. |
| The reference's own shot with the creator in place of its speaker, camera, moves and props kept | `replace`, then `lipsync` for new words | when the creator wants the original's own shot and moves; a whole remake instead recreates the scene with them. |
| The creator's own footage saying other words | `lipsync` | real footage, new mouth. With the default sync model, `sync_mode` says what happens when the audio and video lengths differ: `cut_off` (default; the shorter decides), `loop` / `bounce` (the video repeats under longer audio), `silence` (shorter audio is padded with silence, so the video keeps its length), `remap` (the video is re-timed to the audio). |
| A still of the creator, or of a generated character, speaking a line | `talking` | from a photo or a `frame` of the creator, or a `still` of a character (on a character picture: `speaker` names who talks; the host finds them and keeps the others still); optional `prompt` for the performance (say who speaks); prefer `lipsync` on real footage when there is one. A generated character talks with Kling Avatar Pro unless another model is named. |
| The creator's voice reading lines | `tts` | `lines`; `voice:"creator"` (default, cloned from their material) or a preset voice (the one the creator named, otherwise one you choose by the role: `project.md`, "No voice to clone"); `speed` 0.5-2 sets the speaking rate (default 1). A preset voice always reads in the language of the lines: the preset numbers are kinds of voice (gender and tone), and a preset of another language is swapped for that kind in the lines' language (the step's notes say which). Write the lines in the language the video is spoken in. `language` (zh, en, ja, ko, es, fr, de, pt, it, ru, ar, hi, id, th, vi, tr) and `gender` (male / female) pick a preset without an id. Returns one audio for all lines plus one per line; its `notes` give each line's timing, so run it before the pictures when they have to follow the voice. |
| A picture without the creator (B-roll, a product shot, a scene) | `still` | never the creator: for a shot with the creator use `refvideo`. `prompt`, or `prompts` (2-8) for several pictures made at once; optional `aspect` (`9:16` default, `3:4`, `4:5`, `1:1`, `4:3`, `16:9`) for the picture's shape. Without `refs` it borrows the look (palette, light, grain) of a few frames of the project's videos, their text painted out, never their content. |
| The reference's picture sits inside black bars (a square or wide picture in a vertical frame) | `still` + `still_video` or `layout` | `frame` `shots:true` says so in its notes, with the nearest `aspect`. Make each picture with `still` `aspect` set to it (never a full-frame picture with bars drawn in), then put it on the black 1080x1920 frame: `still_video` `fit:"contain"` (zoom 1 keeps the bars still), or `layout` with the picture in a `box` across the frame's width at the reference's height (`fit:"contain"`), captions and titles in the bars like the reference. |
| Put a picture into motion | `animate` | 5 or 10 seconds, silent. `image` + `prompt`, or `images` (2-8) with `prompts` (one per image, same order) or one shared `prompt`, made at once. |
| The creator's footage somewhere else | `bg` | the person is cut out and laid over a plate; likeness unchanged. |
| A picture or screen over a time range | `overlay` | `t0`, `t1`, optional `box`. |
| Replace a time range with another clip | `splice` | `audio:"base"` keeps the base's sound and length; `"clip"` takes the clip's sound. |
| Join clips, or join sounds into one track | `concat` | 2-20 videos, or 2-20 sounds (all of one kind); a dialogue's lines in order become one track. |
| A transition between joined clips | `concat` with `transition` | `transition`: `cut` (default), `dissolve`, `fade_black` or `slide`; `transition_s` 0.2-1.5 (default 0.5). Picture and sound cross together; each seam shortens the total by `transition_s`, and every clip must be longer than it. Use the reference's own seams: dissolve where it dissolves, fade through black where it fades, cut where it cuts. |
| Paragraphs, lists or quotes on screen | `text_cards` | up to 10 cards of up to 600 characters, each with `t0` / `t1`; placed in the lower half below the face, the font shrinks to fit; `style:"creator"` or `"plain"`. Words that must be read go here, never into a generated picture. |
| Code animation: diagrams, charts, maps, UI walkthroughs, text in motion, photos in motion, callouts over a video | `motion_graphics` | `inputs`: optional `base` (a video; the animation is laid over it at its own size and aspect, sound kept) and optional `refs` (0-4 images, available to the markup as `ref_1.<ext>` ... in the order given, and by their own names). `params`: `duration` (0.5-120 s) and `spec`, one of: (A) your own HyperFrames composition `{"markup", "style" (CSS), "script" (GSAP on the paused timeline `tl`), "palette"?}`; (B) a built-in component `{"component", "fields", "style"?}`; (C) an exemplar page `{"exemplar", "fields", "style"?}`. `style` in B and `palette` in A take a motion style id or a colour object `{bg, fg, accent, secondary?, muted?, font_display?, font_body?}`; leave them out for a neutral look. How to plan and call it: `motion-graphics.md`. |
| Camera shake, flash transition or impact zoom on a video | `shake`, `flash`, `impact_zoom` | `inputs.video`; `params`: optional `t0`, `t1` (or `at` + `duration`), `intensity` (or `zoom` 1.05-1.8 for `impact_zoom`). Beat effects on the picture, audio preserved. |
| Captions on a composed video | `captions` | words come from the video's own sound; `max_words` per caption, `upper` for capitals. Names on the project's cards, voice lines and storyboard are spelled as written there (Kabo passes them to the captions). Sung lines get captions too. When the creator asks for captions, the cut gets them -- never leave them out to keep the reference's on-screen text or to avoid clutter; place them clear of that text (`position`). Text cards stay short: one idea per card and one card per language -- three languages stacked in one block cover the picture. |
| Captions styled like the reference's | `captions` with `font` / `position` / `mode` / `stroke` | `font`: `sans` (default), `serif_caps` (classical serif capitals), `impact` (tall heavy condensed), `condensed`, `rounded` (soft, playful), `cjk_sans` (Chinese / Japanese / Korean); `position`: `bottom`, `center`, `top` or a height 0-1; `mode`: `phrase` (default), `word` (one word at a time, large, centred), `highlight` (the phrase stays up and the spoken word is lit in `color`, yellow by default), or `reveal` (the phrase builds up word by word as it is said; the words stay until the phrase ends) -- when the reference's captions grow a word at a time, Kabo uses `reveal` for a `phrase` request and says so; `stroke`: outline 0-20 px. Choose them from the reference's captions: the closest font family, the height they sit at, how big they are (`size`, 1 = default; put a frame of the captioned cut beside the reference's frame and match the letter height -- captions bigger than the reference's cover the picture), word by word or a phrase at a time. Without `position` in `phrase` mode the captions keep the automatic placement off faces and hands. |
| One frame as an image | `frame` | any video handle; `t` in seconds or `at` `first` / `last` (one of the two); a first frame or a plate for the next step. `shots: true` gives the contact sheet of all shots (`plan.md`); `grid: true` a frame with a coordinate grid. |
| Pictures held as a clip | `still_video` | `images` (1-8) shown for `duration` in total, optional `zoom` 1-1.5 (a slow push-in) and `fit` `cover` / `contain`; silent 1080x1920. Only for a shot over a held picture in the reference; a shot that moves is made to move. |
| A sound's level, fades, tempo or length | `audio_edit` | `media`; `gain_db` or `normalize` (not both), `fade_in`, `fade_out`, `speed` (pitch kept), `duration` (cut or pad). |
| How much a picture looks like the creator | `face_check` | |
| Background music | `music` | `mood`: calm, upbeat or warm (`none` leaves the sound as it is), `gain_db` -30..0 (default -18). An instrumental the package makes itself; never a song. |
| Music described in words, or a sung song | `music` with `prompt` | `prompt` instead of `mood`: the style and mood in words (a dark synth pulse, an epic orchestral build, a children's song with a sung chorus), made as long as the base; `instrumental: true` forbids singing. Use it when the reference has music the three moods do not match. |
| Music that steps back under speech | `music` with `duck: true` | lowers the music wherever the base speaks and lets it back up in the pauses; works with `mood` or `prompt`. Use it whenever speech plays under music. |
| Sound effects on actions and cuts | `sfx` | `base` video; `events`: 1-40 `{t, prompt, duration?, gain_db?}` -- `t` in seconds, `prompt` the sound in a few words (a whoosh, a door slam, a crowd cheer), `duration` 0.5-22 s (default 2), `gain_db` -30..6 (default -6). Each sound is made from its words and laid at its time on the base's own sound; the picture is untouched. When the reference has dense effects, put one event on each action or cut, timed from `transcribe` word times or the cut times of `frame` `shots:true`. |
| A colour look: brighter, darker, warmer, cooler, desaturated, black and white, grainy, or like a reference | `grade` | `video`, optional `match` (an image, e.g. a `frame` of the reference, whose colour the video is moved towards first); `brightness` -0.5..0.5, `contrast` 0.5-2, `saturation` 0-3, `temperature` -1 (cool)..1 (warm), `grain` 0-1, `vignette` 0-1, `bw`. Use it when the reference's look is clearly graded; grade the joined cut before `captions`. |
| Cut out a stretch of a video or audio | `trim` | `t0`, `t1`. |
| Put a sound under a video | `mux` | `mode:"replace"` swaps the sound, `"mix"` adds it at `gain_db`. |
| A video's sound on its own | `extract_audio` | |
| What a video or sound says, in timed segments | `transcribe` | `media`, optional `language`; the text is in `last_step.transcript`, no file. |
| The same speech in another voice | `voice_change` | a preset voice (`warm_female`); the creator's own voice is not available here -- use `tts`. |
| Change a video's speed, loop it, play it forward and back, or hold its last frame, to a new length | `retime` | `mode`: `speed` (`speed` x0.25-x4, or `duration` = the new length; sound stretched, pitch kept), `loop`, `bounce` (range up to 10 s) or `hold` (these three take `duration`). `t0` / `t1` limit it to one range; the rest of the video is kept. `audio:"none"` drops the sound; added time in `bounce` / `hold` is silent. A shot that keeps moving one way (a vehicle passing, a dolly) visibly reverses in `bounce` and jumps back at every `loop` seam, so `bounce` / `loop` of such a shot is played as slow motion instead when that is no slower than x0.4 (the receipt says so); for a longer stretch, use another shot or `hold`. |
| A region of a video or image, enlarged | `crop` | `box` `[x, y, w, h]` as fractions of the frame; `size` `[w, h]` in pixels (default the source's size). The region is widened around its centre to the output's shape, never stretched or padded; the result notes an enlargement over x3 (soft). |
| Burned-in text painted out of a video or image | `inpaint_text` | `boxes` `[[x, y, w, h], ...]` where the text is (leave out to have it found automatically); `fill:"strokes"` (default) paints only the letters and their outline, `"box"` the whole box; `t0` / `t1` limit it to a range. A replacement "with the same animation" copies the original's timing, position, size and motion (a `motion_graphics` overlay timed to when the original showed), not a static caption. For stray or garbled letters in a picture this project generated, re-make that `still` (a prompt that asks for no text) instead: painting text out of a cut with faces and characters can smear them. |
| Several videos or images on one canvas | `layout` | `inputs.layers` (1-8 handles, last on top) and optional `inputs.base`; `params.layers` has one entry per layer, in order: `box` `[x, y, w, h]` on the canvas, optional `src_box` (the part of the layer used), `fit` (`contain` default, `cover`, `stretch`), `t0` / `t1` (when it shows; a shorter video holds its last frame), `opacity` 0-1, `key` (`light` keeps only the layer's near-white pixels, `dark` its near-black ones, grown by `grow`, a fraction of the canvas height). `canvas` `{width, height, color:"#RRGGBB", duration}` when there is no base (default 1080x1920, black). Sound: the base's (`audio:"base"`) or none; add one with `mux`. |
| A fictional on-screen person (only when the creator has no material of their own and wants one) | `persona` | `description` of a person who does not exist (never a real, famous or named person), optional style `seed_images`; returns 2-4 portraits `creator/persona_NN.png` that the face steps then use (`project.md`). Say at delivery that the person is AI-generated and fictional. |

`model` is optional; leave it out to use the tested default. Only tested models are accepted.

## A reference nobody talks in

When nobody speaks in a reference (the whole remake refuses it), make it a project: the reference
as a reference video, `trim` / `concat` to reuse its pictures for the parts without a speaker,
`talking` (from a `tts` line and a frame of the creator) or `refvideo` for the creator's part,
`splice` (a full-screen segment) / `overlay` (the creator in a corner) to put it together, and
`captions` last. Keep the reference's on-screen text where it is; never put the reference's people
forward as the creator.
