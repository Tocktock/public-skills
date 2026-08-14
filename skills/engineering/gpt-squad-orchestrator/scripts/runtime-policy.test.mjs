import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.join(HERE, "gpt-squad-runtime-policy.mjs");
const PERSONA_CATALOG = path.resolve(HERE, "..", "..", "gpt-squad-installer", "assets", "persona-catalog.json");
const REGISTERED_SPECIALISTS = JSON.parse(fs.readFileSync(PERSONA_CATALOG, "utf8")).specialists.map((item) => item.name);
const TEMP_ROOT = fs.realpathSync(os.tmpdir());

function invoke(args, expected = 0) {
  const result = spawnSync(process.execPath, [CLI, ...args, "--json"], { encoding: "utf8" });
  assert.equal(result.status, expected, `${result.stdout}\n${result.stderr}`);
  return JSON.parse(result.stdout || "{}");
}

test("spawn preflight accepts the complete installed specialist catalog", () => {
  for (const specialist of REGISTERED_SPECIALISTS) {
    assert.equal(invoke(["spawn-preflight", "--agent-type", specialist, "--fork-turns", "none"]).status, "PASS");
  }
});

test("spawn preflight rejects known invalid combinations before a runtime call", () => {
  assert.equal(invoke(["spawn-preflight", "--agent-type", "data_systems", "--fork-turns", "5"]).status, "PASS");
  assert.equal(invoke(["spawn-preflight", "--agent-type", "change_review", "--fork-turns", "none"]).status, "PASS");
  assert.equal(invoke(["spawn-preflight", "--fork-turns", "all"]).status, "PASS");
  const invalid = invoke(
    ["spawn-preflight", "--agent-type", "data_systems", "--fork-turns", "all"],
    2,
  );
  assert.match(invalid.message, /mutually exclusive/);
  assert.match(invoke(["spawn-preflight", "--agent-type", "unknown"], 2).message, /unregistered specialist/);
});

test("wait policy permits one refreshed retry and one bounded release per progress epoch", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-wait-policy-"));
  const stateFile = path.join(root, "state.json");
  invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "60"]);
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"], 2).message,
    /pending wait/,
  );
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "timeout"]);
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"], 2).message,
    /inspect status once/,
  );
  const refreshed = invoke([
    "wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "status-refresh",
  ]);
  assert.equal(refreshed.statusRefreshedAfterTimeout, true);
  assert.equal(refreshed.statusRefreshesSinceProgress, 1);
  assert.equal(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"]).status,
    "PASS",
  );
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "timeout"]);
  assert.match(
    invoke([
      "wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "status-refresh",
    ], 2).message,
    /already used its single status inspection/,
  );
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"], 2).message,
    /one bounded wait-release/,
  );
  const released = invoke([
    "wait-release", "--state-file", stateFile, "--agent-id", "agent-1",
    "--reason", "result_blocks_integration",
  ]);
  assert.equal(released.status, "PASS");
  assert.equal(released.waitReleasesSinceProgress, 1);
  assert.equal(released.remainingWaitReleasesWithoutProgress, 0);
  assert.equal(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"]).status,
    "PASS",
  );
  const finalTimeout = invoke([
    "wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "timeout",
  ]);
  assert.equal(finalTimeout.consecutiveTimeouts, 3);
  assert.equal(finalTimeout.waitReleasesSinceProgress, 1);
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"], 2).message,
    /timed out after its bounded wait-release/,
  );
  assert.match(
    invoke([
      "wait-release", "--state-file", stateFile, "--agent-id", "agent-1",
      "--reason", "result_blocks_integration",
    ], 2).message,
    /already used its bounded wait-release/,
  );
  assert.match(
    invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "progress"], 2).message,
    /--progress-id is required/,
  );
  const progress = invoke([
    "wait-record", "--state-file", stateFile, "--agent-id", "agent-1",
    "--outcome", "progress", "--progress-id", "event-001",
  ]);
  assert.equal(progress.consecutiveTimeouts, 0);
  assert.equal(progress.waitReleasesSinceProgress, 0);
  assert.equal(progress.statusRefreshesSinceProgress, 0);
  assert.equal(progress.progressId, "event-001");
  assert.match(
    invoke([
      "wait-record", "--state-file", stateFile, "--agent-id", "agent-1",
      "--outcome", "progress", "--progress-id", "event-001",
    ], 2).message,
    /progress ID must change/,
  );
  assert.equal(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"]).status,
    "PASS",
  );
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "timeout"]);
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "status-refresh"]);
  invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"]);
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "timeout"]);
  const nextEpochRelease = invoke([
    "wait-release", "--state-file", stateFile, "--agent-id", "agent-1",
    "--reason", "result_blocks_integration",
  ]);
  assert.equal(nextEpochRelease.waitReleasesSinceProgress, 1);
  invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"]);
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "completed"]);
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"], 2).message,
    /already completed/,
  );
  assert.equal(fs.statSync(root).mode & 0o777, 0o700);
  assert.equal(fs.statSync(stateFile).mode & 0o777, 0o600);
});

