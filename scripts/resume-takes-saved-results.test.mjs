// Between handoff and resume only "call -> fill the result's number into the resume command" remains
//   (docs/skills-spec.md KS8): the handoff gives each call a numbered slot,
// and resume (--placed --id NN=<number>) itself fetches that download's bytes from Kabo by number, validates
//   them against the sha256 and length in the response headers, and then places them
// (kabo ADR-0084, "2026-11-04"). Having the model copy results by hand was the top failure of plugin handoffs
//   (patches corrupted, signed links copied incompletely, fields rewritten),
// so saving to a file remains only as a fallback: a result without a download link is saved into the
//   host-results/ file named by the slot, and resume still does fetch / stage.
// Here, for the copy of each driving Skill's connector_driver.py (together with its own static_host.py), the
//   following is run in-process: fetch by number
// (fake HTTPS, no network), the save-to-file fallback (download and inline stage), the hint when a slot has
//   neither a number nor a file, and no repeated fetch for the same slot.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const RESULT_ID = "Neutral_Result-Id01234";
const SIGNED = `https://storage.googleapis.com/kabo-media/_temporary/research-export/v1/${RESULT_ID}.json?X-Goog-Signature=SIGNATURE`;
const BY_ID = `https://kabo.sh/v1/research-downloads/${RESULT_ID}`;

// One process per scenario: import that Skill's connector_driver / static_host, replace urllib's HTTPS
//   send/receive,
// first let fetch_round hand off (print and SystemExit 0), then, per scenario, save the result into the named
//   file and resume with --placed.
const HARNESS = String.raw`
import argparse, base64, contextlib, http.client, io, json, os, sys, urllib.request, urllib.response

scripts, spec_file = sys.argv[1], sys.argv[2]
spec = json.load(open(spec_file))
sys.path.insert(0, scripts)
requests = []

class FakeHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        requests.append(req.full_url)
        body = base64.b64decode(spec["download"])
        import hashlib
        head = ("Content-Type: application/json\r\nContent-Length: %d\r\nX-Content-SHA256: %s\r\n\r\n"
                % (len(body), hashlib.sha256(body).hexdigest())).encode()
        headers = http.client.parse_headers(io.BytesIO(head))
        response = urllib.response.addinfourl(io.BytesIO(body), headers, req.full_url, 200)
        response.msg = "fake"
        return response

import static_host
static_host.build_opener = lambda: urllib.request.build_opener(static_host.NoRedirect(), FakeHTTPS())
run = static_host.init(spec["workspace"])
os.environ["KABO_STATIC_RUN_DIR"] = str(run)
os.chdir(run)
import connector_driver as cd

def place():
    print("PLACED", json.dumps(sorted(p.name for p in (run / "snapshot/.host-evidence").glob("*.meta"))))

def step(placed):
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out):
        try:
            cd.fetch_round(spec["calls"], argparse.Namespace(placed=placed), place)
        except SystemExit as stop:
            code = stop.code or 0
        except cd.StageError as error:
            print("STOPPED", error)
            code = 2
    return {"code": code, "out": out.getvalue()}

report = {"run": str(run), "handed": step(bool(spec.get("placed_first")))}
saved = [line.split("has no download url: ", 1)[1].rstrip(")") for line in report["handed"]["out"].splitlines()
         if line.startswith("  result ")]
report["saved"] = saved
if spec.get("id"):
    cd.RESULT_IDS["01"] = spec["id"]
elif spec["result"] is not None:
    for name in saved:
        with open(name, "w") as stream:
            json.dump(spec["result"], stream)
report["resumed"] = step(True)
report["again"] = step(True) if spec.get("again") else None
report["requests"] = requests
print(json.dumps(report))
`;

