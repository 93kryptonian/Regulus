# Regulus

Regulatory intelligence and obligation management platform.

> Deterministic systems detect regulatory changes; AI interprets their semantic
> implications; humans retain final authority.

Built contract-first: each phase ships `docs/NN_*_contract.md` → `src/` → `tests/`
→ adversarial verification → freeze.

| Milestone | Phases | Status |
|---|---|---|
| M1 Detection foundation | 0 Boundary, 1 Domain, 2 Change detection, 3 Documents | Phases 0–3 frozen; M1 complete |
| M2 Regulatory intelligence | 4–8 | Phases 4–8 frozen; M2 complete |
| M3 Human-in-the-loop product | 9–11 | Phases 9–11 frozen; M3 complete |
| M4 Production engineering | 12–16 | Phases 12–16 frozen; milestone table complete |

Start with [docs/00_system_boundary.md](docs/00_system_boundary.md).

All data in this repository is public or synthetic.

## Reference deployment (Phase 16)

A clean checkout can build, configure, start, inspect, operate, snapshot, restore and stop the
reference deployment under the defined tests ([contract](docs/16_deployment_contract.md),
[runbook](docs/16_runbook.md)). State is verified before serving, and corrupted state is refused.

Demonstrated: reproducible reference build and install, packaged runtime data, validated
configuration, governed runtime composition, startup integrity verification, snapshot and restore
under the tested fault model, graceful and unclean restart recovery, health and readiness, and a
tested operational runbook.

Not demonstrated: arbitrary power-loss durability, production capacity, high availability or
replication, real identity integration, TLS and network security, production backup and restore,
container operation in the evaluation environment (reported `NOT_MEASURABLE`), production
monitoring and alerting, and any compliance or security certification.

Notes:

- The stores are in-memory with snapshot persistence. A crash loses changes since the last
  snapshot, and atomicity is tested only under controlled in-process fault injection.
- `dev_header` authentication is insecure by design: any local process can claim any identity,
  so it binds loopback only. With `auth_mode = none` only the health endpoints answer.
- The system makes no production-durability or production-operability claim.

A real deployment still needs: a database behind the store ports, real identity, TLS and
network policy, backups with a tested restore on real storage, monitoring and alert routing,
and capacity testing.
