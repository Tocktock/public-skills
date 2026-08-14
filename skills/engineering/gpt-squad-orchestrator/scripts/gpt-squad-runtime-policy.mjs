#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";

const STATE_VERSION = 1;
const MIN_WAIT_SECONDS = 1;
const MAX_WAIT_SECONDS = 60;
const LOCK_TIMEOUT_MS = 5_000;
const STALE_LOCK_MS = 30_000;
const SPECIALISTS = new Set([
  "product_systems",
  "product_design",
  "experience_design",
  "domain_application",
  "data_systems",
  "distributed_systems",
  "integration_evolution",
  "platform_reliability",
  "security_trust",
  "change_review",
  "quality_falsification",
  "performance_economics",
  "codebase_forensics",
  "technical_communication",
]);
const INTERRUPT_REASONS = new Set([
  "user_goal_changed",
  "canonical_context_changed",
  "mission_scope_invalid",
  "duplicate_work",
  "negative_value_wait",
  "specialist_blocked",
  "runtime_failure",
  "superseded_by_successor",
]);
const WAIT_OUTCOMES = new Set([
  "timeout",
  "status-refresh",
  "progress",
  "completed",
  "cancelled",
  "failed",
  "aborted",
]);
const WAIT_RELEASE_REASONS = new Set([
  "result_blocks_integration",
  "user_requested_completion",
  "no_other_root_work",
]);
const INTERRUPT_OUTCOMES = new Set(["completed", "cancelled", "failed", "not-sent"]);
const MAX_INTERRUPT_RECORDS = 256;
const MAX_WAIT_RELEASES_WITHOUT_PROGRESS = 1;
const MAX_STATUS_REFRESHES_WITHOUT_PROGRESS = 1;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

class PolicyError extends Error {
  constructor(message, exitCode = 2) {
    super(message);
    this.exitCode = exitCode;
  }
}

function now() {
  return new Date().toISOString();
}

function parseArgs(argv) {
  if (argv.length === 0) {
    throw new PolicyError("a command is required");
  }
  const command = argv[0];
  const options = new Map();
  for (let index = 1; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      throw new PolicyError(`unexpected argument: ${token}`);
    }
    const key = token.slice(2);
    if (key === "json") {
      options.set(key, true);
      continue;
    }
    const value = argv[index + 1];
    if (value === undefined || value.startsWith("--")) {
      throw new PolicyError(`missing value for --${key}`);
    }
    options.set(key, value);
    index += 1;
  }
  return { command, options };
}

function getOption(options, key, { required = false, defaultValue = undefined } = {}) {
  const value = options.get(key);
  if (value === undefined) {
    if (required) {
      throw new PolicyError(`--${key} is required`);
    }
    return defaultValue;
  }
  return value;
}

function validateId(value, label) {
  if (!SAFE_ID.test(value)) {
    throw new PolicyError(`${label} contains unsupported characters`);
  }
}

function parseForkTurns(value) {
  if (value === undefined || value === "none") {
    return { mode: "none", turns: 0 };
  }
  if (value === "all" || value === "full-history") {
    return { mode: "all", turns: null };
  }
  if (!/^\d+$/.test(value)) {
    throw new PolicyError("fork turns must be none, all, full-history, or an integer from 1 to 20");
  }
  const turns = Number(value);
  if (turns < 1 || turns > 20) {
    throw new PolicyError("bounded fork turns must be between 1 and 20");
  }
  return { mode: "bounded", turns };
}

function sleep(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

function assertNoSymlinkComponents(target) {
  const absolute = path.resolve(target);
  const parsed = path.parse(absolute);
  let current = parsed.root;
  for (const segment of absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, segment);
    if (!fs.existsSync(current)) {
      break;
    }
    if (fs.lstatSync(current).isSymbolicLink()) {
      throw new PolicyError(`managed path contains a symlink: ${current}`);
    }
  }
}

function ensurePrivateDirectory(directory) {
  assertNoSymlinkComponents(directory);
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  assertNoSymlinkComponents(directory);
  fs.chmodSync(directory, 0o700);
}

function assertNotSymlink(target) {
  assertNoSymlinkComponents(target);
}

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

function removeStaleLock(lockFile) {
  try {
    const stat = fs.statSync(lockFile);
    if (Date.now() - stat.mtimeMs < STALE_LOCK_MS) {
      return false;
    }
    let metadata = {};
    try {
      metadata = JSON.parse(fs.readFileSync(lockFile, "utf8"));
    } catch {
      metadata = {};
    }
    if (processIsAlive(Number(metadata.pid))) {
      return false;
    }
    fs.rmSync(lockFile, { force: true });
    return true;
  } catch (error) {
    if (error.code === "ENOENT") {
      return true;
    }
    throw error;
  }
}

