# Review Thumbnail v0.1.1

The native plugin skill evaluates 1–3 uploads using ten vidIQ-style pass/fail checks. Every failure
has a fix; each candidate has its first 2–3 changes (fewer if fewer fail), and comparisons explain
both sides before recommending a suitable candidate or explicitly recommending none. It implements
the approved ten-check framework, not vidIQ's private scoring algorithm. There are no scores,
quality dimensions or vetoes. The prior local v0.1.0 framework and its results are superseded.

The host inspects original and small images. Python/Pillow copy, decode and measure inputs;
`deliver` validates complete records, evidence constraints, priorities and recommendations and
renders a deterministic Markdown file for unchanged path-based emission. Missing context is an
explicit failed check requesting evidence, not a detected visual defect. Scripts do not judge art.
The v2 request/review/delivery schema rejects old v1 reviews. The plugin release version is unchanged.

## Focused validation

Use Node 24 and Python 3 with Pillow:

```sh
node --test scripts/review-thumbnail.test.mjs scripts/static-skills.test.mjs scripts/openai-plugin-package.test.mjs scripts/web-publish-bundle.test.mjs
node scripts/skills-lint.mjs --skill review-thumbnail --json
node scripts/package-check.mjs
```

Contract fixtures do not measure visual accuracy. For image evaluation, freeze bytes, context and
label provenance. Use all 30 approved round7 images and available historical failures. Record
structural compliance, actual defect recall, false defect findings and repeated ten-verdict
agreement separately. Retain source-dependent misses; do not count missing-context failures as
defect detections. A same-context development pilot is not an independent repeatability benchmark.
Real chat attachment access, skill discovery and unchanged report emission require separate Pre tests.

## Pre shared slot

Before an authorized test, verify recent activity and current slot ownership; archive exact overlay
bytes/generation/digest, account-list bytes/generation and runtime identities. Preserve all unrelated
entries, dry-run the one-skill addition, then use generation CAS. Read back all entries and account
membership; verify active skill digest/version before testing. Restore archived content only if
this run still owns the current generation and accounts remain unchanged. If another writer changed
the slot, stop without overwriting them. Verify restored runtime, not just the storage write.

The generic publisher skips a new ID absent from live channels and the destination overlay.
A separately approved native-skill test-only first-mount path remains necessary; this implementation
does not alter that guard, seed production or create a release to test. Real chat, Pre writes,
publishing, merging and external messages are outside this local change.
