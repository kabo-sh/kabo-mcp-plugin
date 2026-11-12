import { createHash } from "node:crypto";
import { lstatSync, readFileSync, realpathSync } from "node:fs";
import path from "node:path";

// This is the project's delivery gate; the counts and check IDs are not a uniform OpenAI requirement for all plugins.
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
    throw new Error("Evidence path or digest is invalid.");
  let target = directory;
  for (const part of filename.split("/")) {
    target = path.join(target, part);
    if (lstatSync(target).isSymbolicLink()) throw new Error("Evidence must not reference symlinks.");
  }
  const stat = lstatSync(target);
  if (!stat.isFile() || stat.size === 0 || stat.size > 4 * 1024 * 1024)
    throw new Error("Evidence must be a bounded non-empty file.");
  const bytes = readFileSync(target);
  if (sha(bytes) !== expected) throw new Error("Evidence content digest mismatch.");
  // Accept only redacted text; avoid putting OAuth credentials, cookies or the Reviewer password into delivery attachments.
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  if (/\bBearer\s+[A-Za-z0-9._~-]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|(?:access_token|refresh_token|client_secret|password)\s*["']?\s*[:=]\s*["'][^"']+["']|(?:^|\n)(?:set-cookie|cookie|authorization):\s*\S+/i.test(text))
    throw new Error("Evidence may contain credentials; provide a redacted file.");
  return bytes;
}

/** Validate evidence submitted by a person or the production acceptance runner, and its version binding; a file hash cannot prove the test facts themselves are true. */
export function assessAcceptance({ evidencePath, commit, version, zipSha256, toolsSha256, now = Date.now() } = {}) {
  const missing = () => ({ code: "PRODUCTION_ACCEPTANCE_PENDING", message: "Production acceptance evidence bound to this commit, ZIP and tools/list is required." });
  if (!evidencePath) return { blockers: [missing()], evidence: null };
  try {
    if (lstatSync(evidencePath).isSymbolicLink()) throw new Error("The evidence index must not be a link.");
    const directory = realpathSync(path.dirname(path.resolve(evidencePath)));
    if (lstatSync(evidencePath).size > 128 * 1024) throw new Error("Evidence index is too large.");
    const raw = readFileSync(evidencePath);
    if (raw.length > 128 * 1024) throw new Error("Evidence index is too large.");
    const receipt = JSON.parse(raw);
    if (!exactKeys(receipt, ["format", "environment", "resource", "release", "checks"]) ||
        receipt.format !== "kabo.openai-acceptance.v1" || receipt.environment !== "production" ||
        receipt.resource !== "https://kabo.sh/mcp-pub" ||
        !exactKeys(receipt.release, ["commit", "version", "zipSha256", "toolsSha256"]) ||
        !/^[a-f0-9]{40}$/.test(commit ?? "") || !digest(zipSha256) || !digest(toolsSha256) ||
        receipt.release.commit !== commit || receipt.release.version !== version ||
        receipt.release.zipSha256 !== zipSha256 || receipt.release.toolsSha256 !== toolsSha256 ||
        !Array.isArray(receipt.checks) || receipt.checks.length > 100)
      throw new Error("Evidence is not bound to this production candidate artifact.");
    const seen = new Set();
    const pending = [];
    for (const check of receipt.checks) {
      if (!exactKeys(check, ["id", "status", "performedAt", "artifact", "sha256"]) ||
          !acceptanceChecks.includes(check.id) || seen.has(check.id) ||
          !["passed", "failed", "not-run"].includes(check.status) ||
          !(check.status === "not-run" && check.performedAt === null || date(check.performedAt)) ||
          (check.performedAt !== null && Date.parse(check.performedAt) > now + 60_000))
        throw new Error("Evidence check record is invalid or duplicated.");
      seen.add(check.id);
      artifact(directory, check.artifact, check.sha256);
      if (check.id === "mcp.tools-list" && check.status === "passed" && check.sha256 !== toolsSha256)
        throw new Error("Production tools/list must match this pinned tool contract verbatim.");
      if (check.status !== "passed") pending.push(check.id);
    }
    pending.push(...acceptanceChecks.filter(id => !seen.has(id)));
    return {
      blockers: pending.length ? [{ code: "ACCEPTANCE_CHECKS_PENDING", checks: pending.sort(), message: "Production acceptance has failed or unexecuted checks." }] : [],
      evidence: { format: receipt.format, sha256: sha(raw), checks: receipt.checks.length },
    };
  } catch {
    return { blockers: [{ code: "ACCEPTANCE_EVIDENCE_INVALID", message: "Acceptance index, version binding or redacted attachment validation failed; raw evidence is not printed." }], evidence: null };
  }
}
