#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const SCHEMA_VERSION = 1;
const LOCK_TIMEOUT_MS = 5_000;
const STALE_LOCK_MS = 30_000;
const DEFAULT_TTL_MINUTES = 360;
const MAX_TTL_MINUTES = 1_440;
const MIN_TTL_MINUTES = 5;
const MAX_ITEMS = 128;
const MAX_REPLIES_PER_ITEM = 32;
const MAX_ITEM_BYTES = 8 * 1024;
const MAX_REPLY_BYTES = 4 * 1024;
const MAX_COMMONS_BYTES = 128 * 1024;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MISSION_ID = /^M\d{2,4}$/;
const ITEM_ID = /^W-\d{6}$/;
const MODES = ["lightweight", "cooperative", "transactional"];
const MODE_LEVEL = new Map(MODES.map((mode, index) => [mode, index]));
const RELATIONSHIPS = new Set(["lead", "advisor", "parallel-owner", "independent-challenger"]);
const WRITE_MODES = new Set(["read-only", "writer"]);
const COMMONS_TYPES = new Set(["question", "hypothesis", "help-request", "coordination"]);
const COLLABORATION_DECISIONS = new Set(["accepted", "reused", "declined"]);
const ITEM_STATUSES = new Set(["open", "resolved", "expired"]);
const SECRET_PATTERNS = [
  ["GitHub token", /(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}/i],
  ["AWS access key", /AKIA[0-9A-Z]{16}/],
  ["private key", /BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY/i],
  ["Bearer token", /(?:Authorization:\s*)?Bearer\s+[A-Za-z0-9._~-]{16,}/i],
  ["Slack token", /xox[baprs]-[A-Za-z0-9-]{10,}/i],
  ["API key", /\bsk-[A-Za-z0-9_-]{20,}\b/],
  ["credential-bearing URL", /\b(?:postgres(?:ql)?|https?):\/\/[^:\s`'"<>/@]+:[^@\s`'"<>]+@/i],
];
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

class CooperationError extends Error {
  constructor(message, exitCode = 2) {
    super(message);
    this.exitCode = exitCode;
  }
}

function now() {
  return new Date().toISOString();
}

function parseArgs(argv) {
  if (argv.length === 0) throw new CooperationError("a command is required");
  const command = argv[0];
  const options = new Map();
  for (let index = 1; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new CooperationError(`unexpected argument: ${token}`);
    const key = token.slice(2);
    if (key === "json") {
      options.set(key, true);
      continue;
    }
    const value = argv[index + 1];
    if (value === undefined || value.startsWith("--")) {
      throw new CooperationError(`missing value for --${key}`);
    }
    options.set(key, value);
    index += 1;
  }
  return { command, options };
}

function getOption(options, key, { required = false, defaultValue = undefined } = {}) {
  const value = options.get(key);
  if (value === undefined) {
    if (required) throw new CooperationError(`--${key} is required`);
    return defaultValue;
  }
  return value;
}

function requiredText(value, label, maxBytes = MAX_ITEM_BYTES) {
  const normalized = String(value ?? "").trim();
  if (!normalized) throw new CooperationError(`${label} must not be empty`);
  const bytes = Buffer.byteLength(normalized);
  if (bytes > maxBytes) throw new CooperationError(`${label} exceeds ${maxBytes} bytes`);
  return normalized;
}

function safeSharedText(value, label, maxBytes = MAX_ITEM_BYTES) {
  const normalized = requiredText(value, label, maxBytes);
  for (const [rule, pattern] of SECRET_PATTERNS) {
    if (pattern.test(normalized)) {
      throw new CooperationError(`${label} contains secret-like content (${rule}); store a redacted reference instead`);
    }
  }
  return normalized;
}

function optionalBoolean(object, key) {
  const value = object[key];
  if (value === undefined) return false;
  if (typeof value !== "boolean") throw new CooperationError(`${key} must be a JSON boolean`);
  return value;
}

function parseInteger(value, label, { minimum, maximum }) {
  if (!/^\d+$/.test(String(value))) throw new CooperationError(`${label} must be an integer`);
  const parsed = Number(value);
  if (parsed < minimum || parsed > maximum) {
    throw new CooperationError(`${label} must be between ${minimum} and ${maximum}`);
  }
  return parsed;
}

function validateSafeId(value, label) {
  if (!SAFE_ID.test(value)) throw new CooperationError(`${label} contains unsupported characters`);
}

function validateActor(value, label = "actor") {
  if (value === "root") return value;
  if (!MISSION_ID.test(value)) throw new CooperationError(`${label} must be root or a mission ID such as M01`);
  return value;
}

function parseParticipants(value) {
  const participants = [...new Set(String(value ?? "").split(",").map((item) => item.trim()).filter(Boolean))].sort();
  if (participants.length === 0) throw new CooperationError("--participants requires at least one mission ID");
  if (participants.length > 16) throw new CooperationError("working commons supports at most 16 participants");
  for (const participant of participants) {
    if (!MISSION_ID.test(participant)) throw new CooperationError(`participant must be a mission ID such as M01: ${participant}`);
  }
  return participants;
}

function validateParticipant(state, value, label = "actor") {
  validateActor(value, label);
  if (value !== "root" && !state.participants.includes(value)) {
    throw new CooperationError(`${label} is not a registered working-commons participant: ${value}`);
  }
  return value;
}

function parseCsv(value, { defaultAll = false } = {}) {
  if (value === undefined || value === null || String(value).trim() === "") {
    return defaultAll ? ["*"] : [];
  }
  if (value === "all" || value === "*") return ["*"];
  const result = [...new Set(String(value).split(",").map((item) => item.trim()).filter(Boolean))];
  for (const item of result) validateActor(item, "audience member");
  return result.sort();
}

function parseJsonFile(file) {
  const absolute = path.resolve(file);
  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) {
    throw new CooperationError(`JSON file does not exist: ${absolute}`);
  }
  try {
    return JSON.parse(fs.readFileSync(absolute, "utf8"));
  } catch (error) {
    throw new CooperationError(`invalid JSON in ${absolute}: ${error.message}`);
  }
}

function assertNoSymlinkComponents(target) {
  const absolute = path.resolve(target);
  const parsed = path.parse(absolute);
  let current = parsed.root;
  for (const segment of absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, segment);
    if (!fs.existsSync(current)) break;
    if (fs.lstatSync(current).isSymbolicLink()) {
      throw new CooperationError(`managed path contains a symlink: ${current}`);
    }
  }
}

