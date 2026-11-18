"use strict";

const { isDeepStrictEqual } = require("node:util");
const { isAlias, isMap, isSeq, parseDocument, visit } = require("yaml");

function parsePatch(source) {
  const doc = parseDocument(source);
  if (doc.errors.length || doc.warnings.length) {
    throw new Error("The patch file contains invalid or unsupported YAML. Fix it before installing Kabo.");
  }
  // Resolve aliases before editing, so an invalid reference never reaches the file write.
  doc.toJS();
  if (doc.contents === null) doc.contents = doc.createNode([]);
  if (!isSeq(doc.contents)) throw new Error("The patch file must contain a top-level YAML list.");
  return doc;
}

function updateDeepSeekPatch(original, entry) {
  const doc = parsePatch(original ?? "");
  const wanted = parsePatch(entry).toJS()[0].insert[0];
  const matches = [];
  for (const operation of doc.contents.items) {
    if (!isMap(operation)) throw new Error("Each patch operation must be an explicit YAML mapping.");
    const insert = operation.get("insert", true);
    if (insert === undefined) continue;
    if (!isSeq(insert)) throw new Error("Each insert operation must contain an explicit YAML list.");
    for (const item of insert.items) {
      if (!isMap(item)) throw new Error("Each inserted plugin must be an explicit YAML mapping.");
      if (isAlias(item.get("id", true))) throw new Error("Plugin IDs must be explicit values, not YAML aliases.");
      if (item.get("id") === "mcp-kabo") matches.push({ operation, insert, item });
    }
  }
  if (matches.length > 1) {
    throw new Error("The patch file already contains multiple mcp-kabo entries. Keep one and try again.");
  }
  let connection = "added";
  if (matches.length) {
    const { operation, insert, item } = matches[0];
    // Replacing an anchor can change a different plugin through its alias, even when the YAML stays valid.
    let shared = Boolean(operation.anchor || insert.anchor);
    visit(item, (_, node) => {
      if (node?.anchor || isAlias(node)) shared = true;
    });
    if (shared) {
      throw new Error("The mcp-kabo entry uses YAML anchors or aliases. Update that entry by hand; the file was not changed.");
    }
    const current = item.toJSON();
    if (current.name === wanted.name && isDeepStrictEqual(current.config, wanted.config)) {
      return { next: original, connection: "unchanged" };
    }
    item.set("name", wanted.name);
    item.set("config", doc.createNode(wanted.config));
    connection = "replaced";
  } else {
    doc.contents.add(doc.createNode({ insert: [wanted] }));
  }
  const next = doc.toString();
  parsePatch(next);
  return { next, connection };
}

module.exports = { updateDeepSeekPatch };
