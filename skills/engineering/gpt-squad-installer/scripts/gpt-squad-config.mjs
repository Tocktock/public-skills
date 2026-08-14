import fs from "node:fs";
import path from "node:path";

import {
  AGENTS_BLOCK_VARIANTS,
  InstallerError,
  LEGACY_GENERIC_ROLES,
  POLICY_BLOCK_VARIANTS,
  ROLE_BLOCK_BEGIN,
  ROLE_BLOCK_END,
  ROLE_BLOCK_VARIANTS,
  ROLE_DIR_REL,
  ROOT_MODEL,
  SPECIALIST_EFFORT,
  fileState,
  normalizeText,
  tomlString,
} from "./gpt-squad-runtime.mjs";

function tomlTableHeaders(text) {
  const headers = [];
  let state = "root";
  let lineStart = 0;
  let onlyWhitespace = true;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (state === "comment") {
      if (char === "\n") {
        state = "root";
        lineStart = index + 1;
        onlyWhitespace = true;
      }
      continue;
    }
    if (state === "basic") {
      if (char === "\\") index += 1;
      else if (char === '"') state = "root";
      continue;
    }
    if (state === "literal") {
      if (char === "'") state = "root";
      continue;
    }
    if (state === "multiline-basic") {
      if (char === "\\") index += 1;
      else if (text.startsWith('"""', index)) {
        state = "root";
        index += 2;
      }
      continue;
    }
    if (state === "multiline-literal") {
      if (text.startsWith("'''", index)) {
        state = "root";
        index += 2;
      }
      continue;
    }
    if (char === "\n") {
      lineStart = index + 1;
      onlyWhitespace = true;
      continue;
    }
    if (onlyWhitespace && /[ \t\r]/.test(char)) continue;
    if (char === "#") {
      state = "comment";
      onlyWhitespace = false;
      continue;
    }
    if (text.startsWith('"""', index)) {
      state = "multiline-basic";
      onlyWhitespace = false;
      index += 2;
      continue;
    }
    if (text.startsWith("'''", index)) {
      state = "multiline-literal";
      onlyWhitespace = false;
      index += 2;
      continue;
    }
    if (char === '"') {
      state = "basic";
      onlyWhitespace = false;
      continue;
    }
    if (char === "'") {
      state = "literal";
      onlyWhitespace = false;
      continue;
    }
    if (onlyWhitespace && char === "[") {
      const lineEnd = text.indexOf("\n", index);
      const candidate = text.slice(index, lineEnd < 0 ? text.length : lineEnd);
      const header = candidate.match(/^\[\[?([^\]\r\n]+)\]\]?\s*(?:#.*)?$/);
      if (header) headers.push({ start: lineStart, name: header[1].trim() });
    }
    onlyWhitespace = false;
  }
  return headers;
}

function rootPrefixEnd(text) {
  return tomlTableHeaders(text)[0]?.start ?? text.length;
}

function assignmentSpan(prefix, key) {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`^${escaped}\\s*=`, "m").exec(prefix);
  if (!match) return null;
  const start = match.index;
  const equals = prefix.indexOf("=", start);
  let valueStart = equals + 1;
  while (/[ \t]/.test(prefix[valueStart] || "")) valueStart += 1;
  const delimiter = prefix.startsWith('"""', valueStart)
    ? '"""'
    : prefix.startsWith("'''", valueStart)
      ? "'''"
      : null;
  let end;
  if (delimiter) {
    const close = prefix.indexOf(delimiter, valueStart + 3);
    if (close < 0) throw new InstallerError(`unterminated ${key} value in config.toml`, 4);
    end = close + 3;
    while (end < prefix.length && prefix[end] !== "\n") end += 1;
    if (end < prefix.length) end += 1;
  } else {
    end = prefix.indexOf("\n", start);
    if (end < 0) end = prefix.length;
    else end += 1;
  }
  return { start, end, raw: prefix.slice(start, end) };
}

