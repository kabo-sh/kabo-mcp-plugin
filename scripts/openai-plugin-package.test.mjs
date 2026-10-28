import assert from "node:assert/strict";
import { acceptanceChecks } from "./submission-evidence.mjs";
import { execFileSync } from "node:child_process";
import {
  copyFile,
  cp,
  mkdtemp,
  mkdir,
  readFile,
  rm,
  symlink,
  stat,
  writeFile,
} from "node:fs/promises";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  deterministicZip,
  readPackageFiles,
  validatePackage,
} from "./openai-plugin-package.mjs";

function packageFiles() {
  const manifest = {
    $schema: "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    name: "kabo",
    version: "1.0.0",
    extensions: {
      "com.openai": {
        interface: {
          displayName: "Kabo",
          shortDescription: "Creator research",
          longDescription: "Research public content evidence.",
          developerName: "Dealism",
          category: "Productivity",
          websiteURL: "https://kabo.sh",
          supportURL: "https://kabo.sh/support",
          privacyPolicyURL: "https://kabo.sh/privacy",
          termsOfServiceURL: "https://kabo.sh/terms",
          logo: "./assets/icon.png",
          composerIcon: "./assets/icon.png",
        },
      },
    },
  };
  const mcp = {
    $schema: "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
    mcpServers: {
      kabo: JSON.parse(
        readFileSync(new URL("../mcp.json", import.meta.url), "utf8"),
      ).mcpServers.kabo,
    },
  };
  return [
    {
      name: "plugin.json",
      bytes: Buffer.from(JSON.stringify(manifest)),
      mode: 0o100644,
    },
    {
      name: "mcp.json",
      bytes: Buffer.from(JSON.stringify(mcp)),
      mode: 0o100644,
    },
    {
      name: "host-auth.json",
      bytes: readFileSync(new URL("../host-auth.json", import.meta.url)),
      mode: 0o100644,
    },
    {
      name: "assets/icon.png",
      bytes: readFileSync(
        new URL("../assets/composer-icon.png", import.meta.url),
      ),
      mode: 0o100644,
    },
  ];
}

test("MCP-only 包可构建且不强制 Skills；ZIP 不受传入顺序影响", () => {
  const files = packageFiles();
  assert.deepEqual(validatePackage(files), { name: "kabo", version: "1.0.0" });
  assert.deepEqual(
    deterministicZip(files),
    deterministicZip([...files].reverse()),
  );
  files.push({
    name: "skills/optional/SKILL.md",
    bytes: Buffer.from(
      "---\nname: optional\ndescription: Test-only optional skill.\n---\nUse the reviewed tools.",
    ),
    mode: 0o100644,
  });
  assert.equal(validatePackage(files).version, "1.0.0");
});

test("公开 OAuth 明确声明身份与个人资产读写权限", () => {
  const files = packageFiles();
  const record = files.find(file => file.name === "host-auth.json");
  const auth = JSON.parse(record.bytes);
  assert.deepEqual(auth.baseScopes, ["openid", "profile", "email", "offline_access"]);
  assert.deepEqual(auth.defaultScopes, ["data", "video", "workspace:read", "workspace:write"]);
  for (const scopes of [["openid", "offline_access"], [...auth.baseScopes, "profile"]]) {
    record.bytes = Buffer.from(JSON.stringify({ ...auth, baseScopes: scopes }));
    assert.throws(() => validatePackage(files), /OAuth 配置/);
  }
});

