import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";

import {
  AGENTS_POLICY_FILE,
  BACKUP_ROOT_REL,
  InstallerError,
  LEGACY_GENERIC_ROLE_PATHS,
  LEGACY_PROFILE_FILE,
  LEGACY_STATE_REL,
  POLICY_BEGIN,
  POLICY_FILE,
  POLICY_REQUIREMENTS,
  ROLE_DIR_REL,
  ROOT_MODEL,
  SPECIALIST_EFFORT,
  SCHEMA_VERSION,
  STATE_REL,
  assertPolicy,
  assertPolicyRoster,
  assertSafeCodexHome,
  assertSafeTarget,
  codexVersion,
  fileState,
  loadPersonaCatalog,
  lstatIfExists,
  queryCatalog,
  readAsset,
  relativeTarget,
  renderRoleFile,
  runCodex,
  semanticFailures,
  sha256,
  withTemporaryDirectory,
} from "./gpt-squad-runtime.mjs";
import {
  assertOwnedRemoval,
  currentManagedCatalogPaths,
  mergeAgents,
  mergeDesktopConfig,
  readOptionalState,
  rootStringValue,
} from "./gpt-squad-config.mjs";

function buildDesired(options, codexBin) {
  assertSafeCodexHome(options.codexHome);
  const { base, specialists } = loadPersonaCatalog();
  const policy = readAsset(POLICY_FILE);
  const agentsPolicy = readAsset(AGENTS_POLICY_FILE);
  assertPolicy(policy, POLICY_FILE);
  assertPolicy(agentsPolicy, AGENTS_POLICY_FILE);
  assertPolicyRoster(policy, specialists, POLICY_FILE);
  assertPolicyRoster(agentsPolicy, specialists, AGENTS_POLICY_FILE);

  const previousState = readOptionalState(options.codexHome, STATE_REL);
  const legacyState = readOptionalState(options.codexHome, LEGACY_STATE_REL);
  const ownershipStates = [previousState, legacyState].filter(Boolean);
  const configPath = path.join(options.codexHome, "config.toml");
  const agentsPath = path.join(options.codexHome, "AGENTS.md");
  for (const target of [configPath, agentsPath]) {
    assertSafeTarget(options.codexHome, target);
    const stat = lstatIfExists(target);
    if (stat && (!stat.isFile() || stat.isSymbolicLink())) throw new InstallerError(`unsafe managed target: ${target}`, 4);
  }
  const currentConfig = fs.existsSync(configPath) ? fs.readFileSync(configPath, "utf8") : "";
  const currentAgents = fs.existsSync(agentsPath) ? fs.readFileSync(agentsPath, "utf8") : "";
  const currentConfigState = fileState(configPath);
  const previousConfigEntry = (previousState?.managedFiles || []).find(
    (entry) => entry?.path === "config.toml" && entry.absent !== true,
  );
  const legacyForcedHigh = options.rootEffortMode === "preserve"
    && previousState?.rootEffortMode == null
    && previousState?.rootEffort === "high"
    && previousConfigEntry
    && currentConfigState.exists
    && previousConfigEntry.hash === currentConfigState.hash
    && previousConfigEntry.mode === currentConfigState.mode;
  const rootEffortMode = legacyForcedHigh ? "auto" : options.rootEffortMode;
  const requestedRootEffort = rootEffortMode === "explicit"
    ? options.rootEffort
    : rootEffortMode === "preserve"
      ? rootStringValue(currentConfig, "model_reasoning_effort")
      : null;

  const catalogInfo = queryCatalog(codexBin, requestedRootEffort);
  const version = codexVersion(codexBin);
  const desired = new Map();

  let catalogPath = null;
  if (catalogInfo.needsPatch) {
    const relative = path.join("model-catalogs", `gpt-squad-${version}.json`);
    catalogPath = path.join(options.codexHome, relative);
    desired.set(catalogPath, { content: `${JSON.stringify(catalogInfo.catalog, null, 2)}
`, mode: 0o600 });
  }

  for (const relative of currentManagedCatalogPaths(options.codexHome, ownershipStates)) {
    const target = path.join(options.codexHome, relative);
    if (catalogPath && target === catalogPath) continue;
    assertOwnedRemoval(options.codexHome, relative, ownershipStates);
    desired.set(target, { absent: true });
  }

  const desiredRolePaths = new Set();
  for (const specialist of specialists) {
    const relative = path.join(ROLE_DIR_REL, specialist.fileName);
    desiredRolePaths.add(relative);
    desired.set(path.join(options.codexHome, relative), {
      content: renderRoleFile(base, specialist),
      mode: 0o600,
    });
  }

  for (const entry of previousState?.managedFiles || []) {
    if (typeof entry?.path !== "string" || !entry.path.startsWith(`${ROLE_DIR_REL}${path.sep}`)) continue;
    if (desiredRolePaths.has(entry.path)) continue;
    assertOwnedRemoval(options.codexHome, entry.path, ownershipStates);
    desired.set(path.join(options.codexHome, entry.path), { absent: true });
  }

  for (const relative of LEGACY_GENERIC_ROLE_PATHS) {
    assertOwnedRemoval(options.codexHome, relative, ownershipStates);
    desired.set(path.join(options.codexHome, relative), { absent: true });
  }
  assertOwnedRemoval(options.codexHome, LEGACY_PROFILE_FILE, ownershipStates);
  desired.set(path.join(options.codexHome, LEGACY_PROFILE_FILE), { absent: true });

  const mergedConfig = mergeDesktopConfig(currentConfig, {
    policy,
    specialists,
    catalogPath,
    codexHome: options.codexHome,
    rootEffortMode,
    rootEffort: options.rootEffort,
  });
  desired.set(configPath, {
    content: mergedConfig,
    mode: lstatIfExists(configPath) ? fs.statSync(configPath).mode & 0o777 : 0o600,
  });
  desired.set(agentsPath, {
    content: mergeAgents(currentAgents, agentsPolicy),
    mode: lstatIfExists(agentsPath) ? fs.statSync(agentsPath).mode & 0o777 : 0o600,
  });
  for (const target of desired.keys()) assertSafeTarget(options.codexHome, target);
  return {
    desired,
    specialists,
    catalogPath,
    catalogPatched: catalogInfo.needsPatch,
    version,
    rootEffortMode,
    rootEffort: rootStringValue(mergedConfig, "model_reasoning_effort"),
    specialistEffort: SPECIALIST_EFFORT,
    migratedLegacyRootEffort: legacyForcedHigh,
  };
}

