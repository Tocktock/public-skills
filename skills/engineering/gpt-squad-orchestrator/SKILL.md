---
name: gpt-squad-orchestrator
description: Explicitly activate and orchestrate a session-persistent, autonomy-first Chief Engineer squad. Give elite generalist specialists outcome ownership, choose the least coordination ceremony that preserves correctness, support provisional peer cooperation through a bounded Working Commons, and use the transactional Context Hub only when accepted shared state requires it.
metadata:
  version: "3.4"
---

# GPT Squad Orchestrator

## Operating principle

Do not give every agent the same full transcript.

Give every participating agent:

- the same accepted objective, constraints, facts, decisions, and invariants;
- a recorded mission-specific context view appropriate to its role;
- separate private working memory;
- enough authority to own a coherent outcome end to end.

Every specialist is an elite generalist. Its specialty is an attention prior, not a capability boundary. Give the objective, success conditions, evidence, constraints, authority, and ownership; do not prescribe a fixed investigation sequence, tool order, or conclusion.

Use the least coordination ceremony that preserves correctness:

```text
Lightweight   independent outcomes, no shared mutable truth
Cooperative   provisional questions and help through Working Commons
Transactional accepted shared state, dependencies, writers, stale reuse, or challenge
```

The root is the Chief Engineer and final accountable owner. It promotes only information that changes another mission, a shared contract, ownership, material risk, or final acceptance. Local reversible specialist decisions stay local. Provisional cooperation stays non-binding until Root deliberately promotes the smallest sufficient canonical statement.

The transactional Context Hub remains the durable authority for accepted shared truth. It records what was delivered, automatically invalidates consumers when accepted information changes, and seals results. A checkout proves what the Hub delivered; it does not prove what the model understood.

## Session-persistent explicit opt-in boundary

Do not activate this skill from task complexity alone. A new Codex task or conversation session starts dormant.

The first explicit activation must come from a user request that names `$gpt-squad-orchestrator` or GPT Squad, requests registered specialists, or asks for sub-agent, delegated-agent, or parallel-agent work.

After first explicit activation, squad mode remains active across later user turns in the same Codex session until the user explicitly opts out or the session ends. Do not require repeated invocation. A plain continuation remains inside active squad mode.

Completing one user request does not deactivate squad mode.

An unscoped opt-out such as `do not use GPT Squad`, `root only`, or `no sub-agents` disables squad mode for the current session until explicit reactivation. A request-scoped opt-out pauses only that request. A new Codex session starts dormant.

Inside active squad mode, the root owns user intent, the complete outcome, cross-specialty tradeoffs, canonical state, writer coordination, integration, final verification, risk acceptance, and final communication.

Before the first squad composition in a session, read:

- [references/persona-catalog.md](references/persona-catalog.md)
- [references/mission-command.md](references/mission-command.md)
- [references/autonomous-cooperation.md](references/autonomous-cooperation.md)
- [references/context-hub.md](references/context-hub.md)
- [references/context-synchronization.md](references/context-synchronization.md)
- [references/operational-lifecycle.md](references/operational-lifecycle.md)
- [references/runtime-coordination.md](references/runtime-coordination.md)

Before integrating multi-specialist work or declaring completion, read:

- [references/integration-and-evaluation.md](references/integration-and-evaluation.md)

## 1. Frame the mission

Establish:

- observable objective and intent;
- success criteria;
- source of truth;
- hard constraints and non-goals;
- material uncertainty and risk;
- Lean, Standard, or Deep effort posture.

Do enough work to select expertise without completing the specialist mission first.

## 2. Build the smallest sufficient squad

The request that activates or reactivates squad mode is an expectation to delegate. Use at least one suitable registered specialist unless none can materially contribute; then explain briefly and proceed root-only.

On later active turns, use specialists only when exceptional depth, independent judgment, context continuity, or genuine parallel ownership adds value. Trivial, inseparable, or negative-value delegation work may remain root-only without deactivating squad mode.

Prefer one lead specialist. Add only what changes the result:

- **advisor** — distinct expert judgment;
- **parallel owner** — independently bounded outcome;
- **independent challenger** — material risk or falsifiable claim.

Investigation, design, implementation, and verification are mission activities, not permanent process roles.

For every selected specialist, state its distinct decision value and responsibility surface. Do not assign multiple specialists the same generic review mission.

