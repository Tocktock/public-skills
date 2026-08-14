import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, "..");
const REPO_ROOT = path.resolve(SKILL_DIR, "../../..");

function read(relative) {
  return fs.readFileSync(path.join(SKILL_DIR, relative), "utf8");
}

test("orchestrator documents pre-commit budgets and terminal-state repair", () => {
  const skill = read("SKILL.md");
  const lifecycle = read("references/operational-lifecycle.md");
  assert.match(skill, /version: "3\.4"/);
  assert.match(skill, /projected ledger, active-ID, mission, and revision budgets before commit/i);
  assert.match(skill, /terminal-not-applicable/);
  assert.match(skill, /repair-terminal-context/);
  assert.match(skill, /run-rollover/);
  assert.match(skill, /run-abandon/);
  assert.match(lifecycle, /Maximum plus one rejects the transaction/i);
  assert.match(lifecycle, /SQLite online backup API/i);
  assert.match(lifecycle, /non-acceptance/i);
  assert.match(lifecycle, /Rollover and abandonment are deliberately separate/i);
  assert.match(lifecycle, /source canonical snapshot/i);
  assert.match(lifecycle, /omits the local absolute source path/i);
});

test("review persona owns holistic adversarial review without duplicating falsification", () => {
  const skill = read("SKILL.md");
  const mission = read("references/mission-command.md");
  const personas = read("references/persona-catalog.md");
  const autonomy = read("references/autonomous-cooperation.md");
  const integration = read("references/integration-and-evaluation.md");
  assert.match(skill, /change_review[\s\S]*holistic[\s\S]*adversarial pass/i);
  assert.match(skill, /Adversarial review is not a finding quota/i);
  assert.match(mission, /Every review mission includes a proportionate adversarial pass/i);
  assert.match(mission, /Do not duplicate `quality_falsification`/i);
  assert.match(personas, /change_review[\s\S]*acceptance readiness/i);
  assert.match(personas, /quality_falsification[\s\S]*specific material claim/i);
  assert.match(autonomy, /change_review` alone for a normal holistic review/i);
  assert.match(integration, /Review acceptance/i);
});

test("runtime coordination contract blocks invalid spawn and timeout polling loops", () => {
  const skill = read("SKILL.md");
  const runtime = read("references/runtime-coordination.md");
  assert.match(skill, /gpt-squad-runtime-policy\.mjs/);
  assert.match(runtime, /typed specialist \+ full-history fork\s+prohibited/i);
  assert.match(runtime, /1–60 seconds/);
  assert.match(runtime, /permits one deliberate retry/i);
  assert.match(runtime, /one `status-refresh`/i);
  assert.match(runtime, /new `--progress-id`/i);
  assert.match(runtime, /at most once until new progress/i);
  assert.match(runtime, /if the released wait also times out, no further wait is permitted/i);
  assert.match(runtime, /external attention signal or meaningful backoff/i);
  assert.match(runtime, /unchanged status never unlocks another wait/i);
  assert.match(runtime, /wait-release/i);
  assert.match(runtime, /record `aborted`/i);
  assert.match(runtime, /interrupt-record/i);
  assert.match(runtime, /bounded owner-only runtime-policy state/i);
  assert.match(runtime, /not native event-driven completion/i);
});

test("repository CI executes operational and runtime-policy regressions", () => {
  const ci = fs.readFileSync(path.join(REPO_ROOT, "scripts/ci-check.sh"), "utf8");
  assert.match(ci, /operational_hardening_test\.py/);
  assert.match(ci, /runtime-policy\.test\.mjs/);
  assert.match(ci, /gpt-squad-runtime-policy\.mjs/);
  assert.match(ci, /gpt-squad-cooperation\.mjs/);
  assert.match(ci, /cooperation\.test\.mjs/);
});
