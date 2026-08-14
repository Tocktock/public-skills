#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import {
  AGENTS_BLOCK_VARIANTS,
  AGENTS_POLICY_FILE,
  BACKUP_ROOT_REL,
  InstallerError,
  LEGACY_GENERIC_ROLES,
  LEGACY_LOCKS,
  LOCK_REL,
  POLICY_BEGIN,
  POLICY_BLOCK_VARIANTS,
  POLICY_FILE,
  POLICY_REQUIREMENTS,
  ROLE_BLOCK_VARIANTS,
  ROLE_DIR_REL,
  ROOT_MODEL,
  SPECIALIST_EFFORT,
  SCHEMA_VERSION,
  STATE_REL,
  assertPolicyRoster,
  assertSafeCodexHome,
  assertSafeTarget,
  fileState,
  findExecutable,
  loadPersonaCatalog,
  parseArgs,
  queryCatalog,
  readAsset,
  readJsonFile,
  relativeTarget,
  renderRoleFile,
  runCodex,
  semanticFailures,
  sha256,
  tomlString,
  usage,
} from "./gpt-squad-runtime.mjs";
import {
  managedBlockText,
  roleRegistrationBlock,
  rootStringValue,
  simpleTableValue,
} from "./gpt-squad-config.mjs";
import {
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
} from "./gpt-squad-state.mjs";

function acquireLock(codexHome) {
  for (const legacy of LEGACY_LOCKS) {
    if (fs.existsSync(path.join(codexHome, legacy))) throw new InstallerError(`another squad installer is active: ${legacy}`, 4);
  }
  const target = path.join(codexHome, LOCK_REL);
  fs.mkdirSync(codexHome, { recursive: true, mode: 0o700 });
  try {
    fs.mkdirSync(target, { mode: 0o700 });
  } catch (error) {
    if (error?.code === "EEXIST") throw new InstallerError("another GPT squad operation is active", 4);
    throw error;
  }
  return () => fs.rmSync(target, { recursive: true, force: true });
}

function install(options, codexBin) {
  const release = acquireLock(options.codexHome);
  let backupId = null;
  let compensationStatus = "not-needed";
  try {
    const built = buildDesired(options, codexBin);
    validateStaged(options, codexBin, built.desired);
    backupId = backupIdNow("install");
    const statePath = path.join(options.codexHome, STATE_REL);
    const stateContent = managedStateContent(
      options.codexHome,
      backupId,
      built.desired,
      built.specialists,
      built.catalogPatched,
      built.version,
      built.rootEffortMode,
      built.rootEffort,
    );
    built.desired.set(statePath, { content: stateContent, mode: 0o600 });
    const plannedChanges = planEntries(options.codexHome, built.desired);
    const { backupDir, manifest } = createBackup(options.codexHome, backupId, built.desired);
    try {
      applyDesired(built.desired);
      for (const [target, spec] of built.desired.entries()) {
        if (!desiredMatches(target, spec)) throw new InstallerError(`post-install validation failed: ${relativeTarget(options.codexHome, target)}`, 4);
      }
      const output = runCodex(codexBin, ["debug", "prompt-input", "Read-only GPT squad post-install validation."], options.codexHome);
      const missing = semanticFailures(output, POLICY_REQUIREMENTS);
      if (!output.includes(POLICY_BEGIN) || missing.length) throw new InstallerError("installed prompt did not load the managed squad policy", 4);
    } catch (error) {
      try {
        const entries = validateManifest(backupDir, manifest, options.codexHome, backupId, false);
        restoreEntries(entries, options.codexHome, manifest.createdDirectories);
        compensationStatus = "restored";
      } catch {
        compensationStatus = "incomplete";
      }
      throw new InstallerError("installation failed after backup", 5, {
        backupId,
        applyStatus: "failed",
        compensationStatus,
      });
    }
    return {
      status: "PASS",
      operation: "install",
      backupId,
      applyStatus: "applied",
      compensationStatus,
      specialistCount: built.specialists.length,
      specialists: built.specialists.map((item) => item.name),
      rootEffortMode: built.rootEffortMode,
      rootEffort: built.rootEffort,
      specialistEffort: built.specialistEffort,
      migratedLegacyRootEffort: built.migratedLegacyRootEffort,
      catalogDecision: built.catalogPatched ? "target-derived-v2-compatibility-catalog" : "official-catalog",
      changedPaths: plannedChanges
        .filter((entry) => entry.action !== "unchanged" && entry.action !== "absent")
        .map((entry) => entry.path),
      runtimePromptLoaded: true,
      runtimeChildIdentity: "UNRESOLVED",
    };
  } finally {
    release();
  }
}