test("拒绝 hooks、apps、Reviewer 凭据、测试 URL、密钥与越界路径，错误不复述内容", () => {
  for (const field of ["name", "version"]) {
    const files = packageFiles();
    const manifest = JSON.parse(files[0].bytes);
    manifest[field] = [manifest[field]];
    files[0].bytes = Buffer.from(JSON.stringify(manifest));
    assert.throws(
      () => validatePackage(files),
      "不能用可隐式转成字符串的 JSON 数组冒充包名或版本",
    );
  }
  for (const [name, text] of [
    ["hooks/session.sh", "exit 0"],
    [".app.json", "{}"],
    [".env", "secret-value"],
    ["../escape", "data"],
    ["review.json", '{"reviewer_instructions":"secret-value"}'],
    ["review.json", '{"test_credentials":"secret-value"}'],
    ["readme.md", "https://pre.kabo.sh/mcp"],
    ["readme.md", "-----BEGIN PRIVATE KEY-----\nsecret-value"],
    ["readme.md", "/home/example/private"],
  ]) {
    const files = packageFiles();
    files.push({ name, bytes: Buffer.from(text), mode: 0o100644 });
    assert.throws(
      () => validatePackage(files),
      (error) => !error.message.includes("secret-value"),
    );
  }
  for (const edit of [
    (value) => {
      value.mcpServers.kabo.url = "https://kabo.sh/mcp-for-claude";
    },
    (value) => {
      value.mcpServers.kabo.headers = { Authorization: "secret-value" };
    },
    (value) => {
      value.mcpServers.extra = value.mcpServers.kabo;
    },
  ]) {
    const files = packageFiles();
    const mcp = JSON.parse(files[1].bytes);
    edit(mcp);
    files[1].bytes = Buffer.from(JSON.stringify(mcp));
    assert.throws(() => validatePackage(files));
  }
});

