import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");
const ASSET_DIR = path.join(SKILL_DIR, "assets");
const PERSONA_DIR = path.join(ASSET_DIR, "personas");

const ROOT_MODEL = "gpt-5.6-sol";
const SPECIALIST_EFFORT = "high";
const ROLE_DIR_REL = path.join("agents", "gpt-squad");
const STATE_REL = path.join("gpt-squad-installer", "state.json");
const LEGACY_STATE_REL = path.join("sol-sol-squad-installer", "state.json");
const BACKUP_ROOT_REL = path.join("backups", "gpt-squad");
const LOCK_REL = ".gpt-squad-installer.lock";
const LEGACY_LOCKS = [".sol-sol-squad-installer.lock", ".sol-luna-squad-installer.lock"];
const LEGACY_PROFILE_FILE = "sol-sol-squad.config.toml";
const CATALOG_FILE = "persona-catalog.json";
const BASE_PROMPT_FILE = "elite-specialist-base.md";
const POLICY_FILE = "squad-policy.txt";
const AGENTS_POLICY_FILE = "agents-policy.md";
const SCHEMA_VERSION = 2;

const ROLE_BLOCK_VARIANTS = [
  { begin: "# BEGIN GPT-SQUAD SPECIALISTS", end: "# END GPT-SQUAD SPECIALISTS" },
  { begin: "# BEGIN SOL-SOL-SQUAD ROLES", end: "# END SOL-SOL-SQUAD ROLES" },
  { begin: "# BEGIN SOL-LUNA-SQUAD ROLES", end: "# END SOL-LUNA-SQUAD ROLES" },
];
const POLICY_BLOCK_VARIANTS = [
  { begin: "[GPT_SQUAD_POLICY_BEGIN]", end: "[GPT_SQUAD_POLICY_END]" },
  { begin: "[SOL_SOL_SQUAD_POLICY_BEGIN]", end: "[SOL_SOL_SQUAD_POLICY_END]" },
  { begin: "[SOL_LUNA_SQUAD_POLICY_BEGIN]", end: "[SOL_LUNA_SQUAD_POLICY_END]" },
];
const AGENTS_BLOCK_VARIANTS = [
  { begin: "<!-- BEGIN GPT-SQUAD MANAGED -->", end: "<!-- END GPT-SQUAD MANAGED -->" },
  { begin: "<!-- BEGIN SOL-SOL-SQUAD MANAGED -->", end: "<!-- END SOL-SOL-SQUAD MANAGED -->" },
  { begin: "<!-- BEGIN SOL-LUNA-SQUAD MANAGED -->", end: "<!-- END SOL-LUNA-SQUAD MANAGED -->" },
];
const POLICY_BEGIN = POLICY_BLOCK_VARIANTS[0].begin;
const POLICY_END = POLICY_BLOCK_VARIANTS[0].end;
const ROLE_BLOCK_BEGIN = ROLE_BLOCK_VARIANTS[0].begin;
const ROLE_BLOCK_END = ROLE_BLOCK_VARIANTS[0].end;
const AGENTS_BLOCK_BEGIN = AGENTS_BLOCK_VARIANTS[0].begin;
const AGENTS_BLOCK_END = AGENTS_BLOCK_VARIANTS[0].end;

const LEGACY_GENERIC_ROLES = [
  "sol_pathfinder",
  "sol_architect",
  "sol_builder",
  "sol_verifier",
  "sol_sentinel",
];
const LEGACY_GENERIC_ROLE_PATHS = LEGACY_GENERIC_ROLES.map(
  (name) => path.join("agents", "sol-sol", `${name.replaceAll("_", "-")}.toml`),
);

