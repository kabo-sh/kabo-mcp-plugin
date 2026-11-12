// The skills/ directory in this repo is a fixed subset specialised from creator-skills, and is edited directly in this repo from now on.
// The lock file only records the starting point of the specialisation and no longer binds the provider export byte for byte; content is guarded by review and package checks.
export function validateStaticSkills(files) {
  const record = files.get("skills.lock.json");
  if (!record) throw new Error("Missing static Skills source record.");
  const lock = JSON.parse(record.bytes);
  if (lock.format !== "kabo.static-skills.v2" || lock.derivedFrom?.repository !== "https://github.com/kabo-sh/creator-skills" || !/^[a-f0-9]{40}$/.test(lock.derivedFrom?.commit) || !Array.isArray(lock.skills) || !lock.skills.length)
    throw new Error("Static Skills source identity is invalid.");
  const ids = new Set();
  for (const skill of lock.skills) {
    if (!/^[a-z][a-z0-9-]*$/.test(skill.id) || ids.has(skill.id) || !/^\d+\.\d+\.\d+$/.test(skill.derivedFromVersion))
      throw new Error("Static Skill identity is duplicated or lacks a specialization starting version.");
    if (!files.has(`skills/${skill.id}/SKILL.md`)) throw new Error(`Static Skill is missing its body: skills/${skill.id}/SKILL.md`);
    ids.add(skill.id);
  }
  // The set of directories must still match the record: an unrecorded directory would bypass the Skills-list comparison in runtime-contract.
  for (const name of files.keys())
    if (name.startsWith("skills/") && !ids.has(name.split("/")[1])) throw new Error("The static package contains a Skill directory that is not recorded.");
  return lock;
}
