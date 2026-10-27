// 本仓 skills/ 是从 creator-skills 特化出的固定子集，此后在本仓直接修改。
// 锁文件只记录特化起点，不再按字节绑定提供方导出；内容由 review 与包检查把关。
export function validateStaticSkills(files) {
  const record = files.get("skills.lock.json");
  if (!record) throw new Error("缺少静态 Skills 来源记录。");
  const lock = JSON.parse(record.bytes);
  if (lock.format !== "kabo.static-skills.v2" || lock.derivedFrom?.repository !== "https://github.com/kabo-sh/creator-skills" || !/^[a-f0-9]{40}$/.test(lock.derivedFrom?.commit) || !Array.isArray(lock.skills) || !lock.skills.length)
    throw new Error("静态 Skills 来源身份无效。");
  const ids = new Set();
  for (const skill of lock.skills) {
    if (!/^[a-z][a-z0-9-]*$/.test(skill.id) || ids.has(skill.id) || !/^\d+\.\d+\.\d+$/.test(skill.derivedFromVersion))
      throw new Error("静态 Skill 身份重复或缺少特化起点版本。");
    if (!files.has(`skills/${skill.id}/SKILL.md`)) throw new Error(`静态 Skill 缺少正文：skills/${skill.id}/SKILL.md`);
    ids.add(skill.id);
  }
  // 目录集合仍须与记录一致：漏记的目录会绕过 runtime-contract 的 Skills 名单比对。
  for (const name of files.keys())
    if (name.startsWith("skills/") && !ids.has(name.split("/")[1])) throw new Error("静态包含未记录的 Skill 目录。");
  return lock;
}