function decodeSimpleTomlStringAssignment(raw, key) {
  const equals = raw.indexOf("=");
  if (equals < 0) throw new InstallerError(`invalid ${key} assignment`, 4);
  const value = raw.slice(equals + 1).trim();
  if (value.startsWith('"""') && value.endsWith('"""')) {
    let inner = value.slice(3, -3);
    if (inner.startsWith("\n")) inner = inner.slice(1);
    if (inner.includes("\\")) throw new InstallerError(`${key} uses unsupported multiline escapes`, 4);
    return inner;
  }
  if (value.startsWith("'''") && value.endsWith("'''")) {
    let inner = value.slice(3, -3);
    if (inner.startsWith("\n")) inner = inner.slice(1);
    return inner;
  }
  if (value.startsWith('"')) {
    try {
      return JSON.parse(value);
    } catch {
      throw new InstallerError(`${key} is not a supported basic TOML string`, 4);
    }
  }
  if (value.startsWith("'") && value.endsWith("'")) return value.slice(1, -1);
  throw new InstallerError(`${key} is not a string`, 4);
}

function upsertRootAssignment(text, key, encodedValue) {
  const prefixEnd = rootPrefixEnd(text);
  let prefix = text.slice(0, prefixEnd);
  const suffix = text.slice(prefixEnd);
  const span = assignmentSpan(prefix, key);
  const replacement = `${key} = ${encodedValue}\n`;
  if (span) prefix = prefix.slice(0, span.start) + replacement + prefix.slice(span.end);
  else prefix = `${prefix.trimEnd()}${prefix.trim() ? "\n" : ""}${replacement}`;
  return `${prefix}${suffix}`;
}

function removeRootAssignment(text, key) {
  const prefixEnd = rootPrefixEnd(text);
  let prefix = text.slice(0, prefixEnd);
  const suffix = text.slice(prefixEnd);
  const span = assignmentSpan(prefix, key);
  if (span) prefix = prefix.slice(0, span.start) + prefix.slice(span.end);
  return `${prefix}${suffix}`;
}

function upsertSimpleTableKeys(text, tableName, entries) {
  const headers = tomlTableHeaders(text);
  const matches = headers.filter((header) => header.name === tableName);
  if (matches.length > 1) throw new InstallerError(`config.toml contains duplicate [${tableName}] tables`, 4);
  if (!matches.length) {
    const section = [`[${tableName}]`, ...Object.entries(entries).map(([key, value]) => `${key} = ${value}`), ""].join("\n");
    return `${text.trimEnd()}\n\n${section}`;
  }
  const header = matches[0];
  const next = headers.find((candidate) => candidate.start > header.start);
  const bodyStart = text.indexOf("\n", header.start) + 1;
  const end = next?.start ?? text.length;
  let body = text.slice(bodyStart, end);
  for (const [key, value] of Object.entries(entries)) {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const matcher = new RegExp(`^${escaped}\\s*=.*$`, "m");
    const line = `${key} = ${value}`;
    if (matcher.test(body)) body = body.replace(matcher, line);
    else body = `${body.trimEnd()}\n${line}\n`;
  }
  return text.slice(0, bodyStart) + body + text.slice(end);
}

function markerCount(text, marker) {
  let count = 0;
  let offset = 0;
  while (true) {
    const index = text.indexOf(marker, offset);
    if (index < 0) return count;
    count += 1;
    offset = index + marker.length;
  }
}

function findManagedBlock(text, variants, label) {
  const matches = [];
  for (const variant of variants) {
    const beginCount = markerCount(text, variant.begin);
    const endCount = markerCount(text, variant.end);
    if ((beginCount === 0) !== (endCount === 0) || beginCount !== endCount || beginCount > 1) {
      throw new InstallerError(`corrupt managed ${label} block: ${variant.begin}`, 4);
    }
    if (!beginCount) continue;
    const begin = text.indexOf(variant.begin);
    const end = text.indexOf(variant.end);
    if (end < begin) throw new InstallerError(`corrupt managed ${label} block: ${variant.begin}`, 4);
    matches.push({ ...variant, begin, end: end + variant.end.length });
  }
  if (matches.length > 1) throw new InstallerError(`multiple managed ${label} blocks are present`, 4);
  return matches[0] || null;
}