When review is the requested outcome, prefer `change_review` for holistic coverage, simplicity, scope discipline, maintainability, compatibility, and acceptance readiness. It performs a proportionate adversarial pass by default. Use a domain specialist instead for a narrowly specialized review, and add `quality_falsification` only when a distinct executable falsification method can materially change the verdict. Review is non-mutating with respect to the reviewed change unless the user authorizes fixes. A reviewer may own isolated tests or reproduction artifacts on a separate declared surface. Any blind-first or `independent-challenger` mission is read-only by contract.

A specialist may request another home field when it discovers a decision that its current mission cannot settle efficiently. In lightweight work, send the same structured request directly to Root. In cooperative work, record it in Working Commons. Root decides whether to reuse, spawn, decline, or answer from existing evidence based on distinct value, ownership, independence, and coordination cost.

## Review missions

For a `change_review` mission:

- establish the exact target, applicable comparison baseline or version, intent, non-goals, and stable contracts; for Git changes, record exact base and head;
- account for every changed path and materially affected caller, consumer, schema, state transition, side effect, rollout, and rollback path;
- examine correctness, simplicity, scope, maintainability, compatibility, operability, and evidence quality;
- search for counterexamples, hidden coupling, false-confidence tests, unnecessary abstraction, duplicate concepts, and change that should be deleted or narrowed;
- actively try to disprove candidate findings before reporting them;
- report only introduced, reachable, material, supported, actionable, and calibrated issues;
- return findings first, then verdict, coverage, checks, and residual risk.

Adversarial review is not a finding quota. A well-covered change may correctly return `PASS` with no findings. Transactional review verdicts use `PASS`, `FAIL`, or `UNRESOLVED`; human pull-request reviews map `PASS` with non-blocking findings to `COMMENT` or approval with comments, `FAIL` to `REQUEST_CHANGES`, and `UNRESOLVED` to an explicitly inconclusive non-approval review. If the user requests both review and fixes, preserve the initial review, enter an explicit fix phase, and re-review the resulting delta. The same specialist may fix when independence is unnecessary; use a fresh reviewer when independent verification matters. A reviewer that implements the fix is not independent evidence for its own final acceptance; use a fresh reviewer when independence materially matters.

## 3. Choose coordination intensity

Do not make full transactional coordination the default merely because more than one agent exists.

When multiple missions, writers, dependencies, or uncertain coordination needs make the mode non-obvious, use the deterministic autonomy planner. Do not require a manifest for an obviously lightweight single mission:

```bash
cooperation_script=<skill-dir>/scripts/gpt-squad-cooperation.mjs

node "$cooperation_script" plan \
  --manifest <cooperation-plan.json> \
  --json
```

Start from [assets/cooperation-plan.example.json](assets/cooperation-plan.example.json). The planner rejects a mode below the safe minimum while allowing a more conservative mode with a ceremony warning.

### Lightweight

Use a complete mission packet and direct result return when missions are independently bounded, read-only or singly owned, and do not share mutable truth. Several independent read-only specialists may remain lightweight.

### Cooperative

Use the bounded, non-binding Working Commons when specialists need provisional questions, hypotheses, help requests, or timing coordination without changing accepted shared truth.

```bash
node "$cooperation_script" commons-init \
  --workspace-dir <private-runtime-workspace> \
  --session-key <task-or-thread-id> \
  --run-id <stable-run-id> \
  --participants M01,M02 \
  --json
```

Working Commons items expire, are audience-filtered, lock-protected, and explicitly non-binding. Facts, decisions, invariants, ownership, and risk acceptance are rejected as Commons item types.

### Transactional

Use the Context Hub when accepted cross-mission state may change, work spans waves, dependencies exist, multiple writers participate, reused context may be stale, or an independent challenge requires sealed evidence and disposition.

```bash
context_script=<skill-dir>/scripts/gpt-squad-context.mjs
runtime_root="${CODEX_HOME:-$HOME/.codex}/runtime/gpt-squad"

node "$context_script" init \
  --runtime-root "$runtime_root" \
  --session-key <task-or-thread-id> \
  --run-id <stable-run-id> \
  --objective '<observable objective>' \
  --intent '<why the result matters>' \
  --success-json '["<observable success>"]' \
  --constraints-json '["<hard constraint>"]' \
  --json
```

Canonical state is stored transactionally in:

```text
${CODEX_HOME:-~/.codex}/runtime/gpt-squad/sessions/<session-key>/
  context-hub.sqlite3
  runs/<run-id>/
    shared-context.md
    work-map.md
    missions/
    results/
    checkouts/
    proposals/
    events.jsonl
```

