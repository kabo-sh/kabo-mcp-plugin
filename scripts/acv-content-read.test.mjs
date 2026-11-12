// analyze-content-video 的「内容解读」模式回归。
// 起因：一条只有配乐、没有口播的 Reel，问「这个视频说的是什么」时只取了转写，
// 机器把歌词听写成了口播，回答把歌词当成视频内容总结了。
// 模式表原来只有诊断 / 制作拆解 / 导出逐字稿三档，「说的是什么」最容易被归进导出逐字稿。
// 这里钉住：问内容走内容解读（转写 + 抽帧 + 元数据），导出逐字稿只在要文件时走，
// 以及听写出来的词在有现成曲目或画面里没人说话时要先当作可能的歌词。
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const skill = readFileSync(new URL("../skills/analyze-content-video/SKILL.md", import.meta.url), "utf8");
const description = skill.match(/^description: "(.*)"$/m)[1];
const section = (heading) => {
  const start = skill.indexOf(`\n## ${heading}\n`);
  assert.notEqual(start, -1, `缺少 ## ${heading}`);
  const end = skill.indexOf("\n## ", start + 4);
  return skill.slice(start, end === -1 ? undefined : end);
};

test("描述里写明「视频讲了什么 / 说的是什么」，目录里能被选中", () => {
  assert.match(description, /what a video is about or says/);
  // KS1.2：超过 500 字符会告警，挤占宿主的 skill 列表预算。
  assert.ok(description.length <= 500, `description ${description.length} 字符`);
});

test("模式表：问内容走内容解读，导出逐字稿只接要文件的请求", () => {
  const table = section("Which question is this");
  assert.match(table, /\| What it is about or says .*\| \*\*Content read\*\* \(below\) \|/);
  assert.match(table, /\| The words themselves as a file .*\| \*\*Transcript export\*\* \(below\) \|/);
  assert.match(table, /"what does it say" are a content read, not a transcript export/);
  assert.match(table, /machine-heard words can be a song's lyrics/);
});

test("内容解读取转写和抽帧，不出诊断报告，听写的词先判断是不是歌词", () => {
  assert.match(skill, /content read: `transcript,keyframes`, plus `metadata` on\s+Instagram and TikTok/);
  const read = section("Content read");
  assert.match(read, /Run diagnosis steps 1–3/);
  assert.match(read, /`acquire\.owner_metrics` set to `skip`/);
  assert.match(read, /seen in a frame, read from on-screen text or the caption, or heard/);
  assert.match(read, /`audio_attribution` names an existing track/);
  assert.match(read, /may\s+be that track's lyrics/);
  assert.match(read, /never summarize its words as the video's\s+message/);
  assert.match(read, /writes no report/);
  // 开头的交付说明只约束诊断报告；内容解读按证据作答，不能被那句话挡住。
  assert.match(skill, /A content read has no report: it answers from the evidence object/);
});