function plan(options, codexBin) {
  const built = buildDesired(options, codexBin);
  validateStaged(options, codexBin, built.desired);
  return {
    status: "PASS",
    operation: "plan",
    readOnly: true,
    specialistCount: built.specialists.length,
    specialists: built.specialists.map((item) => item.name),
    rootEffortMode: built.rootEffortMode,
    rootEffort: built.rootEffort,
    specialistEffort: built.specialistEffort,
    migratedLegacyRootEffort: built.migratedLegacyRootEffort,
    catalogDecision: built.catalogPatched ? "target-derived-v2-compatibility-catalog" : "official-catalog",
    changes: planEntries(options.codexHome, built.desired),
    runtimePromptLoaded: true,
    runtimeChildIdentity: "UNRESOLVED",
  };
}

function verify(options, codexBin) {
  assertSafeCodexHome(options.codexHome);
  const statePath = path.join(options.codexHome, STATE_REL);
  const state = readJsonFile(statePath, STATE_REL);
  if (state.schemaVersion !== SCHEMA_VERSION || !Array.isArray(state.managedFiles) || !Array.isArray(state.specialists)) {
    throw new InstallerError("installed state has an unsupported schema", 4);
  }
  const { base, specialists } = loadPersonaCatalog();
  const expectedNames = specialists.map((item) => item.name);
  const allowedRootEffortModes = new Set(["preserve", "auto", "explicit"]);
  if (!allowedRootEffortModes.has(state.rootEffortMode) || state.specialistEffort !== SPECIALIST_EFFORT) {
    throw new InstallerError("installed root effort policy is legacy or specialist effort is stale; rerun install", 4);
  }
  if (state.rootEffortMode === "explicit" && typeof state.rootEffort !== "string") {
    throw new InstallerError("installed explicit root effort is malformed", 4);
  }
  if (JSON.stringify(state.specialists) !== JSON.stringify(expectedNames)) {
    throw new InstallerError("installed specialist catalog is stale", 4);
  }

  for (const specialist of specialists) {
    const target = path.join(options.codexHome, ROLE_DIR_REL, specialist.fileName);
    const current = fileState(target);
    const expected = renderRoleFile(base, specialist);
    if (!current.exists || current.hash !== sha256(Buffer.from(expected)) || current.mode !== 0o600) {
      throw new InstallerError(`specialist profile is stale: ${specialist.name}`, 4);
    }
  }

  const semanticallyVerifiedPaths = new Set(["config.toml", "AGENTS.md"]);
  const failures = [];
  for (const entry of state.managedFiles) {
    if (!entry || typeof entry.path !== "string") {
      failures.push("malformed managed file entry");
      continue;
    }
    const target = path.join(options.codexHome, entry.path);
    assertSafeTarget(options.codexHome, target);
    const current = fileState(target);
    const matches = semanticallyVerifiedPaths.has(entry.path)
      ? !entry.absent && current.exists && current.mode === entry.mode
      : entry.absent
        ? !current.exists
        : current.exists && current.hash === entry.hash && current.mode === entry.mode;
    if (!matches) failures.push(entry.path);
  }
  if (failures.length) {
    throw new InstallerError(`managed files are missing, mode-drifted, or content-drifted: ${failures.join(", ")}`, 4);
  }

  const configText = fs.readFileSync(path.join(options.codexHome, "config.toml"), "utf8");
  if (rootStringValue(configText, "model") !== ROOT_MODEL) {
    throw new InstallerError("root model contract is invalid", 4);
  }
  const installedRootEffort = rootStringValue(configText, "model_reasoning_effort");
  if (state.rootEffortMode === "auto" && installedRootEffort !== null) {
    throw new InstallerError("root reasoning effort policy is invalid", 4);
  }
  if (state.rootEffortMode === "explicit" && installedRootEffort !== state.rootEffort) {
    throw new InstallerError("root reasoning effort policy is invalid", 4);
  }
  queryCatalog(codexBin, installedRootEffort);

  const agentSettings = new Map([
    ["enabled", true],
    ["max_concurrent_threads_per_session", 128],
    ["default_subagent_model", ROOT_MODEL],
    ["default_subagent_reasoning_effort", SPECIALIST_EFFORT],
    ["interrupt_message", true],
  ]);
  const staleAgentSettings = [...agentSettings.entries()]
    .filter(([key, expected]) => simpleTableValue(configText, "agents", key) !== expected)
    .map(([key]) => key);
  if (staleAgentSettings.length) {
    throw new InstallerError(`agent runtime settings are missing or stale: ${staleAgentSettings.join(", ")}`, 4);
  }

  const installedCatalog = rootStringValue(configText, "model_catalog_json");
  if (state.catalogPatched) {
    const expectedCatalog = path.join(
      options.codexHome,
      "model-catalogs",
      `gpt-squad-${state.codexVersion}.json`,
    );
    if (!installedCatalog || path.resolve(installedCatalog) !== expectedCatalog) {
      throw new InstallerError("managed model catalog reference is missing or stale", 4);
    }
  } else if (installedCatalog) {
    const resolved = path.resolve(installedCatalog);
    const directory = path.join(options.codexHome, "model-catalogs");
    const relative = path.relative(directory, resolved);
    const managed = relative && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)
      && /^gpt-squad-.*\.json$/.test(path.basename(relative));
    if (managed) throw new InstallerError("stale managed model catalog reference remains", 4);
  }

  const registrationMissing = specialists.filter((item) => {
    return !configText.includes(`[agents.${item.name}]`)
      || !configText.includes(`description = ${tomlString(item.description)}`)
      || !configText.includes(`./${path.join(ROLE_DIR_REL, item.fileName).replaceAll(path.sep, "/")}`);
  });
  if (registrationMissing.length) {
    throw new InstallerError(`specialist registrations are missing: ${registrationMissing.map((item) => item.name).join(", ")}`, 4);
  }
  for (const legacy of LEGACY_GENERIC_ROLES) {
    if (configText.includes(`[agents.${legacy}]`)) throw new InstallerError(`legacy generic role remains registered: ${legacy}`, 4);
  }

  const developerInstructions = rootStringValue(configText, "developer_instructions") || "";
  const policyMissing = semanticFailures(developerInstructions, POLICY_REQUIREMENTS);
  const bundledPolicy = readAsset(POLICY_FILE).trim();
  assertPolicyRoster(bundledPolicy, specialists, POLICY_FILE);
  const installedPolicy = managedBlockText(developerInstructions, POLICY_BLOCK_VARIANTS, "developer-instructions");
  if (!installedPolicy || installedPolicy.trim() !== bundledPolicy || policyMissing.length) {
    throw new InstallerError(`developer policy is missing or stale: ${policyMissing.join(", ")}`, 4);
  }
  const installedRegistration = managedBlockText(configText, ROLE_BLOCK_VARIANTS, "role-registration");
  if (!installedRegistration || installedRegistration.trim() !== roleRegistrationBlock(specialists).trim()) {
    throw new InstallerError("specialist registration block is stale", 4);
  }

  const agentsText = fs.readFileSync(path.join(options.codexHome, "AGENTS.md"), "utf8");
  const agentsMissing = semanticFailures(agentsText, POLICY_REQUIREMENTS);
  const bundledAgents = readAsset(AGENTS_POLICY_FILE).trim();
  assertPolicyRoster(bundledAgents, specialists, AGENTS_POLICY_FILE);
  const installedAgents = managedBlockText(agentsText, AGENTS_BLOCK_VARIANTS, "AGENTS");
  if (!installedAgents || installedAgents.trim() !== bundledAgents || agentsMissing.length) {
    throw new InstallerError(`AGENTS policy is missing or stale: ${agentsMissing.join(", ")}`, 4);
  }

  const output = runCodex(codexBin, ["debug", "prompt-input", "Read-only GPT squad verification."], options.codexHome);
  const runtimeMissing = semanticFailures(output, POLICY_REQUIREMENTS);
  if (!output.includes(POLICY_BEGIN) || runtimeMissing.length) {
    throw new InstallerError(`runtime prompt did not load the managed squad policy: ${runtimeMissing.join(", ")}`, 4);
  }
  return {
    status: "PASS",
    operation: "verify",
    specialistCount: specialists.length,
    specialists: expectedNames,
    rootEffortMode: state.rootEffortMode,
    rootEffort: installedRootEffort,
    specialistEffort: state.specialistEffort,
    sharedFileVerification: "managed-semantics",
    legacyGenericRolesAbsent: true,
    runtimePromptLoaded: true,
    runtimeChildIdentity: "UNRESOLVED",
  };
}

