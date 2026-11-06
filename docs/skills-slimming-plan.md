# Skill 瘦身交接方案（2026-11-02）

接手人从这里开始。审计数据与逐个 Skill 的建议见飞书「插件 Skill 审计：长度、规范与瘦身建议」，本文件是执行方案。

## 目标

1. 本仓 15 个 Skill 的 `SKILL.md` 瘦身，之后这些 Skill 只在本仓迭代，creator-skills 里的同名包不再改。
2. 验收只看三件事：**能跑通、交付了正式报告、过程没有报错或断链**。效果（报告写得好不好）不在本轮看，由各 Skill 负责人之后自己回归。
3. 规范以 `AGENTS.md`、`docs/skills-spec.md` 为准；CI（`scripts/repo-rules.test.mjs`）与 CodeRabbit 已覆盖可机器检查的部分。

## 起点

- `main` 已对齐 creator-skills 冻结基线 `a9514ba301cf52b02d700976e6e94cc11237542d`，每个 Skill 的来源版本记在 `skills.lock.json`。
- 冻结之后的上游改动：账号复盘 0.5.53（TikTok 图文 / 视频分开建基线）已由 #51 合入；trends 的请求目标修复已由 #39 合入；复刻 #938/#944 归视频线。
- 冻结之后的修复一律由作者直接在本仓提 PR，不再从 creator-skills 搬。
- 已发布版本：v1.0.7（`stable` 指向 c5b9937），含 11 个 Skill 与冻结基线同步，不含 #13 的 4 个新 Skill；main 领先 `stable`，4 个新 Skill 瘦身并回归后随下一版发布。发版说明已提示用户重新连接 Kabo。
- 4 个新 Skill（`diagnose-reach-drop`、`recommend-publish-timing`、`plan-platform-monetization`、`verify-platform-rule`）已由 #13 合入；kabo#1817（`official_page_render_page`）已上生产。最后一轮实测四个都产出了正式报告，但三个有执行偏离（见下文「取数管线交给脚本」的证据），瘦身时一并处理。

## 瘦身怎么做

目标：`SKILL.md` 正文约 1 万字符、150 行左右（现在 1.06–2.09 万字符、174–317 行）。上限 21,000 不变。

按这个顺序做，前两步对所有取数类 Skill 通用，先做完再逐个改正文：

1. **交付契约前置。** 出报告的 Skill 在正文开头 15 行内写两三行：校验通过的报告原样交付，不概括、不改数字，最后一行写 `creator_report:`。后文不再分散重复。实测里 DEEP / ACC / VID / IDEA 的最终回复都改写了报告（删证据链接、`0.6147 → 61.5%`），原因是这条规则排在第 60–280 行。
2. **取数管线交给脚本。** 「建 run、调数据工具、fetch / stage、persist、重签、失败处理」在取数类 Skill 正文里占 29–60%，而且各 Skill 高度重复。改成驱动脚本（`drive.py` / `fetch_catalog.py` / `static_host.py`）每一步打印**完整的下一条命令**（包括输入文件路径），正文只写「按脚本打印的下一步执行，不自己拼命令、不用 curl」。实测证据：
   - VID：`persist_envelope.py` 的输入从哪来正文没写清，模型猜了不存在的 `--source`，最后用 `cp` 绕过；另一轮写错 run 目录后改用 curl，整条流程被跳过。
   - ACC / VID：模型手抄签名下载链接抄错字符，下载 400/403。
   - DEEP：为了把结果存成文件，重复调用同一个取数工具。
   - #13 最后一轮：`verify-platform-rule` 用 `urllib` 直接下载签名链接、`plan-platform-monetization` 用 `curl` 下载，都绕过了 `static_host.py fetch`；`recommend-publish-timing` 给最后的 `validate_creator_report.py` 多传了一个参数，报错后直接结束（正文写的命令是对的）。
   共用脚本有多份副本，`scripts/static-host-fetch.test.mjs` 要求共用段逐字一致：改一份就同步改所有副本。
3. **否定式规则审一遍。** 每个 Skill 有 18–51 条 never / do not，多是历次事故累积。validator 已经能拦的从正文删掉；拦不住的合并成正面描述；新例外优先加进校验脚本，正文一行指向。
4. **schema 不整份读。** 一律由驱动打印紧凑 schema（账号复盘已这样做）。
5. **删无人引用的文件**（确认后）：`diagnose-reach-drop/references/traffic-input.md`、`develop-content-ideas/references/selected-idea.schema.json`、`analyze-creator-competitors/references/competitor-discovery-gate-v2.schema.json`。
6. 分支流程、校验细则、错误处理挪到 `references/`，正文只留主流程和跳转（KS3.3）。