function withLock(stateFile, operation) {
  const absolute = path.resolve(stateFile);
  const directory = path.dirname(absolute);
  ensurePrivateDirectory(directory);
  assertNotSymlink(directory);
  assertNotSymlink(absolute);
  const lockFile = `${absolute}.lock`;
  const deadline = Date.now() + LOCK_TIMEOUT_MS;
  let descriptor;
  while (descriptor === undefined) {
    try {
      descriptor = fs.openSync(lockFile, "wx", 0o600);
    } catch (error) {
      if (error.code !== "EEXIST") {
        throw error;
      }
      if (removeStaleLock(lockFile)) {
        continue;
      }
      if (Date.now() >= deadline) {
        throw new PolicyError(`timed out waiting for runtime policy lock: ${lockFile}`, 3);
      }
      sleep(25);
    }
  }
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify({ pid: process.pid, createdAt: now() })}\n`);
    fs.fsyncSync(descriptor);
    return operation(absolute);
  } finally {
    try {
      fs.closeSync(descriptor);
    } finally {
      fs.rmSync(lockFile, { force: true });
    }
  }
}

function emptyState() {
  return {
    schemaVersion: STATE_VERSION,
    agents: {},
    interrupts: [],
    waitReleases: [],
    updatedAt: now(),
  };
}

function readState(stateFile) {
  if (!fs.existsSync(stateFile)) {
    return emptyState();
  }
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  } catch (error) {
    throw new PolicyError(`runtime policy state is invalid JSON: ${error.message}`);
  }
  if (parsed.schemaVersion !== STATE_VERSION || typeof parsed.agents !== "object" || parsed.agents === null) {
    throw new PolicyError("runtime policy state has an unsupported schema");
  }
  if (parsed.interrupts === undefined) {
    parsed.interrupts = [];
  }
  if (!Array.isArray(parsed.interrupts)) {
    throw new PolicyError("runtime policy interrupt history is invalid");
  }
  if (parsed.waitReleases === undefined) {
    parsed.waitReleases = [];
  }
  if (!Array.isArray(parsed.waitReleases)) {
    throw new PolicyError("runtime policy wait-release history is invalid");
  }
  return parsed;
}

function writeState(stateFile, state) {
  state.updatedAt = now();
  const directory = path.dirname(stateFile);
  ensurePrivateDirectory(directory);
  const temporary = path.join(directory, `.${path.basename(stateFile)}.${process.pid}.${Date.now()}.tmp`);
  let published = false;
  const descriptor = fs.openSync(temporary, "wx", 0o600);
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(state, null, 2)}\n`);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  try {
    fs.chmodSync(temporary, 0o600);
    fs.renameSync(temporary, stateFile);
    published = true;
    fs.chmodSync(stateFile, 0o600);
  } finally {
    if (!published) {
      fs.rmSync(temporary, { force: true });
    }
  }
  const directoryDescriptor = fs.openSync(directory, "r");
  try {
    fs.fsyncSync(directoryDescriptor);
  } finally {
    fs.closeSync(directoryDescriptor);
  }
}

function waitReleaseCount(current) {
  const explicit = current.waitReleasesSinceProgress;
  if (Number.isInteger(explicit) && explicit >= 0) return explicit;
  // Version-1 state did not persist this counter. Treat an existing release as
  // consumed until a new progress ID or terminal outcome establishes a fresh epoch.
  return current.lastWaitRelease ? 1 : 0;
}

function statusRefreshCount(current) {
  const explicit = current.statusRefreshesSinceProgress;
  if (Number.isInteger(explicit) && explicit >= 0) return explicit;
  // A second timeout in version-1 state necessarily followed the one permitted
  // status inspection when the old guard was obeyed. Fail closed on upgrade.
  return current.statusRefreshedAfterTimeout || Number(current.consecutiveTimeouts ?? 0) >= 2 ? 1 : 0;
}

