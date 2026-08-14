# Mission Command

## Chief Engineer responsibility

The root remains a frontier-level generalist and final accountable owner. It controls:

- user intent and completion criteria;
- specialist selection and mission relationships;
- cross-domain tradeoffs;
- canonical promotion and shared contracts;
- writer ownership and integration order;
- external, production, credential-bearing, destructive, and irreversible authority;
- final verification, risk acceptance, and communication.

The root is not the approval layer for every reversible local choice. It should not duplicate an active specialist's coherent mission, prescribe a fixed investigation procedure, or require every useful observation to become canonical state.

The root should understand decisive evidence, inspect the integrated result, resolve cross-specialty conflict, and promote only information that can change another mission or final acceptance.

## Smallest sufficient squad

Use one lead specialist by default. Add:

- an advisor for genuinely distinct judgment;
- a parallel owner for an independently bounded outcome;
- an independent challenger for material risk or a falsifiable claim.

Every specialist must have:

```text
one owned outcome
one distinct decision value
one authority envelope
one verification expectation
one concrete responsibility surface
one concrete write path when writing
```

Do not create agents merely to fill roles or demonstrate activity.

## Specialist autonomy

Every specialist is an elite generalist. Its persona is an attention prior, not a capability boundary.

Within the mission envelope, a specialist may:

- investigate unfamiliar code and evidence;
- choose its own method and tool sequence;
- make reversible local product and technical decisions;
- design and implement a coherent solution;
- refactor adjacent code required for correctness;
- add tests, fixtures, documentation, and instrumentation;
- follow adjacent evidence that materially affects the outcome;
- ask another specialist for help when distinct expertise can change a decision.

Do not require permission for local choices that remain inside the mission's authority, write ownership, hard constraints, and acceptance criteria.

Escalate when work changes:

- user intent or final success criteria;
- another mission's behavior;
- a shared or public contract;
- canonical fact, decision, invariant, ownership, or material risk;
- writer ownership or integration order;
- external or irreversible state.

## Coordination intensity

Choose the least coordination mode that preserves correctness.

### Lightweight

Use a complete mission packet and direct result return for independently bounded work with no shared mutable truth. Multiple independent read-only specialists may remain lightweight.

### Cooperative

Use Working Commons for provisional questions, hypotheses, help requests, and coordination when specialists benefit from peer exchange but no binding shared contract has changed.

Working Commons is:

```text
bounded
TTL-based
audience-filtered
lock-protected
explicitly non-binding
```

### Transactional

Use Context Hub checkouts, proposal/promotion, invalidation, sealed results, and closure gates when accepted shared state, dependencies, writers, stale reuse, waves, or independent challenge require durable coordination.

Use `gpt-squad-cooperation.mjs plan` to reject a coordination mode below the safe minimum without forcing a more expensive mode than the work needs.

## Mission relationships

### Lead

Owns a coherent outcome end to end.

### Advisor

Provides distinct evidence or judgment that can change the root or lead decision. It should not duplicate the lead's general investigation.

### Parallel owner

Owns a separate deliverable with disjoint write boundaries and an explicit integration contract.

### Independent challenger

Attempts to falsify a material claim through a distinct evidence path. It initially avoids lead advocacy and returns `PASS`, `FAIL`, or `UNRESOLVED`.

Do not attach a challenger as a quota. Use one when silent failure or irreversible impact justifies the cost. Every `independent-challenger` mission is read-only; implementation requires a separate writer mission.

## Review missions

Use `change_review` when review itself is the owned outcome: pull-request review, branch or patch review, architecture or design review, migration readiness, simplification review, or acceptance review of a completed specialist result.

`change_review` is a persona, not a mandatory final pipeline stage. Assign it as:

- `lead` when producing the complete review is the primary requested outcome;
- `advisor` when a lead owner needs an independent holistic acceptance judgment;
- `independent-challenger` only when blind-first independence and a sealed verdict are materially valuable.

Every review mission includes a proportionate adversarial pass:

1. establish the exact target, applicable comparison baseline or version, intent, non-goals, and stable contracts; record exact base and head for Git changes;
2. account for the complete changed and impacted surface;
3. trace high-risk behavior beyond diff hunks into callers, consumers, persistence, side effects, migration, rollout, and rollback;
4. search for counterexamples, hidden coupling, compatibility breaks, unnecessary complexity, and tests that can pass while behavior is wrong;
5. actively falsify candidate findings through existing guards, alternate contracts, or contrary evidence;
6. report only findings that are introduced, reachable, material, supported, actionable, and calibrated;
7. finish with findings, verdict, coverage, checks, and residual risk.

