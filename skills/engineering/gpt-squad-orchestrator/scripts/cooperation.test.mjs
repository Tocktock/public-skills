import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.join(HERE, "gpt-squad-cooperation.mjs");
const PERSONA_CATALOG = path.resolve(HERE, "..", "..", "gpt-squad-installer", "assets", "persona-catalog.json");
const REGISTERED_SPECIALISTS = JSON.parse(fs.readFileSync(PERSONA_CATALOG, "utf8")).specialists.map((item) => item.name);
const TEMP_ROOT = fs.realpathSync(os.tmpdir());

function withTemp(callback) {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-cooperation-"));
  try {
    return callback(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function invoke(args, expected = 0) {
  const result = spawnSync(process.execPath, [CLI, ...args, "--json"], { encoding: "utf8" });
  assert.equal(result.status, expected, `${result.stdout}\n${result.stderr}`);
  let json;
  try {
    json = JSON.parse(result.stdout || "{}");
  } catch {
    assert.fail(`invalid JSON output\nstdout: ${result.stdout}\nstderr: ${result.stderr}`);
  }
  return json;
}

function writeManifest(root, manifest, name = "manifest.json") {
  const target = path.join(root, name);
  fs.writeFileSync(target, `${JSON.stringify(manifest, null, 2)}\n`);
  return target;
}

function baseMission(overrides = {}) {
  return {
    id: "M01",
    specialist: "domain_application",
    relationship: "lead",
    objective: "Own the coherent domain outcome",
    distinctValue: "Decide the authoritative domain boundary",
    writeMode: "read-only",
    ...overrides,
  };
}

function initCommons(root) {
  const workspace = path.join(root, "commons");
  const result = invoke([
    "commons-init",
    "--workspace-dir", workspace,
    "--session-key", "session-1",
    "--run-id", "run-1",
    "--participants", Array.from({ length: 16 }, (_, index) => `M${String(index + 1).padStart(2, "0")}`).join(","),
  ]);
  assert.equal(result.status, "PASS");
  return workspace;
}

function readCommons(workspace) {
  return JSON.parse(fs.readFileSync(path.join(workspace, "working-commons.json"), "utf8"));
}

test("cooperation planner accepts the complete installed specialist catalog", () => withTemp((root) => {
  for (const [index, specialist] of REGISTERED_SPECIALISTS.entries()) {
    const manifest = writeManifest(root, {
      objective: `Plan a mission for ${specialist}`,
      missions: [baseMission({ specialist })],
    }, `catalog-${index}.json`);
    const plan = invoke(["plan", "--manifest", manifest]);
    assert.equal(plan.missions[0].specialist, specialist);
  }
}));

test("plan chooses the least ceremony for one autonomous specialist", () => withTemp((root) => {
  const manifest = writeManifest(root, {
    objective: "Produce one coherent result",
    requestedMode: "auto",
    missions: [baseMission()],
  });
  const plan = invoke(["plan", "--manifest", manifest]);
  assert.equal(plan.coordinationMode, "lightweight");
  assert.equal(plan.contextHubRequired, false);
  assert.equal(plan.workingCommonsRecommended, false);
  assert.match(plan.autonomyContract, /choose the method/i);
  assert.match(plan.missions[0].canonicalizationRule, /Local decisions stay local/);
}));

test("independent read-only parallel work remains lightweight", () => withTemp((root) => {
  const manifest = writeManifest(root, {
    objective: "Compare independent evidence",
    missions: [
      baseMission(),
      baseMission({
        id: "M02",
        specialist: "codebase_forensics",
        relationship: "parallel-owner",
        objective: "Reconstruct repository intent",
        distinctValue: "Find historical evidence independently",
      }),
    ],
  });
  const plan = invoke(["plan", "--manifest", manifest]);
  assert.equal(plan.minimumMode, "lightweight");
  assert.equal(plan.coordinationMode, "lightweight");
}));

test("holistic review stays lightweight while a distinct adversarial challenger becomes transactional", () => withTemp((root) => {
  const reviewOnly = writeManifest(root, {
    objective: "Review one proposed change for acceptance readiness",
    missions: [baseMission({
      specialist: "change_review",
      relationship: "lead",
      objective: "Review the complete change surface and return a calibrated verdict",
      distinctValue: "Evaluate correctness, simplicity, scope, maintainability, compatibility, and evidence quality",
    })],
  }, "review-only.json");
  const reviewPlan = invoke(["plan", "--manifest", reviewOnly]);
  assert.equal(reviewPlan.coordinationMode, "lightweight");
  assert.equal(reviewPlan.missions[0].specialist, "change_review");

  const adversarialPair = writeManifest(root, {
    objective: "Review a high-risk change with a distinct executable challenge",
    missions: [
      baseMission({
        specialist: "change_review",
        relationship: "lead",
        objective: "Own holistic review coverage and acceptance judgment",
        distinctValue: "Evaluate the whole change, including simplicity and integration risk",
      }),
      baseMission({
        id: "M02",
        specialist: "quality_falsification",
        relationship: "independent-challenger",
        objective: "Attempt to falsify the highest-risk behavioral claim",
        distinctValue: "Use an independent reproduction or failure-injection path",
      }),
    ],
  }, "review-with-challenge.json");
  assert.equal(invoke(["plan", "--manifest", adversarialPair]).coordinationMode, "transactional");
}));

test("independent challengers may own isolated verification artifacts without editing the reviewed surface", () => withTemp((root) => {
  const manifest = writeManifest(root, {
    objective: "Preserve independent review while allowing decisive verification work",
    missions: [baseMission({
      specialist: "change_review",
      relationship: "independent-challenger",
      writeMode: "writer",
      writePaths: ["review-artifacts/M01"],
      objective: "Review the change and build an isolated verification artifact",
      distinctValue: "Provide an independent verdict without modifying the reviewed implementation",
    })],
  }, "isolated-review-writer.json");
  const plan = invoke(["plan", "--manifest", manifest]);
  assert.equal(plan.coordinationMode, "transactional");
  assert.deepEqual(plan.missions[0].writePaths, ["review-artifacts/M01"]);
}));

test("provisional peer sharing selects cooperative mode without forcing canonical state", () => withTemp((root) => {
  const manifest = writeManifest(root, {
    objective: "Let two specialists clarify assumptions",
    provisionalSharing: true,
    peerQuestionsExpected: true,
    missions: [
      baseMission(),
      baseMission({
        id: "M02",
        specialist: "data_systems",
        relationship: "advisor",
        objective: "Challenge persistence assumptions",
        distinctValue: "Provide transaction evidence",
      }),
    ],
  });
  const plan = invoke(["plan", "--manifest", manifest]);
  assert.equal(plan.coordinationMode, "cooperative");
  assert.equal(plan.contextHubRequired, false);
  assert.equal(plan.workingCommonsRecommended, true);
}));

test("shared contracts, dependencies, stale reuse, writers, and challenge select transactional mode", () => withTemp((root) => {
  const cases = [
    { sharedContractsMayChange: true },
    { canonicalStateMayChange: true },
    { multiWave: true },
    { staleContextRisk: true },
  ];
  for (const [index, extra] of cases.entries()) {
    const manifest = writeManifest(root, {
      objective: `Transactional case ${index}`,
      missions: [baseMission()],
      ...extra,
    }, `manifest-${index}.json`);
    assert.equal(invoke(["plan", "--manifest", manifest]).coordinationMode, "transactional");
  }

  const dependent = writeManifest(root, {
    objective: "Dependent evidence",
    missions: [
      baseMission(),
      baseMission({
        id: "M02",
        specialist: "quality_falsification",
        relationship: "advisor",
        objective: "Verify the first mission evidence",
        distinctValue: "Falsify the lead claim",
        dependsOn: ["M01"],
      }),
    ],
  }, "dependent.json");
  assert.equal(invoke(["plan", "--manifest", dependent]).coordinationMode, "transactional");

  const oneWriter = writeManifest(root, {
    objective: "Let one writer own implementation while an independent reader investigates",
    missions: [
      baseMission({ writeMode: "writer", writePaths: ["src/domain"] }),
      baseMission({
        id: "M02",
        specialist: "codebase_forensics",
        relationship: "parallel-owner",
        objective: "Inspect history without changing shared state",
        distinctValue: "Provide independent repository evidence",
      }),
    ],
  }, "one-writer.json");
  assert.equal(invoke(["plan", "--manifest", oneWriter]).coordinationMode, "lightweight");

  const parallelWriters = writeManifest(root, {
    objective: "Coordinate two disjoint writers",
    missions: [
      baseMission({ writeMode: "writer", writePaths: ["src/domain"] }),
      baseMission({
        id: "M02",
        specialist: "data_systems",
        relationship: "parallel-owner",
        objective: "Own persistence implementation",
        distinctValue: "Protect data invariants",
        writeMode: "writer",
        writePaths: ["db/migrations"],
      }),
    ],
  }, "parallel-writers.json");
  assert.equal(invoke(["plan", "--manifest", parallelWriters]).coordinationMode, "transactional");

  const challenger = writeManifest(root, {
    objective: "Independently challenge a material claim",
    missions: [
      baseMission(),
      baseMission({
        id: "M02",
        specialist: "quality_falsification",
        relationship: "independent-challenger",
        objective: "Attempt to falsify the material claim",
        distinctValue: "Use an independent evidence path",
      }),
    ],
  }, "challenger.json");
  assert.equal(invoke(["plan", "--manifest", challenger]).coordinationMode, "transactional");
}));

test("plan rejects an unsafe lower mode but permits an explicit higher mode with warning", () => withTemp((root) => {
  const unsafe = writeManifest(root, {
    objective: "Shared contract change",
    requestedMode: "lightweight",
    sharedContractsMayChange: true,
    missions: [baseMission()],
  });
  assert.match(invoke(["plan", "--manifest", unsafe], 2).message, /below the safe minimum transactional/);

  const higher = writeManifest(root, {
    objective: "Conservative coordination",
    requestedMode: "transactional",
    missions: [baseMission()],
  }, "higher.json");
  const plan = invoke(["plan", "--manifest", higher]);
  assert.equal(plan.coordinationMode, "transactional");
  assert.ok(plan.warnings.some((warning) => /more ceremony/.test(warning)));
}));

test("writer collisions are hard failures while persona and lead composition remain flexible", () => withTemp((root) => {
  const collision = writeManifest(root, {
    objective: "Unsafe parallel writes",
    missions: [
      baseMission({ writeMode: "writer", writePaths: ["src/domain"] }),
      baseMission({
        id: "M02",
        specialist: "data_systems",
        relationship: "parallel-owner",
        objective: "Write persistence changes",
        distinctValue: "Own schema evolution",
        writeMode: "writer",
        writePaths: ["src/domain/persistence"],
      }),
    ],
  });
  assert.match(invoke(["plan", "--manifest", collision], 2).message, /writer path collision/);

  const coLeads = writeManifest(root, {
    objective: "Explicit co-lead experiment",
    missions: [
      baseMission(),
      baseMission({
        id: "M02",
        specialist: "product_systems",
        relationship: "lead",
        objective: "Own product policy meaning",
        distinctValue: "Resolve product policy",
      }),
    ],
  }, "co-leads.json");
  const plan = invoke(["plan", "--manifest", coLeads]);
  assert.equal(plan.status, "PASS");
  assert.ok(plan.warnings.some((warning) => /multiple leads are allowed/.test(warning)));
}));

test("working commons is private, idempotent, bounded, and explicitly non-binding", () => withTemp((root) => {
  const workspace = initCommons(root);
  const second = invoke([
    "commons-init", "--workspace-dir", workspace,
    "--session-key", "session-1", "--run-id", "run-1",
    "--participants", Array.from({ length: 16 }, (_, index) => `M${String(index + 1).padStart(2, "0")}`).join(","),
  ]);
  assert.equal(second.created, false);
  const stateFile = path.join(workspace, "working-commons.json");
  assert.equal(fs.statSync(workspace).mode & 0o777, 0o700);
  assert.equal(fs.statSync(stateFile).mode & 0o777, 0o600);
  assert.equal(readCommons(workspace).binding, false);

  const posted = invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "hypothesis",
    "--text", "The failure may be caused by a stale mapping",
    "--audience", "M01,M02", "--ttl-minutes", "30",
  ]);
  assert.equal(posted.item.id, "W-000001");
  assert.equal(posted.item.binding, false);
  assert.match(posted.canonicalWarning, /provisional and non-binding/);
  assert.equal(readCommons(workspace).items.length, 1);
}));

test("working commons refuses binding fact and decision types", () => withTemp((root) => {
  const workspace = initCommons(root);
  for (const type of ["fact", "decision", "invariant", "ownership", "accepted-risk"]) {
    const failed = invoke([
      "commons-post", "--workspace-dir", workspace,
      "--author", "M01", "--type", type,
      "--text", "This should not become accepted truth",
    ], 2);
    assert.match(failed.message, /binding facts and decisions belong in the Context Hub/);
  }
  assert.equal(readCommons(workspace).items.length, 0);
}));

test("audience filtering enables peer clarification without exposing every note", () => withTemp((root) => {
  const workspace = initCommons(root);
  invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "question",
    "--text", "Can your migration preserve this invariant?",
    "--audience", "M02",
  ]);
  assert.equal(invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "M02"]).items.length, 1);
  const hidden = invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "M03"]);
  assert.equal(hidden.items.length, 0);
  assert.equal(hidden.counts.open, 0);
  assert.equal(invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "root"]).items.length, 1);

  assert.match(invoke([
    "commons-reply", "--workspace-dir", workspace,
    "--author", "M03", "--item-id", "W-000001",
    "--text", "I should not see this",
  ], 2).message, /not allowed/);
  const reply = invoke([
    "commons-reply", "--workspace-dir", workspace,
    "--author", "M02", "--item-id", "W-000001",
    "--text", "Yes; I will preserve it through a database constraint",
  ]);
  assert.equal(reply.status, "PASS");
}));

