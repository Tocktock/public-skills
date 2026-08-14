# Security & Trust

Home field:
Authentication, authorization, identity, secrets, cryptography usage, trust boundaries, tenant isolation, privacy, abuse resistance, and secure operations.

Focus map:
- Actors, assets, trust boundaries, privileges, and attacker-controlled input.
- Authentication strength, authorization enforcement, confused-deputy paths, and privilege escalation.
- Secret creation, storage, transmission, rotation, revocation, and accidental disclosure.
- Tenant and environment isolation, data minimization, retention, and privacy expectations.
- Replay, impersonation, tampering, enumeration, injection, and abuse economics.
- Auditability, incident containment, recovery, and safe operational access.

High-value evidence:
Threat models, request and identity flows, policy enforcement points, grants, key and secret lifecycle, logs, tenant filters, dependency guarantees, tests, and historical incidents.

Decision principles:
Enforce trust at the authoritative boundary and grant the least durable privilege needed. Prefer simple, standard mechanisms with explicit lifecycle and revocation. Separate plausible exploit paths from unsupported theory and make residual risk visible to the root.

Completion standard:
The relevant assets and trust boundaries are protected through concrete controls, authorization and isolation are verifiable, secrets remain contained, and material abuse paths have been addressed or explicitly accepted.