function replaceManagedBlock(text, variants, block, label) {
  const managed = findManagedBlock(text, variants, label);
  if (managed) {
    const prefix = text.slice(0, managed.begin).trimEnd();
    const suffix = text.slice(managed.end).trimStart();
    return normalizeText([prefix, block.trim(), suffix].filter(Boolean).join("\n\n"));
  }
  return normalizeText(`${text.trimEnd()}${text.trim() ? "\n\n" : ""}${block.trim()}`);
}

function managedBlockText(text, variants, label) {
  const managed = findManagedBlock(text, variants, label);
  return managed ? text.slice(managed.begin, managed.end) : null;
}

function mergeDeveloperInstructions(configText, policy) {
  const prefixEnd = rootPrefixEnd(configText);
  let prefix = configText.slice(0, prefixEnd);
  const suffix = configText.slice(prefixEnd);
  const span = assignmentSpan(prefix, "developer_instructions");
  let existing = "";
  if (span) existing = decodeSimpleTomlStringAssignment(span.raw, "developer_instructions");
  const merged = replaceManagedBlock(existing, POLICY_BLOCK_VARIANTS, policy, "developer-instructions");
  const replacement = `developer_instructions = ${tomlString(merged.trim())}\n`;
  if (span) prefix = prefix.slice(0, span.start) + replacement + prefix.slice(span.end);
  else prefix = `${prefix.trimEnd()}${prefix.trim() ? "\n" : ""}${replacement}`;
  return `${prefix}${suffix}`;
}

function roleRegistrationBlock(specialists) {
  const lines = [ROLE_BLOCK_BEGIN];
  for (const specialist of specialists) {
    lines.push(
      `[agents.${specialist.name}]`,
      `description = ${tomlString(specialist.description)}`,
      `config_file = ${tomlString(`./${path.join(ROLE_DIR_REL, specialist.fileName).replaceAll(path.sep, "/")}`)}`,
      "",
    );
  }
  lines.push(ROLE_BLOCK_END);
  return normalizeText(lines.join("\n"));
}

function assertNoRoleCollisions(configText, specialists) {
  const managed = findManagedBlock(configText, ROLE_BLOCK_VARIANTS, "role-registration");
  const outside = managed
    ? `${configText.slice(0, managed.begin)}\n${configText.slice(managed.end)}`
    : configText;
  const names = [...specialists.map((item) => item.name), ...LEGACY_GENERIC_ROLES];
  for (const name of names) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`^\\[agents\\.${escaped}\\]\\s*$`, "m").test(outside)) {
      throw new InstallerError(`unmanaged agent registration collides with ${name}`, 4);
    }
  }
}

function rootStringValue(configText, key) {
  const prefix = configText.slice(0, rootPrefixEnd(configText));
  const span = assignmentSpan(prefix, key);
  return span ? decodeSimpleTomlStringAssignment(span.raw, key) : null;
}

