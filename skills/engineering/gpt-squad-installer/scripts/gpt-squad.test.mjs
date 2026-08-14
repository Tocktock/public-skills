import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");
const SCRIPT = path.join(SCRIPT_DIR, "gpt-squad.mjs");
const ASSETS = path.join(SKILL_DIR, "assets");
const SPECIALISTS = [
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
];
const LEGACY_ROLES = [
  "sol_pathfinder",
  "sol_architect",
  "sol_builder",
  "sol_verifier",
  "sol_sentinel",
];

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function withTemp(callback) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gpt-squad-test-"));
  try {
    return callback(directory);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function writeFakeCodex(directory, { multiAgentVersion = "v1", efforts = ["low", "medium", "high", "xhigh"] } = {}) {
  const target = path.join(directory, "codex");
  const source = `#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const args = process.argv.slice(2);
if (args[0] === "--version") {
  console.log("codex 9.9.9");
  process.exit(0);
}
if (args[0] === "debug" && args[1] === "models") {
  console.log(JSON.stringify({ models: [{
    slug: "gpt-5.6-sol",
    supported_reasoning_levels: ${JSON.stringify(efforts.map((effort) => ({ effort })))},
    multi_agent_version: ${JSON.stringify(multiAgentVersion)}
  }] }));
  process.exit(0);
}
if (args[0] === "debug" && args[1] === "prompt-input") {
  const home = process.env.CODEX_HOME;
  let output = "";
  for (const file of ["config.toml", "AGENTS.md"]) {
    const target = path.join(home, file);
    if (fs.existsSync(target)) output += fs.readFileSync(target, "utf8") + "\\n";
  }
  console.log(output);
  process.exit(0);
}
process.exit(2);
`;
  fs.writeFileSync(target, source, { mode: 0o755 });
  return target;
}

function run(command, home, codex, extra = []) {
  const args = [SCRIPT, command, "--codex-home", home, "--json", ...extra];
  if (command !== "rollback") args.push("--codex-bin", codex);
  const result = spawnSync(process.execPath, args, { encoding: "utf8" });
  let json;
  try {
    json = JSON.parse(result.stdout);
  } catch {
    assert.fail(`invalid JSON output\nstdout: ${result.stdout}\nstderr: ${result.stderr}`);
  }
  return { ...result, json };
}

function installFixture(root, options = {}) {
  const home = path.join(root, "home");
  fs.mkdirSync(home, { recursive: true });
  fs.writeFileSync(path.join(home, "config.toml"), 'approval_policy = "on-request"\n\n[notifications]\nenabled = true\n');
  fs.writeFileSync(path.join(home, "AGENTS.md"), "# Existing User Instructions\n\nKeep this section.\n");
  const codex = writeFakeCodex(root, options);
  const result = run("install", home, codex);
  assert.equal(result.status, 0, result.stdout);
  assert.equal(result.json.status, "PASS");
  return { home, codex, install: result.json };
}

function recursiveFiles(root) {
  if (!fs.existsSync(root)) return [];
  const result = [];
  const visit = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(target);
      else result.push(path.relative(root, target));
    }
  };
  visit(root);
  return result.sort();
}

function readState(home) {
  return JSON.parse(fs.readFileSync(path.join(home, "gpt-squad-installer", "state.json"), "utf8"));
}

function policyRoster(text) {
  const markers = ["The registered specialist catalog is:", "Registered specialists:"];
  const marker = markers.find((candidate) => text.includes(candidate));
  if (!marker) return [];
  const tail = text.slice(text.indexOf(marker) + marker.length);
  const section = tail.split(/\n\s*\n/, 1)[0];
  return [...section.matchAll(/^- `([a-z][a-z0-9_]*)`(?::|$)/gm)].map((match) => match[1]);
}