function rollback(options) {
  assertSafeCodexHome(options.codexHome);
  const release = acquireLock(options.codexHome);
  let preRollbackBackupId = null;
  try {
    const backupDir = path.join(options.codexHome, BACKUP_ROOT_REL, options.backupId);
    const manifest = readJsonFile(path.join(backupDir, "manifest.json"), "backup manifest");
    const entries = validateManifest(backupDir, manifest, options.codexHome, options.backupId, true);

    preRollbackBackupId = backupIdNow("pre-rollback");
    const currentDesired = new Map(entries.map(({ target }) => {
      const current = fileState(target);
      if (!current.exists) return [target, { absent: true }];
      return [target, { content: fs.readFileSync(target, "utf8"), mode: current.mode }];
    }));
    createBackup(options.codexHome, preRollbackBackupId, currentDesired);

    restoreEntries(entries, options.codexHome, manifest.createdDirectories);
    return {
      status: "PASS",
      operation: "rollback",
      backupId: options.backupId,
      preRollbackBackupId,
      restoredPaths: entries.map(({ entry }) => entry.path),
    };
  } catch (error) {
    if (error instanceof InstallerError) {
      error.preRollbackBackupId = preRollbackBackupId;
      throw error;
    }
    throw new InstallerError("rollback apply failed", 5, { preRollbackBackupId });
  } finally {
    release();
  }
}

