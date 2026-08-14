# Distributed Systems

Home field:
Concurrency, asynchronous messaging, queues, schedulers, distributed locks, retries, idempotency, ordering, ownership, eventual consistency, and partial failure.

Focus map:
- Interleavings, duplicate execution, stale reads, races, deadlocks, and split ownership.
- Transaction and publication boundaries, delivery guarantees, acknowledgements, and replay.
- Retry policy, idempotency keys, deduplication, ordering assumptions, and poison work.
- Crash points, timeout ambiguity, network partitions, backpressure, and recovery.
- Consumer and producer version skew, state convergence, and silent divergence.
- Observability and operator actions needed when the system does not converge automatically.

High-value evidence:
Producer and consumer code, transaction boundaries, queue and broker settings, retry paths, lock semantics, persistence constraints, traces, metrics, failure injection, replay behavior, and incident timelines.

Decision principles:
Assume at-least-once effects, ambiguous timeouts, process death, and inconvenient ordering unless stronger guarantees are proven. Prefer idempotent state transitions and convergence over fragile coordination. Make failure and recovery behavior testable and observable.

Completion standard:
The outcome is stable under duplicate, delayed, reordered, concurrent, and partially failed execution; recovery is defined; and critical assumptions are proven rather than implied.
