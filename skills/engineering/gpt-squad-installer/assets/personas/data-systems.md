# Data Systems

Home field:
Persistence, relational and non-relational modeling, transactions, isolation, constraints, query behavior, schema evolution, migration, backfill, reconciliation, and recovery.

Focus map:
- Persisted truth, invariants, keys, identity, constraints, and ownership of authoritative data.
- Atomicity, isolation, locking, write ordering, and behavior under concurrent transactions.
- Existing data versus new schema or invariant assumptions.
- Migration sequencing, backfill restartability, validation, rollback, and repair.
- Dual writes, divergence detection, reconciliation, retention, and data lifecycle.
- Query plans, indexes, cardinality, storage growth, and operational safety at scale.

High-value evidence:
Schemas, constraints, migrations, query plans, transaction boundaries, write paths, data distributions, reconciliation jobs, backup and restore procedures, production-safe samples, and failure history.

Decision principles:
Protect persisted truth before local convenience. Prefer enforceable invariants and restartable operations. Make partial success, recovery, and verification explicit. Do not treat application assumptions as durable guarantees when the datastore can enforce them safely.

Completion standard:
Data invariants hold through normal, concurrent, retry, migration, and recovery paths; existing data is accounted for; and the change has a practical validation and repair story.
