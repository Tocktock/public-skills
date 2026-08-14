# Context Synchronization

## Goal

All participating specialists must operate from the same accepted truth while retaining separate working memory and role-specific context.

Do not synchronize full transcripts. Synchronize accepted state, exact versions, and decision-relevant deltas.

## Four context layers

### 1. Shared canonical core

Delivered to every mission checkout:

- objective and intent;
- success criteria;
- hard constraints and non-goals;
- globally visible accepted facts, decisions, invariants, ownership, risks, and questions;
- globally visible artifact versions.

### 2. Mission context view

Delivered only to the relevant mission:

- specialist relationship and authority;
- owned outcome;
- responsibility surface;
- dependencies;
- required entry IDs;
- mission-scoped accepted entries;
- relevant artifact versions;
- verification expectations and known risks.

### 3. Private working context

Not synchronized by default:

- scratch reasoning;
- raw tool output;
- discarded hypotheses;
- temporary implementation notes;
- irrelevant repository exploration.

### 4. Independent review view

A blind-first challenger receives accepted truth, protected invariants, the actual diff or artifact, and reproducible evidence, but initially does not receive lead advocacy, confidence, or other reviewer votes.

## Checkout protocol

Before dispatch or reuse:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs checkout \
  --run-dir <run-dir> \
  --mission-id M01 \
  --json
```

The returned view records:

```text
revision
canonical snapshot hash
entry IDs and versions
artifact keys and versions
mission contract
view hash
```

The root passes this exact view or its compact contents to the specialist. `checkout` proves delivery, not understanding.

A reused specialist must receive a new checkout when its prior view is stale. Do not rely only on the specialist's previous thread memory.

## Proposal and promotion protocol

A specialist submits a proposal rather than editing shared truth.

```text
proposal
  claim
  evidence
  proposed visibility
  topics
  rationale or boundaries when required
```

The root validates the decisive evidence, then promotes or rejects the proposal.

Promotion automatically records a new entry version and computes affected missions from recorded read sets. Root-supplied additional missions are additive only.

## Automatic invalidation

The Context Hub invalidates:

- missions whose current checkout contains the changed entry or artifact;
- missions that require the changed ID;
- subscribed missions for changed topics;
- missions explicitly visible to the changed state;
- transitive mission dependents;
- additional missions named by the root.

Affected missions become `refresh-required`. Completed affected missions are reopened as blocked. They require a fresh checkout and result before integration.

## Delta protocol

Use:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs delta \
  --run-dir <run-dir> \
  --mission-id M01 \
  --since-revision <revision> \
  --json
```

A delta is a compact index of decision-relevant changes. It is not a substitute for the new checkout view.

Send only to affected missions:

- changed IDs or artifact keys;
- why the change matters;
- dependencies that became stale;
- new checkout view and snapshot hash;
- required next action.

## Context barriers

Create a synchronization barrier for changes to:

- source of truth;
- accepted fact or decision;
- global invariant;
- API, event, schema, transformation, or artifact version;
- ownership or write authority;
- migration, rollout, rollback, or compatibility assumptions;
- any premise that can invalidate another mission.

Do not create revision churn for local variable names, local refactors, private scratch work, or details that cannot change another mission or final acceptance.

## Communication rule

Short direct clarification is allowed.

The following must be recorded in the Hub rather than left only in agent messages or repository files:

- accepted facts;
- decisions;
- invariants;
- ownership changes;
- mission dependencies;
- shared contract changes;
- challenge dispositions;
- decision-relevant risks.

## Completion rule

A result is eligible for integration only when:

- it references the mission's current context-view hash;
- the view contains the required entry and artifact versions;
- its mission and dependencies are current;
- it is sealed in the Hub;
- any blocking challenger verdict has an explicit disposition;
- `check` passes.

Run `check --for-close` immediately before final acceptance.