逐个 Skill 的方向见飞书审计文档「表二」，负责人已在表里 @。

## 一个 Skill 的完整流程

1. 从 `main` 开分支，只改这一个 Skill（共用脚本副本除外）。
2. `npm ci --ignore-scripts && npm run verify`；`npm run skills:lint` 看该 Skill 0 错误、0 警告。
3. Codex 实机测一次（见下），按验收门槛判：跑通、交付正式报告、无报错断链。
4. PR：标题、描述、提交信息用英文；按 `.github/pull_request_template.md` 写风险等级 R0–R3 和证据。R3 需要负责人明确批准。
5. CI 绿了即可合；合 main 是公开但不是发版。

## 实机测试

验证顺序：先在本地（单测、用保存的 run 状态重跑某一步），再用插件在本机 Codex 实测，Web（pre / 生产）只在最后回归时走飞书「任务交流记录」。

- 用本机 Codex 连生产 `https://kabo.sh/mcp-pub`，插件装在独立的 `CODEX_HOME`（已 OAuth 登录），从待测分支的 checkout 安装；换分支后删掉 `$CODEX_HOME/plugins/cache/kabo-plugin-openai/kabo` 再 `codex plugin add kabo@kabo-plugin-openai`，并 `diff -rq` 确认装上的 `skills/` 与分支一致。
- 每条用例单独目录，`prompt.txt` 只放用户原问：
  `codex exec --skip-git-repo-check -C "$PWD" --approve-for-me -m gpt-5.6-luna -c model_reasoning_effort=medium -c sandbox_workspace_write.network_access=true --json -o last.txt < prompt.txt > events.jsonl`
- 最多 2 条并发；拿到 Kabo `quota_exceeded` / 402 立即停下同平台用例；每条只跑一次，不补发「继续」。
- 搭上游测试环境时只复制需要的 `creator-skill-tests/<dir>`，**不要复制 creator-skills 的 `v3` / `v4`**（体积很大，曾把磁盘写满）。
- 已用过的用例与结果可参考：`DEEP`（Instagram @mkbhd 深度复盘）、`ACC`（Instagram 竞品）、`VID`（YouTube 视频分析）、`SCR`（写脚本）、`IDEA`（选题）、`TTA`（TikTok 账号复盘）。

## 进展（2026-11-02）

14 个 Skill 已瘦身并合入 main（复刻归视频线，未动）。每个 Skill 都在本机 Codex（gpt-5.6-luna medium，连生产 `/mcp-pub`）实测过：跑通、出正式报告、无断链。

| Skill | PR | 正文字符 前 → 后 | 实测 |
|---|---|---|---|
| analyze-tiktok-competitors | #53 | 14,227 → 7,127 | 通过，原样交付 |
| analyze-creator-competitors | #54 | 16,501 → 9,248 | 通过，原样交付 |
| research-tiktok-trends | #55 | 20,579 → 12,862 | 通过，原样交付 |
| research-youtube-trends | #57 | 17,853 → 10,957 | 通过，原样交付 |
| develop-content-ideas | #58 | 19,162 → 10,152 | 通过，原样交付 |
| create-script-and-packaging | #59 | 19,578 → 9,769 | 通过，原样交付 |
| research-instagram-trends | #61 | 20,906 → 约 13,500 | 通过，原样交付 |
| review-creator-account | #62 | 20,127 → 11,396 | 通过（先修了 #56），原样交付 |
| plan-platform-monetization | #63 | 19,953 → 10,743 | 通过，原样交付 |
| verify-platform-rule | #64 | 12,376 → 7,985 | 通过，原样交付 |
| recommend-publish-timing | #65 | 19,982 → 约 12,800 | 第 2 轮通过 |
| diagnose-reach-drop | #66 | 10,553 → 约 7,700 | 第 3 轮通过 |
| analyze-content-video | #67 | 17,999 → 17,263 | 通过（A/B 见 PR） |
| review-creator-account-deep | #68 | 18,101 → 12,629 | 第 2 轮通过 |

