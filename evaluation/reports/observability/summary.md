# Observability demonstration

Phase 13 validates observability behaviour under controlled local workloads and failure injection. No production traffic exists; no operational SLO, capacity or uptime claim is made.

Injected: pipeline outages (20%), channel failures (30%), scripted review actions, a fake priced AI provider, one model missing from the price table. Seed 13.

- events emitted: 70, delivered: 70, dropped: 0, buffered: 0
- spans by stage: {"DETECTED_NOTIFY": 2, "ENRICH": 10, "GENERATE": 2, "NOTIFY_DELIVER": 18, "PROCESS": 2, "REVIEW_ACTION": 12, "RUN": 16, "SUBMIT": 8}
- AI accounting: 4 AI calls, 1 unpriced, 0 estimated; money total 3000 micro-units in XXX
- events carry ids, counts and closed-enum values only; no source or obligation text.
