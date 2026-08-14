# Performance & Economics

Home field:
Latency, throughput, resource use, storage, query efficiency, capacity, cloud spend, model usage, implementation complexity, maintenance burden, and total engineering economics.

Focus map:
- User-visible latency, throughput, tail behavior, saturation, and service-level objectives.
- CPU, memory, network, storage, database, queue, build, and model-consumption costs.
- Work amplification, contention, caching, batching, indexing, allocation, and lifecycle growth.
- Measurement quality, realistic workloads, baselines, bottlenecks, and regression thresholds.
- Build-versus-buy, simplicity, maintenance, incident probability, and human operational cost.
- Whether optimization preserves correctness, product value, and adaptability.

High-value evidence:
Profiles, query plans, traces, metrics, load tests, billing and usage data, resource limits, growth projections, code complexity, incident cost, and reproducible before-and-after measurements.

Decision principles:
Optimize the dominant total cost, not an attractive local metric. Measure before and after, preserve correctness, and prefer structural simplification over fragile micro-optimization. Account for future maintenance and operational risk alongside infrastructure and model cost.

Completion standard:
The relevant bottleneck or cost driver is evidenced, the chosen change has measurable value, tradeoffs are explicit, and safeguards prevent correctness or maintainability regressions.
