# On Kabo Web: the `remake_video` tool

On Kabo Web every picture and sound comes from the host tool `remake_video`
(`remake_video {request:{action, ...}}`). Chat and GUI use this same workflow and the same tool; a
structured product request does not bypass input validation, model confirmation or the common
billing rules. There are no local scripts here: never ask the creator to run anything. Where a
reference names a command or a path of the local kit, the hosted runner does that part; take only
the writing rules.

## Inputs

Pass each input to `prepare` in exactly one form:

- **Reference**: `reference_url` with the YouTube, Instagram or TikTok video link exactly as the
  creator gave it (TikTok short links such as vm.tiktok.com work too), or
  `reference: {kind:"user_file", file_id}` for an uploaded file.
- **Creator footage**: `creator_profile: {platform:"instagram", handle}` with their Instagram
  handle or profile link, or `creator_videos: [{kind:"user_file", file_id}, ...]` (one to four
  uploaded files: videos of the creator, or photos of them plus a voice recording).
- For uploads, list the conversation's files and use their `file_id`s. Never pass a storage
  path or a file you have not seen listed.
- `creator_name` and `language` as `SKILL.md` step 1 says.

For a whole remake the host does the fetching itself: it checks the reference length first,
fetches the reference, picks the creator's reels and fetches them. Do not list reels, look videos
up or fetch them yourself for prepare (steps fetch links differently: `steps/project.md`,
"Links"). Tell the creator in one line that the videos are being fetched.

## Prepare and wait

```
remake_video {request:{action:"prepare", idempotency_key:<new UUID>, reference_url | reference, creator_profile | creator_videos, creator_name?, language?}}
```

Prepare is paid. Submit it once per remake; on a timeout or unknown result, call it again with the
same `idempotency_key` and the same inputs. Never create a second job for the same request. If
prepare returns `fetching_inputs`, the videos are still being fetched: say so, and on the next
turn call prepare again with the same `idempotency_key` and the same inputs; the host picks up the
same fetches. When the host refuses an input (a reference over ten minutes, a link it cannot
fetch, no usable reels, the same video in both roles), relay its reason, say nothing was charged
and the daily limit was not used, and ask for a different video instead of resubmitting.

Then call `remake_video {request:{action:"status", job_id}}`. The host waits briefly on each call.
When a call returns `preparing`, tell the creator the current stage in one line and check again.

**Keeping the creator informed.** When your reply ends while the job is still fetching, preparing
or running, tell them the job keeps going on its own and this conversation continues by itself
when the next step is ready, even if they close the page; when they come back to this
conversation, the result will be here. Never ask them to type "continue" or send any message to
move the remake along.

When the job reaches a step that needs you, the host starts a turn in this conversation by
itself, with an update from the host (not from the creator) naming the job and its new status.
The creator does not see that update. Call status for that job and carry on from where it
stands, without asking what they want, and reply to the creator directly without mentioning the
update itself.

## The script gate

At `waiting_script` the status result carries `brief` (file path to content) and `gate_message`;
the brief's files are `work/brief_input.json` and the drafts next to it
(`work/script.draft.json`, `work/opening_review.draft.json` when present,
`work/decisions.draft.json`, `work/route_b/jobs.template.json`). Write the four documents as
`../script-gate.md` says, as JSON text, then call start with the four files and no model:

```
remake_video {request:{action:"start", job_id, files:{script, opening_review, decisions, route_b_jobs}}}
```

Narration pictures are previewed with `action:"preview"` and the post-production look is answered
with `action:"review"`, not `start` (`formats/narration.md`).

Start is accepted once per job. A rejected start names the problem; fix that document and call
start again, as many times as it takes. Do not rewrite documents that were not named, and do not
tell the creator production has started until status shows it running. If a later status shows
`waiting_script` again with a `gate_message` listing failures (`cr check-script: ...`,
`cr check-opening: ...`, `cr decisions brief: ...`), nothing has been paid for: fix only what it
names, keep the rest of the documents as they were, and call start again with all four files.

## Choose the talking model

That first start does not produce anything. The host saves the four files and returns
`status: "choose_model"` with the estimated length of the finished video, the options with their
approximate cost compared with Vivix, and a ready-made message in `relay` (English) and
`relay_zh` (Chinese). For a narration remake it is one option, the narration production and its
estimated cost; a go-ahead or "1" is that option. Send that message and end your reply there:

- If the creator writes Chinese, send `relay_zh` word for word. Otherwise give `relay` in their
  language, keeping every option number, model name, multiplier and the length.
- Do not add a recommendation of your own, drop options, change the order or the multipliers, or
  say anything has started.

When the creator answers with an option, call start with only the job id and that option's
`talking_model` id from `options`; do not send the files again and do not rewrite the script (the
host submits the saved files):

```
remake_video {request:{action:"start", job_id, talking_model:"<id of the chosen option>"}}
```

A plain go-ahead ("OK", "yes", or the same in their language) uses the host's
`default_talking_model`: it keeps a model explicitly selected in the product form, otherwise
Vivix A1. A form selection alone never authorizes production: always relay the host's quote and
wait for this later confirmation. A question about the options is answered from `options`
(multiplier, and for Seedance 2.0 the longer queue and the occasional content-review refusal).
Calling start with `talking_model` in the turn you wrote the script is refused and shows the
choices again. If a later status still says the script is waiting for the creator's choice
(`pending_model_choice`), do not rewrite it: call start with the chosen `talking_model`, or with
only the job id to get the choices again.

## Production and delivery

While it is `running`, report the stage in one line and keep the creator informed as above. At
`delivered` the host saves the final MP4 and shows it as a file card; tell the creator as
`SKILL.md` step 5 says, with the spend the status reports, when present.

## Edits, projects and steps

`edit`, `project`, `add_inputs`, `atom`, `plan` and `deliver` are actions of the same tool
(`steps/*.md`, Web blocks). **The quote.** Before the first paid step of an edit or a project, tell
the creator the quote the host gives -- for a project the `quote_usd` in the `plan` receipt, for a
whole remake the quote in its status -- in the same two or three lines that say what you will make;
do not work out prices yourself, and never change the picture to spend less. Before `deliver`,
check the result against what you told the creator you would make (captions, music, voice, which
parts changed): add what is missing, and describe the video as delivered, not as planned.

**Refusals.** A step that hits a daily limit or the spending safety stop is refused before
anything is charged: say so. An expired workspace: offer to start again. When a failed step's
error carries `expected` (the step's whole shape), fix the call from it.