共用改动：
- **交接打印下一步**（#53 起，#60 定稿）：`connector_driver.py` 交接时在每条调用下打印要存的文件名与 `fetch` 命令，结尾打印续跑命令；并写明「结果里是下载链接，不要自己下载」。`scripts/shared-copies.test.mjs` 要求各副本逐字一致。
- **`references/data-calls.md`**：保存、过期重签、延迟任务、失败处理的通用规则，各 Skill 一份相同副本，只点名所有 Skill 都声明的工具。
- **最终步打印报告与交付说明**：实测里「流程跑通、报告也生成了，但最后回复被改写成摘要」是最常见的问题（main 上同样存在）。最终步打印 `creator_report:`、报告全文和一句「回复就是这份报告」后，回复都变成「一句话 + 报告原文」。已有驱动的 6 个 Skill 的同样改动在 `yutian/delivery-instruction` 实测中。
- 顺带修的 bug：账号复盘校验把帖文里的域名（如 Ridge.com/MKBHD）误判为泄露（#56）。

经验（后续改 Skill 时参照）：
- 没有驱动脚本、由模型自己发调用的 Skill（视频分析）不要压缩取数规则：压缩后模型两次绕开取证直接作答，已退回原文。把这些规则搬进驱动脚本是下一步。
- 测视频类 Skill 不要用极有名的视频（如 dQw4w9WgXcQ），模型会凭记忆作答，测不出流程。
- 测试 CODEX_HOME 可以开多个并行跑（每个独立的插件 worktree）；临时目录里不要留测试产物，模型会去翻。

遗留与待定：
- 竞品补足到用户要的数量（`yutian/acc-backfill-requested`）已改未合：这轮实测候选已够 6 个、没触发补足，修复本身未验证；同时读调用次数 42 次，远超 20 次的测试规定。11-02 已定折中：先合补足（保证数量），再单独压每个账号的翻页（`REEL_PAGES` / `REEL_PAGES_MAX`），读调用目标 30 次以内。不阻塞主线，排在主线之后做。
- 账号复盘：最终校验失败后同一 run 无法恢复（「report already exists」→「existing report differs」）。
- 模型手抄 `creator_report:` 路径时会抄错（Instagram 热门、平台规则各一次），报告本身原样。
- 视频分析：把取数规则搬进驱动。

## 待办（不属于瘦身本身）

- Web Agent / Desktop 改用本仓 Skill 的方案 creator-skills#886：不等评审，直接推进；第一个开放问题是 Desktop 如何拿到 `/mcp-pub` 的 OAuth token。迁移时要补：账号复盘的「下载报告」导出（上游 #936，插件未搬，因为插件交付的就是本地 Markdown）、深度复盘上游 #923/#924 中 Web 运行器专用的落盘与回执机制（插件未搬）。
- 深度复盘在 Web 上的剩余问题，迁移后在本仓修：Pre 测试（deep 0.3.52 + kas #297 单包媒体白名单）提交了 30 个媒体任务、服务端完成 34 个，但模型只取回 3 个 artifact，`scripts/record_watch_outcomes.py` 两次以「N of M planned videos are still waiting on a job」退出，模型没有继续轮询、落盘就以 partial 收尾。待查：终态任务为何没落盘、模型为何不等。deep 的读调用约 67 次，回归规则需单独定。kas #297 已合 kas main 未部署生产；生产 deep 仍是 0.3.46。
- 竞品分析（analyze-creator-competitors）已知问题，迁移后在本仓修：生产回归里用户要 5 个账号，报告只纳入 3 个（"Only 3 of the requested 5 accounts had sufficient verifiable evidence"）。根因：`drive.py` 只在剩余账号少于 3 个时才回补候选，没有补到 `requested_competitor_count`。业务读调用 21 次，略超测试规定的 20。修法：回补到用户要的数量，并让读调用规划在 20 次内完成 5 个账号。
- 11-02 06:20 的 kabo 生产部署让所有已有的 `/mcp-pub` OAuth 会话失效（`invalid_grant: session not found`），重新登录即可；根因待部署方确认。测试时遇到同样报错就重新 `codex mcp login kabo`。
- #27（新增 3 个 Skill）暂不处理。
- 插件上架（目录审核、市场上传）暂缓；正式发版是 version bump + GitHub Release + `stable` fast-forward，瘦身与回归完成后再做。
