# Autonomous Cooperation

## Purpose

GPT Squad should give strong agents room to solve the problem, not turn them into operators of a large ceremony.

The operating goal is:

```text
strong shared truth
+ clear outcome ownership
+ low-friction peer cooperation
+ minimal necessary control
```

The Context Hub remains the durable authority for accepted cross-mission state. It should stay mostly behind the work rather than becoming the work.

## Autonomy contract

Every specialist is an elite generalist with an exceptional home field.

The specialty is an **attention prior**, not a capability boundary. A specialist may use adjacent product, technical, operational, economic, or communication judgment whenever it improves the owned outcome.

Give specialists:

- objective and intent;
- observable success;
- source of truth and known evidence;
- authority envelope;
- hard constraints and non-goals;
- concrete write ownership when applicable;
- material risk and verification expectations.

Do not prescribe:

- a fixed investigation sequence;
- a mandatory tool order;
- an artificial role pipeline;
- a predetermined conclusion;
- unnecessary progress reporting;
- Root approval for reversible local choices inside the mission envelope.

A specialist may investigate, design, implement, refactor, test, document, and follow adjacent evidence end to end.

Escalate only when the work changes:

- user intent or acceptance criteria;
- another mission's behavior;
- a shared or public contract;
- canonical fact, decision, invariant, ownership, or material risk;
- writer ownership or integration order;
- external, destructive, credential-bearing, production, or irreversible state.

## Coordination intensity

Use the least ceremony that preserves correctness.

### Lightweight

Use when missions are independently bounded and do not share mutable truth.

Typical cases:

- one autonomous specialist;
- several independent read-only investigations;
- parallel evidence collection that returns directly to Root;
- short work with no cross-mission dependency or stale-context risk.

Required structure:

```text
complete mission packet
clear ownership
result returned to Root
```

Do not create a Context Hub run merely because more than one agent exists.

### Cooperative

Use when specialists need quick provisional questions, hypotheses, help requests, or coordination, but no binding shared contract has changed.

Add the controlled Working Commons:

```text
private specialist work
        ↓
non-binding Working Commons
        ↓ only when decision-relevant
canonical Context Hub
```

The Working Commons is appropriate for:

- questions;
- hypotheses;
- help requests;
- temporary interface assumptions;
- coordination notes;
- collaboration requests.

It is not accepted truth and must not drive final acceptance by itself.

### Transactional

Use the full Context Hub when any of these apply:

- accepted cross-mission facts or decisions may change;
- shared APIs, schemas, migrations, ownership, rollout, rollback, or compatibility are involved;
- one mission depends on another mission's evidence or decision;
- work spans multiple waves;
- multiple writers participate;
- reused context may be stale;
- an independent challenge must be sealed and dispositioned.

Transactional mode adds versioned checkouts, automatic invalidation, sealed results, and closure gates. It does not reduce specialist autonomy inside the mission envelope.

## Deterministic mode planning

Use the read-only planner when several missions, writers, dependencies, or uncertain shared-state risk make the right mode non-obvious. An obviously lightweight single mission does not need a manifest:

```bash
cooperation_script=<skill-dir>/scripts/gpt-squad-cooperation.mjs

node "$cooperation_script" plan \
  --manifest <cooperation-plan.json> \
  --json
```

Start from [assets/cooperation-plan.example.json](../assets/cooperation-plan.example.json).

The planner:

- recommends `lightweight`, `cooperative`, or `transactional`;
- rejects a requested mode below the safe minimum;
- permits a more conservative mode with a ceremony warning;
- checks mission dependency cycles;
- checks structured parallel-writer path collisions;
- preserves flexible specialist and lead composition;
- returns escalation triggers and mission autonomy contracts.

The planner is decision support, not a substitute for Root judgment. Root may add safeguards, but should not add agents or ceremony without distinct expected value.

## Working Commons

The Working Commons is a controlled, non-binding runtime surface. It is not repository state and not canonical Context Hub state.

Initialize it in a private runtime workspace:

```bash
node "$cooperation_script" commons-init \
  --workspace-dir <private-runtime-workspace> \
  --session-key <session-key> \
  --run-id <run-id> \
  --participants M01,M02 \
  --json
```

The state file is owner-only and uses an atomic lock-protected update path. The declared participant list is fixed at initialization; undeclared mission IDs cannot post, reply, resolve, or read targeted items. The command refuses to change permissions on an existing non-private directory.

Hard limits:

```text
128 items
32 replies per item
8 KiB per item
4 KiB per reply
128 KiB total
5–1,440 minute TTL
```

Supported provisional item types:

```text
question
hypothesis
help-request
coordination
```

Binding types such as fact, decision, invariant, ownership, and accepted risk are rejected. Those belong in the Context Hub.

### Post a provisional item

```bash
node "$cooperation_script" commons-post \
  --workspace-dir <workspace> \
  --author M01 \
  --type question \
  --text '<question or provisional observation>' \
  --audience M02,root \
  --ttl-minutes 360 \
  --json
```

### Reply

```bash
node "$cooperation_script" commons-reply \
  --workspace-dir <workspace> \
  --author M02 \
  --item-id W-000001 \
  --text '<short response>' \
  --json
```

### Resolve provisional coordination

```bash
node "$cooperation_script" commons-resolve \
  --workspace-dir <workspace> \
  --actor M01 \
  --item-id W-000001 \
  --summary '<what was clarified>' \
  --json
```

Resolution remains non-binding. If it changes another mission or final acceptance, Root must record the accepted state through Context Hub proposal and promotion.

### Read and compact

