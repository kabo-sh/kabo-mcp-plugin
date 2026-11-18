Answer in the chat, in a few short paragraphs, from the evidence in section 3 alone: what the video
shows, what is said or written in it, and what it is about or asking for. Put the timestamp beside
each point and say whether it was seen in a frame, read from on-screen text or the caption, heard,
or reported by a whole-video note.

Before repeating heard words as what the video says, decide whose words they are. When
`audio_attribution` names an existing track (`uses_original_audio` false, or a song or artist
name), or the frames show no one speaking, words with `transcript.origin` `speech_recognition` may
be that track's lyrics: say the sound is that track, never summarize its words as the video's
message, and build the answer on the frames, on-screen text and caption. When it stays unclear, say
the words may be sung and keep them apart from what the video itself claims.

This mode writes no file and runs no further step; it is not a diagnosis, so never call it one.
Offer a diagnosis or craft teardown once at the end when the creator may want one.
