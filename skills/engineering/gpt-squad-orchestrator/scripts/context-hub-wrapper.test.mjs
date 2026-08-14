import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.resolve(HERE, "../scripts/gpt-squad-context.mjs");
const TEMP_ROOT = fs.realpathSync(os.tmpdir());

function run(args, expectedStatus = 0) {
  const result = spawnSync(process.execPath, [CLI, ...args, "--json"], {
    encoding: "utf8",
    env: process.env,
  });
  assert.equal(result.status, expectedStatus, `stdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
  return JSON.parse(result.stdout || "{}");
}

test("Node wrapper executes the Python SQLite Context Hub and propagates status", () => {
  const root = fs.mkdtempSync(path.join(TEMP_ROOT, "gpt-squad-context-wrapper-"));
  try {
    const initialized = run([
      "init",
      "--runtime-root", path.join(root, "runtime"),
      "--session-key", "wrapper-session",
      "--run-id", "wrapper-run",
      "--objective", "Verify the public Node CLI",
      "--intent", "Keep Node 18 compatibility while using SQLite transactions",
      "--success-json", "[]",
      "--constraints-json", "[]",
    ]);
    assert.equal(initialized.status, "PASS");
    const checked = run(["check", "--run-dir", initialized.runDir]);
    assert.equal(checked.status, "PASS");
    const failed = run(["delta", "--run-dir", initialized.runDir, "--mission-id", "M01", "--since-revision", "0"], 2);
    assert.equal(failed.status, "FAIL");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
