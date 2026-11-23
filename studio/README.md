# Studio Skills

Kabo Animations starts `code2video` on an authenticated Studio job after the creator has selected the episode, template and narrator. The execution host grants the tool on that job for a specific bundle version and checksum. The desktop catalog and plugin release ZIP enumerate `skills/`.

To build the Studio bundle from a clean checkout, pass `studio/code2video`, the full Git commit and the version in its frontmatter to `buildPluginBundle` in `scripts/web-publish/bundle.mjs`. Publish the resulting content-addressed object to the Studio host's preview registry, register its exact checksum there and verify a delivered episode. Keep the previous immutable object available for rollback.