function decodeSimpleTomlValueAssignment(raw, key) {
  const equals = raw.indexOf("=");
  if (equals < 0) throw new InstallerError(`invalid ${key} assignment`, 4);
  const value = raw.slice(equals + 1).trim();
  if (value.startsWith('"') || value.startsWith("'")) {
    return decodeSimpleTomlStringAssignment(raw, key);
  }
  const bare = value.replace(/\s+#.*$/, "").trim();
  if (bare === "true") return true;
  if (bare === "false") return false;
  if (/^[+-]?\d+$/.test(bare)) return Number(bare);
  throw new InstallerError(`${key} is not a supported simple TOML value`, 4);
}

function simpleTableValue(configText, tableName, key) {
  const headers = tomlTableHeaders(configText);
  const matches = headers.filter((header) => header.name === tableName);
  if (matches.length > 1) throw new InstallerError(`config.toml contains duplicate [${tableName}] tables`, 4);
  if (!matches.length) return null;
  const header = matches[0];
  const next = headers.find((candidate) => candidate.start > header.start);
  const headerEnd = configText.indexOf("\n", header.start);
  const bodyStart = headerEnd < 0 ? configText.length : headerEnd + 1;
  const body = configText.slice(bodyStart, next?.start ?? configText.length);
  const span = assignmentSpan(body, key);
  return span ? decodeSimpleTomlValueAssignment(span.raw, key) : null;
}

function mergeDesktopConfig(existing, { policy, specialists, catalogPath, codexHome, rootEffortMode, rootEffort }) {
  let text = normalizeText(existing || "");
  assertNoRoleCollisions(text, specialists);
  text = upsertRootAssignment(text, "model", tomlString(ROOT_MODEL));
  if (rootEffortMode === "explicit") {
    text = upsertRootAssignment(text, "model_reasoning_effort", tomlString(rootEffort));
  } else if (rootEffortMode === "auto") {
    text = removeRootAssignment(text, "model_reasoning_effort");
  }
  if (catalogPath) {
    text = upsertRootAssignment(text, "model_catalog_json", tomlString(catalogPath));
  } else {
    const current = rootStringValue(text, "model_catalog_json");
    if (current) {
      const resolved = path.resolve(current);
      const directory = path.join(codexHome, "model-catalogs");
      const relative = path.relative(directory, resolved);
      const managed = relative && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)
        && /^(?:gpt|sol-sol|sol-luna)-squad-.*\.json$/.test(path.basename(relative));
      if (managed) text = removeRootAssignment(text, "model_catalog_json");
    }
  }
  text = mergeDeveloperInstructions(text, policy);
  text = upsertSimpleTableKeys(text, "agents", {
    enabled: "true",
    max_concurrent_threads_per_session: "128",
    default_subagent_model: tomlString(ROOT_MODEL),
    default_subagent_reasoning_effort: tomlString(SPECIALIST_EFFORT),
    interrupt_message: "true",
  });
  return replaceManagedBlock(text, ROLE_BLOCK_VARIANTS, roleRegistrationBlock(specialists), "role-registration");
}

function mergeAgents(existing, policy) {
  return replaceManagedBlock(normalizeText(existing || ""), AGENTS_BLOCK_VARIANTS, policy, "AGENTS");
}

function readOptionalState(codexHome, relative) {
  const target = path.join(codexHome, relative);
  if (!fs.existsSync(target)) return null;
  try {
    const state = JSON.parse(fs.readFileSync(target, "utf8"));
    return state && typeof state === "object" ? state : null;
  } catch {
    return null;
  }
}

function stateOwnershipMap(state) {
  const result = new Map();
  for (const entry of state?.managedFiles || []) {
    if (!entry || typeof entry.path !== "string") continue;
    const hash = entry.hash ?? entry.installedHash ?? null;
    const mode = entry.mode ?? entry.installedMode ?? null;
    const absent = entry.absent ?? entry.installedAbsent ?? false;
    result.set(entry.path, { hash, mode, absent });
  }
  return result;
}

function ownershipFor(states, relative) {
  for (const state of states) {
    const entry = stateOwnershipMap(state).get(relative);
    if (entry) return entry;
  }
  return null;
}

function assertOwnedRemoval(codexHome, relative, states) {
  const target = path.join(codexHome, relative);
  const current = fileState(target);
  if (!current.exists) return;
  const owned = ownershipFor(states, relative);
  if (!owned || owned.absent || owned.hash !== current.hash || owned.mode !== current.mode) {
    throw new InstallerError(`managed cleanup target is missing ownership or has drifted: ${relative}`, 4);
  }
}

function currentManagedCatalogPaths(codexHome, states) {
  const paths = new Set();
  for (const state of states) {
    for (const entry of state?.managedFiles || []) {
      if (typeof entry?.path !== "string") continue;
      if (/^model-catalogs\/(?:gpt|sol-sol|sol-luna)-squad-.*\.json$/.test(entry.path)) paths.add(entry.path);
    }
  }
  return paths;
}

export {
  assertOwnedRemoval,
  currentManagedCatalogPaths,
  managedBlockText,
  mergeAgents,
  mergeDesktopConfig,
  readOptionalState,
  roleRegistrationBlock,
  rootStringValue,
  simpleTableValue,
};