test("specialists can request distinct collaboration while root retains composition authority", () => withTemp((root) => {
  const workspace = initCommons(root);
  const request = invoke([
    "collaboration-request", "--workspace-dir", workspace,
    "--author", "M01", "--specialist", "data_systems",
    "--reason", "The implementation depends on transaction isolation",
    "--decision-impact", "It may change the chosen ownership boundary",
    "--expected-value", "A decisive concurrency proof is worth the coordination cost",
    "--surface", "persistence and migration evidence",
    "--write-mode", "read-only",
  ]);
  assert.equal(request.item.type, "collaboration-request");
  assert.equal(request.rootDecisionRequired, true);
  assert.equal(invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "M02"]).items.length, 0);
  assert.equal(invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "root"]).items.length, 1);

  assert.match(invoke([
    "commons-resolve", "--workspace-dir", workspace,
    "--actor", "M01", "--item-id", request.item.id,
    "--summary", "I accept my own request", "--decision", "accepted",
  ], 2).message, /only root/);
  const resolved = invoke([
    "commons-resolve", "--workspace-dir", workspace,
    "--actor", "root", "--item-id", request.item.id,
    "--summary", "Reuse the reachable data specialist with a fresh mission packet",
    "--decision", "reused",
  ]);
  assert.equal(resolved.item.status, "resolved");
  assert.equal(resolved.item.resolution.decision, "reused");
  assert.match(resolved.canonicalWarning, /non-binding/);
}));