```bash
node "$cooperation_script" commons-list \
  --workspace-dir <workspace> \
  --viewer M01 \
  --status open \
  --json

node "$cooperation_script" commons-compact \
  --workspace-dir <workspace> \
  --actor root \
  --older-than-minutes 60 \
  --json
```

Audience filtering prevents one mission's provisional detail from flooding every specialist. Root may inspect every item.

## Specialist-initiated collaboration

A specialist may discover that another home field can materially change the outcome. It should not silently expand the squad or remain blocked waiting for Root to guess.

For lightweight work, send the structured fields directly to Root. When a cooperative workspace exists, submit the request through Working Commons:

```bash
node "$cooperation_script" collaboration-request \
  --workspace-dir <workspace> \
  --author M01 \
  --specialist data_systems \
  --reason '<why current expertise is insufficient>' \
  --decision-impact '<which decision may change>' \
  --expected-value '<why the value exceeds coordination cost>' \
  --surface '<requested responsibility surface>' \
  --write-mode read-only \
  --json
```

Root decides whether to:

- accept and spawn a fresh specialist;
- reuse a reachable specialist with fresh context;
- decline because the expected value is insufficient;
- solve the question through existing evidence.

Resolve the request explicitly:

```bash
node "$cooperation_script" commons-resolve \
  --workspace-dir <workspace> \
  --actor root \
  --item-id W-000001 \
  --decision reused \
  --summary '<why this composition is appropriate>' \
  --json
```

This preserves Root accountability for squad size, writer ownership, independence, and cost while allowing specialists to self-identify missing expertise.

## Direct specialist communication

Direct communication is allowed for short operational cooperation:

- interface clarification;
- a blocker;
- a request to inspect a Working Commons item;
- delivery of an already recorded delta;
- coordination of disjoint writer timing.

Do not prohibit useful peer conversation merely because it is not canonical.

The hard boundary is:

> No accepted fact, decision, invariant, ownership change, risk disposition, or dependency may exist only in a direct message or Working Commons item.

When a provisional exchange changes another mission or final acceptance, Root promotes the smallest sufficient canonical statement.

## Canonical promotion threshold

Do not promote every local finding.

Keep information local when it affects only one mission's reversible implementation choice.

Use Working Commons when another specialist may benefit from the information but it is still provisional.

Promote to canonical state only when the information can change:

- another mission's behavior;
- shared contract or artifact interpretation;
- ownership or integration order;
- material risk acceptance;
- final user acceptance.

This keeps Root from becoming the approval bottleneck for ordinary specialist judgment.

## Review cooperation

Use `change_review` when the requested outcome is a holistic review of a proposed or completed change. It should account for the full change surface, inspect impact beyond the diff, challenge necessity and complexity, validate candidate findings, and produce a calibrated acceptance verdict.

The review specialist performs a proportionate adversarial pass by default. Adversarial means actively searching for counterexamples, hidden assumptions, failure paths, compatibility breaks, scope creep, and false-confidence tests while also trying to disprove its own findings. It does not mean generating criticism as a quota.

Keep review composition small:

- `change_review` alone for a normal holistic review;
- a domain specialist instead when the requested review is narrowly specialized and holistic change review adds little;
- `change_review` plus `quality_falsification` only when an independent executable falsification path has distinct expected value;
- `technical_communication` only when the review artifact itself needs durable reader-focused editing.

Review is non-mutating with respect to the reviewed change by default. Isolated verification artifacts may use a separate surface. If fixes are requested, preserve the review, enter an explicit fix phase, and re-review; the same specialist may fix when independence is unnecessary.

## Challenger cooperation

A challenger remains a fresh independent mission when silent failure matters.

Use the challenger selectively for:

- irreversible or high-impact decisions;
- security or trust boundaries;
- migrations and compatibility claims;
- failures that can pass ordinary tests silently.

Do not add a challenger as a quota.

Initial challenge work should use objective, acceptance criteria, protected invariants, raw artifacts, and reproducible evidence without lead advocacy. After the initial verdict is sealed, Root may expose lead reasoning for open synthesis.

The Working Commons must not be used to leak lead advocacy into a blind-first phase. Blind-first and `independent-challenger` missions are read-only; if fixes are needed, close the review phase and assign a separate writer mission.

## Hard invariants that remain strict

Autonomy does not mean uncontrolled shared effects.

Keep these hard:

- one owner per overlapping write surface;
- external, destructive, credential-bearing, production, and irreversible actions require Root authority;
- canonical state changes are versioned and invalidate consumers;
- stale specialists must refresh before binding work continues;
- results used for acceptance are sealed against their context view;
- secret-like credentials and production data are rejected from collaboration state;
- closed canonical runs are immutable;
- Working Commons remains non-binding and bounded.

Everything else should be outcome-oriented rather than procedure-oriented.

## Anti-patterns

Avoid:

- creating a Context Hub run only because two read-only agents exist;
- requiring Root promotion for a local reversible decision;
- assigning multiple agents the same generic review or pairing `change_review` with `quality_falsification` without distinct evidence paths;
- using persona titles as capability walls;
- forcing fixed investigator → architect → builder → verifier pipelines;
- asking for progress messages with no decision value;
- letting direct messages or Working Commons become hidden accepted truth;
- adding agents to demonstrate activity rather than improve the result;
- measuring proposal count, agent count, or ceremony completion as success.

## Evaluation

Judge cooperation by outcome value:

```text
specialist result adopted by Root
new decision-relevant evidence
reduced duplicate investigation
fewer stale reopenings
challenger findings that changed the result
lower user-visible latency
lower coordination calls per accepted outcome
```

A structurally valid run is necessary but not sufficient. The final question is whether the squad produced a simpler, safer, faster, or more correct result than Root alone.
