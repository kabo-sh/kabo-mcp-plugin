// Mechanical checks moved over from kabo and creator-skills (same-named rules in their .coderabbit.yaml and
//   tests/); this repo is stricter because it is public:
// 1. Vendor names: this whole repo is public (anyone can read the raw files), so scan the entire repo, not
//   just the packaged content;
// 2. Host-specific mechanisms: Skill bodies must not write a particular host's commands or wrapper
//   placeholders, or branch by host;
// 3. Case specialization: Skills must not contain benchmark case numbers, scenario numbers or local run ids;
// 4. Provenance docs: Skill packages must not contain source maps of "how this was distilled from a private
//   repo";
// 5. Bytecode: do not commit __pycache__ / *.pyc;
// 6. Origin markers: a Skill's Markdown must not write version codenames (V3, V4) or dates (measurement or
//   observation dates); the conclusions and numbers stay;
// 7. Foreground-execution note (KS2.4): a Skill with scripts states at the start of its body that it runs in a
//   foreground subagent and not in the background.
// 8. English only: no Chinese, Japanese or Korean text outside docs/i18n/ and the listed data files.
// Parts that need judgment (brand / country keyword gates, wording) are left to CodeRabbit.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const tracked = (...paths) =>
  execFileSync("git", ["ls-files", "-z", "--", ...paths], { cwd: root, encoding: "utf8" }).split("\0").filter(Boolean);
const text = (file) => readFileSync(path.join(root, file), "utf8");
const isText = (file) => !/\.(png|jpe?g|gif|webp|ico|zip|mp4|mov|pdf|woff2?)$/i.test(file);

// Vendor identity words, the same list as the CodeRabbit "No vendor in ..." rules of kabo and creator-skills,
//   plus data-fetching vendors known to appear in this repo.
// This file and .coderabbit.yaml must list these words as the rule itself, so those two files are skipped.
const VENDORS = /tikhu|scrape ?creators|tubelab|vidiq|\bgemini\b|printingpress|yt-dlp|youtube-pp|youtube data api|ensemble ?data|hiker ?api|creator ?db|\bapify\b|firecrawl/i;

const COMPARISON_PAGES = /^(?:README\.md|docs\/i18n\/README\.[\w-]+\.md)$/;

export function vendorHits(files = tracked(".").filter(isText)) {
  const self = path.relative(root, fileURLToPath(import.meta.url));
  const hits = [];
  for (const file of files) {
    if (file === self || file === ".coderabbit.yaml") continue;
    text(file).split("\n").forEach((line, index) => {
      // The README comparison table names vidIQ as a competing product (approved by the product owner).
      // That exception covers the README and its translations only; every other vendor name still fails.
      const checked = COMPARISON_PAGES.test(file) ? line.replace(/vidiq/gi, "") : line;
      if (VENDORS.test(checked)) hits.push(`${file}:${index + 1}: ${line.trim().slice(0, 100)}`);
    });
  }
  return hits;
}