const envelope = (connector_id, operation, n) => ({
  connector_id, operation, status: "completed", summary: `Found ${n} rows`, limitations: [],
  evidence_ref: `ev-${operation}-${n}`, raw_sha256: "a".repeat(64), request_id: `req-${operation}-${n}`,
  data: { rows: Array.from({ length: n }, (_, i) => ({ id: `${operation}-${i}`, caption: `Neutral row ${i}` })) },
});
const composite = (tool, calls) => ({
  schema_version: "kabo-composite-fetch.v1", tool, status: "completed",
  calls: calls.map(([callTool, connector, operation, n], index) => ({
    tool: callTool, group: `g-${index}`, parameters: { n }, attempts: 1, result: envelope(connector, operation, n) })),
  summary: {}, coverage: { provider_calls: calls.length }, limitations: [],
});
const history = (platformCalls) => ({ composite: "collect_account_history", calls: platformCalls,
  arguments: { platform: "instagram", accounts: [{ handle: "neutral.creator" }], delivery: "download" } });
const igHistory = history([["instagram_resolve_profile", "instagram-discovery", "resolve_profile", 1],
  ["instagram_list_reels", "instagram-discovery", "list_reels", 3]]);
const ttCandidates = { composite: "collect_tiktok_video_candidates",
  calls: [["tiktok_discovery_search_videos", "tiktok-discovery", "search_videos", 2], ["tiktok_discovery_search_videos", "tiktok-discovery", "search_videos", 1]],
  arguments: { intents: [{ keyword: "bead craft ideas", publish_time: 30 }], sorts: [0, 1], count: 30, delivery: "download" } };

// The kind of call each driving Skill hands over: a composite tool, or a connector request handed off as a
//   single named data tool.
const DRIVERS = {
  "analyze-creator-competitors": igHistory,
  "analyze-tiktok-competitors": ttCandidates,
  "diagnose-reach-drop": igHistory,
  "research-instagram-trends": { single: ["instagram-baseline-proxy", "search_reels", "instagram_baseline_search_reels"] },
  "research-tiktok-trends": ttCandidates,
  "research-youtube-trends": { single: ["youtube-public", "get_video", "youtube_get_video"] },
  "review-creator-account": igHistory,
  "verify-platform-rule": { composite: "render_official_pages",
    calls: [["official_page_render_page", "official-page-render", "render_page", 1]],
    arguments: { pages: [{ url: "https://help.example.com/rules" }], delivery: "download" } },
};

function scenario(driver, { download, saved = true }) {
  let calls; let full;
  if (driver.composite) {
    calls = [{ tool: driver.composite, arguments: driver.arguments }];
    full = composite(driver.composite, driver.calls);
  } else {
    const [connector, operation] = driver.single;
    calls = [{ tool: "data_connector_run", arguments: { connector_id: connector, operation, params: { n: 2 } } }];
    full = envelope(connector, operation, 2);
  }
  const bytes = Buffer.from(JSON.stringify(full));
  let result = full;
  if (download) {
    const { calls: _calls, data: _data, ...rest } = full;
    result = { ...rest, download: { status: "ready", kind: "envelope", url: SIGNED, expires_at: "2099-01-01T00:10:00Z",
      sha256: sha256(bytes), bytes: bytes.length, content_type: "application/json" } };
  }
  return { calls, result: saved ? { content: [{ type: "text", text: JSON.stringify(result) }], structuredContent: result } : null,
    download: bytes.toString("base64"), again: true };
}