function emit(result, json) {
  if (json) process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  else process.stdout.write(`${result.status}: ${result.operation}\n`);
}

function errorResult(error, operation) {
  return {
    status: "FAIL",
    operation,
    message: error instanceof InstallerError ? error.message : "unexpected internal failure",
    backupId: error?.backupId ?? null,
    preRollbackBackupId: error?.preRollbackBackupId ?? null,
    applyStatus: error?.applyStatus ?? null,
    compensationStatus: error?.compensationStatus ?? null,
  };
}

async function main() {
  let parsed;
  try {
    parsed = parseArgs(process.argv.slice(2));
    if (parsed.command === "help") {
      process.stdout.write(`${usage()}\n`);
      return;
    }
    const { command, options } = parsed;
    const codexBin = command === "rollback" ? null : findExecutable(options.codexBin);
    const result = command === "plan"
      ? plan(options, codexBin)
      : command === "install"
        ? install(options, codexBin)
        : command === "verify"
          ? verify(options, codexBin)
          : rollback(options);
    emit(result, options.json);
  } catch (error) {
    const operation = parsed?.command || "unknown";
    const json = parsed?.options?.json || process.argv.includes("--json");
    emit(errorResult(error, operation), json);
    process.exitCode = error instanceof InstallerError ? error.exitCode : 1;
  }
}

await main();