const HOST_SPECIFIC = [
  ["host helper", /\bkabo-run-(?:dir|pipeline)\b/],
  ["wrapper report flag", /--report-file\b/],
  ["wrapper stage model", /\bPRE\/FETCH\/POST\b/],
  ["Web script tool", /\brun_bundle_(?:script|stage)\b|\bemit_block\b|--export-deliverable\b/],
  ["generic data-call tool", /\bdata_connector_(?:run|batch_run|catalog)\b|\bkabo_connector_run\b/],
  ["registry lookup", /\bregistry_skill_[a-z_]+\b/],
  ["restricted runner", /\bskill-runner\b/],
  ["host-named branch", /\b(?:Native desktop|Plugin host|Plugin pipeline host|Pipeline host|Legacy direct host|Web script-tool host)\b|\bOn (?:Web|Desktop|Codex|Claude)\b/i],
  ["host install path", /<plugin-root>|\$\{?CLAUDE_PLUGIN_ROOT\b|\bCODEX_THREAD_ID\b/],
  ["wrapper placeholder", /\{(?:skill|run|snapshot|analysis|report|owner|envelopes|language)\}|\{param\.[A-Za-z_]+\}/],
];

const CASE_SPECIFIC = [
  ["scene or case number", /\(0\d{2}[a-z]?(?:\s*\/\s*0\d{2}[a-z]?)*\)/],
  ["benchmark case id", /\b(?:COMP|TREND|KAB|REACH|ACCT|IDEA)-(?:[A-Z0-9]+-)?\d{2,}\b/],
  ["run id", /\b20\d{6}T\d{6}Z-[0-9a-f]{6,}\b/],
];

const PROVENANCE = [
  ["private-repo coordinate", /kabo-sh\/kabo@[0-9a-f]{7,}/],
  ["private implementation path", /apps\/web\/src\/app\/tools\//],
  ["provenance document", /(?:^|\/)source-composition\.md$/],
];

export function patternHits(files, rules) {
  const hits = [];
  for (const file of files) {
    for (const [label, pattern] of rules) if (pattern.test(file)) hits.push(`${file}: ${label}`);
    text(file).split("\n").forEach((line, index) => {
      for (const [label, pattern] of rules)
        if (pattern.test(line) && !allowedIdeaFileDelivery(file, label, line))
          hits.push(`${file}:${index + 1}: ${label}: ${line.trim().slice(0, 100)}`);
    });
  }
  return hits;
}

// The user explicitly approved ideas using the existing file-display capability; only this one transport note
//   is allowed through, not other host execution mechanisms.
function allowedIdeaFileDelivery(file, label, line) {
  return file === "skills/develop-content-ideas/references/delivery.md" && label === "Web script tool" &&
    line === "Pass the returned absolute `report_path` to the host's existing `emit_block` capability:";
}

// Dates and version codenames record "when, and in which version, something was discovered", which belongs in
//   the PR description; a Skill keeps only the rule itself.
// Machine values such as schema_version live in JSON, not in the Markdown body, so only .md files are scanned.
const DATED = [
  ["version label", /\bV\d+\b/],
  ["date stamp", /\b20\d{2}-\d{2}-\d{2}\b/],
];

// Length of this opening segment of the body: existing notes all sit within the first 1,600 characters of the
//   body, and anything written after the opening segment has no effect.
const FOREGROUND_WINDOW = 1600;

export function missingForegroundNote(skills = tracked("skills").filter((file) => /^skills\/[^/]+\/SKILL\.md$/.test(file))) {
  const withScripts = new Set(tracked("skills").filter((file) => /^skills\/[^/]+\/scripts\//.test(file)).map((file) => file.split("/")[1]));
  return skills.filter((file) => {
    if (!withScripts.has(file.split("/")[1])) return false;
    const body = text(file).replace(/^---\n[\s\S]*?\n---\n/, "");
    return !/foreground sub-agent/i.test(body.slice(0, FOREGROUND_WINDOW).replace(/\s+/g, " "));
  });
}

// English only (AGENTS.md): outside docs/i18n/ (the localized README translations), tracked text files contain no
// Chinese, Japanese or Korean text. The files below are the exceptions, and each holds such text as data only:
// comments, docstrings, test names and maintainer-facing messages stay in English there too (a comment may quote
// the literal token it is about). A file that no longer needs its entry must be removed from the list.
const NON_ENGLISH = /[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]/;
const LOCALIZED_DIR = "docs/i18n/";
// Localized report strings, and patterns that match non-English user input or platform content.
const LOCALIZED_SKILL_DATA = [
  "skills/analyze-content-video/scripts/build_creator_result.py",
  "skills/analyze-content-video/scripts/creator_measurement_basis.py",
  "skills/analyze-content-video/scripts/render_video_report.py",
  "skills/analyze-content-video/scripts/validate_creator_shape.py",
  "skills/analyze-creator-competitors/scripts/render_reply.py",
  "skills/analyze-creator-competitors/scripts/validate_discovery_intents.py",
  "skills/create-script-and-packaging/scripts/validate_script_package.py",
  "skills/develop-content-ideas/references/report-locales.json",
  "skills/develop-content-ideas/scripts/project_comments.py",
  "skills/develop-content-ideas/scripts/render_idea_report.py",
  "skills/develop-content-ideas/scripts/report_language.py",
  "skills/develop-content-ideas/scripts/validate_ideas.py",
  "skills/diagnose-reach-drop/scripts/author_traffic.py",
  "skills/diagnose-reach-drop/scripts/compile_traffic_brief.py",
  "skills/diagnose-reach-drop/scripts/compose_traffic.py",
  "skills/diagnose-reach-drop/scripts/correction.py",
  "skills/diagnose-reach-drop/scripts/explain_share.py",
  "skills/diagnose-reach-drop/scripts/render_traffic.py",
  "skills/diagnose-reach-drop/scripts/synthesis.py",
  "skills/optimize-creator-brand/references/creator-brand-kit.schema.json",
  "skills/optimize-creator-brand/references/creator-brand-options.schema.json",
  "skills/optimize-creator-brand/references/creator-brand-request.schema.json",
  "skills/optimize-creator-brand/references/creator-brand-strategy-brief.schema.json",
  "skills/optimize-creator-brand/references/creator-brand-visual-spec.schema.json",
  "skills/optimize-creator-brand/scripts/brand_run.py",
  "skills/optimize-creator-brand/scripts/validate_brand_options.py",
  "skills/plan-content-calendar/scripts/calendar_common.py",
  "skills/plan-content-calendar/scripts/render_content_calendar.py",
  "skills/plan-content-calendar/scripts/upstream/validate_script_package.py",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/library.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-instagram-bonuses.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-instagram-gifts.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-instagram-subscriptions.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-tiktok-creator-rewards.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-tiktok-live-gifts.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-tiktok-paid-collections.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-tiktok-shop-commission.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-tiktok-subscriptions.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-youtube-ad-share.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-youtube-channel-memberships.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-youtube-shorts-ad-share.json",
  "skills/plan-platform-monetization/references/rules/platform-monetization-rules.v1/program-youtube-super-thanks.json",
  "skills/price-creator-brand-deals/references/frameworks/creator-brand-deal-pricing.v1.json",
  "skills/recommend-publish-timing/scripts/render_timing_report.py",
  "skills/recommend-publish-timing/scripts/validate_creator_report.py",
  "skills/recommend-publish-timing/scripts/validate_creator_shape.py",
  "skills/research-instagram-trends/scripts/attach_creator_profile.py",
  "skills/research-instagram-trends/scripts/render_creator_report.py",
  "skills/research-instagram-trends/scripts/render_short_window_report.py",
  "skills/research-tiktok-trends/scripts/attach_creator_profile.py",
  "skills/research-tiktok-trends/scripts/render_creator_report.py",
  "skills/research-tiktok-trends/scripts/render_short_window_report.py",
  "skills/research-youtube-trends/scripts/attach_creator_profile.py",
  "skills/research-youtube-trends/scripts/render_creator_report.py",
  "skills/research-youtube-trends/scripts/render_short_window_report.py",
  "skills/review-creator-account-deep/scripts/compose_deep_review.py",
  "skills/review-creator-account/scripts/compose_review.py",
  "skills/review-creator-account/scripts/estimate_growth.py",
  "skills/review-creator-account/scripts/validate_creator_report.py",
  "skills/verify-platform-rule/references/sources/bilibili.json",
];
// Test inputs and expected outputs that exercise the data above.
const NON_ENGLISH_TEST_DATA = [
  "scripts/account-review-correction.test.mjs",
  "scripts/account-review-evidence.test.mjs",
  "scripts/content-language-regression.py",
  "scripts/continuation-overlap.test.mjs",
  "scripts/english-output.test.mjs",
  "scripts/fixtures/creator-profile/youtube-effective.json",
  "scripts/fixtures/creator-profile/youtube.json",
  "scripts/ideas-context-regression.py",
  "scripts/mcp-pub-sync.test.mjs",
  "scripts/publish-timing-report.test.mjs",
  "scripts/reach-drop-age-reading.test.mjs",
  "scripts/reach-drop-calendar-windows.test.mjs",
  "scripts/remake-local-upload.test.mjs",
  "scripts/short-window-topic-regression.py",
  "scripts/static-skills.test.mjs",
  "scripts/trends-profile.test.mjs",
];
const NON_ENGLISH_OTHER = [
  // Generated by the Kabo service and pinned byte for byte in contracts/directory-mcp/pin.json; translate it at the source.
  "contracts/directory-mcp/annotations.md",
  // A review rule that quotes the literal magnitude words it is about.
  ".coderabbit.yaml",
];
// The README language switcher names each language in that language and links into docs/i18n/. Listed apart
// because the entry is valid whether or not the switcher is present.
const NON_ENGLISH_OPTIONAL = ["README.md"];
const NON_ENGLISH_ALLOWED = new Set([...LOCALIZED_SKILL_DATA, ...NON_ENGLISH_TEST_DATA, ...NON_ENGLISH_OTHER]);

export function nonEnglishFiles(files = tracked(".").filter(isText)) {
  return files.filter((file) => !file.startsWith(LOCALIZED_DIR) && NON_ENGLISH.test(text(file)));
}

const skillProse = () => tracked("skills").filter((file) => /\.md$/.test(file));
const skillFiles = () => tracked("skills").filter((file) => /\.(md|py|mjs|js|json|ya?ml)$/.test(file));

test("no data-vendor names anywhere in the repository (it is public; test fixtures and docs count too)", () => {
  assert.deepEqual(vendorHits(), []);
});

test("Skill prose does not describe host-specific mechanisms", () => {
  assert.deepEqual(patternHits(skillProse(), HOST_SPECIFIC), []);
});

test("the idea-report file display exception does not extend to other files or host calls", () => {
  const file = "skills/develop-content-ideas/references/delivery.md";
  const line = "Pass the returned absolute `report_path` to the host's existing `emit_block` capability:";
  assert.equal(allowedIdeaFileDelivery(file, "Web script tool", line), true);
  assert.equal(allowedIdeaFileDelivery("skills/review-creator-account/references/delivery.md", "Web script tool", line), false);
  assert.equal(allowedIdeaFileDelivery(file, "Web script tool", line + " run_bundle_script"), false);
  assert.equal(allowedIdeaFileDelivery(file, "Web script tool", "Call emit_block with rewritten text"), false);
  assert.equal(allowedIdeaFileDelivery(file, "registry lookup", line), false);
});

test("Skills contain no benchmark case ids, scene numbers or local run ids", () => {
  assert.deepEqual(patternHits(skillFiles(), CASE_SPECIFIC), []);
});

test("Skill packages contain no private-repo coordinates, implementation path maps or provenance documents", () => {
  assert.deepEqual(patternHits(tracked("skills"), PROVENANCE), []);
});

test("Skill Markdown contains no version labels or dates", () => {
  assert.deepEqual(patternHits(skillProse(), DATED), []);
});

test("Skills with scripts state at the top of the body that they run in a foreground sub-agent", () => {
  assert.deepEqual(missingForegroundNote(), []);
});

test("no Python bytecode is committed", () => {
  assert.deepEqual(tracked(".").filter((file) => /(?:^|\/)__pycache__\/|\.pyc$/.test(file)), []);
});

test("no non-English text outside docs/i18n/ and the listed data files", () => {
  const found = nonEnglishFiles();
  assert.deepEqual(found.filter((file) => !NON_ENGLISH_ALLOWED.has(file) && !NON_ENGLISH_OPTIONAL.includes(file)), [], "translate these files, or list them if the text is data");
  assert.deepEqual([...NON_ENGLISH_ALLOWED].filter((file) => !found.includes(file)).sort(), [], "remove entries that no longer need the exception");
});

test("the checks themselves catch violations", () => {
  assert.ok(NON_ENGLISH.test("\u4e2d\u6587") && !NON_ENGLISH.test("caf\u00e9 \u2014 na\u00efve"));
  assert.ok(VENDORS.test("provider: tikhub"));
  assert.ok(HOST_SPECIFIC.some(([, pattern]) => pattern.test("call data_connector_run with")));
  assert.ok(CASE_SPECIFIC.some(([, pattern]) => pattern.test("run 20260827T152038Z-5e90c56b")));
  assert.ok(PROVENANCE.some(([, pattern]) => pattern.test("see kabo-sh/kabo@1a2b3c4d")));
  assert.ok(DATED.some(([, pattern]) => pattern.test("# Create Script and Packaging V4")));
  assert.ok(DATED.some(([, pattern]) => pattern.test("measured 2026-09-22 on a ten-video set")));
  assert.ok(!DATED.some(([, pattern]) => pattern.test("`schema_version` is `idea-set.v3`")));
});