const BASE_PROMPT_SECTIONS = [
  "Identity:",
  "Autonomy:",
  "Cost discipline:",
  "Collaboration:",
  "Independent challenge:",
  "Completion standard:",
  "Hard boundaries:",
  "Reporting:",
];
const PERSONA_PROMPT_SECTIONS = [
  "Home field:",
  "Focus map:",
  "High-value evidence:",
  "Decision principles:",
  "Completion standard:",
];
const POLICY_REQUIREMENTS = [
  ["session-persistent explicit opt-in", /session-persistent explicit opt-in|Session-Persistent Explicit Opt-In/i],
  ["dormant at session start", /dormant when a new Codex task or conversation session begins|dormant when a new Codex task/i],
  ["collaboration tools gated", /Do not call `list_agents`, `spawn_agent`, `followup_task`, `wait_agent`, or `send_message`[\s\S]*while squad mode is dormant/i],
  ["explicit first activation", /Activate squad mode when a user request in the current Codex session explicitly/i],
  ["complexity is not activation", /Task complexity alone is not activation before/i],
  ["session persistence", /remains active for later user turns in the same Codex session until the user explicitly opts out or the session ends/i],
  ["no repeated activation", /Do not require (?:the user to repeat GPT Squad on every turn|repeated activation)/i],
  ["unscoped session opt-out", /unscoped[\s\S]*deactivates squad mode[\s\S]*current session/i],
  ["request-scoped pause", /request-scoped opt-out pauses only that request|limits the opt-out to the current request[\s\S]*pause squad use only for that request/i],
  ["new session dormant", /Every new Codex session begins dormant/i],
  ["orchestrator skill", /gpt-squad-orchestrator/i],
  ["chief engineer", /Chief Engineer/i],
  ["initial delegation expectation", /activat(?:es|ing) or reactivat(?:es|ing)[\s\S]*expectation to delegate/i],
  ["smallest sufficient squad", /smallest sufficient squad/i],
  ["active root-only economy", /Trivial, (?:genuinely )?inseparable, or negative-value delegation work may (?:remain|stay) root-only without deactivating/i],
  ["elite generalist attention prior", /elite generalist[\s\S]*attention prior/i],
  ["end-to-end method autonomy", /choose (?:its|their) method[\s\S]*investigate[\s\S]*design[\s\S]*implement[\s\S]*test[\s\S]*document/i],
  ["right-sized coordination", /least coordination intensity[\s\S]*lightweight[\s\S]*cooperative[\s\S]*transactional/i],
  ["non-binding working commons", /(?:Working Commons[\s\S]*non-binding|non-binding[\s\S]*Working Commons)/i],
  ["participant-bound commons", /participant-bound/i],
  ["secret-rejecting commons", /secret-rejecting/i],
  ["canonical promotion threshold", /(?:Do not promote every local finding|smallest sufficient (?:canonical )?statement|Promote only information that can change)/i],
  ["direct communication boundary", /No accepted fact, decision, invariant, ownership change, dependency, or risk disposition may exist only/i],
  ["specialist collaboration request", /structured collaboration request/i],
  ["holistic adversarial review", /change_review[\s\S]*acceptance[\s\S]*adversarial[\s\S]*quality_falsification/i],
  ["active-session reuse", /active session[\s\S]*list_agents[\s\S]*followup_task/i],
  ["stale-context checkout refresh", /fresh Context Hub checkout[\s\S]*stale|checkout is authoritative[\s\S]*Shared Context Ledger revision/i],
  ["spawn schema safety", /never combine mutually exclusive (?:spawn )?parameters/i],
  ["wave wait discipline", /After the first timeout[\s\S]*inspect status once[\s\S]*deliberate retry[\s\S]*wait-release/i],
  ["wait-call failure recovery", /record an `aborted` outcome/i],
  ["interrupt outcome accounting", /structured reason and recorded outcome/i],
  ["writer safety", /Concurrent writers require disjoint/i],
  ["no recursive agents", /cannot recursively create agents/i],
  ["write authority", /Write capability is not standing permission/i],
  ["root final accountability", /final accountability/i],
];

class InstallerError extends Error {
  constructor(message, exitCode = 3, details = {}) {
    super(message);
    this.exitCode = exitCode;
    Object.assign(this, details);
  }
}

function usage() {
  return `Usage:
  node scripts/gpt-squad.mjs plan [options]
  node scripts/gpt-squad.mjs install [options]
  node scripts/gpt-squad.mjs verify [options]
  node scripts/gpt-squad.mjs rollback --backup-id ID [options]

Options:
  --codex-home PATH       Target Codex home (default: CODEX_HOME or ~/.codex)
  --codex-bin PATH        Codex CLI (default: PATH or Desktop bundle)
  --root-model MODEL      Compatibility assertion; must be ${ROOT_MODEL}
  --root-effort EFFORT    Optional explicit root effort, or "auto" to leave it unpinned
  --backup-id ID          Backup generation to restore
  --json                  Emit one redacted JSON result
  -h, --help              Show this help`;
}

