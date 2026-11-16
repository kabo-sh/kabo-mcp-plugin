# Creator photos instead of videos

Read this when the creator has photos of themselves but few or no videos of them talking. Clear
photos of their face (JPEG or PNG) stand in for the footage and give the creator's appearance; the
voice comes from a recording of them speaking or, only when there is none, from a preset voice.

- **Photos**: one to four photos of the creator's face. Videos and photos together are at most
  four, and the creator's name is required.
- **Voice**: with at least one video of the creator speaking, the voice is cloned from it. With
  photos only, ask once, in one message, for a short recording of them speaking (10-30 seconds; an
  audio file or any video where they talk) or one of the preset voices by number and name. If they
  say they have no recording, let them pick a preset by number. Never pick a preset for them, never
  use one when a recording of them exists, and say that the video will use a preset voice, not
  their own.
- The remake may be refused before anything is charged: `voice_sample_needed` (photos only, no
  voice: ask as above), `photo_url_unreadable` or `photo_url_invalid` (a link is not a reachable
  public JPEG/PNG: ask for another link or the file), `creator_appearance_missing`. Relay the
  message in plain words.
- At delivery, if the notes say the appearance came from photos or a preset voice was used, say so
  in one line: likeness from photos is weaker than from video, and a preset voice is not their own.

**On Kabo Web** (the `remake_video` tool is listed): pass the photos in `creator_videos` like
videos (uploaded files listed in this conversation); a recording goes in `creator_videos` too. The
preset voices are the ones the host lists (number and name); pass the pick as `voice_preset` on
`prepare` with the same inputs. When `prepare` returns `voice_sample_needed`, the host's message
lists them.

**In the plugin** (this Skill's scripts): pass each photo with `--creator-photo '<link or
kabo-file:id>'` (a direct public image link that opens without signing in, or a local JPEG / PNG
sent with `local-files.md`); `--creator-name` is required. A recording goes in with
`--creator-video`. Pass the preset pick with `--voice-preset '<id>'`:

1. Female soft: `933563129e564b19a115bedd57b7406a`
2. Female bright: `b545c585f631496c914815291da4e893`
3. Male calm: `536d3a5e000945adb7038665781a4aca`
4. Male energetic: `802e3bc2b27e49c2995d23ef70e6ac89`
