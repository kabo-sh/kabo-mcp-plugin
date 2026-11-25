# Music and sound effects in one step: `auto_audio`

`auto_audio` finishes a cut's sound in one paid call. Give it the finished cut as `base`, after
`captions` and `text_cards` and before `deliver`.

- It generates a music bed as long as the cut, with a real ending, slid onto the beat and lowered
  wherever someone speaks, and lays light sound effects on the cut's clip joins, text cards and
  shot changes (one sound family for the whole cut, never crowding). The mix is levelled to
  -14 LUFS.
- Optional params: `music` `generated` (default) or `none`; `mood` (`science`, `history`,
  `kids`, `narrative`, `horror`, `comedy`, `money`; default: read from the speech); `prompt` (the
  music in a few words: style, instruments); `sfx` `on` (default) or `off`; `aesthetic`
  (`cartoon`, `tech`, `cinematic`, `organic`, `dark`; default: from the mood). Exact shapes are in
  `params.md`.
- A base that already has music gets only the effects.
- When the mix fails its checks the cut comes back unchanged and the notes say so: tell the
  creator the video has no music, do not say it has.
- The receipt says whether music was added and how many effects; say the same, no more.

Prefer it to writing `music` and `sfx` steps by hand. Use those only to match a reference's own
track (a sung song, a named style) or its exact effect timing.