A clean review may return `PASS` with no findings; adversarial does not mean manufacturing criticism. Transactional review verdicts use `PASS`, `FAIL`, or `UNRESOLVED`; human pull-request reviews map `PASS` with non-blocking findings to `COMMENT` or approval with comments, `FAIL` to `REQUEST_CHANGES`, and `UNRESOLVED` to an explicitly inconclusive non-approval review. Do not mutate the reviewed change without explicit fix authority. Isolated tests, reproduction harnesses, or review artifacts may use a separate declared surface. If fixes are requested, preserve the initial review, enter a clear fix phase, and re-review the resulting delta; use a fresh reviewer only when independence materially matters. A reviewer that implements fixes must not count its own follow-up as independent acceptance evidence.

Do not duplicate `quality_falsification`. `change_review` owns holistic coverage, simplicity, scope, maintainability, and acceptance judgment. `quality_falsification` owns decisive reproduction, failure injection, and falsification of a specific material claim. Pair them only when both evidence paths can independently change the decision.

## Specialist-initiated cooperation

A specialist may submit a structured collaboration request when another home field can materially change its decision. It may send the request directly to Root in lightweight mode or record it in Working Commons when cooperative state already exists.

The request states:

```text
needed specialist
why current evidence is insufficient
which decision may change
expected value versus coordination cost
requested responsibility surface
read-only or writer authority
```

The root may:

- accept and spawn;
- reuse a reachable specialist with fresh context;
- decline because expected value is insufficient;
- answer from evidence already available.

Specialists do not recursively spawn agents. Root retains squad-size, independence, ownership, and cost authority.

## Working information tiers

Use three tiers:

### Private working state

Scratch reasoning, raw tool output, discarded hypotheses, and local implementation detail stay with one specialist.

### Working Commons

Questions, hypotheses, help requests, and coordination may be shared provisionally. They may be discussed and resolved without Root promotion.

### Canonical Context Hub

Accepted facts, decisions, invariants, ownership, material risks, artifact versions, dependencies, and acceptance-relevant state are promoted by Root.

Promote the smallest sufficient statement. Do not promote local reversible implementation choices merely for visibility.

## Direct communication

Useful peer communication is allowed for:

- interface clarification;
- blockers;
- help requests;
- linking a Working Commons item;
- delivering an already recorded context delta;
- coordinating disjoint writer timing.

The hard boundary is:

> No accepted fact, decision, invariant, ownership change, dependency, or risk disposition may exist only in direct communication or Working Commons.

If a peer exchange changes another mission or final acceptance, Root records it canonically.

## Writer safety

Read-only evidence work may overlap.

Parallel writers require:

- concrete disjoint relative paths, modules, schemas, or generated state;
- no hidden shared output directory;
- no dependency that makes the work sequential;
- a defined integration order and combined verification;
- worktree or patch isolation when ownership cannot be stated safely.

Structured writer paths reject ambiguous globs. The planner detects path containment collisions. Root must still inspect semantic overlap.

## Efficient coordination

- Reuse known agent IDs. Call `list_agents` only when reachable state is unknown before a potentially redundant fresh spawn, for the single immediate inspection after a first timeout, or later after an external attention signal or meaningful backoff when terminal state is plausible; never poll unchanged state in a tight loop.
- Prefer `followup_task` when home field, authority, independence, and context still fit.
- Refresh reused specialists when accepted context may be stale.
- Dispatch independent assignments before waiting.
- Do not ask for progress updates without decision value.
- Allow specialists to report an early blocker or request help rather than waiting for Root to infer it.
- Use runtime preflight before spawn, wait, or interrupt.
- Use direct messages and Working Commons for low-friction cooperation; use Context Hub only for binding shared state.

## Session behavior

The first explicit GPT Squad request activates squad mode for the current Codex session. It stays active until unscoped opt-out or session end.

One mission run may close while session squad mode remains active. A later turn may reuse a suitable specialist, start lightweight work, open a cooperative workspace, or create a transactional run.

A trivial turn may remain root-only without deactivating the session.
