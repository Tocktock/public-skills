import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, "..");
const INSTALLER_ASSETS = path.resolve(SKILL_DIR, "../gpt-squad-installer/assets");

function read(relative) {
  return fs.readFileSync(path.join(SKILL_DIR, relative), "utf8");
}

test("orchestrator uses same accepted truth with role-specific transactional views", () => {
  const skill = read("SKILL.md");
  assert.match(skill, /Do not give every agent the same full transcript/i);
  assert.match(skill, /same accepted objective, constraints, facts, decisions, and invariants/i);
  assert.match(skill, /recorded mission-specific context view/i);
  assert.match(skill, /transactional Context Hub/i);
  assert.match(skill, /checkout proves what the Hub delivered/i);
  assert.match(skill, /separate private working memory/i);
});

test("session-persistent explicit opt-in remains intact", () => {
  const skill = read("SKILL.md");
  assert.match(skill, /Session-persistent explicit opt-in/i);
  assert.match(skill, /new Codex task or conversation session starts dormant/i);
  assert.match(skill, /first explicit activation/i);
  assert.match(skill, /remains active across later user turns/i);
  assert.match(skill, /explicitly opts out or the session ends/i);
  assert.match(skill, /Completing one user request does not deactivate squad mode/i);
});

test("Context Hub protocol records checkout, proposals, automatic invalidation, and sealed results", () => {
  const skill = read("SKILL.md");
  const hub = read("references/context-hub.md");
  for (const command of ["init", "mission-add", "checkout", "propose", "promote", "delta", "result-submit", "challenge-disposition", "check", "close", "migrate-legacy"]) {
    assert.match(`${skill}\n${hub}`, new RegExp(`\\b${command}\\b`, "i"), `missing command ${command}`);
  }
  assert.match(hub, /per-entry and per-artifact versions/i);
  assert.match(hub, /Manual affected missions are additive/i);
  assert.match(hub, /Result rows are immutable/i);
  assert.match(hub, /SQLite `BEGIN IMMEDIATE`/i);
  assert.match(hub, /generated views/i);
  assert.match(hub, /not an operating-system security sandbox/i);
});

test("synchronization guidance preserves private memory and blind-first independence", () => {
  const synchronization = read("references/context-synchronization.md");
  assert.match(synchronization, /Shared canonical core/i);
  assert.match(synchronization, /Mission context view/i);
  assert.match(synchronization, /Private working context/i);
  assert.match(synchronization, /Independent review view/i);
  assert.match(synchronization, /automatic invalidation/i);
  assert.match(synchronization, /Short direct clarification is allowed/i);
  assert.match(synchronization, /must be recorded in the Hub/i);
});

test("mission and integration guidance enforce distinct ownership and transactional closure", () => {
  const mission = read("references/mission-command.md");
  const integration = read("references/integration-and-evaluation.md");
  assert.match(mission, /one distinct decision value/i);
  assert.match(mission, /one concrete responsibility surface/i);
  assert.match(mission, /Parallel writers require/i);
  assert.match(mission, /followup_task/i);
  assert.match(integration, /sealed result/i);
  assert.match(integration, /FAIL.*UNRESOLVED/is);
  assert.match(integration, /check --for-close|--for-close/i);
  assert.match(integration, /child `session_meta`/i);
});

test("generated templates and persistent policies point to checkout views rather than transcript sharing", () => {
  for (const asset of [
    "assets/shared-context.template.md",
    "assets/mission-brief.template.md",
    "assets/work-map.template.md",
    "assets/result-note.template.md",
  ]) {
    const text = read(asset);
    assert.match(text, /generated|Submit through `result-submit`/i, `${asset} does not identify generated or sealed state`);
  }
  const agents = fs.readFileSync(path.join(INSTALLER_ASSETS, "agents-policy.md"), "utf8");
  const policy = fs.readFileSync(path.join(INSTALLER_ASSETS, "squad-policy.txt"), "utf8");
  for (const text of [agents, policy]) {
    assert.match(text, /transactional.*Context Hub/is);
    assert.match(text, /recorded role-specific checkout view/i);
    assert.match(text, /Do not share the full transcript|rather than the full transcript/i);
    assert.match(text, /automatically invalidates recorded consumers/i);
  }
});
