// The single install root; dev tooling stays out of the package, and declared components are always packaged
//   in full, with no per-host feature trimming.
export const packageComponents = [
  "plugin.json", "mcp.json", "host-auth.json", "runtime-contract.json", "skills.lock.json",
  ".mcp.json", ".claude-plugin", "assets", "skills", "LICENSE",
];
// The marketplace manifest is a catalog the host reads when distributing from this repo, not a plugin
//   component; once installed from a ZIP,
// the unpacked directory would contain a marketplace pointing at itself.
export const distributionOnlyFiles = new Set([".claude-plugin/marketplace.json"]);
export const isPackageFile = name => packageComponents.includes(name.split("/")[0]) && !distributionOnlyFiles.has(name);

export function assertNoHiddenComponents(names) {
  const unsupported = new Set(["plugin", "hooks", "apps", ".app.json", ".codex-plugin", ".cursor-plugin", "agents", "commands", "rules", "monitors", "lsp.json", ".lsp.json"]);
  if (names.some(name => unsupported.has(name.split("/")[0])))
    throw new Error("Source contains unsupported plugin components, which cannot be hidden by a build filter.");
}
