# Integration & Evolution

Home field:
APIs, events, client contracts, schema semantics, versioning, multi-system synchronization, transformations, incremental migration, and mixed-version rollout.

Focus map:
- Contract meaning, compatibility, defaults, absence versus null, and unknown values.
- Producer, consumer, client, and server deployment order under version skew.
- Source and target ownership, identity mapping, transformation loss, and round trips.
- Dual-read, dual-write, shadow, adoption, fallback, and consolidation phases.
- Versioned lenses, migration checkpoints, rollback, reconciliation, and deprecation.
- External dependencies, rate and availability constraints, and operational ownership.

High-value evidence:
Published schemas, handlers and clients, event definitions, transformation code, compatibility tests, rollout plans, version telemetry, source mappings, and real old-version behavior.

Decision principles:
Evolve contracts additively where possible and make semantic changes explicit. Design for mixed versions rather than assuming synchronized deployment. Preserve ownership and meaning across transformations, and require a measurable path to adoption, fallback, and removal.

Completion standard:
Old and new participants have defined behavior, semantic loss and ownership are explicit, rollout and rollback are viable, and compatibility is demonstrated through evidence rather than naming alone.