function spawnPreflight(options) {
  const agentType = getOption(options, "agent-type");
  const fork = parseForkTurns(getOption(options, "fork-turns", { defaultValue: "none" }));
  if (agentType !== undefined && !SPECIALISTS.has(agentType)) {
    throw new PolicyError(`unregistered specialist: ${agentType}`);
  }
  if (agentType !== undefined && fork.mode === "all") {
    throw new PolicyError(
      "typed specialist and full-history fork are mutually exclusive; use a bounded fork or omit agent type",
    );
  }
  return {
    status: "PASS",
    operation: "spawn-preflight",
    agentType: agentType ?? null,
    forkMode: fork.mode,
    forkTurns: fork.turns,
  };
}

function waitPreflight(options) {
  const stateFile = getOption(options, "state-file", { required: true });
  const agentId = getOption(options, "agent-id", { required: true });
  validateId(agentId, "agent ID");
  const timeout = Number(getOption(options, "timeout-seconds", { required: true }));
  if (!Number.isInteger(timeout) || timeout < MIN_WAIT_SECONDS || timeout > MAX_WAIT_SECONDS) {
    throw new PolicyError(`wait timeout must be an integer from ${MIN_WAIT_SECONDS} to ${MAX_WAIT_SECONDS} seconds`);
  }
  return withLock(stateFile, (absolute) => {
    const state = readState(absolute);
    const current = state.agents[agentId] ?? {};
    if (current.terminal) {
      throw new PolicyError(`agent ${agentId} is already ${current.lastOutcome}`);
    }
    if (current.pendingWait) {
      throw new PolicyError(`agent ${agentId} already has a pending wait`);
    }
    const consecutiveTimeouts = Number(current.consecutiveTimeouts ?? 0);
    const waitReleasesSinceProgress = waitReleaseCount(current);
    if (current.waitBlocked && consecutiveTimeouts >= 2) {
      if (waitReleasesSinceProgress >= MAX_WAIT_RELEASES_WITHOUT_PROGRESS) {
        throw new PolicyError(
          `agent ${agentId} timed out after its bounded wait-release; record real progress with a new progress ID or a terminal outcome before another wait`,
        );
      }
      throw new PolicyError(
        `agent ${agentId} timed out repeatedly; record real progress with a new progress ID, a terminal outcome, or one bounded wait-release before another wait`,
      );
    }
    if (current.waitBlocked && !current.statusRefreshedAfterTimeout) {
      throw new PolicyError(
        `agent ${agentId} timed out; inspect status once before one deliberate retry`,
      );
    }
    state.agents[agentId] = {
      ...current,
      pendingWait: true,
      waitBlocked: false,
      statusRefreshedAfterTimeout: false,
      requestedTimeoutSeconds: timeout,
      waitRequestedAt: now(),
    };
    writeState(absolute, state);
    return {
      status: "PASS",
      operation: "wait-preflight",
      agentId,
      timeoutSeconds: timeout,
      stateFile: absolute,
    };
  });
}

