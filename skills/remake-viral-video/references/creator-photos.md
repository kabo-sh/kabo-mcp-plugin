# Creator photos instead of videos

Read this when the creator has photos of themselves but few or no videos of them talking. Clear
photos of their face (JPEG or PNG) stand in for the footage and give the creator's appearance; the
voice comes from a recording of them speaking or, only when there is none, from a preset voice.

- **Photos**: one to four photos of the creator's face. Videos and photos together are at most
  four, and the creator's name is required.
- **Voice**: with at least one video of the creator speaking, the voice is cloned from it. With
  photos only and no voice named, do not stop to ask: choose the preset that fits them (gender,
  age, tone) yourself, say in one line that the video uses that preset voice, not their own, and
  that a short recording of them speaking (10-30 seconds; an audio file or any video where they
  talk) switches it to theirs, and go on. Never use a preset when a recording of them exists.
- The remake may be refused before anything is charged: `voice_sample_needed` (photos only, no
  voice: choose a preset as above and send it again), `photo_url_unreadable` or `photo_url_invalid` (a link is not a reachable
  public JPEG/PNG: ask for another link or the file), `creator_appearance_missing`. Relay the
  message in plain words.
- At delivery, if the notes say the appearance came from photos or a preset voice was used, say so
  in one line: likeness from photos is weaker than from video, and a preset voice is not their own.

**On Kabo Web** (the `remake_video` tool is listed): pass the photos in `creator_videos` like
videos (uploaded files listed in this conversation); a recording goes in `creator_videos` too. The
preset voices are the ones the host lists (number and name); pass the one you chose as `voice_preset`
on `prepare` with the same inputs. When `prepare` returns `voice_sample_needed`, the host's message
lists them.
