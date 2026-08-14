# Operational Lifecycle

## Purpose

The Context Hub must distinguish accepted completion from historical cleanup.

A run that can satisfy all acceptance gates closes with `completed` or `superseded`. A run that is stale, over budget, replaced, or no longer worth completing closes through the explicit non-acceptance `run-abandon` path. Never raise a hard budget merely to make an unhealthy run appear acceptable.

## Terminal mission invariant

A mission in `superseded` or `rejected` state must use:

```text
context_state = terminal-not-applicable
```

The status and context state change in the same transaction. A discarded mission is not eligible for another checkout and does not block closure as stale. A non-terminal mission must never use `terminal-not-applicable`.

Repair historical invalid rows safely:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs repair-terminal-context \
  --run-dir <run-dir> \
  --json

node <skill-dir>/scripts/gpt-squad-context.mjs repair-terminal-context \
  --run-dir <run-dir> \
  --apply \
  --json
```

The first command is a dry run. Apply only after reviewing the exact mission list.

## Mutation-time budgets

The Hub checks the projected post-mutation state before committing:

```text
generated shared-ledger bytes
active canonical entry count
mission count
revision-history count
```

The exact maximum is permitted. Maximum plus one rejects the transaction. Rejection must leave no partial entry version, artifact version, revision, event, mission invalidation, or proposal disposition.

The following mutation paths enforce the guard:

```text
init
promote
artifact-record
migrate-legacy
run-rollover
```

Treat an 80% warning as a rollover signal rather than a reason to enlarge the limit.

## Session audit

Use a read-oriented operational audit before accepting work or when a session contains old runs:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs session-audit \
  --runtime-root "${CODEX_HOME:-$HOME/.codex}/runtime/gpt-squad" \
  --session-key <session-key> \
  --stale-hours 24 \
  --json
```

It reports:

```text
run age and status
budget consumption
terminal-stale rows
refresh-required missions
pending proposals
Context Hub integrity errors and warnings
```

`session-audit` uses a query-only SQLite connection and does not mutate canonical rows or file modes. It prefers SQLite `mode=ro`; when a live WAL cannot be attached in that mode, it falls back to `mode=rw` with `PRAGMA query_only=ON` and still avoids chmod or journal-mode changes. It checks database integrity once per session and then evaluates each run. SQLite may open or attach existing WAL sidecars, so this remains an operational diagnostic rather than a forensic no-touch acquisition command.

## Abandon unhealthy work

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs run-abandon \
  --run-dir <run-dir> \
  --reason '<why the run is not accepted>' \
  --successor-run-id <optional-successor> \
  --json
```

One transaction:

```text
rejects pending proposals
supersedes unfinished missions
normalizes discarded mission context state
records the reason and optional successor
closes the run as abandoned
```

An abandoned run is historical evidence, not final acceptance evidence. Existing budget overruns are reported as warnings after abandonment so cleanup remains possible; structural corruption, hash mismatch, or foreign-key failure still fails integrity checks.

## Minimal rollover

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs run-rollover \
  --run-dir <source-run-dir> \
  --new-run-id <successor-run-id> \
  --reason '<why a compact successor is required>' \
  --entry-ids F-001,D-002,I-001 \
  --artifact-keys repo:primary \
  --json
```

`--include-global-active` selects every active globally visible canonical entry. Use it only after reviewing the resulting set.

The successor copies only explicitly selected active global entries and artifacts. Before commit, the Hub verifies the source canonical snapshot and selected content hashes, evaluates the successor semantic state, and enforces hard budgets. It does not copy missions, results, proposals, checkouts, private context, superseded entries, or old events. Register only currently necessary missions and issue fresh checkouts.

Rollover and abandonment are deliberately separate. First create and verify the successor. Only then close the source explicitly:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs run-abandon \
  --run-dir <source-run-dir> \
  --reason '<why the source is no longer acceptance work>' \
  --successor-run-id <successor-run-id> \
  --json
```

`run-rollover --abandon-source` is rejected. This prevents a successor projection failure from silently abandoning the source in the same operation. If successor projection or directory creation fails, the Hub removes the canonical successor row and its generated directory before returning failure.

## Consistent snapshot

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs snapshot \
  --run-dir <run-dir> \
  --output-dir <new-snapshot-directory> \
  --json
```

The command opens the canonical database read-only, verifies that the requested run exists, uses the SQLite online backup API, validates the actual schema version, and checks `integrity_check` plus `foreign_key_check` before atomically publishing an owner-only database and manifest. The manifest records session key, source run ID, source revision and status, but omits the local absolute source path. The command refuses overwrite and symlinked managed paths.

A first-class restore command and automatic retention are not part of this version. Test restore procedures before relying on snapshots for disaster recovery.

## Acceptance sequence

Before final acceptance:

```text
session-audit has no active FAIL
current run check passes
pending proposals are zero
refresh-required missions are zero
check --for-close passes
close succeeds
```

If those conditions cannot be met without hiding history or raising a hard limit, roll over or abandon instead.
