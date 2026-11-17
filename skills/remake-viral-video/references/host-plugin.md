# In the plugin: plan the video, Kabo makes it

In the plugin you do not run the steps yourself. You understand the request, look at the
material, write the plan (an analysis and a storyboard), get the creator's go-ahead on the quote,
and hand the plan to Kabo's producer, which makes the video on Kabo's servers with the rest of
this Skill. You relay what the producer asks and deliver what it makes. Never draw, record or
assemble a picture yourself, and never promise a video the producer has not delivered.

Tools: `start_video_project`, `upload_file`, `check_video_plan`, `make_video`, `reply_to_video`,
`get_remake_video`, and the public video tools for looking at a reference
(`public_video_fetch_transcript`, `public_video_extract_keyframes`).

## 1. Start the project

Every video in the plugin -- a remake of a reference, an approved script, a video from steps --
lives in one project job. Collect what "Choose what to make" in `SKILL.md` needs (the reference,
the creator's footage or photos, product pictures), then call `start_video_project` with them: the
creator's own videos (an Instagram handle, or one to four video links), up to eight photos of the
creator, reference videos and reference images, and the creator's name. A video or photo the user
gives as a file on this machine is sent first with `local-files.md` and passed as its
`kabo-file:<id>` wherever a link goes. Video links are YouTube, Instagram or TikTok; picture links
are public JPEG or PNG. It returns the `job_id`; `fetching_inputs` means the files are still being
fetched: say so in one line and call again with the same arguments after `retry_after_s` seconds.
Use only material the user gave in this conversation; never reuse one video for two roles. A voice
the creator has not recorded is asked for as `steps/project.md` says ("No voice to clone"), before
the project starts.

## 2. Look before you plan

Plan from what the material shows, not from its words alone. For a public reference link, read
its transcript (`public_video_fetch_transcript`) and look at its frames
(`public_video_extract_keyframes`): the shots, who or what is in each, how big, how it moves, the
text on screen, the look. Look at the creator's own clips and photos the same way when the plan
uses them. What you cannot see, you do not describe: leave the analysis out rather than guess, and
say in the storyboard's `picture` only what the row must show.

## 3. Write the plan

Write the analysis (plain text) and the storyboard (one JSON object) exactly as
`steps/plan.md` says ("The plan: analysis and storyboard"): `form`, `total_s` and, for recurring
characters, `characters` (`{name, look}` each, no `sheet`) at the top, then one row per shot with
`shot`, `t0`, `t1`, `words`, `picture`, `sources`, `keep_change`, `motion`, `on_screen_text`, and
optionally `on_screen_cast`, `speaker`, `how`, `prompt`, `captions`, `sound`, `transition`.
Keep the reference's form (`steps/plan.md`, "Break the reference down first"): one picture per
shot, motion where it moves, the voices and talking shots it has. For an approved script, put
every word of it, unchanged and in order, into the rows' `words`. Leave `how` and `prompt` out
when you are not sure; the producer chooses the steps from the rest of the row.

Then call `check_video_plan` with `{job_id, storyboard}`. It is free; nothing is made or saved.
When `ok` is false, fix what `problem` names and check again until `ok` is true. It returns
`quote_usd` (the code's estimate for making this plan), `rows` and `total_seconds`.

## 4. The go-ahead, then make it

Tell the creator in two or three lines what will be made and in which order, and the quote
(`quote_usd`, rounded up; the final charge is usually a little lower). Never work out a price
yourself and never change the plan to spend less. End your reply there and wait. Read the answer
by its meaning, in any language: a go-ahead makes it; a change goes back to step 3; a question is
answered, then you wait again.

After the go-ahead, call `make_video` with `{job_id, request, analysis, storyboard, quote_usd,
idempotency_key}`: `request` is the creator's own words for what they want, verbatim (for an
approved script, the script itself, marked to be used word for word); `storyboard` exactly as
checked, with `analysis` (required with a storyboard); `quote_usd` the quote the creator agreed
to; a new `idempotency_key` (8-128 of `A-Za-z0-9._:-`), reused only to retry the same call after a
timeout. It is paid; call it once. It returns `{job_id, producer}`. When the creator asks for a
video and you could not look at the material, you may call `make_video` with `request` alone (and
the key): the producer plans it itself and asks for the go-ahead on its quote through
`needs_reply` (below).

## 5. While it is made

Call `get_remake_video` with `{"job_id": "<id>", "project": true, "producer": true, "wait_s": 30}`
(at least half a minute apart; never in a tight loop) and report a stage change in one line. Its
`producer.state` says who has the turn:

- `not_started`: `make_video` has not been called yet.
- `working`: the producer is making it; keep waiting.
- `needs_reply`: the producer asks the creator something (a model to choose, a go-ahead on a
  quote, a voice, a missing file). Give the creator `producer.message` in their language, keeping
  every option, number and name, with no recommendation of your own, and wait for their answer.
  Then call `reply_to_video` with `{job_id, message, idempotency_key}`: their answer in their own
  words, verbatim, with a new key. Never answer for them, and never write your own instructions to
  the producer: when you notice something wrong in what it reports, tell the creator what you
  saw and send what they answer. Reply only after the latest `get_remake_video` shows
  `needs_reply`, `done` or `failed`; while it is `working` a reply is refused (`conflict`) --
  wait and read the job again.
- `done`: the video is delivered and the producer has said what it made: deliver (step 6).
- `failed`: the last round broke off or the job failed. Tell the creator plainly what
  `producer.message` says; if they want to go on, send their words with `reply_to_video` and the
  producer carries on.

A remake takes 30 min to 3 hours, mostly waiting. Do not promise a finish time.

One video is made at a time per account: start another `make_video` only after the one in progress
is `done` (or the creator cancels it). When the producer says it is waiting for another video, tell
the creator so; once that video is `done`, send `reply_to_video` with the creator's go-on (for
example "The other video is finished now, please continue.") -- it does not resume by itself.

## 6. Delivery and changes

When the job lists a delivered video (the newest of `project.revisions`, its `video.download`;
links expire, so read the job again to re-sign), give the creator its download link, what was made in two or
three lines, the spend the job reports, and what the producer's message says about any part that
looks less like the creator, a preset voice or an AI-generated presenter. Do not claim views,
retention or likeness that nobody measured, and suggest they watch it in full before publishing.

A change to a delivered video (other words in a line, captions, a picture over a moment, another
clip) goes to the same job with `reply_to_video`, the creator's request in their own words; never
a new project. Cancel a job (`get_remake_video` with `"cancel": true`) only when the creator asks;
spend so far stays charged. Stopping takes a minute or two: keep calling `get_remake_video` until it no longer says
working; if you stop sooner, say the cancel was requested and is still stopping.

## 7. When it does not finish

A job that ends `failed`, `out_of_scope` or `timed_out` comes with a reason: tell the creator the
reason in plain words and the spend the job reports, and never start a replacement on your own. A
tool error carries `code`, `message` and `retryable`: relay `message` in plain words. A
`quota_exceeded` that says another video is still being made is not a limit: wait for it and call
again. Any other `quota_exceeded` is a daily limit or the spending safety stop: nothing was
started; say so. A status call that fails: try once more; if it still fails, say the job is
preserved and can be checked later with its job id.
