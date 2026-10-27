// 唯一安装根目录；开发工具不入包，声明的组件始终完整打包，不按宿主裁剪功能。
export const packageComponents = [
  "plugin.json", "mcp.json", "host-auth.json", "runtime-contract.json", "skills.lock.json",
  ".mcp.json", ".claude-plugin", "assets", "skills", "LICENSE",
];
// 市场清单是从本仓分发时宿主读的目录，不是插件组件；装进 ZIP 后解包目录会多出一个指向自身的市场。
export const distributionOnlyFiles = new Set([".claude-plugin/marketplace.json"]);
export const isPackageFile = name => packageComponents.includes(name.split("/")[0]) && !distributionOnlyFiles.has(name);

export function assertNoHiddenComponents(names) {
  const unsupported = new Set(["plugin", "hooks", "apps", ".app.json", ".codex-plugin", ".cursor-plugin", "agents", "commands", "rules", "monitors", "lsp.json", ".lsp.json"]);
  if (names.some(name => unsupported.has(name.split("/")[0])))
    throw new Error("源码含未支持的插件组件，不能靠构建过滤器隐藏。");
}
