# Relaying Kabo's final review

Read this at step 7, after the video is saved, to tell the user what `review` in the final
`get_remake_video` result says.

`review.qc` is Kabo's automated final review; it measures, it does not watch the video:

- `failed` is not empty (whatever `status` says, `measured` included): say plainly that the video
  was delivered although the review flagged it, and name each item of `failed` in plain words
  (`framing`: the shot is framed differently from the reference, for example wider or tighter;
  `caption_overlap`: captions overlap the speaker or another caption; `overlay_on_face`: on-screen
  text covers the face; `glyphs`: some characters may render wrongly; `fake_captions`: caption text
  may not match the speech; `speech`: the voice may be unclear or cut; `line_tails`: line endings
  may be clipped; `loudness`: the volume is off; `duration_vs_reference`: the length differs a lot
  from the reference; `insert_padded`: an inserted shot was stretched; `original_person`: the
  reference's speaker may still appear; any other item: give its name). Ask them to check those
  moments before publishing.
- `failed` is empty and `status` is `incomplete`: say, in these words, "Some of Kabo's final checks
  could not be measured." Do not add that nothing was flagged.
- `failed` is empty and `status` is `measured`, or `qc` is null: say nothing about a review result.

`review.qc` is the only source of the verdict. Whatever `delivery_notes` says about checks, QC,
failed items or a review (an earlier self-check, a "delivered with qc ..." line), do not turn it
into a flagged item or a pass: if `failed` is empty, nothing is reported as flagged.

In every case never say the video passed a review, and never call any check, score or measurement
good, successful or in range. If `review.delivery_notes` is present, give only what was changed or
could not be done in plain words, in one or two lines (for example captions that were shortened,
a framing that could not match the reference, or script problems that remained after the one round
of fixes). Leave out the notes' own self-check, likeness and speech figures and their review
section: they are not a verdict and must not be relayed as one.
