// 交付检查只保护已渲染内容，不把摘要当全文，也不把固定标签翻译当正文改写。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("报告译标签后可交付；删正文、证据、指标或成功标准均不能冒充完整报告", () => {
  const scripts = fileURLToPath(new URL("../skills/review-creator-account/scripts", import.meta.url));
  const result = spawnSync("python3", ["-c", String.raw`
import json, sys, tempfile, subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from validate_delivery import delivery_issues
report={"schema_version":"account-review-report.v3",
        "headline":"窗口没有对齐，先验证原因", "diagnosis":"当前累计量不能证明内容强弱。",
        "what_works":[{"pattern":"标题提出一个具体问题", "explanation":"这里只观察标题，不据此确认销量原因。"}],
        "recommendations":{"test":[{"action":"保持相同观察窗口与归因周期。", "success_metric":"记录每一组的询盘和付费订单。"}]}}
body="# 窗口没有对齐，先验证原因\n\n当前累计量不能证明内容强弱。\n\n## Public content observations\n\n### 标题提出一个具体问题\n\n这里只观察标题，不据此确认销量原因。\n\n- [原始标题](https://example.com/post) (200 views; cumulative snapshot, not equal windows)\n\n## What to do next\n\n保持相同观察窗口与归因周期。 (Success criterion: 记录每一组的询盘和付费订单。)\n"
assert not delivery_issues(body, report, body)
localized=body.replace("Public content observations","公开内容观察").replace("What to do next","下一步").replace("views","播放").replace("Success criterion:","成功标准：").replace("cumulative snapshot, not equal windows","累计快照，不是等长窗口")
assert not delivery_issues(body,report,localized)
for incomplete in ["# 窗口没有对齐，先验证原因\n\n当前累计量不能证明内容强弱。", body.replace(report["what_works"][0]["explanation"],""),body.replace(" (Success criterion: 记录每一组的询盘和付费订单。)",""),body.replace("https://example.com/post","https://example.com/other"),body.replace("200 views","20 views")]:
    assert delivery_issues(body,report,incomplete), incomplete
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);md=root/'ACCOUNT_REVIEW.md';js=root/'account_review.json'
    md.write_text(body);js.write_text(json.dumps(report,ensure_ascii=False));before=(md.read_bytes(),js.read_bytes())
    cmd=[sys.executable,str(Path(sys.argv[1])/'validate_delivery.py'),'--report-dir',temp,'--reply-file','-']
    good=subprocess.run(cmd,input=localized,text=True,capture_output=True)
    assert good.returncode == 0 and json.loads(good.stdout)['status']=='ready_to_send',good.stdout
    bad=subprocess.run(cmd,input=report['diagnosis'],text=True,capture_output=True)
    assert bad.returncode == 1 and json.loads(bad.stdout)['status']=='needs_revision',bad.stdout
    assert before == (md.read_bytes(),js.read_bytes()), 'checking replies must not edit sources'
`, scripts], { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  assert.equal(result.status, 0, result.stdout + result.stderr);
});
