# 唯一插件的提交准备

本地安装、集成验证与最终提交使用同一个根目录插件。构建只读完整 commit，全部文件
原样入包；`--submission` 检查同一内容，不生成裁剪后的第二种版本。

## 已实现的代码条件

- portable manifest、品牌资产与公开目录 MCP；生产 scopes 及 UserInfo 仍须按下文实测。
- 十一个固定 Skills、源 commit/版本/文件哈希、逐项数据工具映射和报告单次交付说明。
  其中 `remake-viral-video` 依赖的三个复刻工具已固定，但固定来源仍是 kabo#1777 分支 commit；该 PR 部署生产并改钉到合入 commit 前不具备提交条件。
- 原生宿主 OAuth，无 lifecycle hooks；脚本执行需要实际宿主提供相应运行环境。
- 固定工具/标准来源、静态 Skills 记录与证据隔离回归、确定性 ZIP 和逐文件摘要。
- `contracts/directory-mcp/data-tool-bindings.json` 固定提供方的全部基础依赖及
  connector/operation → 工具对应关系；仅检查目标工具存在不能代替逐项匹配。
- 有版本绑定的生产证据门，拒绝缺项、失败、未执行、篡改、越界文件和凭据附件。

## OAuth 连接设置

MCP URL 为 `https://kabo.sh/mcp-pub`，OAuth 通过公开 metadata 发现授权端点、
DCR、PKCE S256 与 resource。`host-auth.json` 是本包的公开认证契约，**不是**官方后台
自动导入文件，也不能假设连接面板提供高级 OAuth 编辑器。
其目标 scopes 为 `openid email offline_access data video`；生产部署前必须确认
`/mcp-pub` 的资源策略已允许 `email`，仅修改此交接文件不会改变服务端授权结果。

当前 portable 1.0.0 MCP schema 不接受 server extensions，故本包保留可直接安装的
`mcp.json`，依赖标准发现。先在官方草稿验证 OAuth/DCR、scope 和 UserInfo；若必须
override，官方入口是 `mcp.json` 中 server 的 `extensions.com.openai.auth`，须先解决
portable schema 与实际宿主兼容性，再更新同一包。不得在构建时删字段或生成一份不同的
“审核包”，也不能把 `host-auth.json` 已存在当作官方配置成功。

OpenAI 工作区域名限制需要 `openid`、`email` 与 UserInfo 的 `email`、
`email_verified: true`。生产资源发现、实际授权、consent 和 UserInfo 必须一致；不能
伪造已验证标志，亦不能为了补 scope 把所有全站权限都请求过来。已有连接若未授予
新增 scope，应通过宿主重新授权；原有 `data` / `video` 工具权限不因该身份能力而扩大。
服务端仍须强制认证、audience 与 scope，未授权请求返回 401。

[官方认证配置](https://developers.openai.com/plugins/build/plugins#configure-mcp-authentication) ·
[工作区域名限制](https://developers.openai.com/plugins/build/auth#support-workspace-domain-restrictions)

## 域名验证与宿主范围

门户生成挑战后，把精确 token 作为纯文本部署到其显示的
`https://<challenge-base-host>/.well-known/openai-apps-challenge`，再由门户验证。
未配置时返回 404 不等于代码缺少路由；必须检查生产配置。不得用占位 token 或其他
插件的 token 冒充验证成功，不得覆盖正在使用的挑战。代码 PR 不部署配置或完成门户验证。

十一个 Skills 需要 Python 3、可写工作区以及完整结果导出或证据下载（`remake-viral-video` 只走下载）；本地视频另需
ffmpeg/ffprobe。先证明目标宿主能完成完整流程，再声明支持；Codex 安装成功不能替代
ChatGPT 网页端、移动端验收。无法提供所需执行能力时，在调用消耗额度的工具前停止
对应工作流并说明缺失条件，不转发 Kabo 网页端 agent。若只能本机执行，按
[Desktop-only 指南](https://developers.openai.com/plugins/deploy/desktop-only)与 OpenAI
确认远程 MCP + Skills 的适用路径，不直接套用仅针对 skills-only 或本地 stdio MCP 的设置。

## 仍需验收的事实

| 项目 | 完成条件 |
| --- | --- |
| 提供方生产服务 | API 的公开数据工具可用，实际 tools/list 与固定契约一致；旧 2.0.0 / 3.0.0 连的 `/mcp-directory` 已删除，不再要求兼容 |
| 宿主联调 | 声明支持的 ChatGPT 环境及 Codex 实际安装、授权、refresh、工具执行及完整报告交付；Claude Code/Cursor 单独记录，不替代 OpenAI 宿主验收 |
| 执行独立性 | 宿主使用固定包内容、取证、脚本与报告轨迹；对网页端 agent 的任务与报告请求为零，网页端 agent 不可用时仍能完成 |
| 生产入口 | Support/Legal/challenge/公开 MCP/OAuth/账号删除验收通过 |
| 业务与隔离 | 5+3 案例、两账号 run/artifact 隔离、删除完整性、旧 `/mcp` 回归（仍在线）；已删除的 `/mcp-directory` 返回 404 |
| 审核资料 | Reviewer、稳定频道与视频 URL、Demo；凭据只填官方后台 |
| 官方审核 | 上传最终包与连接生产 MCP、扫描、审核；Publish 另行确认 |

`npm run check:submission` 缺证据时明确失败。收据中的 `submissionReady` 是本项目
交付门结论，不代表 OpenAI 接受或已经发布。[验收流程](acceptance.md) 绑定 commit、
ZIP 和工具契约摘要；人仍需核实附件叙述。不得修改收据冒充实测成功。

Kabo 网页端 agent 的部署和可用性不是此插件的前置条件。官方对 Skills/MCP 的
支持不等于每个宿主都提供本包所需 Python、文件，以及脚本访问下载交付链接的网络（或回退所需的完整
响应导出）能力；不能通过远程研究回退隐藏这个限制。新增公开工具仍需官方扫描，固定 Skills 更新随插件提交审核。

[官方打包](https://developers.openai.com/plugins/build/plugins) ·
[工具规范](https://developers.openai.com/plugins/plugin-guidelines) ·
[提交](https://developers.openai.com/plugins/deploy/submission)
