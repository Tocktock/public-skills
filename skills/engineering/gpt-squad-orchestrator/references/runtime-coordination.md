# Runtime Coordination

## Purpose

The Context Hub coordinates accepted state. Collaboration tools still need preflight rules so invalid spawn calls and timeout-centered polling do not dominate user-visible latency.

Use:

```text
<skill-dir>/scripts/gpt-squad-runtime-policy.mjs
```

This helper is a deterministic orchestration guard. It is not a replacement for Codex runtime events and cannot prevent a root from bypassing it.

## Spawn preflight

Before `spawn_agent`:

```bash
node <skill-dir>/scripts/gpt-squad-runtime-policy.mjs spawn-preflight \
  --agent-type data_systems \
  --fork-turns 8 \
  --json
```

Rules:

```text
typed specialist + full-history fork  prohibited
typed specialist                       no fork or bounded 1–20 turns
full-history fork                       omit specialist override
unregistered specialist                 prohibited
```

Dispatch all independent missions in a wave before waiting.

## Wait backpressure

Initialize a session-local state file outside the repository, for example:

```text
${CODEX_HOME:-~/.codex}/runtime/gpt-squad/sessions/<session-key>/runtime-policy.json
```

Before one blocking wait:

```bash
node <skill-dir>/scripts/gpt-squad-runtime-policy.mjs wait-preflight \
  --state-file <state-file> \
  --agent-id <agent-id> \
  --timeout-seconds 60 \
  --json
```

Record the observed outcome:

```bash
node <skill-dir>/scripts/gpt-squad-runtime-policy.mjs wait-record \
  --state-file <state-file> \
  --agent-id <agent-id> \
  --outcome timeout \
  --json
```

Supported outcomes:

```text
timeout
status-refresh
progress
completed
cancelled
failed
aborted
```

After the first timeout, record one `status-refresh`, but do not treat an unchanged running status as progress. That refresh permits one deliberate retry. If the retry also times out, status refresh alone is no longer sufficient: record real `progress` with a new `--progress-id`, a terminal outcome, or one explicit `wait-release` with a bounded reason. A progress ID must identify a newly observed child event, result, or evidence digest; never invent or reuse it merely to unlock another wait. A pending wait blocks duplicate waits and cannot be overwritten by a concurrent status refresh. General blocking waits are restricted to 1–60 seconds.

If the collaboration call itself fails after preflight, record `aborted`. This clears the pending wait without falsely marking the specialist terminal.

For the rare case where a repeatedly timed-out result is now the only integration blocker:

```bash
node <skill-dir>/scripts/gpt-squad-runtime-policy.mjs wait-release \
  --state-file <state-file> \
  --agent-id <agent-id> \
  --reason result_blocks_integration \
  --json
```

Allowed release reasons are `result_blocks_integration`, `user_requested_completion`, and `no_other_root_work`. A release is available only after two consecutive timeouts and may be used at most once until new progress is recorded. If the released wait also times out, no further wait is permitted until a new progress ID or terminal outcome is recorded. Every release is recorded; it is an auditable final-blocker override, not permission to resume a polling loop.

Recommended wave policy:

```text
dispatch independent work
continue non-duplicative root integration work
perform at most one initial wait per wave
on the first timeout, inspect status once
allow one deliberate retry after that single inspection
use at most one bounded final-blocker release after the retry times out
never re-wait again until a new progress ID or terminal outcome exists
after the final timeout, inspect status again only after an external attention signal or meaningful backoff when terminal state is plausible; unchanged status never unlocks another wait
```

This is backpressure, not native event-driven completion. Measure timeout rate and user-visible latency after adoption.

## Structured interrupt reason

Before `interrupt_agent`:

```bash
node <skill-dir>/scripts/gpt-squad-runtime-policy.mjs interrupt-preflight \
  --state-file <state-file> \
  --agent-id <agent-id> \
  --reason canonical_context_changed \
  --json
```

Allowed reasons:

```text
user_goal_changed
canonical_context_changed
mission_scope_invalid
duplicate_work
negative_value_wait
specialist_blocked
runtime_failure
superseded_by_successor
```

The helper rejects duplicate pending interrupt requests and records the reason in bounded owner-only runtime-policy state. After the actual interrupt call, record its outcome:

```bash
node <skill-dir>/scripts/gpt-squad-runtime-policy.mjs interrupt-record \
  --state-file <state-file> \
  --agent-id <agent-id> \
  --outcome completed \
  --json
```

Supported outcomes are `completed`, `cancelled`, `failed`, and `not-sent`. Do not interrupt solely because elapsed time feels long; compare remaining decision value, current progress, and user intent.

## Runtime-policy state boundary

The helper stores owner-only JSON and uses an exclusive lock plus atomic replacement. It coordinates cooperating root invocations, but it is not an operating-system sandbox against another process running as the same user.
