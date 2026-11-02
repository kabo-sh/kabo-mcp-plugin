# Skill 瘦身交接方案（2026-11-02）

接手人从这里开始。审计数据与逐个 Skill 的建议见飞书「插件 Skill 审计：长度、规范与瘦身建议」，本文件是执行方案。

## 目标

1. 本仓 15 个 Skill 的 `SKILL.md` 瘦身，之后这些 Skill 只在本仓迭代，creator-skills 里的同名包不再改。
2. 验收只看三件事：**能跑通、交付了正式报告、过程没有报错或断链**。效果（报告写得好不好）不在本轮看，由各 Skill 负责人之后自己回归。
3. 规范以 `AGENTS.md`、`docs/skills-spec.md` 为准；CI（`scripts/repo-rules.test.mjs`）与 CodeRabbit 已覆盖可机器检查的部分。

## 起点

- `main` 已对齐 creator-skills 冻结基线 `a9514ba301cf52b02d700976e6e94cc11237542d`，每个 Skill 的来源版本记在 `skills.lock.json`。
- 冻结之后的上游改动：账号复盘 0.5.53（TikTok 图文 / 视频分开建基线）在 #51；trends 的请求目标修复已由 #39 合入；复刻 #938/#944 归视频线。
- 冻结之后的修复一律由作者直接在本仓提 PR，不再从 creator-skills 搬。
- 4 个新 Skill（`diagnose-reach-drop`、`recommend-publish-timing`、`plan-platform-monetization`、`verify-platform-rule`）在 #13，等 kabo#1817（`official_page_render_page`）上生产后实测 `verify-platform-rule` 再合；在此之前瘦身先做其余 11 个。

## 瘦身怎么做

目标：`SKILL.md` 正文约 1 万字符、150 行左右（现在 1.06–2.09 万字符、174–317 行）。上限 21,000 不变。

按这个顺序做，前两步对所有取数类 Skill 通用，先做完再逐个改正文：

1. **交付契约前置。** 出报告的 Skill 在正文开头 15 行内写两三行：校验通过的报告原样交付，不概括、不改数字，最后一行写 `creator_report:`。后文不再分散重复。实测里 DEEP / ACC / VID / IDEA 的最终回复都改写了报告（删证据链接、`0.6147 → 61.5%`），原因是这条规则排在第 60–280 行。
2. **取数管线交给脚本。** 「建 run、调数据工具、fetch / stage、persist、重签、失败处理」在取数类 Skill 正文里占 29–60%，而且各 Skill 高度重复。改成驱动脚本（`drive.py` / `fetch_catalog.py` / `static_host.py`）每一步打印**完整的下一条命令**（包括输入文件路径），正文只写「按脚本打印的下一步执行，不自己拼命令、不用 curl」。实测证据：
   - VID：`persist_envelope.py` 的输入从哪来正文没写清，模型猜了不存在的 `--source`，最后用 `cp` 绕过；另一轮写错 run 目录后改用 curl，整条流程被跳过。
   - ACC / VID：模型手抄签名下载链接抄错字符，下载 400/403。
   - DEEP：为了把结果存成文件，重复调用同一个取数工具。
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

- 用本机 Codex 连生产 `https://kabo.sh/mcp-pub`，插件装在独立的 `CODEX_HOME`（已 OAuth 登录），从待测分支的 checkout 安装；换分支后删掉 `$CODEX_HOME/plugins/cache/kabo-plugin-openai/kabo` 再 `codex plugin add kabo@kabo-plugin-openai`，并 `diff -rq` 确认装上的 `skills/` 与分支一致。
- 每条用例单独目录，`prompt.txt` 只放用户原问：
  `codex exec --skip-git-repo-check -C "$PWD" --approve-for-me -m gpt-5.6-luna -c model_reasoning_effort=medium -c sandbox_workspace_write.network_access=true --json -o last.txt < prompt.txt > events.jsonl`
- 最多 2 条并发；拿到 Kabo `quota_exceeded` / 402 立即停下同平台用例；每条只跑一次，不补发「继续」。
- 搭上游测试环境时只复制需要的 `creator-skill-tests/<dir>`，**不要复制 creator-skills 的 `v3` / `v4`**（体积很大，曾把磁盘写满）。
- 已用过的用例与结果可参考：`DEEP`（Instagram @mkbhd 深度复盘）、`ACC`（Instagram 竞品）、`VID`（YouTube 视频分析）、`SCR`（写脚本）、`IDEA`（选题）、`TTA`（TikTok 账号复盘）。

## 待办（不属于瘦身本身）

- kabo#1817 合入上生产（kabo main 目前因他人改动的 i18n 检查失败而无法部署）→ 实测 `verify-platform-rule` → 合 #13。
- #51（账号复盘 0.5.53）实测通过后合入。
- Web Agent / Desktop 改用本仓 Skill 的方案 creator-skills#886：不等评审，直接推进；第一个开放问题是 Desktop 如何拿到 `/mcp-pub` 的 OAuth token。迁移时要补：账号复盘的「下载报告」导出（上游 #936，插件未搬，因为插件交付的就是本地 Markdown）、深度复盘上游 #923/#924 中 Web 运行器专用的落盘与回执机制（插件未搬）。
- #27（新增 3 个 Skill）暂不处理。
- 插件上架（目录审核、市场上传）暂缓；正式发版是 version bump + GitHub Release + `stable` fast-forward，瘦身与回归完成后再做。
