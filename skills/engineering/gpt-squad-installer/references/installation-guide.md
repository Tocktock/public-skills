# GPT Squad Installation and Migration Guide

## 1. Purpose

This package configures Codex Desktop with:

- a GPT-5.6 Sol root acting as Chief Engineer without a mandatory root reasoning effort;
- fourteen GPT-5.6 Sol specialist agents pinned to high reasoning;
- compact instructions that keep the catalog dormant at the beginning of each Codex session;
- one-time explicit activation that persists for later turns in the same session;
- autonomy-first coordination that selects lightweight, cooperative, or transactional mode according to actual shared-state risk;
- a bounded non-binding Working Commons for provisional peer questions and collaboration requests;
- a root-controlled transactional Context Hub that records role-specific checkouts, proposals, per-entry versions, automatic invalidation, and sealed results when binding shared state requires it;
- target-derived model-catalog compatibility when Codex does not expose multi-agent V2 for Sol;
- bounded migration from the legacy five generic process roles;
- backup, semantic verification, drift detection, compensation, and rollback.

Detailed mission-command and synchronization instructions live in `gpt-squad-orchestrator`. They are used after the session is explicitly activated, reducing default token and latency cost before opt-in.

## 2. Specialist roster

| Specialist | Exceptional home field |
| --- | --- |
| `product_systems` | User intent, product policy, operating rules, workflows, state meaning, and measurable outcomes |
| `product_design` | Product discovery, concepts, feature architecture, service design, prototyping, and coherent product evolution |
| `experience_design` | UI/UX, interaction design, information architecture, accessibility, responsive behavior, and design systems |
| `domain_application` | Business semantics, domain and application boundaries, state, architecture, and implementation |
| `data_systems` | Persistence, transactions, schema evolution, migration, recovery, and query behavior |
| `distributed_systems` | Concurrency, messaging, retries, ordering, idempotency, and partial failure |
| `integration_evolution` | APIs, events, compatibility, versioning, synchronization, and incremental evolution |
| `platform_reliability` | Infrastructure, delivery, runtime configuration, observability, recovery, and operations |
| `security_trust` | Trust boundaries, identity, authorization, secrets, privacy, abuse resistance, and isolation |
| `change_review` | Holistic review of proposed changes for correctness, simplicity, scope, maintainability, compatibility, and acceptance readiness |
| `quality_falsification` | Reproduction, behavioral proof, edge cases, failure injection, and independent falsification |
| `performance_economics` | Latency, throughput, resources, infrastructure cost, complexity, and engineering economics |
| `codebase_forensics` | Large-repository discovery, history, hidden ownership, stale documentation, and intent reconstruction |
| `technical_communication` | Decisions, reviews, documentation, runbooks, and reader-first technical narratives |

## 3. Session activation contract

A new Codex task or conversation session starts with GPT Squad dormant. Complexity, risk, repository size, or obvious parallelism does not activate it.

The first user request that names GPT Squad, `$gpt-squad-orchestrator`, a registered specialist, or delegated/parallel agents activates squad mode. Once activated, it remains active across later user turns in the same session. The user does not need to repeat the activation phrase.

An unscoped instruction such as `do not use GPT Squad`, `root only`, or `no sub-agents` disables squad mode for the current session until explicit reactivation. If the user says `for this request only`, pause squad use for that request and restore the prior active mode on the next turn. A new session always starts dormant.

The first activating or reactivating request should use at least one suitable specialist when possible. Later active turns still follow smallest-sufficient-squad economics: trivial, tightly coupled, or negative-value delegation work may remain root-only without disabling the session mode.

## 4. Files managed in the target Codex home

```text
config.toml
AGENTS.md
agents/gpt-squad/*.toml
gpt-squad-installer/state.json
model-catalogs/gpt-squad-<codex-version>.json   # only when required
backups/gpt-squad/<backup-id>/
```

Cooperation runtime state is created only after activation and only at the intensity the work requires. Lightweight missions need no shared runtime. Cooperative work may use a private Working Commons. Transactional Context Hub state is created only for binding shared-state work:

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

