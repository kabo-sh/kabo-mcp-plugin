import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { assessAcceptance, acceptanceChecks } from "./submission-evidence.mjs";

const hash = bytes => createHash("sha256").update(bytes).digest("hex");
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "kabo-acceptance-test-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const body = "Synthetic fixture only; no production test was performed.\n";
  const release = { commit: "a".repeat(40), version: "1.0.0", zipSha256: "b".repeat(64), toolsSha256: hash(body) };
  fs.writeFileSync(path.join(root, "report.txt"), body);
  const receipt = {
    format: "kabo.openai-acceptance.v1", environment: "production", resource: "https://kabo.sh/mcp-pub", release,
    checks: acceptanceChecks.map(id => ({ id, status: "passed", performedAt: "2026-10-10T00:00:00Z", artifact: "report.txt", sha256: hash(body) })),
  };
  const evidencePath = path.join(root, "acceptance.json");
  const assess = edit => {
    const value = structuredClone(receipt);
    edit?.(value);
    fs.writeFileSync(evidencePath, JSON.stringify(value));
    return assessAcceptance({ evidencePath, ...release, now: Date.parse("2026-10-10T12:00:00Z") });
  };
  return { root, assess, receipt, release, evidencePath };
}

test("提交门由完整证据决定，缺席、未执行、失败与错误版本均不能通过", t => {
  const { assess } = fixture(t);
  assert.equal(assess().blockers.length, 0);
  assert.equal(assessAcceptance().blockers[0].code, "PRODUCTION_ACCEPTANCE_PENDING");
  for (const status of ["failed", "not-run"])
    assert.deepEqual(assess(r => { r.checks[0].status = status; }).blockers[0].checks, ["host.chatgpt"]);
  assert.ok(assess(r => { r.checks.pop(); }).blockers[0].checks.includes("review.N-03"));
  for (const edit of [
    r => { r.environment = "fixture"; },
    r => { r.release.commit = "d".repeat(40); },
    r => { r.release.zipSha256 = "d".repeat(64); },
    r => { r.release.toolsSha256 = "d".repeat(64); },
    r => { r.checks.push(r.checks[0]); },
    r => { r.checks[0].performedAt = "2999-01-01T00:00:00Z"; },
    r => { r.password = "fixture"; },
  ]) assert.equal(assess(edit).blockers[0].code, "ACCEPTANCE_EVIDENCE_INVALID");
});

test("提交门拒绝被改写、越界、链接和含凭据的验收附件", t => {
  const { root, assess } = fixture(t);
  assert.equal(assess(r => { r.checks[0].artifact = "../report.txt"; }).blockers[0].code, "ACCEPTANCE_EVIDENCE_INVALID");
  fs.symlinkSync(path.join(root, "report.txt"), path.join(root, "linked.txt"));
  assert.equal(assess(r => { r.checks[0].artifact = "linked.txt"; }).blockers[0].code, "ACCEPTANCE_EVIDENCE_INVALID");
  fs.writeFileSync(path.join(root, "report.txt"), "changed");
  assert.equal(assess().blockers[0].code, "ACCEPTANCE_EVIDENCE_INVALID");
  const secret = '{"access_token":"synthetic-fixture-not-a-real-token"}';
  fs.writeFileSync(path.join(root, "report.txt"), secret);
  assert.equal(assess(r => { r.checks.forEach(c => c.sha256 = hash(secret)); }).blockers[0].code, "ACCEPTANCE_EVIDENCE_INVALID");
});