function writePrivateFile(target, content, mode = 0o600) {
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  const temporary = path.join(path.dirname(target), `.${path.basename(target)}.${process.pid}.${crypto.randomUUID()}.tmp`);
  const descriptor = fs.openSync(temporary, "wx", mode);
  try {
    fs.writeFileSync(descriptor, content, "utf8");
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  try {
    fs.renameSync(temporary, target);
    fs.chmodSync(target, mode);
  } catch (error) {
    fs.rmSync(temporary, { force: true });
    throw error;
  }
}

function installedMetadata(spec) {
  if (spec.absent) return { installedAbsent: true, installedHash: null, installedMode: null };
  return {
    installedAbsent: false,
    installedHash: sha256(Buffer.from(spec.content)),
    installedMode: spec.mode,
  };
}

function desiredMatches(target, spec) {
  const current = fileState(target);
  if (spec.absent) return !current.exists;
  return current.exists && current.hash === sha256(Buffer.from(spec.content)) && current.mode === spec.mode;
}

function planEntries(codexHome, desired) {
  return [...desired.entries()].map(([target, spec]) => {
    const current = fileState(target);
    if (spec.absent) {
      return { path: relativeTarget(codexHome, target), action: current.exists ? "remove" : "absent", mode: null };
    }
    const wanted = sha256(Buffer.from(spec.content));
    return {
      path: relativeTarget(codexHome, target),
      action: !current.exists ? "create" : current.hash === wanted && current.mode === spec.mode ? "unchanged" : "update",
      mode: spec.mode.toString(8).padStart(4, "0"),
    };
  });
}

function backupIdNow(prefix = "install") {
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `${prefix}-${timestamp}-${crypto.randomBytes(3).toString("hex")}`;
}

function createBackup(codexHome, backupId, desired) {
  const backupDir = path.join(codexHome, BACKUP_ROOT_REL, backupId);
  if (fs.existsSync(backupDir)) throw new InstallerError(`backup already exists: ${backupId}`, 5);
  fs.mkdirSync(path.join(backupDir, "files"), { recursive: true, mode: 0o700 });
  const files = [];
  const createdDirectories = new Set();
  let index = 0;
  for (const [target, spec] of desired.entries()) {
    const current = fileState(target);
    let cursor = path.dirname(target);
    while (cursor !== codexHome) {
      if (!fs.existsSync(cursor)) createdDirectories.add(relativeTarget(codexHome, cursor));
      cursor = path.dirname(cursor);
    }
    let backupName = null;
    if (current.exists) {
      backupName = `files/${String(index).padStart(3, "0")}`;
      const backupTarget = path.join(backupDir, backupName);
      fs.copyFileSync(target, backupTarget, fs.constants.COPYFILE_EXCL);
      fs.chmodSync(backupTarget, 0o600);
    }
    files.push({
      path: relativeTarget(codexHome, target),
      existed: current.exists,
      beforeHash: current.hash,
      beforeMode: current.mode,
      backupName,
      ...installedMetadata(spec),
    });
    index += 1;
  }
  const manifest = {
    schemaVersion: SCHEMA_VERSION,
    backupId,
    createdAt: new Date().toISOString(),
    codexHome,
    files,
    createdDirectories: [...createdDirectories].sort((left, right) => right.length - left.length),
  };
  writePrivateFile(path.join(backupDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  return { backupDir, manifest };
}

function validateManifest(backupDir, manifest, expectedHome, expectedId, strictInstalled = false) {
  if (!manifest || manifest.schemaVersion !== SCHEMA_VERSION || manifest.codexHome !== expectedHome || manifest.backupId !== expectedId) {
    throw new InstallerError("backup manifest identity or schema is invalid", 5);
  }
  if (!Array.isArray(manifest.files) || !Array.isArray(manifest.createdDirectories)) {
    throw new InstallerError("backup manifest entries are malformed", 5);
  }
  const seen = new Set();
  const entries = manifest.files.map((entry) => {
    if (!entry || typeof entry.path !== "string" || seen.has(entry.path)) {
      throw new InstallerError("backup manifest contains an invalid or duplicate path", 5);
    }
    seen.add(entry.path);
    const target = path.resolve(expectedHome, entry.path);
    if (relativeTarget(expectedHome, target) !== entry.path) throw new InstallerError(`unsafe backup path: ${entry.path}`, 5);
    assertSafeTarget(expectedHome, target);
    let backupTarget = null;
    if (entry.existed) {
      if (typeof entry.backupName !== "string") throw new InstallerError("backup payload name is missing", 5);
      backupTarget = path.resolve(backupDir, entry.backupName);
      if (!backupTarget.startsWith(`${path.join(backupDir, "files")}${path.sep}`)) {
        throw new InstallerError("backup payload path escapes backup directory", 5);
      }
      const state = fileState(backupTarget);
      if (!state.exists || state.hash !== entry.beforeHash) throw new InstallerError(`backup payload is missing or corrupt: ${entry.path}`, 5);
    }
    if (strictInstalled) {
      const current = fileState(target);
      const matches = entry.installedAbsent
        ? !current.exists
        : current.exists && current.hash === entry.installedHash && current.mode === entry.installedMode;
      if (!matches) throw new InstallerError(`managed target drift prevents rollback: ${entry.path}`, 5);
    }
    return { entry, target, backupTarget };
  });
  return entries;
}

function restoreEntries(entries, codexHome, createdDirectories = []) {
  for (const { entry, target, backupTarget } of entries) {
    if (entry.existed) {
      writePrivateFile(target, fs.readFileSync(backupTarget, "utf8"), entry.beforeMode);
    } else if (fs.existsSync(target)) {
      const stat = lstatIfExists(target);
      if (!stat?.isFile() || stat.isSymbolicLink()) throw new InstallerError(`unsafe restore removal target: ${entry.path}`, 5);
      fs.unlinkSync(target);
    }
  }
  for (const relative of createdDirectories) {
    const target = path.resolve(codexHome, relative);
    if (relativeTarget(codexHome, target) !== relative) throw new InstallerError(`unsafe created directory path: ${relative}`, 5);
    try {
      fs.rmdirSync(target);
    } catch (error) {
      if (!["ENOENT", "ENOTEMPTY"].includes(error?.code)) throw error;
    }
  }
}

function applyDesired(desired) {
  for (const [target, spec] of desired.entries()) {
    if (spec.absent) {
      if (!fs.existsSync(target)) continue;
      const stat = lstatIfExists(target);
      if (!stat?.isFile() || stat.isSymbolicLink()) throw new InstallerError(`unsafe removal target: ${target}`, 4);
      fs.unlinkSync(target);
    } else {
      writePrivateFile(target, spec.content, spec.mode);
    }
  }
}

function managedStateContent(codexHome, backupId, desired, specialists, catalogPatched, version, rootEffortMode, rootEffort) {
  const managedFiles = [...desired.entries()].map(([target, spec]) => ({
    path: relativeTarget(codexHome, target),
    hash: spec.absent ? null : sha256(Buffer.from(spec.content)),
    mode: spec.absent ? null : spec.mode,
    absent: Boolean(spec.absent),
  }));
  return `${JSON.stringify({
    schemaVersion: SCHEMA_VERSION,
    installedAt: new Date().toISOString(),
    backupId,
    rootModel: ROOT_MODEL,
    rootEffortMode,
    rootEffort,
    specialistEffort: SPECIALIST_EFFORT,
    codexVersion: version,
    catalogPatched,
    specialists: specialists.map((item) => item.name),
    managedFiles,
  }, null, 2)}\n`;
}

function validateStaged(options, codexBin, desired) {
  return withTemporaryDirectory("gpt-squad-stage-", (stageHome) => {
    for (const [target, spec] of desired.entries()) {
      if (spec.absent) continue;
      const relative = relativeTarget(options.codexHome, target);
      let content = spec.content;
      content = content.split(options.codexHome).join(stageHome);
      writePrivateFile(path.join(stageHome, relative), content, spec.mode);
    }
    const output = runCodex(codexBin, ["debug", "prompt-input", "Read-only GPT squad configuration validation."], stageHome);
    const missing = semanticFailures(output, POLICY_REQUIREMENTS);
    if (!output.includes(POLICY_BEGIN) || missing.length) {
      throw new InstallerError(`staged Codex prompt is missing squad policy semantics: ${missing.join(", ")}`, 4);
    }
  });
}

export {
  applyDesired,
  backupIdNow,
  buildDesired,
  createBackup,
  desiredMatches,
  managedStateContent,
  planEntries,
  restoreEntries,
  validateManifest,
  validateStaged,
};