test("persona catalog uses general, model-independent specialist names", () => {
  const catalog = JSON.parse(fs.readFileSync(path.join(ASSETS, "persona-catalog.json"), "utf8"));
  assert.equal(catalog.schemaVersion, 1);
  assert.deepEqual(catalog.specialists.map((item) => item.name), SPECIALISTS);
  assert.equal(new Set(SPECIALISTS).size, SPECIALISTS.length);
  for (const specialist of catalog.specialists) {
    assert.match(specialist.name, /^[a-z][a-z0-9_]*$/);
    assert.equal(specialist.name.startsWith("sol_"), false);
    assert.equal(specialist.name.startsWith("luna_"), false);
    const overlay = fs.readFileSync(path.join(ASSETS, "personas", specialist.personaFile), "utf8");
    for (const section of ["Home field:", "Focus map:", "High-value evidence:", "Decision principles:", "Completion standard:"]) {
      assert.ok(overlay.includes(section), `${specialist.name} missing ${section}`);
    }
  }
});

test("change review is a holistic adversarial reviewer distinct from falsification and communication", () => {
  const review = fs.readFileSync(path.join(ASSETS, "personas", "change-review.md"), "utf8");
  const falsification = fs.readFileSync(path.join(ASSETS, "personas", "quality-falsification.md"), "utf8");
  const communication = fs.readFileSync(path.join(ASSETS, "personas", "technical-communication.md"), "utf8");
  assert.match(review, /Holistic review/i);
  assert.match(review, /simplicity[\s\S]*scope discipline[\s\S]*maintainability/i);
  assert.match(review, /Adversarial review:/i);
  assert.match(review, /Try to disprove every candidate finding/i);
  assert.match(review, /Do not manufacture criticism/i);
  assert.match(review, /PASS.*FAIL.*UNRESOLVED/i);
  assert.match(review, /APPROVE.*COMMENT.*REQUEST_CHANGES/i);
  assert.match(falsification, /failure injection[\s\S]*independent falsification/i);
  assert.match(communication, /reader-first technical writing/i);
  assert.doesNotMatch(communication, /finding validity/i);
});

test("persistent policy is explicit opt-in, session-scoped, compact, and roster-complete", () => {
  for (const file of ["squad-policy.txt", "agents-policy.md"]) {
    const text = fs.readFileSync(path.join(ASSETS, file), "utf8");
    assert.match(text, /session-persistent explicit opt-in|Session-Persistent Explicit Opt-In/i);
    assert.match(text, /dormant when a new Codex task or conversation session begins|dormant when a new Codex task/i);
    assert.match(text, /Do not call `list_agents`, `spawn_agent`, `followup_task`, `wait_agent`, or `send_message`[\s\S]*while squad mode is dormant/i);
    assert.match(text, /Activate squad mode when a user request in the current Codex session explicitly/i);
    assert.match(text, /Task complexity alone is not activation before/i);
    assert.match(text, /remains active for later user turns in the same Codex session until the user explicitly opts out or the session ends/i);
    assert.match(text, /Do not require (?:the user to repeat GPT Squad on every turn|repeated activation)/i);
    assert.match(text, /unscoped[\s\S]*deactivates squad mode[\s\S]*current session/i);
    assert.match(text, /request-scoped opt-out pauses only that request|limits the opt-out to the current request[\s\S]*pause squad use only for that request/i);
    assert.match(text, /Every new Codex session begins dormant/i);
    assert.match(text, /gpt-squad-orchestrator/i);
    assert.match(text, /expectation to delegate/i);
    assert.match(text, /smallest sufficient squad/i);
    assert.match(text, /root-only without deactivating|stay root-only without deactivating/i);
    assert.match(text, /elite generalist[\s\S]*attention prior/i);
    assert.match(text, /choose (?:its|their) method[\s\S]*investigate[\s\S]*design[\s\S]*implement[\s\S]*test[\s\S]*document/i);
    assert.match(text, /least coordination intensity[\s\S]*lightweight[\s\S]*cooperative[\s\S]*transactional/i);
    assert.match(text, /(?:Working Commons[\s\S]*non-binding|non-binding[\s\S]*Working Commons)/i);
    assert.match(text, /participant-bound/i);
    assert.match(text, /secret-rejecting/i);
    assert.match(text, /No accepted fact, decision, invariant, ownership change, dependency, or risk disposition may exist only/i);
    assert.match(text, /structured collaboration request/i);
    assert.match(text, /change_review[\s\S]*acceptance[\s\S]*adversarial[\s\S]*quality_falsification/i);
    assert.match(text, /Do not promote every local finding|smallest sufficient (?:canonical )?statement|Promote only information that can change/i);
    assert.match(text, /active session[\s\S]*list_agents[\s\S]*followup_task/i);
    assert.match(text, /fresh Context Hub checkout[\s\S]*stale|checkout is authoritative[\s\S]*Shared Context Ledger revision/i);
    assert.match(text, /runtime-policy preflight/i);
    assert.match(text, /never combine mutually exclusive spawn parameters/i);
    assert.match(text, /After the first timeout[\s\S]*inspect status once[\s\S]*deliberate retry[\s\S]*wait-release/i);
    assert.match(text, /record an `aborted` outcome/i);
    assert.match(text, /Interruptions require a structured reason and recorded outcome/i);
    assert.doesNotMatch(text, /Activation is scoped to the current user request/i);
    assert.doesNotMatch(text, /Do not carry activation into a later user turn/i);
    assert.deepEqual(policyRoster(text), SPECIALISTS, `${file} roster drifted from persona catalog`);
    const byteLimit = file === "squad-policy.txt" ? 7500 : 6000;
    assert.ok(Buffer.byteLength(text) <= byteLimit, `${file} exceeds compact persistent-policy budget`);
    for (const role of LEGACY_ROLES) assert.equal(text.includes(role), false, `${file} still references ${role}`);
  }
});

