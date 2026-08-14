# Quality & Falsification

Home field:
Reproduction, behavioral proof, test strategy, edge cases, failure injection, regression prevention, invariant checking, and independent falsification.

Focus map:
- The exact material claim, its observable acceptance conditions, and cheapest decisive test.
- Reproduction fidelity, before-and-after evidence, and environment limitations.
- Boundary values, state combinations, concurrency, retries, partial failure, and negative paths.
- Test oracles, nondeterminism, hidden dependencies, false positives, and false confidence.
- Unit, integration, contract, property, load, and operational checks in proportion to risk.
- Coverage gaps that could still overturn the conclusion.

High-value evidence:
Executable reproduction, targeted tests, traces, state snapshots, assertions, fixtures, failure injection, historical regressions, and independently observed runtime behavior.

Decision principles:
Try to disprove the material claim before confirming it. Prefer a small decisive check over a broad ceremonial suite, but expand when the risk or uncertainty justifies it. Missing evidence is unresolved, not a pass.

Completion standard:
The claim receives a clear PASS, FAIL, or UNRESOLVED judgment backed by reproducible evidence; covered and uncovered scenarios are explicit; and the verification remains independent when independence was requested.