function parseArgs(argv) {
  const args = [...argv];
  const command = args.shift();
  if (!command || command === "-h" || command === "--help") return { command: "help" };
  if (!["plan", "install", "verify", "rollback"].includes(command)) {
    throw new InstallerError(`unknown command: ${command}`, 2);
  }
  const options = {
    codexHome: path.resolve(process.env.CODEX_HOME || path.join(os.homedir(), ".codex")),
    codexBin: null,
    rootModel: ROOT_MODEL,
    rootEffortMode: "preserve",
    rootEffort: null,
    backupId: null,
    json: false,
  };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const next = () => {
      index += 1;
      if (index >= args.length) throw new InstallerError(`${arg} requires a value`, 2);
      return args[index];
    };
    if (arg === "--codex-home") options.codexHome = path.resolve(next());
    else if (arg === "--codex-bin") options.codexBin = path.resolve(next());
    else if (arg === "--root-model") options.rootModel = next();
    else if (arg === "--root-effort") {
      const value = next();
      if (value === "auto") {
        options.rootEffortMode = "auto";
        options.rootEffort = null;
      } else {
        options.rootEffortMode = "explicit";
        options.rootEffort = value;
      }
    }
    else if (arg === "--backup-id") options.backupId = next();
    else if (arg === "--json") options.json = true;
    else if (arg === "-h" || arg === "--help") return { command: "help" };
    else throw new InstallerError(`unknown option: ${arg}`, 2);
  }
  if (options.rootModel !== ROOT_MODEL) throw new InstallerError(`--root-model must be ${ROOT_MODEL}`, 2);
  if (options.rootEffortMode === "explicit" && !/^[a-z][a-z0-9_-]*$/.test(options.rootEffort || "")) {
    throw new InstallerError("--root-effort must be a reasoning effort name or auto", 2);
  }
  if (command === "rollback" && !options.backupId) throw new InstallerError("rollback requires --backup-id", 2);
  return { command, options };
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function normalizeText(text) {
  const normalized = String(text).replaceAll("\r\n", "\n");
  return normalized.endsWith("\n") ? normalized : `${normalized}\n`;
}

function tomlString(value) {
  return JSON.stringify(value);
}

