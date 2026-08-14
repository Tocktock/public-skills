# Integration and Evaluation

## Root integration contract

The root does not accept a specialist result because it sounds complete or because coordination ceremony passed. It verifies:

- exact mission and authority;
- checked-out context-view hash;
- decisive evidence;
- actual diff, artifact, or runtime state;
- verification result;
- dependency completion;
- cross-specialty consequences;
- current canonical versions;
- challenge status and disposition;
- remaining uncertainty that can change the decision;
- whether the chosen coordination mode was no heavier than necessary;
- whether specialist evidence changed the result enough to justify coordination cost.

## Working Commons boundary

Working Commons is provisional cooperation, not acceptance evidence. A question, hypothesis, help request, reply, or resolution may guide investigation, but it cannot by itself establish:

```text
accepted fact
accepted decision
shared invariant
ownership boundary
material risk disposition
final acceptance
```

If a Commons exchange changes another mission or final acceptance, Root promotes the smallest sufficient canonical statement through the Context Hub before integration.

For lightweight work with no Context Hub, Root still verifies the mission packet, evidence, actual artifact or diff, and observable success directly. Do not create a transactional run after the fact merely to manufacture ceremony.

## Sealed result contract

A completed result is valid only when `result-submit` succeeds.

The sealed record contains:

- immutable result version and SHA-256;
- exact context-view ID and SHA-256;
- structured outcome;
- verification evidence;
- challenger verdict and distinct method when applicable;
- superseded result version;
- seal timestamp.

A mutable Markdown file is never completion evidence. Generated result Markdown is only a view of the sealed SQLite row.

## Dependency and stale-result handling

When canonical state changes, the Hub automatically invalidates known consumers and transitive dependents. A completed affected mission becomes blocked and must produce a new result from a fresh checkout.

Do not manually waive stale context. Promote a new decision or record an explicit challenge disposition instead.

## Review acceptance

When `change_review` is used, Root verifies that the review:

- identified the exact target, applicable comparison baseline or version, and review mode; for Git changes, recorded exact base and head;
- accounted for every changed path or explicitly justified mechanical or excluded coverage;
- traced high-risk effects beyond the changed hunk;
- separated introduced defects from pre-existing issues and optional preferences;
- tested candidate findings against existing guards and contrary evidence;
- returned a calibrated `PASS`, `FAIL`, or `UNRESOLVED` verdict and distinguished blocking findings, non-blocking findings, no findings, and unresolved review gaps;
- evaluated unnecessary complexity and scope, not only runtime correctness;
- did not mutate the reviewed change without explicit fix authority, while allowing isolated verification artifacts on a separate surface.

A review verdict is expert evidence, not automatic acceptance. Root still inspects decisive findings, the integrated artifact, and residual risk. If the reviewer implemented a fix, its follow-up review is not independent evidence; use a fresh review mission when independent acceptance is material.

## Independent challenge

A challenger should use a materially different evidence path, such as:

- failure injection instead of implementation inspection;
- integration behavior instead of unit tests;
- schema or data invariant analysis instead of service-code reasoning;
- runtime traces instead of the lead's narrative;
- user-flow usability evidence instead of interface implementation claims.

`FAIL` and `UNRESOLVED` block closure until a disposition is recorded and its requirements remain valid.

## Hub gates

For sessions with historical or long-running work, run `session-audit` first. An active run with `FAIL`, a pending proposal, refresh-required work, or hard-budget overflow is not acceptance-ready.

Run during integration:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs check \
  --run-dir <run-dir> \
  --json
```

Run before final acceptance:

```bash
node <skill-dir>/scripts/gpt-squad-context.mjs check \
  --run-dir <run-dir> \
  --for-close \
  --json
```

Revision-producing mutations already reject projected hard-budget overflow before commit. The close gate still verifies the complete persisted state:

- SQLite integrity;
- contiguous canonical revisions and version histories;
- checkout hashes and exact delivered read sets;
- generated-view consistency;
- result hashes and version chains;
- fresh mission context;
- completed dependencies;
- writer safety;
- no pending proposals;
- no unresolved challenger blockers;
- context and result budgets.

## Runtime evidence beyond the Hub

The Hub does not prove actual agent identity, model, effort, domain quality, or comprehension.

For runtime acceptance, inspect:

- parent `list_agents`, `spawn_agent`, `followup_task`, `wait_agent`, and `send_message` events;
- child `session_meta` role/model/effort;
- actual child tool calls and changed files;
- overlap between root and specialist missions;
- checkout view hashes delivered to each child;
- actual independent evidence used by challengers;
- final integrated diff and external behavior.

## Evaluation metrics

Measure outcomes before protocol volume:

```text
specialist result adoption rate
new decision-relevant evidence
finding duplication
root/child investigation overlap
coordination calls per adopted outcome
lightweight/cooperative/transactional mode distribution
mode escalation rate
collaboration requests accepted, reused, and declined
stale-result reopen count
review findings adopted or falsified
challenger findings that changed the result
user-visible latency and wait time
context and Working Commons size
invalid spawn and interrupt reasons
```

Do not optimize for agent count, proposal count, promotion rate, or Context Hub usage. A larger or more transactional squad is not automatically better. The objective is the smallest structure that materially improves correctness, speed, simplicity, or evidence quality.

Operational targets remain zero invalid spawns, no immediate re-wait after timeout, and no general blocking wait above 60 seconds. Autonomy targets are low duplicate investigation, low unnecessary canonical promotion, and high adoption of genuinely distinct specialist evidence.

## Completion report

The root's final report should state:

- delivered outcome;
- selected coordination mode and why it was sufficient;
- specialist ownership and meaningful contributions;
- material collaboration requests or provisional findings that changed composition;
- accepted and rejected canonical proposals when a Context Hub was used;
- material changes;
- verification performed;
- challenge verdicts and dispositions;
- unresolved risk;
- what the Hub proved;
- what still relies on runtime or human judgment.