test("general notes can be resolved by author or root but remain non-binding", () => withTemp((root) => {
  const workspace = initCommons(root);
  const item = invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "coordination",
    "--text", "I will finish the parser before you integrate the API",
  ]).item;
  assert.match(invoke([
    "commons-resolve", "--workspace-dir", workspace,
    "--actor", "M02", "--item-id", item.id,
    "--summary", "Not my item",
  ], 2).message, /only root or the item author/);
  const resolved = invoke([
    "commons-resolve", "--workspace-dir", workspace,
    "--actor", "M01", "--item-id", item.id,
    "--summary", "Parser delivery completed",
  ]);
  assert.equal(resolved.item.status, "resolved");
}));

test("expired and resolved provisional state can be compacted without touching canonical history", () => withTemp((root) => {
  const workspace = initCommons(root);
  const posted = invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "question",
    "--text", "Short lived question", "--ttl-minutes", "5",
  ]).item;
  const state = readCommons(workspace);
  state.items[0].createdAt = new Date(Date.now() - 10 * 60_000).toISOString();
  state.items[0].expiresAt = new Date(Date.now() - 5 * 60_000).toISOString();
  fs.writeFileSync(path.join(workspace, "working-commons.json"), `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  const listed = invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "root", "--status", "expired"]);
  assert.equal(listed.items[0].id, posted.id);
  assert.match(invoke([
    "commons-compact", "--workspace-dir", workspace,
    "--actor", "M01", "--older-than-minutes", "0",
  ], 2).message, /only root/);
  const compacted = invoke([
    "commons-compact", "--workspace-dir", workspace,
    "--actor", "root", "--older-than-minutes", "0",
  ]);
  assert.deepEqual(compacted.removed, [posted.id]);
  assert.equal(readCommons(workspace).items.length, 0);
}));

test("size guards fail before publishing partial collaboration state", () => withTemp((root) => {
  const workspace = initCommons(root);
  const before = fs.readFileSync(path.join(workspace, "working-commons.json"), "utf8");
  const failed = invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "hypothesis",
    "--text", "x".repeat(8 * 1024 + 1),
  ], 2);
  assert.match(failed.message, /exceeds 8192 bytes/);
  assert.equal(fs.readFileSync(path.join(workspace, "working-commons.json"), "utf8"), before);
}));

test("concurrent posts are serialized into unique working-commons items", async () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-cooperation-concurrent-"));
  try {
    const workspace = initCommons(root);
    const promises = Array.from({ length: 12 }, (_, index) => new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [
        CLI,
        "commons-post",
        "--workspace-dir", workspace,
        "--author", `M${String(index + 1).padStart(2, "0")}`,
        "--type", "coordination",
        "--text", `Independent update ${index + 1}`,
        "--json",
      ], { stdio: ["ignore", "pipe", "pipe"] });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (chunk) => { stdout += chunk; });
      child.stderr.on("data", (chunk) => { stderr += chunk; });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code !== 0) reject(new Error(`${stdout}\n${stderr}`));
        else resolve(JSON.parse(stdout));
      });
    }));
    const results = await Promise.all(promises);
    assert.equal(new Set(results.map((result) => result.item.id)).size, 12);
    const state = readCommons(workspace);
    assert.equal(state.items.length, 12);
    assert.deepEqual(state.items.map((item) => item.id), Array.from({ length: 12 }, (_, index) => `W-${String(index + 1).padStart(6, "0")}`));
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("corrupted or binding working-commons state fails closed", () => withTemp((root) => {
  const workspace = initCommons(root);
  invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "question",
    "--text", "Provisional question",
  ]);
  const file = path.join(workspace, "working-commons.json");
  const state = readCommons(workspace);
  state.items[0].binding = true;
  fs.writeFileSync(file, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  assert.match(
    invoke(["commons-list", "--workspace-dir", workspace, "--viewer", "root"], 2).message,
    /must remain non-binding/,
  );
}));

test("structured writer paths reject globs that would make collision checks ambiguous", () => withTemp((root) => {
  const manifest = writeManifest(root, {
    objective: "Reject ambiguous writer ownership",
    missions: [baseMission({ writeMode: "writer", writePaths: ["src/**"] })],
  });
  assert.match(invoke(["plan", "--manifest", manifest], 2).message, /without globs/);
}));

test("working commons refuses undeclared participants and preserves an existing public directory mode", () => withTemp((root) => {
  const publicWorkspace = path.join(root, "public-workspace");
  fs.mkdirSync(publicWorkspace, { mode: 0o755 });
  fs.chmodSync(publicWorkspace, 0o755);
  const failedInit = invoke([
    "commons-init", "--workspace-dir", publicWorkspace,
    "--session-key", "session-1", "--run-id", "run-1",
    "--participants", "M01,M02",
  ], 2);
  assert.match(failedInit.message, /must already be owner-only/);
  assert.equal(fs.statSync(publicWorkspace).mode & 0o777, 0o755);

  const workspace = initCommons(root);
  assert.match(invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M99", "--type", "question", "--text", "Undeclared actor",
  ], 2).message, /not a registered working-commons participant/);
  assert.match(invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "question", "--text", "Unknown audience",
    "--audience", "M99",
  ], 2).message, /not a registered working-commons participant/);
}));

test("working commons rejects secret-like provisional content without logging the value", () => withTemp((root) => {
  const workspace = initCommons(root);
  const secret = `ghp_${"a".repeat(30)}`;
  const failed = invoke([
    "commons-post", "--workspace-dir", workspace,
    "--author", "M01", "--type", "hypothesis", "--text", secret,
  ], 2);
  assert.match(failed.message, /secret-like content \(GitHub token\)/);
  assert.equal(failed.message.includes(secret), false);
  assert.equal(readCommons(workspace).items.length, 0);
}));

test("planner rejects ambiguous JSON booleans and normalizes case and dot path collisions", () => withTemp((root) => {
  const malformed = writeManifest(root, {
    objective: "Reject string booleans",
    provisionalSharing: "false",
    missions: [baseMission()],
  });
  assert.match(invoke(["plan", "--manifest", malformed], 2).message, /must be a JSON boolean/);

  const collision = writeManifest(root, {
    objective: "Detect normalized writer collision",
    missions: [
      baseMission({ writeMode: "writer", writePaths: ["Src/./Domain"] }),
      baseMission({
        id: "M02",
        specialist: "data_systems",
        relationship: "parallel-owner",
        objective: "Write nested persistence code",
        distinctValue: "Own storage implementation",
        writeMode: "writer",
        writePaths: ["src/domain/persistence"],
      }),
    ],
  }, "normalized-collision.json");
  assert.match(invoke(["plan", "--manifest", collision], 2).message, /writer path collision/);
}));

test("working commons rejects symlinked managed paths without changing target permissions", () => withTemp((root) => {
  const target = path.join(root, "target");
  const linked = path.join(root, "linked");
  fs.mkdirSync(target, { mode: 0o755 });
  fs.chmodSync(target, 0o755);
  fs.symlinkSync(target, linked, "dir");
  const failed = invoke([
    "commons-init", "--workspace-dir", linked,
    "--session-key", "session-1", "--run-id", "run-1",
    "--participants", "M01,M02",
  ], 2);
  assert.match(failed.message, /contains a symlink/);
  assert.equal(fs.statSync(target).mode & 0o777, 0o755);
}));
