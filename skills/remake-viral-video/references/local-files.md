# Local files

A video or photo the user gave as a file on this machine is sent to Kabo once and then used by its
`kabo-file:<id>` reference wherever a link goes. Send each file separately, before the call that
uses it. Only send files the user gave in this conversation, for the role they gave them.

1. Build the arguments (the file name is not sent; the file is named by its content):

   ```sh
   cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' upload-call --file '<local file path>'
   ```

   It refuses other types and files over 200 MB (video) or 10 MB (JPEG / PNG photo); then ask the
   user for a shorter or smaller file, or a public link.
2. Call `start_file_upload` with the printed `arguments`. Save its complete result to
   `host-results/<NN>-start_file_upload.json`. Never show or repeat the upload link.
3. Send the bytes:

   ```sh
   cd '<run directory>' && KABO_STATIC_RUN_DIR='<run directory>' python3 '<skill directory>/scripts/static_host.py' upload --file '<local file path>' --input 'host-results/<NN>-start_file_upload.json'
   ```

   If it prints `"status": "ready"`, the file was already sent: use its `file_ref`. Otherwise call
   `finish_file_upload` with the printed `arguments`. When that answers `ready`, the reference is
   `kabo-file:<file_id>`. If a step says the link expired or was refused, do what it prints (call
   `start_file_upload` again with the same arguments; nothing is duplicated).
4. Pass `kabo-file:<file_id>` in place of the link: `--reference-url`, `--creator-video`,
   `--creator-photo`, `--reference-video` or `--reference-image`. Kabo still checks the content: a
   reference over 10 minutes, a photo that is not JPEG or PNG, or a video given as a photo is refused
   before anything is generated.

If the upload script reports that this host blocks network access for scripts, say that local
files cannot be sent from here and ask for a YouTube, Instagram or TikTok link instead.