test("orchestrator skill keeps explicit activation active until session opt-out", () => {
  const skill = fs.readFileSync(
    path.resolve(SKILL_DIR, "..", "gpt-squad-orchestrator", "SKILL.md"),
    "utf8",
  );
  assert.match(skill, /session-persistent explicit opt-in/i);
  assert.match(skill, /Do not activate this skill from task complexity alone/i);
  assert.match(skill, /first explicit activation/i);
  assert.match(skill, /remains active across later user turns/i);
  assert.match(skill, /explicitly opts out or the session ends/i);
  assert.match(skill, /unscoped opt-out/i);
  assert.match(skill, /request-scoped opt-out/i);
  assert.match(skill, /new Codex session starts dormant/i);
  assert.match(skill, /Use at least one suitable registered specialist/i);
  assert.match(skill, /Completing one user request does not deactivate squad mode/i);
  assert.match(skill, /Choose coordination intensity/i);
  assert.match(skill, /Lightweight[\s\S]*Cooperative[\s\S]*Transactional/i);
  assert.match(skill, /Working Commons/i);
  assert.match(skill, /collaboration-request/i);
  assert.match(skill, /specialty is an attention prior/i);
});

test("autonomy-first cooperation assets are installed with deterministic contracts", () => {
  const orchestrator = path.resolve(SKILL_DIR, "..", "gpt-squad-orchestrator");
  const cooperationScript = path.join(orchestrator, "scripts", "gpt-squad-cooperation.mjs");
  const cooperationTests = path.join(orchestrator, "scripts", "cooperation.test.mjs");
  const reference = path.join(orchestrator, "references", "autonomous-cooperation.md");
  const example = path.join(orchestrator, "assets", "cooperation-plan.example.json");
  for (const file of [cooperationScript, cooperationTests, reference, example]) {
    assert.equal(fs.existsSync(file), true, `${file} is missing`);
  }
  const guide = fs.readFileSync(reference, "utf8");
  assert.match(guide, /strong shared truth[\s\S]*clear outcome ownership[\s\S]*low-friction peer cooperation/i);
  assert.match(guide, /Private (?:workspace|specialist work)[\s\S]*Working Commons[\s\S]*(?:Canonical|canonical)/i);
  assert.match(guide, /binding types[\s\S]*rejected/i);
  assert.match(guide, /Specialist-initiated collaboration/i);
  const manifest = JSON.parse(fs.readFileSync(example, "utf8"));
  assert.equal(manifest.requestedMode, "auto");
  assert.ok(Array.isArray(manifest.missions));
});