SQLite is canonical. The Markdown and JSON files under each run are generated, human-readable projections.

## 5. Plan, install, and verify

```bash
node <skill-dir>/scripts/gpt-squad.mjs plan --json
node <skill-dir>/scripts/gpt-squad.mjs install --json
node <skill-dir>/scripts/gpt-squad.mjs verify --json
```

`plan` is read-only. Installation validates catalog, policies, model support, ownership, and collisions; stages the desired state; creates a complete backup; writes atomically; verifies prompt loading; and compensates after failed apply.

Root effort remains flexible. Omit `--root-effort` to preserve a supported choice, pass a supported effort to pin it, or pass `--root-effort auto` to remove the root-level assignment. Specialists remain GPT-5.6 Sol High.

Verification checks exact generated-file hashes, shared-file managed semantics, roster parity, runtime agent settings, session activation and opt-out semantics, root effort compatibility, legacy cleanup, and prompt loading. Static verification does not prove actual session behavior.

The transactional Context Hub requires Python 3.10 or newer with the standard-library `sqlite3` module. No native npm dependency is required.

## 6. Autonomy-first cooperation and transactional context

Use the least coordination intensity that preserves correctness:

- **Lightweight** for one or more independently bounded outcomes with no shared mutable truth. Independent read-only specialists may return directly to Root.
- **Cooperative** when specialists need provisional questions, hypotheses, help requests, or timing coordination. Use the bounded non-binding Working Commons.
- **Transactional** when accepted cross-mission state, dependencies, shared contracts, multiple writers, stale reuse, multi-wave work, or independent challenge requires versioned evidence and closure gates.

Use the read-only planner when multiple missions, writers, dependencies, or uncertain shared-state risk make the right mode non-obvious. Obvious lightweight single-specialist work does not require a manifest:

```bash
node <orchestrator-dir>/scripts/gpt-squad-cooperation.mjs plan \
  --manifest <cooperation-plan.json> \
  --json
```

The planner rejects a mode below the safe minimum, warns when a higher mode adds avoidable ceremony, checks dependency cycles and structured writer-path collisions, and returns mission autonomy contracts. A specialist may submit a structured collaboration request when another home field can materially change a decision; Root decides whether to reuse, spawn, decline, or answer from existing evidence.

Working Commons is TTL-based, audience-filtered, size-bounded, lock-protected, and explicitly non-binding. It supports questions, hypotheses, help requests, coordination, and collaboration requests. Binding fact, decision, invariant, ownership, dependency, and accepted-risk state must move through the Context Hub.

Initialize cooperative state with an explicit participant set:

```bash
node <orchestrator-dir>/scripts/gpt-squad-cooperation.mjs commons-init \
  --workspace-dir <private-runtime-workspace> \
  --session-key <session-key> \
  --run-id <run-id> \
  --participants M01,M02 \
  --json
```

The command rejects undeclared actors, secret-like content, symlinked paths, and existing directories that are not already owner-only.

The design rule remains:

> Agents operate from the same accepted truth while keeping separate working memory.

The Hub therefore separates:

- a shared canonical core containing accepted objective, constraints, facts, decisions, invariants, ownership, and artifact versions;
- an immutable mission-specific checkout containing only the entries, dependencies, artifacts, authority, risks, and success conditions relevant to that specialist;
- private specialist working context such as scratch reasoning, discarded hypotheses, raw tool output, and local implementation notes;
- a blind-first challenger view that withholds lead conclusions and implementation advocacy until an initial independent judgment is recorded.

