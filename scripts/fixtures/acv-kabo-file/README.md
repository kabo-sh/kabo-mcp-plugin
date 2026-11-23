# Uploaded-file media envelopes (`kabo-file:<id>`)

`envelopes.json` holds one terminal `public-video-media` envelope per operation for a video the creator
attached in Kabo, as `/mcp-pub` returns them inside a `collect_video_media` composite. The shapes follow
the backend tests that pin them (the uploaded-file branch of the public-video-media adapter):

- `collect_public_metadata`: the same `data.video` keys as a link, platform fields null, plus `width`,
  `height`, `fps`, `has_audio`; `data.origin: "uploaded_file"`; a `source_scope_limited` limitation
  (envelopes carry limitation messages as strings).
- `fetch_transcript`: speech-recognition cues (`start_ms`, `end_ms: null`, `text`) with
  `origin: "speech_recognition"`. No audio or no speech is `completed_partial` with no cues; no speech
  recognition configured is `unsupported` (the test derives both).
- `extract_keyframes`: the link's frame fields and `duration_scaled_v1` plan, plus `data.frame_preview`
  (frames scaled to 1280 px, at most 200 KiB each).
- `measure_media_signals`: the link's shape.

Synthetic values; no real file or account.
