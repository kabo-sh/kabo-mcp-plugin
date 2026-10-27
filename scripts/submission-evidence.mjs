import { createHash } from "node:crypto";
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import path from "node:path";

// 这是项目交付门，数量与检查 ID 不是 OpenAI 对所有插件的统一要求。
export const acceptanceChecks = Object.freeze([
  "host.chatgpt", "host.codex", "oauth.authorization", "oauth.refresh",
  "architecture.host-execution", "report.single-delivery",
  "oauth.bad-token", "oauth.wrong-audience", "oauth.missing-scope",
  "isolation.run", "isolation.artifact", "deletion.account",
  "mcp.regression", "mcp.tools-list", "production.canary", "domain.challenge",
  "legal.support", "legal.privacy-terms", "reviewer.access", "reviewer.demo",
  "review.P-01", "review.P-02", "review.P-03", "review.P-04", "review.P-05",
  "review.N-01", "review.N-02", "review.N-03",
]);

const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const exactKeys = (value, keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const digest = value => /^[a-f0-9]{64}$/.test(value ?? "");
const date = value => typeof value === "string" && /^\d{4}-\d\d-\d\dT/.test(value) && Number.isFinite(Date.parse(value));

function artifact(directory, filename, expected) {
  if (typeof filename !== "string" || !/^[A-Za-z0-9_./-]+$/.test(filename) || filename.startsWith("/") ||
      filename.split("/").some(part => !part || part === "." || part === "..") || !digest(expected))
    throw new Error("证据路径或摘要无效。");
  let target = directory;
  for (const part of filename.split("/")) {
    target = path.join(target, part);
    if (lstatSync(target).isSymbolicLink()) throw new Error("证据不得引用符号链接。");
  }
  const stat = lstatSync(target);
  if (!stat.isFile() || stat.size === 0 || stat.size > 4 * 1024 * 1024)
    throw new Error("证据必须是有界非空文件。");
  const bytes = readFileSync(target);
  if (sha(bytes) !== expected) throw new Error("证据内容摘要不符。");
  // 仅收脱敏文本；避免把 OAuth 凭据、Cookie 或 Reviewer 密码夹进交付附件。
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  if (/\bBearer\s+[A-Za-z0-9._~-]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|(?:access_token|refresh_token|client_secret|password)\s*["']?\s*[:=]\s*["'][^"']+["']|(?:^|\n)(?:set-cookie|cookie|authorization):\s*\S+/i.test(text))
    throw new Error("证据可能含凭据；请提供脱敏文件。");
  return bytes;
}

/** 校验人或生产验收器提交的证据及版本绑定；文件哈希不能证明测试事实本身真实。 */
export function assessAcceptance({ evidencePath, commit, version, zipSha256, toolsSha256, now = Date.now() } = {}) {
  const missing = () => ({ code: "PRODUCTION_ACCEPTANCE_PENDING", message: "需要与本次 commit、ZIP 和 tools/list 绑定的生产验收证据。" });
  if (!evidencePath) return { blockers: [missing()], evidence: null };
  try {
    if (lstatSync(evidencePath).isSymbolicLink()) throw new Error("证据索引不能是链接。");
    const directory = realpathSync(path.dirname(path.resolve(evidencePath)));
    if (lstatSync(evidencePath).size > 128 * 1024) throw new Error("证据索引过大。");
    const raw = readFileSync(evidencePath);
    if (raw.length > 128 * 1024) throw new Error("证据索引过大。");
    const receipt = JSON.parse(raw);
    if (!exactKeys(receipt, ["format", "environment", "resource", "release", "checks"]) ||
        receipt.format !== "kabo.openai-acceptance.v1" || receipt.environment !== "production" ||
        receipt.resource !== "https://kabo.sh/mcp-pub" ||
        !exactKeys(receipt.release, ["commit", "version", "zipSha256", "toolsSha256"]) ||
        !/^[a-f0-9]{40}$/.test(commit ?? "") || !digest(zipSha256) || !digest(toolsSha256) ||
        receipt.release.commit !== commit || receipt.release.version !== version ||
        receipt.release.zipSha256 !== zipSha256 || receipt.release.toolsSha256 !== toolsSha256 ||
        !Array.isArray(receipt.checks) || receipt.checks.length > 100)
      throw new Error("证据未绑定本次生产候选制品。");
    const seen = new Set();
    const pending = [];
    for (const check of receipt.checks) {
      if (!exactKeys(check, ["id", "status", "performedAt", "artifact", "sha256"]) ||
          !acceptanceChecks.includes(check.id) || seen.has(check.id) ||
          !["passed", "failed", "not-run"].includes(check.status) ||
          !(check.status === "not-run" && check.performedAt === null || date(check.performedAt)) ||
          (check.performedAt !== null && Date.parse(check.performedAt) > now + 60_000))
        throw new Error("证据检查记录无效或重复。");
      seen.add(check.id);
      artifact(directory, check.artifact, check.sha256);
      if (check.id === "mcp.tools-list" && check.status === "passed" && check.sha256 !== toolsSha256)
        throw new Error("生产 tools/list 必须与本次固定工具契约逐字一致。");
      if (check.status !== "passed") pending.push(check.id);
    }
    pending.push(...acceptanceChecks.filter(id => !seen.has(id)));
    return {
      blockers: pending.length ? [{ code: "ACCEPTANCE_CHECKS_PENDING", checks: pending.sort(), message: "生产验收存在未通过或未执行项。" }] : [],
      evidence: { format: receipt.format, sha256: sha(raw), checks: receipt.checks.length },
    };
  } catch {
    return { blockers: [{ code: "ACCEPTANCE_EVIDENCE_INVALID", message: "验收索引、版本绑定或脱敏附件校验失败；不会打印原始证据。" }], evidence: null };
  }
}
