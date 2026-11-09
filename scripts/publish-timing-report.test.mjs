// 发布时间报告里的钟点：标题和摘要只报推荐窗口；单小时答出时，分块投票的胜出段不能以时间段出现在正文里
// （一次迁移实测的报告标题推荐 18:00，「怎么比的」又写 06:00–09:00 表现最好）。没拿到创作者时区时，
// 渲染器自己在答案下面打印「参考钟点、不是本地时间」那句，不再靠模型记得写。
// 这里只核对钟点和时区两条规则的报错，不要求最小样本过完全部形状检查。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const scripts = path.join(root, "skills", "recommend-publish-timing", "scripts");

function recommendation({ source = "creator_confirmed", start = "18:00", end = "19:00", resolution = "hour" } = {}) {
  return {
    outcome: "recommended",
    recommendation: { windows: [{ weekday: "all", start_local: start, end_local: end, zone: "America/New_York", resolution, supporting_n: 5 }],
      confidence_penalties: [] },
    evidence_base: {
      timezone: { analysis_zone: source === "creator_confirmed" ? "America/New_York" : "UTC", source, note: null },
      ranking: { granularity_hours: 3, winner: "06-09", windows: [] },
      signals: [], hour_curve: { hours: {} }, cohort: {}, practical_stakes: {},
    },
  };
}

function result({ headline = "下一条发在 18:00", summary = "你自己的 40 条内容里，18 点这一小时的播放中位数最高。", lines = [], next = [] } = {}) {
  return {
    schema_version: "creator-task-result.v2-final", result_id: "r1", task: "recommend_publish_timing", status: "complete",
    details: {}, evidence_index: [], interaction: {},
    creator_view: {
      language: "zh-CN", headline, summary, data_note: "",
      cards: [{ title: "这是怎么比出来的", why_for_you: lines.join("\n"), action: "下一条排在 18:00–19:00。", evidence_refs: ["hour_curve"] }],
      next_actions: next,
    },
  };
}

async function validate(t, rec, res) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-timing-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  await writeFile(path.join(dir, "rec.json"), JSON.stringify(rec));
  await writeFile(path.join(dir, "result.json"), JSON.stringify(res));
  const out = spawnSync("python3", [path.join(scripts, "validate_creator_shape.py"), path.join(dir, "result.json"), path.join(dir, "rec.json")],
    { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  return out.stdout + out.stderr;
}

const clockErrors = (out) => out.split("\n").filter((line) => /block vote|outside the recommended/.test(line));

test("单小时答出时，正文报出分块投票的胜出段被拒，报错点名推荐窗口", async (t) => {
  const out = await validate(t, recommendation(), result({ lines: ["06:00–09:00 这一段整体表现最好。", "18 点这一小时有 5 条内容支撑。"] }));
  const errors = clockErrors(out);
  assert.equal(errors.length, 1, out);
  assert.match(errors[0], /06:00–09:00, the 3-hour block vote/);
  assert.match(errors[0], /18:00–19:00/);
});

test("只报推荐窗口、投票只说同不同意：没有钟点报错", async (t) => {
  const out = await validate(t, recommendation(), result({ lines: ["18 点这一小时有 5 条内容支撑。", "按 3 小时分段投票时，各指标没有都选这一段。"] }));
  assert.deepEqual(clockErrors(out), [], out);
});

test("标题或摘要报出推荐窗口以外的钟点被拒", async (t) => {
  const out = await validate(t, recommendation(), result({ headline: "下一条发在 06:00", summary: "早上 7 点前后发表现更好。" }));
  const errors = clockErrors(out);
  assert.equal(errors.length, 2, out);
  assert.match(errors[0], /^ERROR: headline states 06:00/);
  assert.match(errors[1], /^ERROR: summary states 07:00/);
});

test("下一步里的对照实验可以提别的小时；分块答出时报那一段不算冲突", async (t) => {
  const experiment = await validate(t, recommendation(), result({ next: ["顺手在 20 点试两条，看同赛道账号的时段在你这成不成立。"] }));
  assert.deepEqual(clockErrors(experiment), [], experiment);
  const block = await validate(t, recommendation({ start: "06:00", end: "09:00", resolution: "3h" }),
    result({ headline: "下一条发在 06:00–09:00", summary: "按 3 小时分段比，06:00–09:00 这一段票数最多。", lines: ["06:00–09:00 这一段整体表现最好。"] }));
  assert.deepEqual(clockErrors(block), [], block);
});

// 只渲染创作者那份文档（creator_view），审计文档要的字段这里不造。
async function render(t, rec, res) {
  const dir = await mkdtemp(path.join(os.tmpdir(), "kabo-timing-render-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  await writeFile(path.join(dir, "rec.json"), JSON.stringify(rec));
  await writeFile(path.join(dir, "result.json"), JSON.stringify(res));
  const code = "import json,sys; sys.path.insert(0, sys.argv[1]); import render_timing_report as r; "
    + "print(r.creator_view(json.load(open(sys.argv[3])), json.load(open(sys.argv[2]))), end='')";
  const out = spawnSync("python3", ["-c", code, scripts, path.join(dir, "rec.json"), path.join(dir, "result.json")],
    { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  assert.equal(out.status, 0, out.stdout + out.stderr);
  return out.stdout;
}

test("没拿到时区时，渲染器在答案下面打印参考钟点说明；拿到时区时不打印", async (t) => {
  const missing = await render(t, recommendation({ source: "not_supplied" }), result());
  const lines = missing.split("\n").filter(Boolean);
  assert.match(lines[2], /没有拿到你所在的时区.*参考钟点，不是你的本地时间/, missing);
  const unresolved = await render(t, recommendation({ source: "zone_unresolved" }), result());
  assert.match(unresolved, /你给的时区没能识别/);
  const english = await render(t, recommendation({ source: "not_supplied" }), { ...result(), creator_view: { ...result().creator_view, language: "en" } });
  assert.match(english, /reference clock, not your local time/);
  const known = await render(t, recommendation({ source: "creator_confirmed" }), result());
  assert.doesNotMatch(known, /参考钟点|reference clock/);
});