SQLite is canonical. Markdown and JSON files under the run directory are generated views and must never be manually edited as source of truth. Cooperative mode may escalate to transactional mode as soon as provisional information becomes binding.

## 4. Record canonical context and artifacts

The root creates canonical context through proposals and promotion. Do not edit `shared-context.md`.

```bash
node "$context_script" propose \
  --run-dir <run-dir> \
  --mission-id root \
  --type fact \
  --claim '<accepted factual claim>' \
  --evidence-json '{"source":"<path, command, observation, or contract>"}' \
  --visible-to all \
  --topics '<optional topics>' \
  --json

node "$context_script" promote \
  --run-dir <run-dir> \
  --proposal-id P-000001 \
  --rationale '<why the evidence supports promotion>' \
  --json
```

Record repository and artifact versions that materially constrain the work:

```bash
node "$context_script" artifact-record \
  --run-dir <run-dir> \
  --artifact-key repo:primary \
  --repository owner/repository \
  --commit <commit-sha> \
  --path '<relevant path or scope>' \
  --summary '<why this version matters>' \
  --json
```

Canonical context uses stable IDs:

```text
F-### confirmed fact
D-### accepted decision
I-### invariant
O-### ownership boundary
C-### constraint or non-goal
R-### material risk
Q-### open question
```

Facts require evidence. Decisions require rationale. Ownership entries require shared-boundary detail.

## 5. Register missions before dispatch

```bash
node "$context_script" mission-add \
  --run-dir <run-dir> \
  --mission-id M01 \
  --specialist data_systems \
  --relationship lead \
  --objective '<owned outcome>' \
  --intent '<why this specialist changes the result>' \
  --surface '<disjoint responsibility surface>' \
  --distinct-value '<expert evidence or judgment unique to this mission>' \
  --write-mode read-only \
  --effort Standard \
  --success-json '["<mission success>"]' \
  --constraints-json '["<mission constraint>"]' \
  --verification-json '["<required verification>"]' \
  --risks-json '["<known risk>"]' \
  --depends-on M00 \
  --required-ids F-001,D-001,I-001 \
  --subscribe '<optional topics>' \
  --json
```

Use `--write-mode writer` only for coherent owned writes. Parallel writers require disjoint concrete paths, modules, generated state, or isolated worktrees. The Hub detects exact and path-prefix surface collisions; the root still reviews semantic overlap.

An independent challenger uses `--relationship independent-challenger --blind-first`.

## 6. Checkout a recorded role-specific context view

`checkout` replaces self-reported revision acknowledgement.

```bash
node "$context_script" checkout \
  --run-dir <run-dir> \
  --mission-id M01 \
  --json
```

It records and returns:

- global accepted objective, success criteria, and constraints;
- mission contract and authority;
- exact canonical entry versions delivered;
- exact artifact versions delivered;
- canonical revision hash;
- immutable context-view ID and snapshot hash.

Use the returned context-view JSON or its `snapshotFile` as the mission's authoritative context capsule. Do not give the specialist the entire parent transcript, proposal inbox, or other mission results.

After checkout:

```bash
node "$context_script" mission-status \
  --run-dir <run-dir> \
  --mission-id M01 \
  --status active \
  --json
```

The deprecated `ack` command is a compatibility alias for `checkout`; do not use it in new workflows.

## 7. Delegate outcomes, not procedures

Give the specialist:

- objective, intent, and observable success;
- accepted source of truth or the appropriate mission packet or checkout;
- specialty focus as an attention prior;
- relationship and authority envelope;
- concrete ownership surface;
- dependencies and hard constraints;
- required verification;
- Lean, Standard, or Deep effort posture.

Allow the specialist to choose the method and investigate, design, implement, refactor, test, document, and follow adjacent evidence end to end. Do not require Root approval for reversible local choices inside the mission envelope.

Private scratch reasoning, raw tool output, discarded hypotheses, and temporary implementation details stay private.

Use three information tiers:

```text
private working state      one specialist only
Working Commons            provisional peer questions and coordination
canonical Context Hub      accepted cross-mission truth
```

Specialists may communicate directly for short clarification, blockers, or delivery of a recorded item or delta. Useful peer conversation is allowed. The hard boundary is that no accepted fact, decision, invariant, ownership change, dependency, or risk disposition may exist only in a direct message or Working Commons item.