async function drive(t, skill, spec) {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-resume-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const file = path.join(temp, "spec.json");
  await writeFile(file, JSON.stringify({ ...spec, workspace: temp }));
  const output = execFileSync("python3", ["-I", "-B", "-c", HARNESS, path.join(root, "skills", skill, "scripts"), file],
    { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  return JSON.parse(output.trim().split("\n").at(-1));
}

for (const [skill, driver] of Object.entries(DRIVERS)) {
  const tool = driver.composite ?? driver.single[2];

  test(`${skill}: handoff gives each call one slot and one resume command with --id; resume fetches by id itself (fake HTTPS), validates and places, and a rerun does not fetch again`, async (t) => {
    const report = await drive(t, skill, { ...scenario(driver, { download: true }), id: RESULT_ID });
    const handed = report.handed.out;
    assert.equal(report.handed.code, 0, handed);
    assert.deepEqual(report.saved, [path.join(report.run, "host-results", `01-${tool}.json`)]);
    assert.match(handed, /^call: /m);
    assert.match(handed, /^  result 01 {2}\(fallback file, only if this result has no download url: /m);
    assert.match(handed, /Do not save the results/);
    assert.match(handed, /Never download anything yourself; call get_research_data_download only when the resume says an id expired/);
    assert.doesNotMatch(handed, /static_host\.py/, "the model runs no fetch or stage command itself");
    const resume = handed.split("\n").filter((line) => line.startsWith("Then run this one command"));
    assert.equal(resume.length, 1, handed);
    assert.ok(resume[0].includes(`cd '${report.run}' && python3 `), resume[0]);
    assert.doesNotMatch(resume[0], /KABO_STATIC_RUN_DIR/, "the run is found from the working directory");
    assert.ok(resume[0].endsWith(" --placed --id 01=<id>"), resume[0]);
    assert.equal(report.resumed.code, 0, report.resumed.out);
    assert.match(report.resumed.out, new RegExp(`result 01: fetched by id ${tool}`));
    assert.match(report.resumed.out, /^PLACED \[.+\]$/m);
    assert.deepEqual(report.requests, [BY_ID], "one download by id, made by the resume");
    // Run the same command again: this round is already placed, so nothing is downloaded again.
    assert.equal(report.again.code, 0, report.again.out);
    assert.doesNotMatch(report.again.out, /fetched|staged|PLACED/);
  });

  test(`${skill}: when no id was handed over but a result with a download link was saved, resume downloads as before (fake HTTPS), validates and places`, async (t) => {
    const report = await drive(t, skill, scenario(driver, { download: true }));
    assert.equal(report.resumed.code, 0, report.resumed.out);
    assert.match(report.resumed.out, new RegExp(`result 01: fetched ${tool}`));
    assert.match(report.resumed.out, /^PLACED \[.+\]$/m);
    assert.deepEqual(report.requests, [SIGNED]);
  });

  test(`${skill}: when the result has no ready download, resume falls back to stage; ${driver.composite ? "the full composite result saved by the model is accepted as is" : "the inline envelope is accepted as is"}`, async (t) => {
    const report = await drive(t, skill, scenario(driver, { download: false }));
    assert.equal(report.resumed.code, 0, report.resumed.out);
    assert.match(report.resumed.out, new RegExp(`result 01: staged ${tool}`));
    const placed = JSON.parse(/^PLACED (.+)$/m.exec(report.resumed.out)[1]);
    assert.equal(placed.length, driver.composite ? driver.calls.length + 1 : 1, report.resumed.out);
    assert.deepEqual(report.requests, []);
  });

  test(`${skill}: running with --placed before this round has handed off still hands off normally without reporting a missing result; resume by id still places`, async (t) => {
    const report = await drive(t, skill, { ...scenario(driver, { download: true }), id: RESULT_ID, placed_first: true, again: false });
    assert.equal(report.handed.code, 0, report.handed.out);
    assert.match(report.handed.out, /--placed, but this round was not handed over yet; handing it over now/);
    assert.match(report.handed.out, /^  result 01 /m);
    assert.equal(report.resumed.code, 0, report.resumed.out);
    assert.match(report.resumed.out, /^PLACED \[.+\]$/m);
  });

  test(`${skill}: when resuming a slot with neither id nor file, one sentence names the slot and the --id to supply, and nothing is placed`, async (t) => {
    const report = await drive(t, skill, { ...scenario(driver, { download: false, saved: false }), again: false });
    assert.equal(report.resumed.code, 2, report.resumed.out);
    assert.ok(report.resumed.out.includes(
      `STOPPED no result for slot 01 (${tool}). Run the resume command again with --id 01=<id>`), report.resumed.out);
    assert.doesNotMatch(report.resumed.out, /PLACED/);
  });
}

// The same number given to two slots: the later one would be treated as "already held" and skipped, leaving
//   one result short, so resume rejects it before fetching and downloads nothing.
const DUPLICATE = String.raw`
import json, os, sys
from pathlib import Path
scripts, workspace, given = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, scripts)
import static_host
run = static_host.init(workspace)
os.environ["KABO_STATIC_RUN_DIR"] = str(run)
os.chdir(run)
import connector_driver as cd
static_host.download_result = lambda result_id: (_ for _ in ()).throw(AssertionError("downloaded"))
cd.RESULT_IDS.update({"01": given, "02": given})
try:
    cd.take_saved_results([("t", run / "host-results/01-t.json"), ("t", run / "host-results/02-t.json")])
    print("TAKEN")
except cd.StageError as error:
    print("STOPPED", error)
`;
for (const skill of Object.keys(DRIVERS)) {
  test(`${skill}: when two slots hand over the same id, resume names both slots and downloads nothing`, async (t) => {
    const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-resume-dup-"));
    t.after(() => rm(temp, { recursive: true, force: true }));
    const out = execFileSync("python3", ["-I", "-B", "-c", DUPLICATE, path.join(root, "skills", skill, "scripts"), temp,
      `${RESULT_ID}.json`], { encoding: "utf8" });
    assert.match(out, /^STOPPED slots 01 and 02 were given the same result id/m, out);
  });
}

// research-instagram-trends' slimmed-down completion handoff prints itself (not via a call: line), likewise
//   naming absolute paths and recording the files to fetch, and resume fetches as usual.
test("research-instagram-trends: condensed completion handoff names the absolute path and one resume command; when the file is missing, resume names it", async (t) => {
  const temp = await mkdtemp(path.join(os.tmpdir(), "kabo-resume-lean-"));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const script = String.raw`
import argparse, contextlib, io, json, os, sys
sys.path.insert(0, sys.argv[1])
import static_host
run = static_host.init(sys.argv[2])
os.environ["KABO_STATIC_RUN_DIR"] = str(run)
os.chdir(run)
import drive, connector_driver as cd
sent = {"items": [{"url": "https://www.instagram.com/reel/NEUTRAL1/"}], "window": {"since": "2026-10-01T00:00:00Z"}}
calls = [{"tool": "enrich_instagram_shortlist", "arguments": sent}]
def step(placed):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            cd.fetch_round(calls, argparse.Namespace(placed=placed), lambda: print("PLACED"),
                           hand_over_calls=lambda: drive.hand_over_lean(sent))
        except SystemExit:
            pass
        except cd.StageError as error:
            print("STOPPED", error)
    return out.getvalue()
print(json.dumps({"run": str(run), "handed": step(False), "resumed": step(True)}))
`;
  const report = JSON.parse(execFileSync("python3", ["-I", "-B", "-c", script,
    path.join(root, "skills", "research-instagram-trends", "scripts"), temp], { encoding: "utf8" }).trim().split("\n").at(-1));
  const file = path.join(report.run, "host-results", "01-enrich_instagram_shortlist.json");
  assert.ok(report.handed.includes(`  result 01  (fallback file, only if this result has no download url: ${file})`), report.handed);
  assert.match(report.handed, /call get_research_data_download only when the resume says an id expired/);
  assert.doesNotMatch(report.handed, /static_host\.py/);
  assert.match(report.handed, /^Then run this one command right away.* --placed --id 01=<id>$/m);
  assert.ok(report.resumed.includes("STOPPED no result for slot 01 (enrich_instagram_shortlist)"), report.resumed);
});