function waitRecord(options) {
  const stateFile = getOption(options, "state-file", { required: true });
  const agentId = getOption(options, "agent-id", { required: true });
  const outcome = getOption(options, "outcome", { required: true });
  const progressId = outcome === "progress"
    ? getOption(options, "progress-id", { required: true })
    : null;
  validateId(agentId, "agent ID");
  if (progressId !== null) validateId(progressId, "progress ID");
  if (!WAIT_OUTCOMES.has(outcome)) {
    throw new PolicyError(`wait outcome must be one of: ${[...WAIT_OUTCOMES].sort().join(", ")}`);
  }
  return withLock(stateFile, (absolute) => {
    const state = readState(absolute);
    const current = state.agents[agentId] ?? {};
    if ((outcome === "timeout" || outcome === "aborted") && !current.pendingWait) {
      throw new PolicyError(`cannot record ${outcome} without a pending wait for ${agentId}`);
    }
    if ((outcome === "status-refresh" || outcome === "progress") && current.pendingWait) {
      throw new PolicyError(`cannot record ${outcome} while agent ${agentId} has a pending wait`);
    }
    if (outcome === "status-refresh" && !current.waitBlocked) {
      throw new PolicyError(`cannot record status refresh before a timeout for ${agentId}`);
    }
    const statusRefreshesSinceProgress = statusRefreshCount(current);
    if (outcome === "status-refresh" && statusRefreshesSinceProgress >= MAX_STATUS_REFRESHES_WITHOUT_PROGRESS) {
      throw new PolicyError(`agent ${agentId} already used its single status inspection; unchanged state cannot authorize another refresh`);
    }
    if (outcome === "progress" && current.lastProgressId === progressId) {
      throw new PolicyError(`progress ID must change before it can reset wait backpressure for ${agentId}`);
    }
    const terminal = outcome === "completed" || outcome === "cancelled" || outcome === "failed";
    const next = {
      ...current,
      pendingWait: false,
      lastOutcome: outcome,
      lastObservedAt: now(),
      terminal,
    };
    if (outcome === "timeout") {
      next.consecutiveTimeouts = Number(current.consecutiveTimeouts ?? 0) + 1;
      next.waitReleasesSinceProgress = waitReleaseCount(current);
      next.statusRefreshesSinceProgress = statusRefreshesSinceProgress;
      next.waitBlocked = true;
      next.statusRefreshedAfterTimeout = false;
    } else if (outcome === "status-refresh") {
      next.statusRefreshesSinceProgress = statusRefreshesSinceProgress + 1;
      next.waitBlocked = Boolean(current.waitBlocked);
      next.statusRefreshedAfterTimeout = Boolean(current.waitBlocked);
    } else if (outcome === "progress") {
      next.consecutiveTimeouts = 0;
      next.waitReleasesSinceProgress = 0;
      next.statusRefreshesSinceProgress = 0;
      next.waitBlocked = false;
      next.statusRefreshedAfterTimeout = false;
      next.lastProgressId = progressId;
    } else if (terminal) {
      next.consecutiveTimeouts = 0;
      next.waitReleasesSinceProgress = 0;
      next.statusRefreshesSinceProgress = 0;
      next.waitBlocked = false;
      next.statusRefreshedAfterTimeout = false;
    } else if (outcome === "aborted") {
      next.waitBlocked = false;
      next.statusRefreshedAfterTimeout = false;
    }
    state.agents[agentId] = next;
    writeState(absolute, state);
    return {
      status: "PASS",
      operation: "wait-record",
      agentId,
      outcome,
      consecutiveTimeouts: Number(next.consecutiveTimeouts ?? 0),
      waitReleasesSinceProgress: Number(next.waitReleasesSinceProgress ?? 0),
      statusRefreshesSinceProgress: Number(next.statusRefreshesSinceProgress ?? 0),
      waitBlocked: Boolean(next.waitBlocked),
      statusRefreshedAfterTimeout: Boolean(next.statusRefreshedAfterTimeout),
      progressId: next.lastProgressId ?? null,
      terminal: next.terminal,
      stateFile: absolute,
    };
  });
}

function waitRelease(options) {
  const stateFile = getOption(options, "state-file", { required: true });
  const agentId = getOption(options, "agent-id", { required: true });
  const reason = getOption(options, "reason", { required: true });
  validateId(agentId, "agent ID");
  if (!WAIT_RELEASE_REASONS.has(reason)) {
    throw new PolicyError(`wait-release reason must be one of: ${[...WAIT_RELEASE_REASONS].sort().join(", ")}`);
  }
  return withLock(stateFile, (absolute) => {
    const state = readState(absolute);
    const current = state.agents[agentId] ?? {};
    if (current.pendingWait) {
      throw new PolicyError(`cannot release wait while agent ${agentId} has a pending wait`);
    }
    if (!current.waitBlocked) {
      throw new PolicyError(`agent ${agentId} is not blocked from waiting`);
    }
    const consecutiveTimeouts = Number(current.consecutiveTimeouts ?? 0);
    if (consecutiveTimeouts < 2) {
      throw new PolicyError(`wait-release is available only after at least two consecutive timeouts for ${agentId}`);
    }
    const waitReleasesSinceProgress = waitReleaseCount(current);
    if (waitReleasesSinceProgress >= MAX_WAIT_RELEASES_WITHOUT_PROGRESS) {
      throw new PolicyError(`agent ${agentId} already used its bounded wait-release; record real progress or a terminal outcome`);
    }
    const record = {
      agentId,
      reason,
      consecutiveTimeouts,
      releaseNumber: waitReleasesSinceProgress + 1,
      releasedAt: now(),
    };
    state.waitReleases = [...state.waitReleases, record].slice(-MAX_INTERRUPT_RECORDS);
    state.agents[agentId] = {
      ...current,
      waitBlocked: false,
      statusRefreshedAfterTimeout: false,
      waitReleasesSinceProgress: waitReleasesSinceProgress + 1,
      lastWaitRelease: record,
    };
    writeState(absolute, state);
    return {
      status: "PASS",
      operation: "wait-release",
      agentId,
      reason,
      waitReleasesSinceProgress: waitReleasesSinceProgress + 1,
      remainingWaitReleasesWithoutProgress: 0,
      stateFile: absolute,
    };
  });
}