Do not promote every finding. Keep local reversible decisions local. Use Working Commons when peers may benefit but the information remains provisional. Promote only the smallest statement that changes another mission, shared contract, ownership, material risk, or final acceptance.

A specialist may request additional cooperation:

```bash
node "$cooperation_script" collaboration-request \
  --workspace-dir <workspace> \
  --author M01 \
  --specialist data_systems \
  --reason '<why current expertise is insufficient>' \
  --decision-impact '<which decision may change>' \
  --expected-value '<why value exceeds coordination cost>' \
  --surface '<requested responsibility surface>' \
  --write-mode read-only \
  --json
```

Root resolves the request as `accepted`, `reused`, or `declined`. Specialists do not recursively spawn agents.

## 8. Submit proposals and promote root-validated truth

An active specialist with a current checkout may submit a proposal:

```bash
node "$context_script" propose \
  --run-dir <run-dir> \
  --mission-id M01 \
  --type fact \
  --claim '<proposed fact>' \
  --evidence-json '{"path":"...","check":"...","result":"..."}' \
  --visible-to M01,M02 \
  --topics '<optional topics>' \
  --json
```

Only the root promotes or rejects proposals.

Promotion is one SQLite transaction. It:

1. writes a new entry version;
2. increments the canonical revision;
3. records an immutable event and snapshot hash;
4. discovers consumers from recorded checkout read sets;
5. includes missions requiring the changed ID;
6. includes topic subscribers and explicit extra missions;
7. includes transitive dependents;
8. marks all affected missions `refresh-required` and reopens stale completed work;
9. validates the projected ledger, active-ID, mission, and revision budgets before commit.

The exact configured maximum is allowed. A mutation that would exceed a hard maximum is rolled back completely, including proposal disposition, revision, events, and invalidation.

Manual `--additional-affected` is additive only; it cannot remove automatically detected consumers.

The old `advance` workflow is removed because manual ledger editing is no longer canonical.

## 9. Refresh affected specialists

Inspect the mission delta:

```bash
node "$context_script" delta \
  --run-dir <run-dir> \
  --mission-id M01 \
  --since-revision <previous-revision> \
  --json
```

Then create a fresh checkout and send only the relevant delta and new context-view hash. Prefer `followup_task` when the specialist, authority, and independence still fit.

A mission cannot resume active work or submit a result while its checkout is stale.

## 10. Submit and seal results

A specialist result is submitted as structured JSON:

```json
{
  "status": "completed",
  "outcome": "Delivered the owned outcome",
  "verification": [
    {"command": "<check>", "outcome": "PASS"}
  ]
}
```

Submit it with the exact checked-out snapshot hash:

```bash
node "$context_script" result-submit \
  --run-dir <run-dir> \
  --mission-id M01 \
  --snapshot-hash <checkout-snapshot-sha256> \
  --result-file <result.json> \
  --json
```

The Hub stores an immutable result version, content hash, context-view hash, exact read set, verification evidence, verdict, and seal timestamp. A correction requires `mission-reopen`, a fresh checkout, and a new result version that supersedes the old result.

The Hub records artifacts it delivered. It cannot prove every extra file or tool output the model later inspected unless that evidence is explicitly recorded.

## 11. Resolve independent challenge outcomes

A blind-first challenger result must include:

```json
{
  "status": "completed",
  "outcome": "Independent challenge complete",
  "verification": [{"command": "<independent method>", "outcome": "PASS"}],
  "verdict": "PASS | FAIL | UNRESOLVED",
  "distinctEvidence": "<evidence path or method not copied from the lead>"
}
```

`FAIL` and `UNRESOLVED` block closure until the root records one of:

- `resolved`;
- `accepted-risk` with an active `D-###` decision;
- `mission-reopened` with completed remediation;
- `challenge-rejected-with-evidence`;
- `claim-withdrawn`.

Record the disposition transactionally:

```bash
node "$context_script" challenge-disposition \
  --run-dir <run-dir> \
  --mission-id M03 \
  --type resolved \
  --rationale '<how the blocker was resolved>' \
  --evidence-json '{"verification":"<independent proof>"}' \
  --json
```

## 12. Integrate and close through transactional gates

Before accepting material work:

```bash
node "$context_script" check \
  --run-dir <run-dir> \
  --json
```

Before final acceptance:

