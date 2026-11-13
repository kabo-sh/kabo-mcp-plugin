import { test } from "node:test";
import assert from "node:assert/strict";
import { offendingLines } from "./pr-language-check.mjs";

test("English prose passes", () => {
  assert.deepEqual(offendingLines("fix(remake-viral-video): trim the reference before upload\n\nSee #12."), []);
});

test("Chinese, Japanese and Korean prose fails", () => {
  assert.equal(offendingLines("feat: \u590d\u523b\u5408\u4e00\u7b2c 3 \u9636\u6bb5").length, 1);
  assert.equal(offendingLines("\u4fee\u6b63\u3057\u307e\u3057\u305f").length, 1);
  assert.equal(offendingLines("\uc218\uc815").length, 1);
  assert.equal(offendingLines("Done.\uff08note\uff09").length, 1);
});

test("code, block quotes, HTML comments and bot sections are ignored", () => {
  const body = [
    "Routes a quoted query:",
    "> \u4e0b\u4e2a\u6708\u603b\u5171\u53d14\u6761\u957f\u89c6\u9891",
    "Token `\u63a2\u5e97` is matched in data.",
    "```",
    "\u4e2d\u6587 fixture",
    "```",
    "<!-- \u9690\u85cf -->",
    "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->",
    "## Summary by CodeRabbit \u4e2d\u6587\u6458\u8981",
  ].join("\n");
  assert.deepEqual(offendingLines(body), []);
});
