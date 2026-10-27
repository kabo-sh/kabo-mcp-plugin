# Kabo 插件仓库

- 协作说明、代码注释、提交与 PR 使用中文；插件元数据与用户可见内容使用英文。
- 仓库根目录就是插件根目录。只维护一份 `skills/`、一个 `kabo` 条目和一个构建入口；
  Codex、Claude Code、Cursor 只增加宿主元数据，不复制业务内容或按宿主删功能。
- 用户已选六类十个 Skills，清单见 `skills.lock.json`。它们从 creator-skills 特化而来，此后
  直接在本仓修改，不再从 creator-skills 导入覆盖；锁文件只记录特化起点。
  修改 Skill 遵守 `docs/skills-spec.md`；门禁不启用，`skills-spec.json` 的 `enforced` 保持为空，不要自行加入。
  默认构建与验证只读本仓，不读取相邻仓，不在安装或执行时下载 Skills。
- API、OAuth、数据库、Web 和部署归 Kabo 服务端，不在本仓。研究判断、脚本与报告在 AI 宿主执行。
  插件与 Kabo 网页端 agent 运行时独立，不直接或通过 API、队列等代理调用它。
  不共享会话、任务、模型循环、沙箱或报告链；只共享 Skills 来源。
- 唯一生产 MCP 连接为 `/mcp-pub`。数据操作逐项固定并与提供方制品匹配；不得
  引入 registry、通用 executor 或远程完整研究任务。旧服务端动态协议由提供方保持兼容。
- 无 lifecycle hooks。显式保存完整 MCP 响应，校验摘要、运行归属与报告；不读取宿主
  会话记录。静态包版本与来源 Skill 业务版本分别维护，包内内容不在运行时自行更新。
- 包中不得放 apps、`.app.json`、私有 registry、真实本机路径、测试 URL 或凭据。
  用户认证由宿主管理。公开验签公钥可入包，但不能把内容摘要冒充数字签名或服务端证明。
- Node 24 执行 `npm ci --ignore-scripts` 与 `npm run verify`；Python 3 校验静态脚本。
  正式 ZIP 只读取完整 commit，不能混入工作区。所有 Skill 资源必须完整打包。
- 代码经 PR review，main 不直推。不得自动部署、上传后台或 Publish。CI、可构建 ZIP、
  实际宿主与生产验收、市场审核是不同事实；缺失验收必须明确，不宣称已上架就绪。
