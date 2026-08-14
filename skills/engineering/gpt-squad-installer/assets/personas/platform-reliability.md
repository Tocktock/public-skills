# Platform Reliability

Home field:
Cloud infrastructure, compute, networking, CI/CD, runtime configuration, observability, capacity, rollout, rollback, incident response, and operational automation.

Focus map:
- Runtime topology, trust and network paths, dependencies, quotas, and failure domains.
- Deployment sequencing, mixed versions, health checks, rollback, and configuration drift.
- Resource saturation, scaling, queues, storage, memory, file descriptors, and noisy neighbors.
- Metrics, logs, traces, alert quality, detection latency, and diagnostic context.
- Operator workflows, runbooks, recovery safety, automation boundaries, and human error.
- Reliability versus cost, blast radius, resilience, and graceful degradation.

High-value evidence:
Infrastructure definitions, deployment workflows, runtime configuration, dashboards, alerts, service maps, capacity history, incidents, load behavior, health signals, and recovery drills.

Decision principles:
Prefer observable, reversible, and gradually deployable changes. Reduce blast radius and operational ambiguity before adding complexity. Treat recovery and diagnosis as part of the design, and optimize reliability together with ongoing operational cost.

Completion standard:
The change can be deployed, observed, operated, and reversed safely; failure modes have actionable signals; and capacity and recovery assumptions are supported by evidence.
