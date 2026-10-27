# Optional thumbnail image operations

Existing-image `download`, `resize` and `preview` are one optional host image capability, independent of this skill. Image-only requests do not require `SelectedIdea` or this packaging skill.

## Using the capability

Use the host's image download/resize/preview capability only when the host offers one, and call it with structured arguments, not shell text. A capability named in this Skill is not proof that the host offers it. When the host offers none, state that image operations are unavailable here and continue with the text package; do not hand the operation elsewhere or substitute shell network calls. Do not use it unless the user requests an existing-image operation.

Example resize request:

```json
{"action":"resize","source_url":"https://i.ytimg.com/vi/aqz-KE-bpKQ/hqdefault.jpg","mode":"contain","zoom":1,"pan":{"x":0,"y":0}}
```

`download` needs `source_url`. `resize` additionally accepts mode `cover` or `contain`, zoom 1–3 and pixel pan. It exports a verified 1280×720 JPEG no larger than 2 MiB. Animated inputs cannot be resized; ask for the intended still frame.

`preview` needs `source_url`, `title` (1–110 characters) and `channel` (1–40). Optional `comparison_url` and `theme` (`light` or `dark`) produce a self-contained HTML comparison across Search, Home, Suggested and Mobile. It is illustrative, not an exact reproduction of every live YouTube layout or a CTR prediction.

Use public YouTube/Instagram/TikTok image URLs or artifact URLs previously returned for this user. Local paths are not URLs. Success contains `ok: true` and an `artifact` with URL, expiration, MIME type, bytes, SHA-256 and image dimensions when applicable. Resize → Preview must reuse the returned artifact URL, not a guessed storage path.

## Local files

When the host's image capability accepts local files, replace `source_url` with absolute `source_path`, and `comparison_url` with absolute `comparison_path`, and pass the request as structured arguments or a written request file, never as shell text. Never interpolate a user-supplied path, title or channel into shell source. Local images remain local; the decoder receives only image bytes and does not fetch URLs. Local success returns `artifact.path`, not a URL. Do not claim local processing is available without checking. If it is not, explain that local image processing is unavailable here; do not silently upload files or rebuild an image processor inside the skill.

## Failures and delivery

Only `source_not_found` means the source actually returned 404/410. `unsupported_source` means the origin is not supported; `source_expired` means access was denied or expired. `storage_unavailable` and `runtime_unavailable` are service failures, not missing images. Respect `retryable`; do not loop on permanent failures. No output artifact may be invented after `ok: false`.

The capability limits combined inputs to 50 MiB and 40 megapixels; preview inputs must total at most 8 MiB because the self-contained HTML embeds them in four scenes. Resize, preview and download do not generate artwork, establish rights, approve publication, or change `script-package.v1` / `brief_only`. Keep the verified package intact if an optional image operation fails. Report actual artifacts using their returned URLs or paths; a local path is not automatically an attachment.

For an optional thumbnail operation, report only artifacts returned by a successful image operation, separately from the validated `script_package.json`. Preserve every field the operation returned — URL or local path, dimensions, expiration, MIME type, bytes and SHA-256 — exactly as supplied, and never invent a missing one. A local path does not imply a clickable attachment. Keep one package `creator_report`; append a concise image-operation result without changing the package's `brief_only` approval semantics.