test("legacy runtime state preserves consumed refresh and release budgets until new progress", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-wait-legacy-"));
  const stateFile = path.join(root, "state.json");
  fs.writeFileSync(stateFile, `${JSON.stringify({
    schemaVersion: 1,
    agents: {
      "agent-1": {
        pendingWait: false,
        waitBlocked: true,
        statusRefreshedAfterTimeout: false,
        consecutiveTimeouts: 3,
        terminal: false,
        lastOutcome: "timeout",
        lastWaitRelease: {
          agentId: "agent-1",
          reason: "result_blocks_integration",
          releasedAt: "2026-08-14T00:00:00.000Z",
        },
      },
    },
    interrupts: [],
    waitReleases: [],
    updatedAt: "2026-08-14T00:00:00.000Z",
  }, null, 2)}\n`, { mode: 0o600 });

  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"], 2).message,
    /timed out after its bounded wait-release/,
  );
  assert.match(
    invoke([
      "wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "status-refresh",
    ], 2).message,
    /already used its single status inspection/,
  );
  assert.match(
    invoke([
      "wait-release", "--state-file", stateFile, "--agent-id", "agent-1",
      "--reason", "result_blocks_integration",
    ], 2).message,
    /already used its bounded wait-release/,
  );

  const progress = invoke([
    "wait-record", "--state-file", stateFile, "--agent-id", "agent-1",
    "--outcome", "progress", "--progress-id", "legacy-upgrade-event-001",
  ]);
  assert.equal(progress.statusRefreshesSinceProgress, 0);
  assert.equal(progress.waitReleasesSinceProgress, 0);
  assert.equal(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "15"]).status,
    "PASS",
  );
});

test("an aborted runtime wait clears pending state without marking the specialist terminal", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-wait-abort-"));
  const stateFile = path.join(root, "state.json");
  invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"]);
  const aborted = invoke([
    "wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "aborted",
  ]);
  assert.equal(aborted.terminal, false);
  assert.equal(aborted.waitBlocked, false);
  assert.equal(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"]).status,
    "PASS",
  );
});

test("status refresh cannot overwrite an in-flight wait and early releases are rejected", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-wait-transition-"));
  const stateFile = path.join(root, "state.json");
  invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "30"]);
  assert.match(
    invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "status-refresh"], 2).message,
    /pending wait/,
  );
  invoke(["wait-record", "--state-file", stateFile, "--agent-id", "agent-1", "--outcome", "timeout"]);
  assert.match(
    invoke(["wait-release", "--state-file", stateFile, "--agent-id", "agent-1", "--reason", "keep-polling"], 2).message,
    /wait-release reason/,
  );
  assert.match(
    invoke([
      "wait-release", "--state-file", stateFile, "--agent-id", "agent-1",
      "--reason", "result_blocks_integration",
    ], 2).message,
    /only after at least two consecutive timeouts/,
  );
});

test("wait timeouts are bounded to user-visible backpressure limits", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-wait-bounds-"));
  const stateFile = path.join(root, "state.json");
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "a", "--timeout-seconds", "0"], 2).message,
    /1 to 60/,
  );
  assert.match(
    invoke(["wait-preflight", "--state-file", stateFile, "--agent-id", "a", "--timeout-seconds", "61"], 2).message,
    /1 to 60/,
  );
});


test("stale runtime-policy locks are recovered without weakening live locks", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-stale-lock-"));
  const stateFile = path.join(root, "state.json");
  const lockFile = `${stateFile}.lock`;
  fs.writeFileSync(lockFile, `${JSON.stringify({ pid: 99999999 })}\n`, { mode: 0o600 });
  const stale = new Date(Date.now() - 60_000);
  fs.utimesSync(lockFile, stale, stale);
  const result = invoke([
    "wait-preflight", "--state-file", stateFile, "--agent-id", "agent-1", "--timeout-seconds", "5",
  ]);
  assert.equal(result.status, "PASS");
  assert.equal(fs.existsSync(lockFile), false);
});


test("runtime policy refuses symlinked state paths before changing target permissions", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-runtime-symlink-"));
  const target = path.join(root, "target");
  const linked = path.join(root, "linked");
  fs.mkdirSync(path.join(target, "nested"), { recursive: true, mode: 0o755 });
  fs.chmodSync(target, 0o755);
  fs.chmodSync(path.join(target, "nested"), 0o755);
  fs.symlinkSync(target, linked, "dir");
  const failed = invoke([
    "wait-preflight", "--state-file", path.join(linked, "nested", "state.json"),
    "--agent-id", "agent-1", "--timeout-seconds", "30",
  ], 2);
  assert.match(failed.message, /contains a symlink/);
  assert.equal(fs.statSync(target).mode & 0o777, 0o755);
  assert.equal(fs.statSync(path.join(target, "nested")).mode & 0o777, 0o755);
  fs.rmSync(root, { recursive: true, force: true });
});

test("interrupt preflight requires and records a structured reason code", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-runtime-interrupt-"));
  const state = path.join(root, "runtime-policy.json");
  const accepted = invoke([
    "interrupt-preflight", "--state-file", state, "--agent-id", "agent-1",
    "--reason", "canonical_context_changed",
  ]);
  assert.equal(accepted.status, "PASS");
  assert.match(
    invoke([
      "interrupt-preflight", "--state-file", state, "--agent-id", "agent-1",
      "--reason", "duplicate_work",
    ], 2).message,
    /pending interrupt/,
  );
  let stored = JSON.parse(fs.readFileSync(state, "utf8"));
  assert.equal(stored.interrupts.length, 1);
  assert.equal(stored.interrupts[0].reason, "canonical_context_changed");
  const recorded = invoke([
    "interrupt-record", "--state-file", state, "--agent-id", "agent-1", "--outcome", "completed",
  ]);
  assert.equal(recorded.status, "PASS");
  stored = JSON.parse(fs.readFileSync(state, "utf8"));
  assert.equal(stored.interrupts[0].outcome, "completed");
  assert.equal(stored.agents["agent-1"].pendingInterrupt, null);
  assert.match(
    invoke([
      "interrupt-preflight", "--state-file", state, "--agent-id", "agent-1",
      "--reason", "too-slow",
    ], 2).message,
    /interrupt reason/,
  );
  fs.rmSync(root, { recursive: true, force: true });
});
