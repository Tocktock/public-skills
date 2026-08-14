#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PYTHON_BACKEND = path.join(SCRIPT_DIR, "gpt_squad_context.py");

if (!fs.existsSync(PYTHON_BACKEND)) {
  process.stderr.write(`gpt-squad-context: FAIL\nPython backend is missing: ${PYTHON_BACKEND}\n`);
  process.exit(3);
}

const python = process.env.PYTHON || process.env.PYTHON3 || "python3";
const versionProbe = spawnSync(
  python,
  ["-c", "import sqlite3, sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
  { encoding: "utf8", env: process.env },
);

if (versionProbe.error) {
  process.stderr.write(`gpt-squad-context: FAIL\nUnable to execute ${python}: ${versionProbe.error.message}\n`);
  process.exit(3);
}

if (versionProbe.status !== 0) {
  process.stderr.write("gpt-squad-context: FAIL\nPython 3.10 or newer is required.\n");
  process.exit(3);
}

const result = spawnSync(python, [PYTHON_BACKEND, ...process.argv.slice(2)], {
  stdio: "inherit",
  env: process.env,
});

if (result.error) {
  process.stderr.write(`gpt-squad-context: FAIL\nUnable to execute ${python}: ${result.error.message}\n`);
  process.exit(3);
}

if (result.signal) {
  process.stderr.write(`gpt-squad-context: FAIL\nPython backend terminated by signal ${result.signal}\n`);
  process.exit(3);
}

process.exit(result.status ?? 3);
