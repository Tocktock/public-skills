# Transactional GPT Squad Context Hub

## Purpose

The Context Hub lets independent specialists operate from the same accepted truth without sharing one large transcript or one private reasoning space.

It is the transactional tier for accepted cross-mission state, not the default communication mechanism for every multi-agent task. Independent work may remain lightweight, and provisional peer cooperation belongs in the bounded Working Commons described in [autonomous-cooperation.md](autonomous-cooperation.md).

It provides:

- root-controlled canonical state;
- role-specific recorded checkout views;
- per-entry and per-artifact versions;
- proposal and promotion workflows;
- automatic consumer invalidation;
- immutable result versions;
- explicit challenger dispositions;
- SQLite transactions and cross-process write serialization;
- generated Markdown and JSON views for humans and agents.

The Hub is a coordination and integrity boundary. It is not an operating-system security sandbox against another process running as the same user. It should remain mostly behind the specialist work: strong where shared effects matter and absent where independently bounded work does not need it.

## Storage model

Each activated Codex session owns one SQLite database:

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

`context-hub.sqlite3` is canonical. All files under `runs/<run-id>/` are generated views. Deleting generated views is recoverable with `render`; manually editing them never changes canonical state and makes `check` fail until regenerated.

The Node entry point remains:

```text
scripts/gpt-squad-context.mjs
```

It delegates to the Python 3.10+ standard-library SQLite backend. This preserves Node 18 compatibility without a native npm database dependency.

## Same truth, different views

### Shared canonical core

Every checkout includes:

- user objective and intent;
- success criteria;
- hard constraints;
- accepted globally visible facts, decisions, invariants, ownership boundaries, constraints, risks, and questions;
- globally visible artifact versions.

### Mission view

Each checkout additionally includes:

- specialist and relationship;
- owned objective and intent;
- authority and write mode;
- responsibility surface;
- distinct decision value;
- mission success criteria and constraints;
- verification expectations and known risks;
- dependencies;
- required canonical IDs;
- mission-visible context and artifacts.

### Private working context

Scratch reasoning, raw tool output, discarded hypotheses, and temporary notes remain private. They enter shared state only when they become decision-relevant evidence, a proposal, or a sealed result.

### Provisional Working Commons

Questions, hypotheses, help requests, and coordination may be shared through the separate non-binding Working Commons. Commons items are not accepted facts, decisions, invariants, ownership, dependencies, or risk dispositions. If a Commons exchange changes another mission or final acceptance, Root promotes the smallest sufficient canonical statement through this Hub.

The Hub must not ingest every provisional note. Keeping provisional cooperation outside canonical revisions prevents Root from becoming the approval bottleneck for ordinary specialist judgment.

### Blind-first review view

An independent challenger receives its own checkout and should initially avoid lead conclusions, confidence, implementation advocacy, and reviewer votes. Canonical facts and protected invariants remain available because they are accepted truth, not advocacy.

## What checkout proves

`checkout` records:

```text
mission ID
canonical revision
canonical snapshot hash
exact delivered entry IDs and versions
exact delivered artifact keys and versions
mission contract
immutable context-view hash
```

This proves what the Hub delivered. It does not prove that the model read, remembered, or correctly understood every item.

The Hub also cannot automatically know every extra repository file, web page, or tool result an agent independently inspects after checkout. Record material additional evidence in proposals or results.

## Canonical context

Canonical entries use stable IDs:

```text
F-### confirmed fact
D-### accepted decision
I-### invariant
O-### ownership boundary
C-### constraint or non-goal
R-### material risk
Q-### open question
```

Each ID has immutable versions. A mission checkout records the exact version it received.

Entries have visibility:

```text
all
M01,M02
```

Only globally visible entries are rendered in `shared-context.md`. Mission-scoped entries appear only in the relevant checkout view and the SQLite canonical store.

Entries may also carry topics. Mission subscriptions allow automatic invalidation when a relevant new entry appears even if the mission did not previously consume that ID.

## Proposal lifecycle

A proposal is pending evidence and judgment, not shared truth.

Do not create a proposal for every local implementation choice. A proposal is warranted when the information can change another mission, a shared contract or artifact interpretation, ownership, material risk acceptance, or final user acceptance.

```text
specialist or root
  → propose
  → root validates evidence
  → promote or proposal-reject
```

Specialist proposals require:

- an active mission;
- a current checkout view;
- a concrete claim;
- evidence appropriate to the entry type;
- cross-mission or acceptance relevance that justifies canonical promotion overhead.

Promotion is root-only by operating contract. The Hub does not attempt to distinguish processes running as the same operating-system user.

A promotion transaction:

1. validates the pending proposal;
2. writes one immutable entry version;
3. increments the run revision;
4. computes the canonical snapshot hash;
5. records an append-only event;
6. discovers affected consumers;
7. marks them and transitive dependents `refresh-required`;
8. reopens completed stale missions as blocked;
9. regenerates derived views.

Manual affected missions are additive. They can widen invalidation, never narrow automatically discovered consumers.

## Automatic invalidation

For an entry change:

```text
affected missions =
    current checkout views containing the changed ID
  + missions declaring the changed ID as required
  + topic subscribers
  + missions explicitly visible to the entry
  + root-added extra missions
  + transitive dependents
```