function ensurePrivateDirectory(directory) {
  const absolute = path.resolve(directory);
  assertNoSymlinkComponents(absolute);
  const existed = fs.existsSync(absolute);
  if (!existed) fs.mkdirSync(absolute, { recursive: true, mode: 0o700 });
  assertNoSymlinkComponents(absolute);
  const stat = fs.statSync(absolute);
  if (!stat.isDirectory()) throw new CooperationError(`managed path is not a directory: ${absolute}`);
  const mode = stat.mode & 0o777;
  if (existed && (mode & 0o077) !== 0) {
    throw new CooperationError(`existing working-commons directory must already be owner-only; refusing to change permissions: ${absolute}`);
  }
  if (!existed) fs.chmodSync(absolute, 0o700);
  return absolute;
}

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
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
    if (Date.now() - stat.mtimeMs < STALE_LOCK_MS) return false;
    let metadata = {};
    try {
      metadata = JSON.parse(fs.readFileSync(lockFile, "utf8"));
    } catch {
      metadata = {};
    }
    if (processIsAlive(Number(metadata.pid))) return false;
    fs.rmSync(lockFile, { force: true });
    return true;
  } catch (error) {
    if (error.code === "ENOENT") return true;
    throw error;
  }
}

function sleep(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

function withLock(stateFile, operation) {
  const absolute = path.resolve(stateFile);
  const directory = ensurePrivateDirectory(path.dirname(absolute));
  assertNoSymlinkComponents(absolute);
  const lockFile = `${absolute}.lock`;
  const deadline = Date.now() + LOCK_TIMEOUT_MS;
  let descriptor;
  while (descriptor === undefined) {
    try {
      descriptor = fs.openSync(lockFile, "wx", 0o600);
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      if (removeStaleLock(lockFile)) continue;
      if (Date.now() >= deadline) {
        throw new CooperationError(`timed out waiting for working-commons lock: ${lockFile}`, 3);
      }
      sleep(25);
    }
  }
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify({ pid: process.pid, createdAt: now() })}\n`);
    fs.fsyncSync(descriptor);
    return operation(absolute, directory);
  } finally {
    try {
      fs.closeSync(descriptor);
    } finally {
      fs.rmSync(lockFile, { force: true });
    }
  }
}

function atomicWrite(file, content) {
  const directory = ensurePrivateDirectory(path.dirname(file));
  assertNoSymlinkComponents(file);
  const temporary = path.join(directory, `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
  let published = false;
  const descriptor = fs.openSync(temporary, "wx", 0o600);
  try {
    fs.writeFileSync(descriptor, content);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  try {
    fs.renameSync(temporary, file);
    fs.chmodSync(file, 0o600);
    published = true;
  } finally {
    if (!published) fs.rmSync(temporary, { force: true });
  }
  const directoryDescriptor = fs.openSync(directory, "r");
  try {
    fs.fsyncSync(directoryDescriptor);
  } finally {
    fs.closeSync(directoryDescriptor);
  }
}

function canonicalJson(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function commonsFile(workspaceDir) {
  return path.join(path.resolve(workspaceDir), "working-commons.json");
}

function emptyCommons(sessionKey, runId, participants) {
  return {
    schemaVersion: SCHEMA_VERSION,
    sessionKey,
    runId,
    participants,
    binding: false,
    nextItem: 1,
    items: [],
    createdAt: now(),
    updatedAt: now(),
  };
}

function validateCommons(state) {
  if (!state || typeof state !== "object" || state.schemaVersion !== SCHEMA_VERSION) {
    throw new CooperationError("working commons has an unsupported schema");
  }
  validateSafeId(state.sessionKey, "session key");
  validateSafeId(state.runId, "run ID");
  if (!Array.isArray(state.participants) || state.participants.length === 0 || state.participants.length > 16) {
    throw new CooperationError("working commons participants are invalid");
  }
  const participantSet = new Set();
  for (const participant of state.participants) {
    if (!MISSION_ID.test(participant) || participantSet.has(participant)) throw new CooperationError("working commons participants are invalid");
    participantSet.add(participant);
  }
  if (state.binding !== false) throw new CooperationError("working commons must remain explicitly non-binding");
  if (!Number.isInteger(state.nextItem) || state.nextItem < 1) {
    throw new CooperationError("working commons nextItem is invalid");
  }
  if (!Array.isArray(state.items)) throw new CooperationError("working commons items are invalid");
  if (state.items.length > MAX_ITEMS) throw new CooperationError(`working commons exceeds ${MAX_ITEMS} items`);
  const seen = new Set();
  for (const item of state.items) {
    if (!ITEM_ID.test(item.id) || seen.has(item.id)) throw new CooperationError("working commons item IDs are invalid");
    seen.add(item.id);
    validateParticipant(state, item.author, "item author");
    if (![...COMMONS_TYPES, "collaboration-request"].includes(item.type)) {
      throw new CooperationError(`working commons item ${item.id} has an invalid type`);
    }
    if (!ITEM_STATUSES.has(item.status)) throw new CooperationError(`working commons item ${item.id} has an invalid status`);
    safeSharedText(item.text, `working commons item ${item.id} text`);
    if (item.binding !== false) throw new CooperationError(`working commons item ${item.id} must remain non-binding`);
    if (!Array.isArray(item.audience) || item.audience.length === 0) {
      throw new CooperationError(`working commons item ${item.id} has no audience`);
    }
    for (const audienceMember of item.audience) {
      if (audienceMember !== "*") validateParticipant(state, audienceMember, `working commons item ${item.id} audience member`);
    }
    if (!Array.isArray(item.replies) || item.replies.length > MAX_REPLIES_PER_ITEM) {
      throw new CooperationError(`working commons item ${item.id} replies are invalid`);
    }
    for (const reply of item.replies) {
      validateParticipant(state, reply.author, `working commons item ${item.id} reply author`);
      safeSharedText(reply.text, `working commons item ${item.id} reply text`, MAX_REPLY_BYTES);
    }
    if (item.type === "collaboration-request") {
      const request = item.collaborationRequest;
      if (!request || !SPECIALISTS.has(request.specialist) || !WRITE_MODES.has(request.writeMode)) {
        throw new CooperationError(`working commons collaboration request ${item.id} is invalid`);
      }
      for (const [label, value] of [
        ["reason", request.reason],
        ["decision impact", request.decisionImpact],
        ["expected value", request.expectedValue],
        ["surface", request.surface],
      ]) safeSharedText(value, `working commons collaboration request ${item.id} ${label}`);
      if (item.audience.length !== 1 || item.audience[0] !== "root") {
        throw new CooperationError(`working commons collaboration request ${item.id} must be visible only to root`);
      }
    } else if (item.collaborationRequest !== null) {
      throw new CooperationError(`working commons item ${item.id} has unexpected collaboration request data`);
    }
    const createdAt = Date.parse(item.createdAt);
    const expiresAt = Date.parse(item.expiresAt);
    if (!Number.isFinite(createdAt) || !Number.isFinite(expiresAt) || expiresAt <= createdAt) {
      throw new CooperationError(`working commons item ${item.id} timestamps are invalid`);
    }
    if (item.status === "resolved") {
      if (!item.resolution || typeof item.resolution !== "object") throw new CooperationError(`resolved item ${item.id} lacks resolution data`);
      validateParticipant(state, item.resolution.actor, `working commons item ${item.id} resolution actor`);
      safeSharedText(item.resolution.summary, `working commons item ${item.id} resolution summary`);
      if (item.type === "collaboration-request") {
        if (item.resolution.actor !== "root" || !COLLABORATION_DECISIONS.has(item.resolution.decision)) {
          throw new CooperationError(`collaboration request ${item.id} has an invalid root decision`);
        }
      } else if (item.resolution.decision !== null) {
        throw new CooperationError(`non-collaboration item ${item.id} has an unexpected decision`);
      }
    } else if (item.resolution !== null) {
      throw new CooperationError(`non-resolved item ${item.id} must not contain resolution data`);
    }
  }
  const bytes = Buffer.byteLength(canonicalJson(state));
  if (bytes > MAX_COMMONS_BYTES) throw new CooperationError(`working commons exceeds ${MAX_COMMONS_BYTES} bytes`);
  return state;
}

function readCommons(file) {
  if (!fs.existsSync(file)) throw new CooperationError(`working commons is not initialized: ${file}`);
  try {
    return validateCommons(JSON.parse(fs.readFileSync(file, "utf8")));
  } catch (error) {
    if (error instanceof CooperationError) throw error;
    throw new CooperationError(`working commons is invalid JSON: ${error.message}`);
  }
}

function effectiveStatus(item, timestamp = Date.now()) {
  if (item.status !== "open") return item.status;
  return new Date(item.expiresAt).getTime() <= timestamp ? "expired" : "open";
}

function expireItems(state, timestamp = Date.now()) {
  for (const item of state.items) {
    if (effectiveStatus(item, timestamp) === "expired" && item.status === "open") item.status = "expired";
  }
}

function writeCommons(file, state) {
  expireItems(state);
  state.updatedAt = now();
  validateCommons(state);
  atomicWrite(file, canonicalJson(state));
}

function visibleTo(item, viewer) {
  return viewer === "root" || item.author === viewer || item.audience.includes("*") || item.audience.includes(viewer);
}

function itemById(state, itemId) {
  if (!ITEM_ID.test(itemId)) throw new CooperationError("item ID must look like W-000001");
  const item = state.items.find((candidate) => candidate.id === itemId);
  if (!item) throw new CooperationError(`working commons item does not exist: ${itemId}`);
  return item;
}

function normalizeWritePaths(value) {
  if (value === undefined || value === null || value === "") return [];
  const raw = Array.isArray(value) ? value : String(value).split(",");
  return [...new Set(raw.map((item) => String(item).trim()).filter(Boolean).map((item) => {
    const prepared = String(item).normalize("NFC").replaceAll("\\", "/");
    const normalized = path.posix.normalize(prepared).replace(/^\.\//, "").replace(/\/+$/, "");
    if (!normalized || normalized === "." || normalized.startsWith("/") || normalized === ".." || normalized.startsWith("../") || /[*?\[\]{}]/.test(normalized)) {
      throw new CooperationError(`write path must be a concrete safe relative path without globs: ${item}`);
    }
    return normalized;
  }))].sort();
}

function pathsOverlap(left, right) {
  const normalizedLeft = left.toLocaleLowerCase("en-US");
  const normalizedRight = right.toLocaleLowerCase("en-US");
  return normalizedLeft === normalizedRight
    || normalizedLeft.startsWith(`${normalizedRight}/`)
    || normalizedRight.startsWith(`${normalizedLeft}/`);
}

function validateDependencyGraph(missions) {
  const ids = new Set(missions.map((mission) => mission.id));
  const graph = new Map(missions.map((mission) => [mission.id, mission.dependsOn]));
  for (const mission of missions) {
    for (const dependency of mission.dependsOn) {
      if (!ids.has(dependency)) throw new CooperationError(`${mission.id} depends on unknown mission ${dependency}`);
      if (dependency === mission.id) throw new CooperationError(`${mission.id} cannot depend on itself`);
    }
  }
  const visiting = new Set();
  const visited = new Set();
  function visit(id) {
    if (visiting.has(id)) throw new CooperationError(`mission dependency cycle includes ${id}`);
    if (visited.has(id)) return;
    visiting.add(id);
    for (const dependency of graph.get(id) ?? []) visit(dependency);
    visiting.delete(id);
    visited.add(id);
  }
  for (const id of ids) visit(id);
}

function normalizeManifest(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new CooperationError("manifest must be a JSON object");
  const objective = requiredText(raw.objective, "manifest objective");
  const requestedMode = raw.requestedMode ?? "auto";
  if (!["auto", ...MODES].includes(requestedMode)) throw new CooperationError("requestedMode must be auto, lightweight, cooperative, or transactional");
  if (!Array.isArray(raw.missions) || raw.missions.length === 0) throw new CooperationError("manifest requires at least one mission");
  if (raw.missions.length > 16) throw new CooperationError("manifest exceeds the 16-mission coordination limit");
  const seen = new Set();
  const missions = raw.missions.map((mission, index) => {
    if (!mission || typeof mission !== "object" || Array.isArray(mission)) throw new CooperationError(`mission ${index + 1} must be an object`);
    const id = mission.id ?? `M${String(index + 1).padStart(2, "0")}`;
    if (!MISSION_ID.test(id)) throw new CooperationError(`mission ID must look like M01: ${id}`);
    if (seen.has(id)) throw new CooperationError(`duplicate mission ID: ${id}`);
    seen.add(id);
    if (!SPECIALISTS.has(mission.specialist)) throw new CooperationError(`unregistered specialist: ${mission.specialist}`);
    const relationship = mission.relationship ?? (index === 0 ? "lead" : "advisor");
    if (!RELATIONSHIPS.has(relationship)) throw new CooperationError(`invalid relationship for ${id}: ${relationship}`);
    const writeMode = mission.writeMode ?? "read-only";
    if (!WRITE_MODES.has(writeMode)) throw new CooperationError(`invalid write mode for ${id}: ${writeMode}`);
    if (mission.dependsOn !== undefined && !Array.isArray(mission.dependsOn)) throw new CooperationError(`${id} dependsOn must be an array`);
    const dependsOn = [...new Set((mission.dependsOn ?? []).map(String))].sort();
    const writePaths = normalizeWritePaths(mission.writePaths ?? mission.surface ?? []);
    return {
      id,
      specialist: mission.specialist,
      relationship,
      objective: requiredText(mission.objective, `${id} objective`),
      distinctValue: requiredText(mission.distinctValue, `${id} distinctValue`),
      writeMode,
      writePaths,
      dependsOn,
      reused: optionalBoolean(mission, "reused"),
      staleContextRisk: optionalBoolean(mission, "staleContextRisk"),
    };
  });
  validateDependencyGraph(missions);
  const writers = missions.filter((mission) => mission.writeMode === "writer");
  for (const writer of writers) {
    if (writers.length > 1 && writer.writePaths.length === 0) {
      throw new CooperationError(`${writer.id} is a parallel writer without structured writePaths`);
    }
  }
  for (let leftIndex = 0; leftIndex < writers.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < writers.length; rightIndex += 1) {
      for (const left of writers[leftIndex].writePaths) {
        for (const right of writers[rightIndex].writePaths) {
          if (pathsOverlap(left, right)) {
            throw new CooperationError(`writer path collision: ${writers[leftIndex].id} (${left}) and ${writers[rightIndex].id} (${right})`);
          }
        }
      }
    }
  }
  return {
    objective,
    requestedMode,
    missions,
    sharedContractsMayChange: optionalBoolean(raw, "sharedContractsMayChange"),
    canonicalStateMayChange: optionalBoolean(raw, "canonicalStateMayChange"),
    multiWave: optionalBoolean(raw, "multiWave"),
    provisionalSharing: optionalBoolean(raw, "provisionalSharing"),
    peerQuestionsExpected: optionalBoolean(raw, "peerQuestionsExpected"),
    staleContextRisk: optionalBoolean(raw, "staleContextRisk") || missions.some((mission) => mission.staleContextRisk),
    externalOrIrreversible: optionalBoolean(raw, "externalOrIrreversible"),
  };
}

function coordinationPlan(manifest) {
  const transactionalReasons = [];
  const cooperativeReasons = [];
  if (manifest.sharedContractsMayChange) transactionalReasons.push("shared contracts may change");
  if (manifest.canonicalStateMayChange) transactionalReasons.push("accepted cross-mission state may change");
  if (manifest.multiWave) transactionalReasons.push("work spans multiple waves");
  if (manifest.staleContextRisk) transactionalReasons.push("reused context may be stale");
  if (manifest.missions.some((mission) => mission.dependsOn.length > 0)) transactionalReasons.push("mission dependencies exist");
  if (manifest.missions.some((mission) => mission.relationship === "independent-challenger")) transactionalReasons.push("an independent challenge requires sealed evidence and disposition");
  if (manifest.missions.filter((mission) => mission.writeMode === "writer").length > 1) transactionalReasons.push("parallel writers require ownership and integration control");
  if (manifest.provisionalSharing) cooperativeReasons.push("specialists need provisional shared notes");
  if (manifest.peerQuestionsExpected) cooperativeReasons.push("peer clarification is expected");

  let minimumMode = "lightweight";
  if (transactionalReasons.length > 0) minimumMode = "transactional";
  else if (cooperativeReasons.length > 0) minimumMode = "cooperative";

  const requestedMode = manifest.requestedMode === "auto" ? minimumMode : manifest.requestedMode;
  if (MODE_LEVEL.get(requestedMode) < MODE_LEVEL.get(minimumMode)) {
    throw new CooperationError(`requested coordination mode ${requestedMode} is below the safe minimum ${minimumMode}`);
  }
  const warnings = [];
  if (MODE_LEVEL.get(requestedMode) > MODE_LEVEL.get(minimumMode)) {
    warnings.push(`requested mode ${requestedMode} adds more ceremony than the minimum ${minimumMode}`);
  }
  const leads = manifest.missions.filter((mission) => mission.relationship === "lead");
  if (leads.length === 0) warnings.push("no lead is declared; root should confirm who owns the coherent outcome");
  if (leads.length > 1) warnings.push("multiple leads are allowed but require an explicit integration boundary");
  const values = new Map();
  for (const mission of manifest.missions) {
    const key = mission.distinctValue.toLowerCase();
    if (values.has(key)) warnings.push(`${mission.id} duplicates the distinct decision value of ${values.get(key)}`);
    else values.set(key, mission.id);
  }
  const writers = manifest.missions.filter((mission) => mission.writeMode === "writer");
  if (writers.length === 1 && manifest.missions.length > 1) {
    warnings.push("one writer plus independent read-only missions may remain lightweight only while no binding state or dependency crosses mission boundaries");
  }
  if (writers.length === 1 && writers[0].writePaths.length === 0) {
    warnings.push(`${writers[0].id} is the only writer but has no structured write path; root must still make ownership concrete before dispatch`);
  }
  if (manifest.externalOrIrreversible) warnings.push("external or irreversible actions remain root-controlled regardless of coordination mode");

  return {
    status: "PASS",
    operation: "plan",
    objective: manifest.objective,
    requestedMode: manifest.requestedMode,
    minimumMode,
    coordinationMode: requestedMode,
    reasons: minimumMode === "transactional" ? transactionalReasons : minimumMode === "cooperative" ? cooperativeReasons : ["missions are independently bounded and do not share mutable truth"],
    warnings,
    contextHubRequired: requestedMode === "transactional",
    workingCommonsRecommended: requestedMode === "cooperative" || requestedMode === "transactional",
    rootAuthority: [
      "user intent and final acceptance",
      "cross-mission canonical promotion",
      "writer ownership and integration",
      "external, destructive, credential-bearing, or irreversible actions",
    ],
    autonomyContract: "Specialists own the outcome and choose the method inside their authority envelope; specialty is an attention prior, not a capability boundary.",
    escalationTriggers: [
      "a provisional item changes another mission's behavior",
      "a shared fact, decision, invariant, ownership boundary, or material risk becomes binding",
      "shared contracts or writer ownership change",
      "a reused specialist may be stale",
      "independent challenge or multi-wave acceptance is required",
    ],
    missions: manifest.missions.map((mission) => ({
      ...mission,
      authority: "end-to-end inside the declared mission envelope",
      canonicalizationRule: "Local decisions stay local. Escalate only information that changes another mission, a shared contract, ownership, risk acceptance, or final acceptance.",
    })),
  };
}

function commandPlan(options) {
  const manifest = normalizeManifest(parseJsonFile(getOption(options, "manifest", { required: true })));
  return coordinationPlan(manifest);
}

function commandCommonsInit(options) {
  const workspaceDir = ensurePrivateDirectory(getOption(options, "workspace-dir", { required: true }));
  const sessionKey = getOption(options, "session-key", { required: true });
  const runId = getOption(options, "run-id", { required: true });
  const participants = parseParticipants(getOption(options, "participants", { required: true }));
  validateSafeId(sessionKey, "session key");
  validateSafeId(runId, "run ID");
  const file = commonsFile(workspaceDir);
  return withLock(file, (absolute) => {
    if (fs.existsSync(absolute)) {
      const existing = readCommons(absolute);
      if (existing.sessionKey !== sessionKey || existing.runId !== runId) {
        throw new CooperationError("working commons already belongs to a different session or run");
      }
      if (JSON.stringify(existing.participants) !== JSON.stringify(participants)) {
        throw new CooperationError("working commons participants differ from the initialized participant set");
      }
      return { status: "PASS", operation: "commons-init", created: false, workspaceDir, participants, stateFile: absolute };
    }
    writeCommons(absolute, emptyCommons(sessionKey, runId, participants));
    return { status: "PASS", operation: "commons-init", created: true, workspaceDir, participants, stateFile: absolute };
  });
}

function buildItem(state, { author, type, text, audience, ttlMinutes, request = null }) {
  const id = `W-${String(state.nextItem).padStart(6, "0")}`;
  state.nextItem += 1;
  const createdAt = now();
  return {
    id,
    type,
    author,
    audience,
    text,
    binding: false,
    status: "open",
    createdAt,
    expiresAt: new Date(Date.now() + ttlMinutes * 60_000).toISOString(),
    replies: [],
    resolution: null,
    collaborationRequest: request,
  };
}

function commandCommonsPost(options) {
  const file = commonsFile(getOption(options, "workspace-dir", { required: true }));
  const author = validateActor(getOption(options, "author", { required: true }), "author");
  const type = getOption(options, "type", { required: true });
  if (!COMMONS_TYPES.has(type)) {
    throw new CooperationError(`commons type must be one of: ${[...COMMONS_TYPES].sort().join(", ")}; binding facts and decisions belong in the Context Hub`);
  }
  const text = safeSharedText(getOption(options, "text", { required: true }), "item text");
  const audience = parseCsv(getOption(options, "audience"), { defaultAll: true });
  const ttlMinutes = parseInteger(getOption(options, "ttl-minutes", { defaultValue: String(DEFAULT_TTL_MINUTES) }), "TTL minutes", { minimum: MIN_TTL_MINUTES, maximum: MAX_TTL_MINUTES });
  return withLock(file, (absolute) => {
    const state = readCommons(absolute);
    validateParticipant(state, author, "author");
    for (const member of audience) if (member !== "*") validateParticipant(state, member, "audience member");
    expireItems(state);
    if (state.items.length >= MAX_ITEMS) throw new CooperationError(`working commons reached the ${MAX_ITEMS}-item limit; compact it before posting`);
    const item = buildItem(state, { author, type, text, audience, ttlMinutes });
    state.items.push(item);
    writeCommons(absolute, state);
    return {
      status: "PASS",
      operation: "commons-post",
      item,
      stateFile: absolute,
      canonicalWarning: "This item is provisional and non-binding. Promote it through the Context Hub before it changes another mission or final acceptance.",
    };
  });
}

function commandCollaborationRequest(options) {
  const file = commonsFile(getOption(options, "workspace-dir", { required: true }));
  const author = validateActor(getOption(options, "author", { required: true }), "author");
  if (author === "root") throw new CooperationError("collaboration-request is for a specialist to request help; root may compose the squad directly");
  const specialist = getOption(options, "specialist", { required: true });
  if (!SPECIALISTS.has(specialist)) throw new CooperationError(`unregistered specialist: ${specialist}`);
  const reason = safeSharedText(getOption(options, "reason", { required: true }), "request reason");
  const decisionImpact = safeSharedText(getOption(options, "decision-impact", { required: true }), "decision impact");
  const expectedValue = safeSharedText(getOption(options, "expected-value", { required: true }), "expected value");
  const surface = safeSharedText(getOption(options, "surface", { required: true }), "responsibility surface");
  const writeMode = getOption(options, "write-mode", { defaultValue: "read-only" });
  if (!WRITE_MODES.has(writeMode)) throw new CooperationError(`write mode must be one of: ${[...WRITE_MODES].join(", ")}`);
  const ttlMinutes = parseInteger(getOption(options, "ttl-minutes", { defaultValue: String(DEFAULT_TTL_MINUTES) }), "TTL minutes", { minimum: MIN_TTL_MINUTES, maximum: MAX_TTL_MINUTES });
  const request = { specialist, reason, decisionImpact, expectedValue, surface, writeMode };
  return withLock(file, (absolute) => {
    const state = readCommons(absolute);
    validateParticipant(state, author, "author");
    expireItems(state);
    if (state.items.length >= MAX_ITEMS) throw new CooperationError(`working commons reached the ${MAX_ITEMS}-item limit; compact it before requesting collaboration`);
    const item = buildItem(state, {
      author,
      type: "collaboration-request",
      text: `Request ${specialist}: ${reason}`,
      audience: ["root"],
      ttlMinutes,
      request,
    });
    state.items.push(item);
    writeCommons(absolute, state);
    return {
      status: "PASS",
      operation: "collaboration-request",
      item,
      stateFile: absolute,
      rootDecisionRequired: true,
      nextStep: "Root should compare distinct value with coordination cost, inspect reachable specialists, and resolve this request as accepted, reused, or declined.",
    };
  });
}

function commandCommonsReply(options) {
  const file = commonsFile(getOption(options, "workspace-dir", { required: true }));
  const author = validateActor(getOption(options, "author", { required: true }), "author");
  const itemId = getOption(options, "item-id", { required: true });
  const text = safeSharedText(getOption(options, "text", { required: true }), "reply text", MAX_REPLY_BYTES);
  return withLock(file, (absolute) => {
    const state = readCommons(absolute);
    validateParticipant(state, author, "author");
    expireItems(state);
    const item = itemById(state, itemId);
    if (!visibleTo(item, author)) throw new CooperationError(`${author} is not allowed to read or reply to ${itemId}`);
    if (item.status !== "open") throw new CooperationError(`cannot reply to ${item.status} item ${itemId}`);
    if (item.replies.length >= MAX_REPLIES_PER_ITEM) throw new CooperationError(`${itemId} reached the ${MAX_REPLIES_PER_ITEM}-reply limit`);
    const reply = { author, text, createdAt: now() };
    item.replies.push(reply);
    writeCommons(absolute, state);
    return { status: "PASS", operation: "commons-reply", itemId, reply, stateFile: absolute };
  });
}

function commandCommonsResolve(options) {
  const file = commonsFile(getOption(options, "workspace-dir", { required: true }));
  const actor = validateActor(getOption(options, "actor", { required: true }), "actor");
  const itemId = getOption(options, "item-id", { required: true });
  const summary = safeSharedText(getOption(options, "summary", { required: true }), "resolution summary");
  const decision = getOption(options, "decision");
  return withLock(file, (absolute) => {
    const state = readCommons(absolute);
    validateParticipant(state, actor, "actor");
    expireItems(state);
    const item = itemById(state, itemId);
    if (item.status !== "open") throw new CooperationError(`cannot resolve ${item.status} item ${itemId}`);
    if (item.type === "collaboration-request") {
      if (actor !== "root") throw new CooperationError("only root may resolve a collaboration request");
      if (!COLLABORATION_DECISIONS.has(decision)) {
        throw new CooperationError(`collaboration request resolution requires --decision ${[...COLLABORATION_DECISIONS].join("|")}`);
      }
    } else {
      if (decision !== undefined) throw new CooperationError("--decision is only valid for collaboration requests");
      if (actor !== "root" && actor !== item.author) throw new CooperationError("only root or the item author may resolve this item");
    }
    item.status = "resolved";
    item.resolution = { actor, summary, decision: decision ?? null, resolvedAt: now() };
    writeCommons(absolute, state);
    return {
      status: "PASS",
      operation: "commons-resolve",
      item,
      stateFile: absolute,
      canonicalWarning: "Resolution is still non-binding. Record any accepted cross-mission fact, decision, ownership change, or risk disposition in the Context Hub.",
    };
  });
}

function commandCommonsList(options) {
  const file = commonsFile(getOption(options, "workspace-dir", { required: true }));
  const viewer = validateActor(getOption(options, "viewer", { required: true }), "viewer");
  const requestedStatus = getOption(options, "status", { defaultValue: "open" });
  if (![...ITEM_STATUSES, "all"].includes(requestedStatus)) throw new CooperationError("status must be open, resolved, expired, or all");
  assertNoSymlinkComponents(file);
  const state = readCommons(file);
  validateParticipant(state, viewer, "viewer");
  const timestamp = Date.now();
  const visibleItems = state.items
    .map((item) => ({ ...item, status: effectiveStatus(item, timestamp) }))
    .filter((item) => visibleTo(item, viewer));
  const items = visibleItems.filter((item) => requestedStatus === "all" || item.status === requestedStatus);
  return {
    status: "PASS",
    operation: "commons-list",
    viewer,
    sessionKey: state.sessionKey,
    runId: state.runId,
    items,
    counts: Object.fromEntries([...ITEM_STATUSES].map((status) => [status, visibleItems.filter((item) => item.status === status).length])),
    canonicalWarning: "Working Commons is provisional. It is not accepted truth or final evidence.",
  };
}

function commandCommonsCompact(options) {
  const file = commonsFile(getOption(options, "workspace-dir", { required: true }));
  const actor = validateActor(getOption(options, "actor", { required: true }), "actor");
  if (actor !== "root") throw new CooperationError("only root may compact the working commons");
  const olderThanMinutes = parseInteger(getOption(options, "older-than-minutes", { defaultValue: "60" }), "older-than minutes", { minimum: 0, maximum: 43_200 });
  return withLock(file, (absolute) => {
    const state = readCommons(absolute);
    expireItems(state);
    const cutoff = Date.now() - olderThanMinutes * 60_000;
    const removed = [];
    state.items = state.items.filter((item) => {
      if (item.status === "open") return true;
      const terminalAt = item.resolution?.resolvedAt ?? item.expiresAt;
      if (new Date(terminalAt).getTime() > cutoff) return true;
      removed.push(item.id);
      return false;
    });
    writeCommons(absolute, state);
    return { status: "PASS", operation: "commons-compact", removed, remaining: state.items.length, stateFile: absolute };
  });
}

function emit(result, asJson) {
  if (asJson) process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  else process.stdout.write(`${result.operation}: ${result.status}\n`);
}

function main(argv = process.argv.slice(2)) {
  let parsed;
  try {
    parsed = parseArgs(argv);
    let result;
    switch (parsed.command) {
      case "plan": result = commandPlan(parsed.options); break;
      case "commons-init": result = commandCommonsInit(parsed.options); break;
      case "commons-post": result = commandCommonsPost(parsed.options); break;
      case "collaboration-request": result = commandCollaborationRequest(parsed.options); break;
      case "commons-reply": result = commandCommonsReply(parsed.options); break;
      case "commons-resolve": result = commandCommonsResolve(parsed.options); break;
      case "commons-list": result = commandCommonsList(parsed.options); break;
      case "commons-compact": result = commandCommonsCompact(parsed.options); break;
      default: throw new CooperationError(`unknown command: ${parsed.command}`);
    }
    emit(result, Boolean(parsed.options.get("json")));
    return 0;
  } catch (error) {
    const cooperationError = error instanceof CooperationError ? error : new CooperationError(`unexpected error: ${error.message}`, 3);
    const asJson = parsed?.options?.get("json") ?? argv.includes("--json");
    const result = { status: "FAIL", operation: parsed?.command ?? "cooperation", message: cooperationError.message };
    if (asJson) process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    else process.stderr.write(`${result.operation}: FAIL\n${result.message}\n`);
    return cooperationError.exitCode;
  }
}

process.exitCode = main();
