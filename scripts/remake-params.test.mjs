// Contract test between the remake skill's parameter wording and the Web host's schema. Requests were
// refused because the prose and the schema disagreed (positions written as a list, [] per batch item,
// sfx duration below 0.5). Parameter shapes come only from contracts/web-remake-tool.v1.json:
// params.md is generated from it; every params.X named in the prose is a field the host takes, and in
// "<op> {params:{X" / "`<op>` with `params.X`" the field X is one that op takes.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { loadContract, paramKeysByOp, render } from "./remake-params-gen.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const skill = path.join(root, "skills/remake-viral-video");
const contract = loadContract();
const byOp = paramKeysByOp(contract);
const allKeys = new Set(Object.values(byOp).flat());

function docs() {
  const out = [];
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir)) {
      const p = path.join(dir, name);
      if (fs.statSync(p).isDirectory()) walk(p);
      else if (name.endsWith(".md") && name !== "params.md") out.push(p);
    }
  };
  walk(skill);
  return out;
}

test("params.md matches what the host schema generates (regenerate after a schema change)", () => {
  const now = fs.readFileSync(path.join(skill, "references/steps/params.md"), "utf8");
  assert.equal(now, render(contract), "run: node scripts/remake-params-gen.mjs");
});

test("every params.X named in the skill prose is a field the host takes", () => {
  const bad = [];
  for (const file of docs()) {
    const text = fs.readFileSync(file, "utf8");
    for (const m of text.matchAll(/params\.(?!md\b)([a-z_]+)/g))
      if (!allKeys.has(m[1])) bad.push(`${path.relative(skill, file)}: params.${m[1]}`);
  }
  assert.deepEqual([...new Set(bad)], []);
});

test("where the prose gives a step a parameter, that step takes it", () => {
  const bad = [];
  const pairs = [
    /`?\b([a-z_]+)`? \{params:\{\s*([a-z_]+)/g, // e.g. still {params:{shot: N}}
    /`([a-z_]+)` with `params\.([a-z_]+)`/g, // e.g. `still` with `params.sheet_for`
  ];
  for (const file of docs()) {
    const text = fs.readFileSync(file, "utf8");
    for (const re of pairs)
      for (const m of text.matchAll(re)) {
        const [, op, key] = m;
        if (!byOp[op]) continue;
        if (!byOp[op].includes(key)) bad.push(`${path.relative(skill, file)}: ${op} does not take params.${key}`);
      }
  }
  assert.deepEqual([...new Set(bad)], []);
});
