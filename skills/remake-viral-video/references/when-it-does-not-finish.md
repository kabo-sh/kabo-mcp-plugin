# When a remake does not finish

Every final status (`out_of_scope`, `failed`, `timed_out`) comes with the runner's reason when it
gave one. Take it from where your host puts it (below); if there is none, say that no reason was
given and do not invent one. Always tell the creator the reason in plain words, not only that the
remake was refused or stopped (for example: the reference is filmed with a camera that keeps
moving, like a walking or travel vlog, rather than one person talking to the camera). Do not quote
stage names or internal terms. Always say whether it was charged and whether it counts toward the
daily limit, and never drop either half: a reason without "nothing was charged and it does not
count toward the daily limit" (or, for a paid failure, "it counts toward today's limit") is
incomplete.

- `out_of_scope`: relay the reason. For a reference that is not a talking-head video, suggest one
  of ten minutes or less where one person speaks to the camera for most of it (cutting to screen
  recordings or to a product they show is fine), or a narrated one where a voice talks over the
  pictures. When no clear frontal face of the creator was found in their videos, or too little of
  them speaking, give both ways on in the same reply: an uploaded clip, or a link to a reel, where
  they talk facing the camera; or, when the request does not need them on camera (an approved
  script, a tutorial, a before/after, a product or scenery video), the same words as a narrated
  video built from steps -- their clips as the pictures, the voice from a recording of theirs or a
  preset voice they pick (`steps/project.md`, "No voice to clone"). Never only ask for a face.
  When the reason is that nobody talks to the camera in the reference (a product demo, scenes,
  footage without a speaker), offer to build it from steps instead (`steps/atoms.md`, "A reference
  nobody talks in"); start it only after the creator agrees to the plan. In every `out_of_scope`
  case nothing was charged and the daily limit is not used; say so.
- `failed` with a likeness reason: the generated person did not look like the creator, so the
  video was stopped or not delivered. Say so plainly and ask for clearer footage of the creator
  facing the camera; do not resubmit the same inputs.
- `failed` or `timed_out`: say the remake did not finish, why (the returned reason), and that no
  video was produced. These jobs ran paid steps and count toward the daily limit; do not say
  otherwise. Do not resubmit on your own; offer to start a new remake if the creator wants one.
- Refused because of the limit: when the daily limit is reached, say no new remake was started,
  nothing was charged and they can start another tomorrow. When another remake is still running,
  say one remake runs at a time and look at that job if this conversation has its `job_id`.
- Any other failure: relay its reason and the reported spend; do not guess whether it was charged.
- A status call that fails: try once more; if it still fails, say the job is preserved and can be
  checked later with its job id. Never start a replacement job for an unknown outcome.

**On Kabo Web** (the `remake_video` tool is listed): the status carries `reason` alongside
`failed_at`, and every final status also returns `relay`: one ready-made message that puts the
reason together with whether the remake was charged and counts toward the daily limit. Tell the
creator everything in `relay`, in their language and in plain words. Describe where it stopped by
the returned `failed_at` text, not the raw stage name.