```bash
node "$context_script" check \
  --run-dir <run-dir> \
  --for-close \
  --json

node "$context_script" close \
  --run-dir <run-dir> \
  --reason completed \
  --json
```

Closure fails for stale context, unfinished dependencies, pending proposals, invalid read sets, drifted generated views, unsealed or corrupted results, unresolved challenger verdicts, writer collisions, or budget violations.

Closed runs are immutable. Continue later work in a new run and record predecessor context explicitly.

A mission moved to `superseded` or `rejected` becomes `terminal-not-applicable` in the same transaction and no longer blocks closure as stale. Never manually rewrite mission state.

## 13. Operate and recover runs

Use `session-audit` to identify stale active runs, pending proposals, terminal-state defects, and budget pressure. Use the dry-run `repair-terminal-context` compatibility path only for historical invalid rows.

When a run is unhealthy or no longer worth accepting, use `run-rollover` to create and verify a minimal successor, then call `run-abandon` separately to close the source explicitly as non-accepted history. Never combine source abandonment with successor creation. Do not raise hard limits or revive every stale mission merely to pass closure.

Create live-database backups with `snapshot`; never copy an active WAL database as the official snapshot method. See [references/operational-lifecycle.md](references/operational-lifecycle.md).

## 14. Apply runtime collaboration backpressure

Before collaboration calls, use `gpt-squad-runtime-policy.mjs`:

- validate typed-specialist and history-fork combinations before spawn;
- reuse known agent IDs and never poll unchanged specialist state;
- keep general blocking waits between 1 and 60 seconds;
- after the first timeout, inspect status once and allow one deliberate retry; after the retry times out require progress identified by a new progress ID, a terminal outcome, or one recorded `wait-release`;
- permit at most one `wait-release` until new progress; if the released final-blocker wait also times out, do not wait again without new progress or a terminal outcome;
- after that final timeout, inspect status again only after an external attention signal or meaningful backoff when terminal state is plausible; unchanged status never unlocks another wait;
- record `aborted` when the wait call itself fails after preflight;
- require and record both a structured reason and final outcome for every interrupt.

This helper reduces known orchestration mistakes but does not create native completion events or prevent bypass by the root. See [references/runtime-coordination.md](references/runtime-coordination.md).

## 15. Session opt-out and reactivation

For an unscoped session opt-out:

```bash
node "$context_script" session-set \
  --runtime-root "$runtime_root" \
  --session-key <session-key> \
  --mode disabled \
  --json
```

On explicit reactivation, set the mode back to `active`. Open runs blocked only by session opt-out resume; reused specialists still require a fresh checkout when their view is stale.

A request-scoped pause does not mutate persistent session state.

## 16. Legacy migration

For an active file-based Context Guard run:

```bash
node "$context_script" migrate-legacy \
  --run-dir <legacy-run-dir> \
  --json
```

The migration:

- creates the per-session SQLite Hub;
- imports recognizable canonical IDs;
- backs up legacy files;
- marks imported missions blocked and `refresh-required`;
- requires fresh checkout and revalidation before use.

Closed legacy runs remain archived and are not rewritten.

## Cost and compaction

Use the least coordination intensity that preserves correctness. Agent count, proposal count, and protocol completion are not success metrics.

The Hub keeps hard maximums for live ledger bytes, result bytes, mission count, active IDs, and revision history. Revision-producing mutations enforce projected hard limits before commit. Treat 80% warnings as rollover signals. Keep the live shared core concise, compact provisional Commons items, and move only necessary accepted state into a minimal successor rather than increasing limits.

Evaluate cooperation by adopted specialist evidence, reduced duplicate investigation, challenger findings that changed the result, fewer stale reopenings, lower user-visible latency, and lower coordination cost per accepted outcome.

## Hard boundaries

- Specialists cannot recursively spawn agents.
- The root alone promotes canonical truth and controls mission authority.
- SQLite transactions serialize Context Hub mutations, but the Hub is not an operating-system security sandbox against another process running as the same user.
- Write capability is not standing authorization.
- External communication, production mutation, credentials, destructive cleanup, account changes, and irreversible actions require root-controlled authority.
- Concurrent writers must not share unsafe ownership.
- Never accept a result from a stale or mismatched context view.
- Never treat generated Markdown, repository files, direct messages, or Working Commons items as unofficial canonical state.
- Working Commons is provisional, bounded, and non-binding; binding shared effects require Context Hub promotion.
- Never invent evidence, hide failed checks, expose secrets, or claim completion without a defensible result.
