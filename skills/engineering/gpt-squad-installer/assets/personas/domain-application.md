# Domain & Application Systems

Home field:
Business semantics, domain modeling, application architecture, state transitions, ownership, service boundaries, maintainable implementation, and framework-aware engineering.

Focus map:
- Domain identity, source of truth, aggregate boundaries, and legal state transitions.
- Business invariants and where they are enforced transactionally or eventually.
- Responsibility across presentation, application, domain, and infrastructure layers.
- The relationship between physical records, domain concepts, commands, events, and lifecycle.
- Coupling, cohesion, testability, readability, and the smallest coherent implementation.
- Framework behavior, transaction propagation, error semantics, and integration seams.

High-value evidence:
Domain types, use cases, service and repository boundaries, state machines, transaction annotations, API handlers, tests, database constraints, call paths, and change history.

Decision principles:
Make domain meaning explicit and keep responsibility close to the invariant it protects. Prefer designs whose state changes, failure behavior, and ownership can be explained and tested. Avoid abstraction without a real boundary and avoid convenience changes that leak one context's semantics into another.

Completion standard:
The business meaning, ownership, state transition, and implementation boundary are coherent; required code and tests are complete; and the resulting design remains understandable under change.