The public entry point remains:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs <command>
```

The Node wrapper delegates to a Python standard-library SQLite backend. SQLite transactions use WAL mode, busy timeouts, and `BEGIN IMMEDIATE` for serialized mutations.

Core lifecycle:

```text
init
mission-add
checkout
propose
promote
delta
result-submit
challenge-disposition
check
close
session-audit
repair-terminal-context
run-rollover
run-abandon
snapshot
```

### 6.1 Recorded checkout views

Before substantive work, each ledger-required mission receives `checkout`. The Hub records:

```text
mission ID
run revision
checkout snapshot hash
entry IDs and exact versions delivered
artifact identities and exact versions delivered
mission authority, dependencies, and visibility
```

A checkout proves what the Hub delivered. It does not prove what the model internally understood.

A reused specialist receives a fresh checkout whenever its prior context may be stale. The deprecated `ack` compatibility command creates a real recorded checkout; it does not merely trust a self-reported revision number.

### 6.2 Proposals and root-only promotion

Specialists submit proposals with evidence. They do not edit canonical truth. Only the root may promote a proposal.

A promotion transaction:

1. validates the proposal and supporting evidence;
2. creates or updates a canonical entry with a new per-entry version;
3. creates the next run revision;
4. records the new canonical snapshot and event;
5. discovers affected missions automatically;
6. marks affected missions and transitive dependents `refresh-required` or reopens stale completed work;
7. regenerates the human-readable views.

Automatically inferred affected missions include:

```text
missions whose recorded read sets contain a changed entry
missions that require a changed entry
missions whose delivered artifact version changed
missions subscribed to a changed topic
missions affected by entry-visibility changes
transitive dependent missions
missions explicitly added by the root
```

The root's explicit affected list is additive only. It cannot exclude a known consumer.

### 6.3 Deltas and private working memory

`delta` returns only changes relevant to one mission since its previous checkout. Full transcripts, sibling scratchpads, discarded hypotheses, and unrelated tool output are not shared.

Temporary direct clarification between specialists may be useful, but no accepted fact, decision, ownership change, dependency, or risk disposition may exist only in direct messages. Decision-relevant information must be recorded as a proposal, promotion, disposition, or Hub event.

### 6.4 Sealed results and challenger dispositions

`result-submit` seals a versioned result with:

```text
result content hash
checkout snapshot hash
exact entry and artifact read sets
verification evidence
challenger verdict when applicable
finalization timestamp
```

A correction creates a new result version that supersedes the previous one. The prior version remains immutable.

A challenger `FAIL` or `UNRESOLVED` blocks closure until the root records one supported disposition:

```text
resolved
accepted-risk
mission-reopened
challenge-rejected-with-evidence
claim-withdrawn
```

Accepted risk must reference an active accepted decision and evidence. Closed runs reject every mutation.

### 6.5 Operational lifecycle and collaboration backpressure

Revision-producing mutations validate the projected ledger bytes, active canonical IDs, mission count, and revision history before commit. Exact maximum is allowed; maximum plus one rolls back the complete transaction.

Discarded missions become `terminal-not-applicable` atomically. Use `repair-terminal-context` only for historical invalid rows, beginning with its dry-run output. Use `session-audit` to find stale runs, pending proposals, refresh-required missions, and budget pressure.

When a run cannot remain acceptance-ready, create and verify a minimal successor with `run-rollover`, then close the source in a separate `run-abandon --successor-run-id` operation. Combined rollover-and-abandon is rejected so successor projection failure cannot mutate the source lifecycle. Use `snapshot` for a consistent SQLite online backup rather than copying an active WAL database.

Before collaboration calls, use the orchestrator runtime-policy helper to reject typed-specialist/full-history spawn conflicts, bound waits to 60 seconds, allow one status-refreshed retry after the first timeout, require progress/terminal state or an auditable `wait-release` after repeated timeouts, record aborted wait calls, and record structured interrupt reasons plus outcomes. This is deterministic backpressure, not native event-driven completion.

### 6.6 Generated views, migration, and proof boundary

The Hub generates:

```text
shared-context.md
work-map.md
missions/M01.md
results/M01.md
checkouts/<snapshot-hash>.json
proposals/<proposal-id>.json
events.jsonl
```

Manual changes are drift and are not canonical. `render` regenerates projections from SQLite.

The legacy file guard can be migrated through the orchestrator's documented migration command. Migration is fail-closed, creates a complete read-only backup, imports supported state, and requires a fresh transactional checkout before resumed specialist work.

The Hub proves transactional state integrity, recorded delivery, deterministic invalidation, immutable result versions, and closure conditions. It does not prove internal model comprehension, optimal specialist selection, semantic writer isolation, or freedom from same-model blind spots. Those still require parent collaboration events, child `session_meta`, actual diffs, evidence diversity, and root review.

## 7. Runtime smoke tests

Quit Codex Desktop completely, reopen it, and start a new task.

### 7.1 New session remains dormant

```text
Investigate a substantive read-only regression in this repository.
```

Pass when no squad collaboration tools are called.

### 7.2 Explicit activation delegates

```text
Use $gpt-squad-orchestrator to investigate this regression with the smallest sufficient squad.
```

Pass when at least one suitable GPT-5.6 Sol High specialist owns a coherent outcome.

### 7.3 Unqualified continuation remains active

Without naming GPT Squad again:

```text
Now inspect one more related case and implement the coherent fix.
```

Pass when the root still treats squad mode as active, checks reachable specialists, creates a fresh recorded Context Hub checkout for the matching specialist, and uses `followup_task` when appropriate. A fresh spawn is valid when independence, expertise, ownership, or stale context requires it.

### 7.4 Active mode does not force agents onto trivial work

```text
Fix this obvious typo.
```

Pass when the root handles it directly without deactivating squad mode.

### 7.5 Request-scoped pause

```text
For this request only, do not use GPT Squad. Just summarize the current result.
```

Pass when the request is root-only and the following turn resumes active mode.

### 7.6 Session opt-out

```text
Stop using GPT Squad for this session. Use root-only mode from now on.
```

Pass when later turns call no squad collaboration tools until explicit reactivation.

### 7.7 Reactivation

```text
Reactivate GPT Squad and continue with the prior specialist if its context still fits.
```

Pass when the root creates a fresh recorded Context Hub checkout for the specialist and prefers `followup_task` when safe.

### 7.8 New session resets to dormant

Open a separate new Codex task and submit a substantive request without activation. Pass when it remains root-only.

### 7.9 Transactional context synchronization

In an active session, use at least two specialists and an independent challenger.

Pass when:

- the Hub records immutable role-specific checkout hashes and exact read sets;
- a promoted entry or artifact change automatically invalidates every recorded consumer and transitive dependent;
- refreshed work receives a new checkout before continuation;
- completed results are sealed against their checkout hashes;
- challenger `FAIL` or `UNRESOLVED` prevents closure until a supported disposition is recorded;
- `check --for-close` passes before final acceptance.

Judge behavior from parent collaboration events, child `session_meta`, Context Hub records, sealed result hashes, and generated views. Final-answer self-report is not sufficient evidence.

## 8. Rollback

```bash
node <skill-dir>/scripts/gpt-squad.mjs rollback \
  --backup-id <backup-id> \
  --json
```

Rollback keeps exact whole-file drift protection and refuses to overwrite later user changes.

## 9. Troubleshooting

### No specialist runs before activation

Expected. A new session is dormant until the user explicitly opts in.

### A later turn unexpectedly returns to root-only

Confirm the turn belongs to the same Codex task/session, no session-wide opt-out occurred, and the managed session-persistence policy loaded. Inspect parent events and conversation state.

### Squad continues after an opt-out

Verify whether the user scoped the opt-out to one request or the whole session. An unscoped opt-out should disable squad mode until explicit reactivation.

### Context Hub command reports an unavailable runtime

Confirm `python3 --version` is Python 3.10 or newer and the standard-library `sqlite3` module is available.

### A generated Markdown view differs from SQLite

Treat the file as drift. Run the Context Hub `check`, inspect the canonical SQLite state, and use `render` to regenerate the view. Do not copy the manual edit back into canonical state.

### Model or effort unavailable

Update Codex and confirm account access. The root may use any supported effort; specialists require GPT-5.6 Sol High.
