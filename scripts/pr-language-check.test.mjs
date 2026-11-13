import { test } from "node:test";
import assert from "node:assert/strict";
import { offendingLines } from "./pr-language-check.mjs";

test("English prose passes", () => {
  assert.deepEqual(offendingLines("fix(remake-viral-video): trim the reference before upload\n\nSee #12."), []);
});

test("Chinese, Japanese and Korean prose fails", () => {
  assert.equal(offendingLines("feat: 复刻合一第 3 阶段").length, 1);
  assert.equal(offendingLines("修正しました").length, 1);
  assert.equal(offendingLines("수정").length, 1);
  assert.equal(offendingLines("Done.（note）").length, 1);
});

test("code, block quotes, HTML comments and bot sections are ignored", () => {
  const body = [
    "Routes a quoted query:",
    "> 下个月总共发4条长视频",
    "Token `探店` is matched in data.",
    "```",
    "中文 fixture",
    "```",
    "<!-- 隐藏 -->",
    "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->",
    "## Summary by CodeRabbit 中文摘要",
  ].join("\n");
  assert.deepEqual(offendingLines(body), []);
});