test("plan is read-only and exposes the complete specialist catalog", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(home);
  fs.writeFileSync(path.join(home, "config.toml"), 'approval_policy = "on-request"\n');
  const codex = writeFakeCodex(root);
  const before = recursiveFiles(home);
  const result = run("plan", home, codex);
  const after = recursiveFiles(home);
  assert.equal(result.status, 0, result.stdout);
  assert.equal(result.json.status, "PASS");
  assert.equal(result.json.readOnly, true);
  assert.deepEqual(result.json.specialists, SPECIALISTS);
  assert.deepEqual(after, before);
  assert.ok(result.json.changes.some((item) => item.path === "agents/gpt-squad/data-systems.toml"));
}));

test("install preserves unrelated config and generates autonomous specialist profiles", () => withTemp((root) => {
  const { home, install } = installFixture(root);
  assert.deepEqual(install.specialists, SPECIALISTS);
  assert.ok(install.changedPaths.includes("config.toml"));
  assert.ok(install.changedPaths.includes("AGENTS.md"));
  const config = fs.readFileSync(path.join(home, "config.toml"), "utf8");
  assert.match(config, /approval_policy = "on-request"/);
  assert.match(config, /\[notifications\]\nenabled = true/);
  assert.match(config, /model = "gpt-5.6-sol"/);
  assert.equal(/^model_reasoning_effort\s*=/m.test(config), false);
  assert.match(config, /default_subagent_reasoning_effort = "high"/);
  assert.equal(install.rootEffortMode, "preserve");
  assert.equal(install.rootEffort, null);
  assert.equal(install.specialistEffort, "high");
  assert.match(config, /# BEGIN GPT-SQUAD SPECIALISTS/);
  assert.match(config, /\[agents\.product_systems\]/);
  for (const legacy of LEGACY_ROLES) assert.equal(config.includes(`[agents.${legacy}]`), false);

  const agents = fs.readFileSync(path.join(home, "AGENTS.md"), "utf8");
  assert.match(agents, /# Existing User Instructions/);
  assert.match(agents, /<!-- BEGIN GPT-SQUAD MANAGED -->/);

  for (const name of SPECIALISTS) {
    const file = path.join(home, "agents", "gpt-squad", `${name.replaceAll("_", "-")}.toml`);
    const role = fs.readFileSync(file, "utf8");
    assert.match(role, new RegExp(`name = "${name}"`));
    assert.match(role, /model = "gpt-5.6-sol"/);
    assert.match(role, /model_reasoning_effort = "high"/);
    assert.match(role, /sandbox_mode = "workspace-write"/);
    assert.match(role, /Autonomy:/);
    assert.match(role, /Cost discipline:/);
    assert.match(role, /\[agents\]\nenabled = false/);
  }
}));

test("reinstall upgrades a stale thirteen-role installation with the change reviewer", () => withTemp((root) => {
  const { home, codex } = installFixture(root);
  const reviewerRelative = path.join("agents", "gpt-squad", "change-review.toml");
  fs.rmSync(path.join(home, reviewerRelative));

  const configPath = path.join(home, "config.toml");
  const config = fs.readFileSync(configPath, "utf8").replace(
    /\n\[agents\.change_review\]\ndescription = [^\n]+\nconfig_file = [^\n]+\n/g,
    "\n",
  );
  fs.writeFileSync(configPath, config);

  const agentsPath = path.join(home, "AGENTS.md");
  const agents = fs.readFileSync(agentsPath, "utf8")
    .replace(/^.*For review work, use `change_review`.*\n/m, "")
    .replace(/^- `change_review`\n/m, "");
  fs.writeFileSync(agentsPath, agents);

  const statePath = path.join(home, "gpt-squad-installer", "state.json");
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
  state.specialists = state.specialists.filter((name) => name !== "change_review");
  state.managedFiles = state.managedFiles.filter((entry) => entry.path !== reviewerRelative);
  fs.writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`);

  const upgraded = run("install", home, codex);
  assert.equal(upgraded.status, 0, upgraded.stdout);
  assert.equal(upgraded.json.status, "PASS");
  assert.equal(upgraded.json.specialistCount, SPECIALISTS.length);
  assert.ok(upgraded.json.specialists.includes("change_review"));
  assert.ok(fs.existsSync(path.join(home, reviewerRelative)));
  assert.match(fs.readFileSync(configPath, "utf8"), /\[agents\.change_review\]/);
  assert.match(fs.readFileSync(agentsPath, "utf8"), /- `change_review`/);
  assert.equal(run("verify", home, codex).json.status, "PASS");
}));

test("root effort is flexible by default, preserves user choice, and supports explicit or auto modes", () => withTemp((root) => {
  const preservedHome = path.join(root, "preserved-home");
  fs.mkdirSync(preservedHome);
  fs.writeFileSync(
    path.join(preservedHome, "config.toml"),
    'model_reasoning_effort = "medium"\napproval_policy = "on-request"\n',
  );
  fs.writeFileSync(path.join(preservedHome, "AGENTS.md"), "# Existing\n");
  const codex = writeFakeCodex(root);
  const preserved = run("install", preservedHome, codex);
  assert.equal(preserved.status, 0, preserved.stdout);
  assert.equal(preserved.json.rootEffortMode, "preserve");
  assert.equal(preserved.json.rootEffort, "medium");
  assert.match(fs.readFileSync(path.join(preservedHome, "config.toml"), "utf8"), /^model_reasoning_effort = "medium"$/m);

  const explicitHome = path.join(root, "explicit-home");
  fs.mkdirSync(explicitHome);
  const explicit = run("install", explicitHome, codex, ["--root-effort", "low"]);
  assert.equal(explicit.status, 0, explicit.stdout);
  assert.equal(explicit.json.rootEffortMode, "explicit");
  assert.equal(explicit.json.rootEffort, "low");
  const explicitConfig = fs.readFileSync(path.join(explicitHome, "config.toml"), "utf8");
  assert.match(explicitConfig, /^model_reasoning_effort = "low"$/m);
  assert.match(explicitConfig, /default_subagent_reasoning_effort = "high"/);

  const autoHome = path.join(root, "auto-home");
  fs.mkdirSync(autoHome);
  fs.writeFileSync(path.join(autoHome, "config.toml"), 'model_reasoning_effort = "medium"\n');
  const automatic = run("install", autoHome, codex, ["--root-effort", "auto"]);
  assert.equal(automatic.status, 0, automatic.stdout);
  assert.equal(automatic.json.rootEffortMode, "auto");
  assert.equal(automatic.json.rootEffort, null);
  assert.equal(/^model_reasoning_effort\s*=/m.test(fs.readFileSync(path.join(autoHome, "config.toml"), "utf8")), false);
}));

test("unsupported explicit root effort fails before mutation", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(home);
  const codex = writeFakeCodex(root, { efforts: ["medium", "high"] });
  const result = run("plan", home, codex, ["--root-effort", "low"]);
  assert.equal(result.status, 4);
  assert.equal(result.json.status, "FAIL");
  assert.match(result.json.message, /requested root reasoning effort: low/);
  assert.deepEqual(recursiveFiles(home), []);
}));

test("upgrade removes the legacy installer-owned forced high root effort", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(path.join(home, "gpt-squad-installer"), { recursive: true });
  const config = 'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "high"\napproval_policy = "on-request"\n';
  fs.writeFileSync(path.join(home, "config.toml"), config, { mode: 0o600 });
  fs.writeFileSync(path.join(home, "gpt-squad-installer", "state.json"), JSON.stringify({
    schemaVersion: 2,
    rootModel: "gpt-5.6-sol",
    rootEffort: "high",
    managedFiles: [{
      path: "config.toml",
      hash: sha256(Buffer.from(config)),
      mode: 0o600,
      absent: false,
    }],
  }, null, 2));
  const codex = writeFakeCodex(root);
  const result = run("install", home, codex);
  assert.equal(result.status, 0, result.stdout);
  assert.equal(result.json.rootEffortMode, "auto");
  assert.equal(result.json.rootEffort, null);
  assert.equal(result.json.migratedLegacyRootEffort, true);
  assert.equal(/^model_reasoning_effort\s*=/m.test(fs.readFileSync(path.join(home, "config.toml"), "utf8")), false);
}));

test("verify proves managed semantics, general names, and runtime prompt loading", () => withTemp((root) => {
  const { home, codex } = installFixture(root);
  const result = run("verify", home, codex);
  assert.equal(result.status, 0, result.stdout);
  assert.equal(result.json.status, "PASS");
  assert.deepEqual(result.json.specialists, SPECIALISTS);
  assert.equal(result.json.legacyGenericRolesAbsent, true);
  assert.equal(result.json.runtimePromptLoaded, true);
  assert.equal(result.json.runtimeChildIdentity, "UNRESOLVED");
  assert.equal(result.json.rootEffortMode, "preserve");
  assert.equal(result.json.rootEffort, null);
  assert.equal(result.json.specialistEffort, "high");
  assert.equal(result.json.sharedFileVerification, "managed-semantics");
}));

test("verify tolerates unrelated shared-file edits and a supported preserve-mode root effort change", () => withTemp((root) => {
  const { home, codex } = installFixture(root);
  const configPath = path.join(home, "config.toml");
  const agentsPath = path.join(home, "AGENTS.md");
  const config = fs.readFileSync(configPath, "utf8");
  fs.writeFileSync(
    configPath,
    `model_reasoning_effort = "xhigh"
${config}
# user-owned config note

[mcp_servers.example]
command = "example"
`,
  );
  fs.appendFileSync(agentsPath, "\n# User-owned instructions\n\nKeep this note.\n");

  const result = run("verify", home, codex);
  assert.equal(result.status, 0, result.stdout);
  assert.equal(result.json.status, "PASS");
  assert.equal(result.json.rootEffortMode, "preserve");
  assert.equal(result.json.rootEffort, "xhigh");
  assert.equal(result.json.sharedFileVerification, "managed-semantics");
}));

test("verify rejects managed agent runtime setting drift", () => withTemp((root) => {
  const { home, codex } = installFixture(root);
  const configPath = path.join(home, "config.toml");
  const config = fs.readFileSync(configPath, "utf8").replace(
    'default_subagent_reasoning_effort = "high"',
    'default_subagent_reasoning_effort = "medium"',
  );
  fs.writeFileSync(configPath, config);

  const result = run("verify", home, codex);
  assert.equal(result.status, 4);
  assert.match(result.json.message, /agent runtime settings are missing or stale/);
}));

test("official multi-agent v2 catalog does not create a compatibility catalog", () => withTemp((root) => {
  const { home, install } = installFixture(root, { multiAgentVersion: "v2" });
  assert.equal(install.catalogDecision, "official-catalog");
  assert.equal(fs.existsSync(path.join(home, "model-catalogs")), false);
  const config = fs.readFileSync(path.join(home, "config.toml"), "utf8");
  assert.equal(config.includes("model_catalog_json"), false);
}));

test("missing specialist high reasoning fails closed", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(home);
  const codex = writeFakeCodex(root, { efforts: ["medium"] });
  const result = run("plan", home, codex);
  assert.equal(result.status, 4);
  assert.equal(result.json.status, "FAIL");
  assert.match(result.json.message, /does not advertise specialist high reasoning/);
}));

test("unmanaged specialist registration collision fails before mutation", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(home);
  fs.writeFileSync(path.join(home, "config.toml"), '[agents.data_systems]\ndescription = "custom"\nconfig_file = "./custom.toml"\n');
  const codex = writeFakeCodex(root);
  const before = fs.readFileSync(path.join(home, "config.toml"), "utf8");
  const result = run("install", home, codex);
  assert.equal(result.status, 4);
  assert.match(result.json.message, /unmanaged agent registration collides/);
  assert.equal(fs.readFileSync(path.join(home, "config.toml"), "utf8"), before);
  assert.equal(fs.existsSync(path.join(home, "gpt-squad-installer")), false);
}));

test("migration removes installer-owned generic roles and replaces managed blocks", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(path.join(home, "agents", "sol-sol"), { recursive: true });
  const managedFiles = [];
  for (const role of LEGACY_ROLES) {
    const relative = path.join("agents", "sol-sol", `${role.replaceAll("_", "-")}.toml`);
    const target = path.join(home, relative);
    const content = `name = "${role}"\nlegacy = true\n`;
    fs.writeFileSync(target, content, { mode: 0o600 });
    managedFiles.push({ path: relative, hash: sha256(Buffer.from(content)), mode: 0o600 });
  }
  fs.mkdirSync(path.join(home, "sol-sol-squad-installer"), { recursive: true });
  fs.writeFileSync(path.join(home, "sol-sol-squad-installer", "state.json"), JSON.stringify({ managedFiles }, null, 2));
  fs.writeFileSync(path.join(home, "config.toml"), `developer_instructions = "[SOL_SOL_SQUAD_POLICY_BEGIN]\\nlegacy policy\\n[SOL_SOL_SQUAD_POLICY_END]"\n\n# BEGIN SOL-SOL-SQUAD ROLES\n[agents.sol_pathfinder]\ndescription = "legacy"\nconfig_file = "./agents/sol-sol/sol-pathfinder.toml"\n# END SOL-SOL-SQUAD ROLES\n`);
  fs.writeFileSync(path.join(home, "AGENTS.md"), "<!-- BEGIN SOL-SOL-SQUAD MANAGED -->\nlegacy\n<!-- END SOL-SOL-SQUAD MANAGED -->\n");
  const codex = writeFakeCodex(root);
  const result = run("install", home, codex);
  assert.equal(result.status, 0, result.stdout);
  for (const role of LEGACY_ROLES) {
    assert.equal(fs.existsSync(path.join(home, "agents", "sol-sol", `${role.replaceAll("_", "-")}.toml`)), false);
  }
  const config = fs.readFileSync(path.join(home, "config.toml"), "utf8");
  assert.equal(config.includes("SOL-SOL-SQUAD ROLES"), false);
  assert.equal(config.includes("SOL_SOL_SQUAD_POLICY_BEGIN"), false);
  assert.match(config, /GPT-SQUAD SPECIALISTS/);
  assert.match(config, /GPT_SQUAD_POLICY_BEGIN/);
}));

test("drifted legacy role refuses cleanup", () => withTemp((root) => {
  const home = path.join(root, "home");
  const roleDir = path.join(home, "agents", "sol-sol");
  fs.mkdirSync(roleDir, { recursive: true });
  const target = path.join(roleDir, "sol-pathfinder.toml");
  fs.writeFileSync(target, "current drift\n", { mode: 0o600 });
  fs.mkdirSync(path.join(home, "sol-sol-squad-installer"), { recursive: true });
  fs.writeFileSync(path.join(home, "sol-sol-squad-installer", "state.json"), JSON.stringify({
    managedFiles: [{ path: "agents/sol-sol/sol-pathfinder.toml", hash: sha256(Buffer.from("old\n")), mode: 0o600 }],
  }));
  const codex = writeFakeCodex(root);
  const result = run("plan", home, codex);
  assert.equal(result.status, 4);
  assert.match(result.json.message, /missing ownership or has drifted/);
  assert.equal(fs.readFileSync(target, "utf8"), "current drift\n");
}));

test("rollback restores the exact pre-install config, AGENTS file, and removes created roles", () => withTemp((root) => {
  const home = path.join(root, "home");
  fs.mkdirSync(home);
  const configBefore = 'approval_policy = "never"\n\n[projects."/tmp/example"]\ntrust_level = "trusted"\n';
  const agentsBefore = "# Personal Rules\n\nDo not remove.\n";
  fs.writeFileSync(path.join(home, "config.toml"), configBefore);
  fs.writeFileSync(path.join(home, "AGENTS.md"), agentsBefore);
  const codex = writeFakeCodex(root);
  const installed = run("install", home, codex);
  assert.equal(installed.status, 0, installed.stdout);
  const rolledBack = run("rollback", home, codex, ["--backup-id", installed.json.backupId]);
  assert.equal(rolledBack.status, 0, rolledBack.stdout);
  assert.equal(fs.readFileSync(path.join(home, "config.toml"), "utf8"), configBefore);
  assert.equal(fs.readFileSync(path.join(home, "AGENTS.md"), "utf8"), agentsBefore);
  assert.equal(fs.existsSync(path.join(home, "agents", "gpt-squad", "product-systems.toml")), false);
  assert.ok(rolledBack.json.preRollbackBackupId);
}));

test("rollback refuses managed drift before the first restore mutation", () => withTemp((root) => {
  const { home, codex, install } = installFixture(root);
  const role = path.join(home, "agents", "gpt-squad", "data-systems.toml");
  const roleBefore = fs.readFileSync(role, "utf8");
  fs.appendFileSync(path.join(home, "config.toml"), "\n# concurrent user change\n");
  const result = run("rollback", home, codex, ["--backup-id", install.backupId]);
  assert.equal(result.status, 5);
  assert.match(result.json.message, /drift prevents rollback/);
  assert.equal(fs.readFileSync(role, "utf8"), roleBefore);
  assert.equal(result.json.preRollbackBackupId, null);
}));

test("corrupt backup payload refuses rollback without changing installed targets", () => withTemp((root) => {
  const { home, codex, install } = installFixture(root);
  const manifestPath = path.join(home, "backups", "gpt-squad", install.backupId, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const payload = manifest.files.find((entry) => entry.existed)?.backupName;
  assert.ok(payload);
  fs.appendFileSync(path.join(path.dirname(manifestPath), payload), "corrupt");
  const configBefore = fs.readFileSync(path.join(home, "config.toml"), "utf8");
  const result = run("rollback", home, codex, ["--backup-id", install.backupId]);
  assert.equal(result.status, 5);
  assert.match(result.json.message, /missing or corrupt/);
  assert.equal(fs.readFileSync(path.join(home, "config.toml"), "utf8"), configBefore);
  assert.equal(result.json.preRollbackBackupId, null);
}));

test("verify detects a modified specialist profile", () => withTemp((root) => {
  const { home, codex } = installFixture(root);
  fs.appendFileSync(path.join(home, "agents", "gpt-squad", "security-trust.toml"), "# drift\n");
  const result = run("verify", home, codex);
  assert.equal(result.status, 4);
  assert.match(result.json.message, /stale|missing or drifted/);
}));

test("state records exactly the new specialist roster and no generic process roles", () => withTemp((root) => {
  const { home } = installFixture(root);
  const state = readState(home);
  assert.deepEqual(state.specialists, SPECIALISTS);
  assert.equal(state.rootEffortMode, "preserve");
  assert.equal(state.rootEffort, null);
  assert.equal(state.specialistEffort, "high");
  const paths = state.managedFiles.map((entry) => entry.path);
  for (const role of LEGACY_ROLES) {
    assert.equal(state.specialists.includes(role), false);
    assert.ok(paths.includes(path.join("agents", "sol-sol", `${role.replaceAll("_", "-")}.toml`)));
    const entry = state.managedFiles.find((item) => item.path.endsWith(`${role.replaceAll("_", "-")}.toml`));
    assert.equal(entry.absent, true);
  }
}));