function interruptPreflight(options) {
  const stateFile = getOption(options, "state-file", { required: true });
  const agentId = getOption(options, "agent-id", { required: true });
  const reason = getOption(options, "reason", { required: true });
  validateId(agentId, "agent ID");
  if (!INTERRUPT_REASONS.has(reason)) {
    throw new PolicyError(`interrupt reason must be one of: ${[...INTERRUPT_REASONS].sort().join(", ")}`);
  }
  return withLock(stateFile, (absolute) => {
    const state = readState(absolute);
    const current = state.agents[agentId] ?? {};
    if (current.pendingInterrupt) {
      throw new PolicyError(`agent ${agentId} already has a pending interrupt request`);
    }
    const record = { agentId, reason, requestedAt: now() };
    state.interrupts = [...state.interrupts, record].slice(-MAX_INTERRUPT_RECORDS);
    state.agents[agentId] = { ...current, pendingInterrupt: record };
    writeState(absolute, state);
    return {
      status: "PASS",
      operation: "interrupt-preflight",
      agentId,
      reason,
      stateFile: absolute,
    };
  });
}

function interruptRecord(options) {
  const stateFile = getOption(options, "state-file", { required: true });
  const agentId = getOption(options, "agent-id", { required: true });
  const outcome = getOption(options, "outcome", { required: true });
  validateId(agentId, "agent ID");
  if (!INTERRUPT_OUTCOMES.has(outcome)) {
    throw new PolicyError(`interrupt outcome must be one of: ${[...INTERRUPT_OUTCOMES].sort().join(", ")}`);
  }
  return withLock(stateFile, (absolute) => {
    const state = readState(absolute);
    const current = state.agents[agentId] ?? {};
    if (!current.pendingInterrupt) {
      throw new PolicyError(`agent ${agentId} has no pending interrupt request`);
    }
    const completed = { ...current.pendingInterrupt, outcome, completedAt: now() };
    const index = [...state.interrupts].reverse().findIndex(
      (item) => item.agentId === agentId && item.requestedAt === current.pendingInterrupt.requestedAt,
    );
    if (index >= 0) {
      const actualIndex = state.interrupts.length - 1 - index;
      state.interrupts[actualIndex] = completed;
    } else {
      state.interrupts = [...state.interrupts, completed].slice(-MAX_INTERRUPT_RECORDS);
    }
    state.agents[agentId] = { ...current, pendingInterrupt: null, lastInterrupt: completed };
    writeState(absolute, state);
    return {
      status: "PASS",
      operation: "interrupt-record",
      agentId,
      outcome,
      stateFile: absolute,
    };
  });
}

function stateStatus(options) {
  const stateFile = getOption(options, "state-file", { required: true });
  return withLock(stateFile, (absolute) => ({
    status: "PASS",
    operation: "status",
    stateFile: absolute,
    state: readState(absolute),
  }));
}

function emit(result, asJson) {
  if (asJson) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  process.stdout.write(`${result.operation}: ${result.status}\n`);
}

function main(argv = process.argv.slice(2)) {
  let parsed;
  try {
    parsed = parseArgs(argv);
    let result;
    switch (parsed.command) {
      case "spawn-preflight":
        result = spawnPreflight(parsed.options);
        break;
      case "wait-preflight":
        result = waitPreflight(parsed.options);
        break;
      case "wait-record":
        result = waitRecord(parsed.options);
        break;
      case "wait-release":
        result = waitRelease(parsed.options);
        break;
      case "interrupt-preflight":
        result = interruptPreflight(parsed.options);
        break;
      case "interrupt-record":
        result = interruptRecord(parsed.options);
        break;
      case "status":
        result = stateStatus(parsed.options);
        break;
      default:
        throw new PolicyError(`unknown command: ${parsed.command}`);
    }
    emit(result, Boolean(parsed.options.get("json")));
    return 0;
  } catch (error) {
    const policyError = error instanceof PolicyError ? error : new PolicyError(`unexpected error: ${error.message}`, 3);
    const asJson = parsed?.options?.get("json") ?? argv.includes("--json");
    const result = { status: "FAIL", operation: parsed?.command ?? "runtime-policy", message: policyError.message };
    if (asJson) {
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    } else {
      process.stderr.write(`${result.operation}: FAIL\n${result.message}\n`);
    }
    return policyError.exitCode;
  }
}

process.exitCode = main();