function lstatIfExists(target) {
  try {
    return fs.lstatSync(target);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function fileState(target) {
  const stat = lstatIfExists(target);
  if (!stat) return { exists: false, hash: null, mode: null };
  if (stat.isSymbolicLink() || !stat.isFile()) throw new InstallerError(`unsafe non-file target: ${target}`, 4);
  return {
    exists: true,
    hash: sha256(fs.readFileSync(target)),
    mode: stat.mode & 0o777,
  };
}

function readJsonFile(target, label) {
  try {
    return JSON.parse(fs.readFileSync(target, "utf8"));
  } catch {
    throw new InstallerError(`${label} is missing or malformed`, 4);
  }
}

function readAsset(relative) {
  const target = path.join(ASSET_DIR, relative);
  const stat = lstatIfExists(target);
  if (!stat?.isFile() || stat.isSymbolicLink()) throw new InstallerError(`invalid bundled asset: ${relative}`, 4);
  const text = normalizeText(fs.readFileSync(target, "utf8"));
  if (/\[(?:mcp_servers|projects)(?:\.|\])|(?:TOKEN|PASSWORD|SECRET|PRIVATE_KEY)\s*=/i.test(text)) {
    throw new InstallerError(`bundled asset violates the secret/config allowlist: ${relative}`, 4);
  }
  return text;
}

function semanticFailures(text, requirements) {
  const normalized = String(text).replaceAll("\\n", "\n");
  return requirements.filter(([, expression]) => !expression.test(normalized)).map(([label]) => label);
}

function assertPolicy(text, label) {
  const missing = semanticFailures(text, POLICY_REQUIREMENTS);
  if (missing.length) throw new InstallerError(`${label} is missing required semantics: ${missing.join(", ")}`, 4);
}

function policySpecialistNames(text) {
  const markers = ["The registered specialist catalog is:", "Registered specialists:"];
  const marker = markers.find((candidate) => text.includes(candidate));
  if (!marker) return [];
  const tail = text.slice(text.indexOf(marker) + marker.length);
  const section = tail.split(/\n\s*\n/, 1)[0];
  return [...section.matchAll(/^- `([a-z][a-z0-9_]*)`(?::|$)/gm)].map((match) => match[1]);
}

function assertPolicyRoster(text, specialists, label) {
  const expected = specialists.map((item) => typeof item === "string" ? item : item.name);
  const actual = policySpecialistNames(text);
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new InstallerError(`${label} specialist roster does not match ${CATALOG_FILE}`, 4);
  }
}

function loadPersonaCatalog() {
  const raw = readJsonFile(path.join(ASSET_DIR, CATALOG_FILE), CATALOG_FILE);
  if (raw?.schemaVersion !== 1 || !Array.isArray(raw.specialists) || raw.specialists.length < 6) {
    throw new InstallerError(`${CATALOG_FILE} has an unsupported schema or too few specialists`, 4);
  }
  const base = readAsset(BASE_PROMPT_FILE);
  const missingBase = BASE_PROMPT_SECTIONS.filter((section) => !base.includes(section));
  if (missingBase.length) throw new InstallerError(`${BASE_PROMPT_FILE} is missing: ${missingBase.join(", ")}`, 4);
  if (base.includes('"""')) throw new InstallerError(`${BASE_PROMPT_FILE} contains unsupported TOML delimiter text`, 4);

  const names = new Set();
  const files = new Set();
  const specialists = raw.specialists.map((item) => {
    if (!item || typeof item !== "object") throw new InstallerError(`${CATALOG_FILE} contains an invalid specialist`, 4);
    const { name, displayName, description, personaFile } = item;
    if (typeof name !== "string" || !/^[a-z][a-z0-9_]*$/.test(name)) {
      throw new InstallerError(`invalid specialist name: ${String(name)}`, 4);
    }
    if (name.startsWith("sol_") || name.startsWith("luna_")) {
      throw new InstallerError(`model-branded specialist name is not allowed: ${name}`, 4);
    }
    if (names.has(name)) throw new InstallerError(`duplicate specialist name: ${name}`, 4);
    names.add(name);
    if (typeof displayName !== "string" || !displayName.trim()) throw new InstallerError(`missing display name for ${name}`, 4);
    if (typeof description !== "string" || description.length < 30) throw new InstallerError(`invalid description for ${name}`, 4);
    if (typeof personaFile !== "string" || path.basename(personaFile) !== personaFile || !personaFile.endsWith(".md")) {
      throw new InstallerError(`invalid persona file for ${name}`, 4);
    }
    if (files.has(personaFile)) throw new InstallerError(`duplicate persona file: ${personaFile}`, 4);
    files.add(personaFile);
    const overlayPath = path.join(PERSONA_DIR, personaFile);
    const stat = lstatIfExists(overlayPath);
    if (!stat?.isFile() || stat.isSymbolicLink()) throw new InstallerError(`missing persona overlay: ${personaFile}`, 4);
    const overlay = normalizeText(fs.readFileSync(overlayPath, "utf8"));
    const missing = PERSONA_PROMPT_SECTIONS.filter((section) => !overlay.includes(section));
    if (missing.length) throw new InstallerError(`${personaFile} is missing: ${missing.join(", ")}`, 4);
    if (overlay.includes('"""')) throw new InstallerError(`${personaFile} contains unsupported TOML delimiter text`, 4);
    return {
      name,
      displayName,
      description,
      personaFile,
      fileName: `${name.replaceAll("_", "-")}.toml`,
      overlay,
    };
  });
  return { base, specialists };
}

function renderRoleFile(base, specialist) {
  const instructions = `${base.trim()}\n\n${specialist.overlay.trim()}\n`;
  return normalizeText([
    `name = ${tomlString(specialist.name)}`,
    `description = ${tomlString(specialist.description)}`,
    `model = ${tomlString(ROOT_MODEL)}`,
    `model_reasoning_effort = ${tomlString(SPECIALIST_EFFORT)}`,
    'sandbox_mode = "workspace-write"',
    "",
    'developer_instructions = """',
    instructions.trimEnd(),
    '"""',
    "",
    "[agents]",
    "enabled = false",
    "",
  ].join("\n"));
}

function findExecutable(candidate) {
  if (candidate) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
    throw new InstallerError(`Codex executable not found: ${candidate}`, 2);
  }
  for (const directory of (process.env.PATH || "").split(path.delimiter)) {
    if (!directory) continue;
    const target = path.join(directory, "codex");
    if (fs.existsSync(target) && fs.statSync(target).isFile()) return target;
  }
  const desktop = "/Applications/ChatGPT.app/Contents/Resources/codex";
  if (fs.existsSync(desktop) && fs.statSync(desktop).isFile()) return desktop;
  throw new InstallerError("Codex CLI not found in PATH or the Desktop bundle", 2);
}