For an artifact change:

```text
affected missions =
    current checkout views containing the changed artifact version
  + topic subscribers
  + missions explicitly visible to the artifact
  + root-added extra missions
  + transitive dependents
```

Old and new visibility and topics are considered when an existing entry or artifact changes. This prevents narrowing a scope from hiding consumers that depended on the previous version.

A mission marked `refresh-required` cannot resume active work or submit a result until it checks out a new view.

## Result lifecycle

`result-submit` seals structured JSON against an exact context-view hash.

The Hub stores:

```text
mission ID
result version
result status
result content hash
context-view ID and hash
exact delivered read set through the view
verification evidence
challenger verdict and distinct method when applicable
superseded result version
seal timestamp
```

Result rows are immutable. A correction requires:

```text
mission-reopen
→ fresh checkout
→ active mission
→ result-submit
```

The new result version supersedes the prior version without deleting it.

## Challenger dispositions

A challenger may return:

```text
PASS
FAIL
UNRESOLVED
```

`FAIL` and `UNRESOLVED` block closure until the root records one of:

```text
resolved
accepted-risk
mission-reopened
challenge-rejected-with-evidence
claim-withdrawn
```

An accepted-risk disposition requires an active `D-###` decision. If that decision is later superseded, closure becomes blocked again.

A mission-reopened disposition requires the referenced remediation mission to be completed or superseded.

## Transaction and locking behavior

Every canonical mutation uses SQLite `BEGIN IMMEDIATE` with WAL mode, foreign keys, full synchronous durability, and a busy timeout.

This provides:

- one cross-process writer at a time;
- atomic entry promotion;
- atomic artifact version changes;
- atomic result sealing;
- atomic challenge disposition;
- atomic run closure;
- recovery after process interruption through SQLite durability.

Generated views are rendered while holding the same writer lock. If rendering still fails after canonical commit, SQLite remains authoritative and `render` repairs the views.

## Run and mission immutability

Mission transitions are explicit:

```text
planned → active | blocked | rejected | superseded
active  → blocked | rejected | superseded | sealed result
blocked → active | rejected | superseded
completed → mission-reopen only
rejected → terminal
superseded → terminal
```

`mission-status completed` is removed. Completion occurs only through `result-submit`.

Closed runs reject every canonical mutation. Later work starts a new run and records predecessor context explicitly.

Session activation may change after a run closes, but closed run data and generated views retain the session mode recorded at closure.

## Artifact records

Artifacts identify material repository or external state:

```text
artifact key
repository
path or scope
commit or immutable version
optional content SHA-256
metadata
visibility
topics
```

Every artifact version is immutable and included in recorded checkout read sets.

## Context budgets

Compiled maxima:

```text
shared global ledger: 32 KiB
mission-specific checkout JSON: 64 KiB
result JSON: 32 KiB
missions per run: 16
active canonical IDs: 120
revision-history entries: 64
warning threshold: 80%
```

The shared ledger intentionally omits mission-private entries and artifacts. The database remains complete while generated shared context stays small. The separate checkout limit prevents oversized private entries or artifacts from producing an unbounded specialist prompt.

Do not increase budgets to avoid curation. Supersede outdated entries, keep claims concise, and retain detailed evidence in durable referenced artifacts.

## Direct agent communication

Short operational clarification is allowed. No accepted fact, decision, invariant, ownership change, dependency, or risk disposition may exist only in direct messages, repository comments, file names, or untracked files.

Anything that can change another mission or final acceptance must become:

```text
proposal + evidence
→ root validation
→ promotion
→ automatic delta and refresh
```

## Compatibility

- `ack` remains a deprecated alias for `checkout`.
- `advance` fails with a migration message because manual ledger editing is no longer canonical.
- `migrate-legacy` imports active file-based guard state, preserves backups, and requires fresh checkout and revalidation.
- closed legacy runs remain archived.

## Proof boundaries

The Hub proves:

- canonical SQLite integrity;
- exact delivered context-view contents and hashes;
- per-entry and per-artifact versions;
- transactional promotions and invalidation;
- sealed result hashes and version chains;
- explicit challenge dispositions;
- machine-enforced closure preconditions.

It does not prove:

- that a model understood its checkout;
- that the selected persona was optimal;
- that a specialist's domain judgment was correct;
- that differently worded writer surfaces do not overlap semantically;
- that a same-model challenger has no shared blind spot;
- that another process running as the same user cannot intentionally manipulate all local state;
- that all independently inspected artifacts were recorded without tool instrumentation.

Use parent collaboration events, child `session_meta`, actual diffs, concrete path ownership, independent evidence, and runtime smoke tests for claims outside the Hub.


## Operational hardening

Revision-producing mutations calculate the projected shared ledger, active canonical IDs, mission count, and revision history before commit. Maximum plus one rolls back the complete SQLite transaction.

Discarded missions (`superseded` or `rejected`) use `terminal-not-applicable`; historical invalid rows have a dry-run repair command. Operational lifecycle commands provide session audit, explicit abandonment, minimal rollover, and SQLite-consistent snapshots. See [operational-lifecycle.md](operational-lifecycle.md).
