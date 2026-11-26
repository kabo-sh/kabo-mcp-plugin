#!/usr/bin/env node
// Generates skills/remake-viral-video/references/steps/params.md from the Web host's schema
// (contracts/web-remake-tool.v1.json, exported by kabo-agent-service scripts/remake-skill-schema.ts):
// which inputs / params each step takes, with types and ranges. Parameter shapes come only from the
// schema, never from hand-written prose.
// Usage: node scripts/remake-params-gen.mjs [--check]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CONTRACT = path.join(root, "contracts/web-remake-tool.v1.json");
const OUT = path.join(root, "skills/remake-viral-video/references/steps/params.md");

const num = (s) => {
  const lo = s.minimum ?? s.exclusiveMinimum;
  const hiRaw = s.maximum ?? s.exclusiveMaximum;
  const hi = hiRaw !== undefined && hiRaw < 1e12 ? hiRaw : undefined;
  const kind = s.type === "integer" ? "integer" : "number";
  return lo !== undefined && hi !== undefined ? `${kind} ${lo}..${hi}` : lo !== undefined ? `${kind} >= ${lo}` : hi !== undefined ? `${kind} <= ${hi}` : kind;
};
function shape(s, depth = 0) {
  if (!s || typeof s !== "object") return "any";
  if (s.const !== undefined) return JSON.stringify(s.const);
  if (s.enum) return s.enum.map((v) => JSON.stringify(v)).join(" | ");
  const alts = s.anyOf ?? s.oneOf;
  if (alts) {
    const parts = [...new Set(alts.map((a) => shape(a, depth)))];
    return parts.join(" | ");
  }
  if (s.type === "null") return "null";
  if (s.type === "boolean") return "true | false";
  if (s.type === "number" || s.type === "integer") return num(s);
  if (s.type === "string") {
    if (s.pattern && /mp4\|png/.test(s.pattern)) return "handle";
    if (s.format === "uuid") return "uuid";
    return s.maxLength ? `text (<= ${s.maxLength})` : "text";
  }
  if (s.type === "array") {
    if (s.maxItems === 0) return "[] (empty)";
    const n = s.minItems !== undefined || s.maxItems !== undefined ? ` (${s.minItems ?? 0}-${s.maxItems ?? "n"} items)` : "";
    const item = Array.isArray(s.prefixItems) ? `[${s.prefixItems.map((p) => shape(p, depth + 1)).join(", ")}]` : `[${shape(s.items, depth + 1)}, ...]`;
    return item + n;
  }
  if (s.type === "object" || s.properties || s.additionalProperties) {
    if (!s.properties && s.additionalProperties && typeof s.additionalProperties === "object")
      return `{<name>: ${shape(s.additionalProperties, depth + 1)}}`;
    if (!s.properties) return "{}";
    if (depth >= 3) return `{${Object.keys(s.properties).map((k) => k + ((s.required ?? []).includes(k) ? "" : "?")).join(", ")}}`;
    const req = new Set(s.required ?? []);
    return `{${Object.entries(s.properties).map(([k, v]) => `${k}${req.has(k) ? "" : "?"}: ${shape(v, depth + 1)}`).join("; ")}}`;
  }
  return "any";
}
function fields(s) {
  const objs = s?.anyOf ?? s?.oneOf ?? [s];
  const out = new Map();
  for (const o of objs) {
    if (!o?.properties) continue;
    const req = new Set(o.required ?? []);
    for (const [k, v] of Object.entries(o.properties)) {
      const line = `\`${k}\`${req.has(k) ? "" : " (optional)"}: ${shape(v, 1)}`;
      if (!out.has(k)) out.set(k, line);
    }
  }
  return [...out.values()];
}

export function render(contract) {
  const ops = contract.atom.oneOf ?? contract.atom.anyOf;
  const lines = [
    "# Step parameters (generated -- do not edit)",
    "",
    "Generated from the Web host's own schema (`contracts/web-remake-tool.v1.json`, kabo-agent-service",
    `\`scripts/remake-skill-schema.ts\` at ${contract.commit ?? "unknown"}) by \`scripts/remake-params-gen.mjs\`.`,
    "These are the exact shapes the host accepts; where any other file in this Skill reads",
    "differently, this file is right. A field not listed under a step is refused on that step.",
    "`?` / (optional) = may be left out; `a | b` = one of; `[x, ...] (2-16 items)` = a list;",
    "`{<name>: x}` = an object keyed by name (never a list).",
    "",
    "## Storyboard (`plan`)",
    "",
  ];
  const sb = contract.storyboard;
  const expanded = new Set(["shots", "characters", "environments", "props"]);
  for (const f of fields(sb)) {
    const key = f.slice(1, f.indexOf("`", 1));
    const prop = sb.properties?.[key];
    lines.push(expanded.has(key) && prop?.items
      ? `- \`${key}\`${(sb.required ?? []).includes(key) ? "" : " (optional)"}: a list${prop.maxItems ? ` (at most ${prop.maxItems})` : ""}, each entry below`
      : `- ${f}`);
  }
  const row = sb.properties?.shots?.items;
  if (row) {
    lines.push("", "Each row of `shots`:", "");
    for (const f of fields(row)) lines.push(`- ${f}`);
  }
  for (const key of ["characters", "environments", "props"]) {
    const item = sb.properties?.[key]?.items;
    if (!item) continue;
    lines.push("", `Each entry of \`${key}\`:`, "");
    for (const f of fields(item)) lines.push(`- ${f}`);
  }
  lines.push("", "## Steps (`atom`)", "");
  for (const o of ops) {
    const op = o.properties?.op?.const;
    if (!op) continue;
    lines.push(`### \`${op}\``, "");
    const ins = fields(o.properties.inputs);
    const ps = fields(o.properties.params);
    lines.push(ins.length ? `- inputs: ${ins.join("; ")}` : "- inputs: none");
    lines.push(ps.length ? `- params: ${ps.join("; ")}` : "- params: none");
    lines.push("");
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

/** The params keys each op takes (for the contract test). */
export function paramKeysByOp(contract) {
  const ops = contract.atom.oneOf ?? contract.atom.anyOf;
  const out = {};
  for (const o of ops) {
    const op = o.properties?.op?.const;
    if (!op) continue;
    const p = o.properties.params;
    const objs = p?.anyOf ?? p?.oneOf ?? [p];
    out[op] = [...new Set(objs.flatMap((x) => Object.keys(x?.properties ?? {})))];
  }
  return out;
}

export function loadContract() {
  return JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const text = render(loadContract());
  if (process.argv.includes("--check")) {
    const now = fs.existsSync(OUT) ? fs.readFileSync(OUT, "utf8") : "";
    if (now !== text) {
      console.error("params.md is out of date: run node scripts/remake-params-gen.mjs");
      process.exit(1);
    }
  } else fs.writeFileSync(OUT, text);
}