function runCodex(codexBin, args, codexHome = null) {
  const env = { ...process.env };
  if (codexHome) env.CODEX_HOME = codexHome;
  const result = spawnSync(codexBin, args, {
    encoding: "utf8",
    env,
    maxBuffer: 20 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    throw new InstallerError(`Codex command failed: ${args.slice(0, 2).join(" ")}`, 4);
  }
  return result.stdout;
}

function withTemporaryDirectory(prefix, callback) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  fs.chmodSync(directory, 0o700);
  try {
    return callback(directory);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function codexVersion(codexBin) {
  return runCodex(codexBin, ["--version"]).trim().replace(/[^a-zA-Z0-9._-]+/g, "-");
}

function queryCatalog(codexBin, requestedRootEffort = null) {
  return withTemporaryDirectory("gpt-squad-catalog-", (temporaryHome) => {
    let catalog;
    try {
      catalog = JSON.parse(runCodex(codexBin, ["debug", "models"], temporaryHome));
    } catch (error) {
      if (error instanceof InstallerError) throw error;
      throw new InstallerError("Codex returned malformed model catalog JSON", 4);
    }
    if (!catalog || !Array.isArray(catalog.models)) {
      throw new InstallerError("Codex model catalog does not contain a models array", 4);
    }
    const models = catalog.models.filter((model) => model?.slug === ROOT_MODEL);
    if (models.length !== 1) throw new InstallerError("target catalog must contain exactly one GPT-5.6 Sol model", 4);
    const efforts = [...new Set(
      (models[0].supported_reasoning_levels || [])
        .map((entry) => entry?.effort)
        .filter((effort) => typeof effort === "string" && effort),
    )];
    if (!efforts.includes(SPECIALIST_EFFORT)) {
      throw new InstallerError("target Sol model does not advertise specialist high reasoning", 4);
    }
    if (requestedRootEffort && !efforts.includes(requestedRootEffort)) {
      throw new InstallerError(
        `target Sol model does not advertise requested root reasoning effort: ${requestedRootEffort}`,
        4,
      );
    }
    const needsPatch = models[0].multi_agent_version !== "v2";
    if (needsPatch) models[0].multi_agent_version = "v2";
    return { catalog, needsPatch, supportedEfforts: efforts };
  });
}

function assertSafeCodexHome(codexHome) {
  if (!path.isAbsolute(codexHome) || codexHome === path.parse(codexHome).root) {
    throw new InstallerError(`unsafe Codex home: ${codexHome}`, 4);
  }
  let cursor = codexHome;
  while (true) {
    const stat = lstatIfExists(cursor);
    if (stat?.isSymbolicLink()) throw new InstallerError(`Codex home ancestor is a symlink: ${cursor}`, 4);
    if (stat || cursor === path.parse(cursor).root) break;
    cursor = path.dirname(cursor);
  }
  const home = lstatIfExists(codexHome);
  if (home && !home.isDirectory()) throw new InstallerError(`Codex home must be a directory: ${codexHome}`, 4);
}

function relativeTarget(codexHome, target) {
  const relative = path.relative(codexHome, target);
  if (!relative || relative === "." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new InstallerError(`target escapes Codex home: ${target}`, 4);
  }
  return relative;
}

function assertSafeTarget(codexHome, target) {
  relativeTarget(codexHome, target);
  let cursor = target;
  while (true) {
    const stat = lstatIfExists(cursor);
    if (stat?.isSymbolicLink()) throw new InstallerError(`target ancestor is a symlink: ${cursor}`, 4);
    if (cursor === codexHome) break;
    const parent = path.dirname(cursor);
    if (parent === cursor) throw new InstallerError(`target escapes Codex home: ${target}`, 4);
    cursor = parent;
  }
}

export {
  AGENTS_BLOCK_VARIANTS,
  AGENTS_POLICY_FILE,
  BACKUP_ROOT_REL,
  InstallerError,
  LEGACY_GENERIC_ROLES,
  LEGACY_GENERIC_ROLE_PATHS,
  LEGACY_LOCKS,
  LEGACY_PROFILE_FILE,
  LEGACY_STATE_REL,
  LOCK_REL,
  POLICY_BEGIN,
  POLICY_BLOCK_VARIANTS,
  POLICY_FILE,
  POLICY_REQUIREMENTS,
  ROLE_BLOCK_BEGIN,
  ROLE_BLOCK_END,
  ROLE_BLOCK_VARIANTS,
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
  findExecutable,
  loadPersonaCatalog,
  lstatIfExists,
  normalizeText,
  parseArgs,
  policySpecialistNames,
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
  withTemporaryDirectory,
};
