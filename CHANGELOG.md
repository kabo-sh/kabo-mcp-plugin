# 变更说明

版本号以 `plugin.json` 为准；`.claude-plugin/plugin.json`、`package.json` 与 `package-lock.json` 的根包版本与之同步。

## 1.0.3（2026-10-28；GitHub Release）

- 新增第十一个 Skill `remake-viral-video`：把 60 秒以内的爆款纯口播视频复刻成创作者本人出镜的成片（MP4）。
  移植自网页端 creator-remake-web 0.1.23（creator-skills `2206478d`）的写稿关口（读音校对、四个改写位、
  画面文字与继承台账、来源规则、四份文档），只做纯口播；录屏/画中画、实物、旁白与网页端专有机制未移植。
  依赖 `/mcp-pub` 新增的 `start_remake_video`、`get_remake_video`、`render_remake_video`（kabo#1777），
  三个工具已随 kabo#1777 重新固定进 `contracts/directory-mcp/`（62 个工具，另含 kabo main 上新增的两个 TikTok 话题工具与十一个个人资产工具），
  `runtime-contract.json` 的 `requiredTools` 已补上。固定来源是 kabo#1777 的合入 commit `005fcbc6d`。
  第一次提出复刻时先用两三句话说明支持与会被拒的参考视频（同网页端 0.1.26）。
  生产验收：Codex 0.164 经 OAuth 安装本包、连 `kabo.sh/mcp-pub` 跑通一条纯口播（job `ed76cc05`，runner r56，
  约 19 分钟、$0.53，成片抽帧检查通过）；Claude Code 与其他宿主未实测。
  生产 runner 换成 r58q（开头快速粗筛）后回归：正常口播在开头粗筛被放行并交付（job `b04218cd`）；两人同框的参考视频
  在开头粗筛 30 秒内以 `out_of_scope` 被拒、未做付费生成（job `0d1575bb`）。交付结果不含终审结论，
  技能不再声称成片「通过终审」，改为建议用户发布前完整看一遍。
- 视频分析（#12）：来源本身写成「27B / 27 billion」这类带量级词的数字，不再被当作编造而中断诊断。
- 个人资产工具（#11）：授权 workspace 权限后可读已绑定账号、创作者画像、社媒连接状态、脚本与视频库，
  保存或更新脚本，绑定公开账号；`review-creator-account` 与 `create-script-and-packaging` 按需使用。

## 1.0.2（2026-10-27；GitHub Release）

- 视频分析：服务端抽帧少于采样计划（如请求 120 帧、返回 119 帧）时不再中断报告生成，`data_note` 写明
  「119 extracted frames of 120 requested」；帧记录多于计划仍拒绝。
- 视频分析与深度复盘的抽帧请求封顶 60 帧（此前默认顶到服务端上限 120）：`static_host.py job-call` 按各 Skill 的
  `FRAME_CAPS` 补上 `max_frames`，显式超过上限的值被拒绝；开头三秒密度不变，只摊薄正文采样。
  未在真实宿主或生产环境实测，提速幅度未计时。
- README 补充 MCP 与 Skills 的安装、更新说明。

## 1.0.1（2026-10-27；GitHub Release）

- 支持用 skills CLI 单独安装十个 Skills（`npx skills add kabo-sh/kabo-mcp-plugin#stable`）：README 说明安装、
  另行添加 `/mcp-pub` 连接、版本与更新方式；`stable` 分支只指向已发布 tag，作为 `npx skills update` 的更新渠道。
  每个 SKILL.md 新增 `license: MIT`，许可随单独安装的 Skill 分发，包检查要求与 `plugin.json` 一致。
  已验证安装完整与 Codex 0.164 识别；登录与端到端运行待验收。
- 仓库协作约定（AGENTS.md）改为英文，提交说明与 PR 使用英文。

## 1.0.0（2026-10-23 首发；2026-10-27 随公开仓库重新发布）

- 2026-10-27 重新发布：仓库转为公开，开发历史不随公开仓库发布；ZIP 从新提交重新构建，旧 ZIP 作废。
- 插件采用 MIT 许可：新增根目录 `LICENSE` 并随 ZIP 打包，`plugin.json`、`.claude-plugin/plugin.json` 与 `package.json` 声明 `MIT`；
  `.claude-plugin/plugin.json` 显式声明隐私政策链接，`claude plugin validate --profile directory` 不再报目录提交问题。
  许可只覆盖本仓内容，kabo.sh 服务仍受其服务条款约束。
- 公开仓库前的清理：删除 1.x/2.x 历史迁移记录，文档与代码注释不再引用非公开仓库的 issue、PR 与设计文档，
  README 去掉私有仓读权限的安装要求。
- 对外发布版本统一为 `1.0.0`，替代此前开发阶段的包版本编号；不是回退到旧代码。
- 保留最新主分支的十个固定 Skills、`/mcp-pub` 连接、完整证据下载、宿主适配与打包修复；
  deep 只使用本对话中已完成的普通账号复盘校验输出。
- 同步 portable / Claude Code 清单、npm 根包及锁文件、解包测试、发布文案和安装迁移说明；构建产物为 `kabo-1.0.0.zip`。
- 统一英文体验：深度复盘默认英文，目录摘要与评论证据的固定说明改为英文，修复报告单复数；README 提供英文安装与排错说明，保留显式中文输出及来源原文。
- `1.0.0` 的数值低于此前 `3.x`，旧安装需刷新市场并确认实际加载版本；不假设宿主会自动降号更新。
- 来源 Skill 业务版本、依赖与 schema 版本独立维护。
- GitHub Release 发布不改变生产验收或市场审核状态，仍需绑定本次 commit 与 ZIP 重新验收。

## 旧编号（3.x 及更早，开发阶段）

以下只保留升级时需要知道的事实，不作为当前发布版本。

- 3.1.1（2026-10-22）：读帧改走 `delivery: "download"` 下载交付，脚本把图片落到运行目录，不再依赖宿主
  会话目录；十个 Skill 要求子 agent 在前台执行，避免 `claude -p` 退出时丢失报告。从 3.0.1 及以后更新不需要重新授权。
- 3.1.0（2026-10-22）：新增 Claude Code 市场清单 `.claude-plugin/marketplace.json`（插件 ID `kabo@kabo-mcp-plugin`），
  Codex 市场名仍是 `kabo-plugin-openai`；图标改为 K Fold 圆角图标；十个 Skill 按 `docs/skills-spec.md` 改造；
  数据工具默认走 10 分钟有效的 GCS 签名链接下载，`static_host.py fetch` 核对大小与 sha256 后落盘。
  `/mcp-directory` 已从服务端删除，从 3.0.0 及更早版本更新须为 `/mcp-pub` 重新授权。
- 3.0.1：连接与 OAuth resource 统一迁到 `/mcp-pub`，从旧版更新后需要为新地址重新授权。
- 3.0.0：改为十个固定 Skills 随包分发、在宿主执行；动态 Skill 下载、签名包缓存与 lifecycle hooks 退出。