test("只从锁定 commit 读取文件，忽略工作区修改；拒绝符号链接与不完整版本引用", async () => {
  const repository = await mkdtemp(
    path.join(os.tmpdir(), "kabo-package-test-"),
  );
  const git = (...args) =>
    execFileSync("git", ["-c", `core.hooksPath=${os.devNull}`, ...args], {
      cwd: repository,
      env: {
        ...process.env,
        GIT_CONFIG_NOSYSTEM: "1",
        GIT_CONFIG_GLOBAL: os.devNull,
      },
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  try {
    git("init", "--quiet");
    git("config", "user.email", "fixture@example.invalid");
    git("config", "user.name", "Package fixture");
    for (const file of packageFiles()) {
      const target = path.join(repository, "package", file.name);
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, file.bytes);
    }
    git("add", "package");
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "测试包");
    const commit = git("rev-parse", "HEAD");
    const options = { repository, commit, packagePath: "package" };
    const initial = readPackageFiles(options);
    await writeFile(
      path.join(repository, "package/plugin.json"),
      "working-tree-secret",
    );
    await writeFile(
      path.join(repository, "package/untracked"),
      "untracked-secret",
    );
    assert.deepEqual(
      deterministicZip(readPackageFiles(options)),
      deterministicZip(initial),
    );
    assert.ok(!deterministicZip(initial).includes("working-tree-secret"));
    assert.ok(!deterministicZip(initial).includes("untracked-secret"));
    await mkdir(path.join(repository, "scripts"));
    const runner = path.join(repository, "scripts/openai-plugin-package.mjs");
    await copyFile(
      new URL("./openai-plugin-package.mjs", import.meta.url),
      runner,
    );
    await copyFile(
      new URL("./package-standard.mjs", import.meta.url),
      path.join(repository, "scripts/package-standard.mjs"),
    );
    await copyFile(
      new URL("./submission-evidence.mjs", import.meta.url),
      path.join(repository, "scripts/submission-evidence.mjs"),
    );
    for (const name of ["static-skills.mjs", "package-layout.mjs"])
      await copyFile(new URL(`./${name}`, import.meta.url), path.join(repository, "scripts", name));
    for (const directory of ["schemas", "contracts"])
      await cp(
        new URL(`../${directory}`, import.meta.url),
        path.join(repository, directory),
        { recursive: true },
      );
    await symlink(
      new URL("../node_modules", import.meta.url),
      path.join(repository, "node_modules"),
      "dir",
    );
    await writeFile(path.join(repository, "package.json"), '{"type":"module"}');
    const run = (output, submission = false, evidence) =>
      execFileSync(
        process.execPath,
        [
          runner,
          "--commit",
          commit,
          "--package-path",
          "package",
          "--output",
          path.join(repository, output),
          ...(submission ? ["--submission"] : []),
          ...(evidence ? ["--evidence", evidence] : []),
        ],
        { stdio: ["ignore", "pipe", "pipe"] },
      );
    run("first");
    run("second");
    // macOS 的 /var → /private/var 及其他目录别名不能让 CLI 静默跳过 main。
    const alias = `${repository}-alias`;
    await symlink(repository, alias, "dir");
    try {
      execFileSync(process.execPath, [
        path.join(alias, "scripts/openai-plugin-package.mjs"),
        "--commit", commit, "--package-path", "package",
        "--output", path.join(repository, "via-alias"),
      ], { stdio: ["ignore", "pipe", "pipe"] });
      assert.deepEqual(
        await readFile(path.join(repository, "via-alias/kabo-1.0.0.zip")),
        await readFile(path.join(repository, "first/kabo-1.0.0.zip")),
      );
    } finally {
      await rm(alias);
    }
    const archive = await readFile(
      path.join(repository, "first/kabo-1.0.0.zip"),
    );
    assert.deepEqual(
      archive,
      await readFile(path.join(repository, "second/kabo-1.0.0.zip")),
    );
    const receipt = JSON.parse(
      await readFile(path.join(repository, "first/manifest.json"), "utf8"),
    );
    assert.equal(receipt.commit, commit);
    assert.equal(receipt.version, "1.0.0");
    assert.equal(
      receipt.sha256,
      createHash("sha256").update(archive).digest("hex"),
    );
    assert.equal(receipt.submissionReady, false);
    assert.ok(receipt.submissionBlockers.length > 0);
    assert.throws(() => run("submission", true));
    await assert.rejects(stat(path.join(repository, "submission")), { code: "ENOENT" });
    // 只有合成临时仓夹具：证明门禁能由真实传入的完整证据转绿，不是硬编码 false。
    const proof = "Synthetic test evidence only. No production acceptance was performed.\n";
    const proofHash = createHash("sha256").update(proof).digest("hex");
    const toolsHash = createHash("sha256").update(await readFile(path.join(repository, "contracts/directory-mcp/tools-list.json"))).digest("hex");
    await writeFile(path.join(repository, "proof.txt"), proof);
    const evidence = path.join(repository, "acceptance.json");
    await writeFile(evidence, JSON.stringify({
      format: "kabo.openai-acceptance.v1", environment: "production", resource: "https://kabo.sh/mcp-pub",
      release: { commit, version: "1.0.0", zipSha256: receipt.sha256, toolsSha256: toolsHash },
      checks: acceptanceChecks.map(id => ({ id, status: "passed", performedAt: "2020-01-01T00:00:00Z", artifact: id === "mcp.tools-list" ? "contracts/directory-mcp/tools-list.json" : "proof.txt", sha256: id === "mcp.tools-list" ? toolsHash : proofHash })),
    }));
    run("accepted", true, evidence);
    const accepted = JSON.parse(await readFile(path.join(repository, "accepted/manifest.json"), "utf8"));
    assert.equal(accepted.submissionReady, true);
    assert.deepEqual(archive, await readFile(path.join(repository, "accepted/kabo-1.0.0.zip")));
    assert.equal(receipt.validation, "portable-schema-and-local-policy");
    for (const file of initial)
      assert.equal(
        receipt.files.find((item) => item.path === file.name).sha256,
        createHash("sha256").update(file.bytes).digest("hex"),
      );
    assert.throws(() => run("first"));
    assert.deepEqual(
      archive,
      await readFile(path.join(repository, "first/kabo-1.0.0.zip")),
    );
    assert.throws(() => readPackageFiles({ ...options, commit: "HEAD" }));
    assert.throws(() =>
      readPackageFiles({ ...options, packagePath: "../package" }),
    );
    await symlink("plugin.json", path.join(repository, "package/link"));
    git("add", "package/link");
    git(
      "-c",
      "commit.gpgsign=false",
      "commit",
      "--quiet",
      "-m",
      "测试链接拒绝",
    );
    assert.throws(
      () => readPackageFiles({ ...options, commit: git("rev-parse", "HEAD") }),
      /普通文件/,
    );
  } finally {
    await rm(repository, { recursive: true, force: true });
  }
});
