# Regulus — Deployment & Operations Contract

**Phase:** 16 · **Status:** FROZEN

```
Phases 1–15  what Regulus does, and the evidence for it
Phase 16     can another engineer reproduce, configure, start, inspect, operate and
             safely stop Regulus from a clean checkout?
```

> Phase 16 makes Regulus reproducible and operable as a **reference deployment**. It is not a
> production deployment, and it makes no availability, capacity, disaster-recovery, security or
> compliance claim.

**Scope statement.** Phase 16 validates that a clean checkout can be built, configured, started,
inspected, operated, stopped and restarted on one machine, with integrity-checked state, and
that its operational commands behave as the runbook says. There is no real environment, no
production traffic and no operations team, and none is simulated.

## 1. Boundary

| Does | Does not |
|---|---|
| package everything the runtime needs, pin its dependencies, and prove an installed copy runs without the repository | provide a database, replication, clustering or high availability |
| define a validated configuration schema, with secrets only from the environment | manage identity, TLS or network exposure (host concerns) |
| compose the reference stores, the governed review app and the observability buffer into one process | add features to any earlier phase |
| expose liveness and readiness, startup and shutdown with state snapshot and verified restore | claim durability beyond "the last clean snapshot" |
| ship a container recipe, an example configuration and a tested runbook | claim the image is secure, hardened or production-ready |

**The state model, stated plainly.** The stores are the in-memory reference stores. Persistence
is a **snapshot** of that state written atomically at graceful shutdown (and on request) and
restored, verified, at startup. A crash loses changes since the last snapshot. This is a
single-process, single-writer reference, not a durable service; a real deployment replaces the
store ports with a database, which is outside this contract.

## 2. Reproducible build

- `pyproject.toml` declares runtime dependencies; `requirements.lock` pins the **exact versions
  of the runtime dependency closure**. A script (`scripts/lock.py`) regenerates it from the
  installed metadata, **walking only the dependencies reachable from the declared runtime set**,
  never every package in the development environment. A test fails if the lock misses a runtime
  dependency, contains a package that is not reachable from the declared set, or disagrees with
  the declared ranges.
- **Every runtime data file is package data.** The governance files (`access_matrix`,
  `retention_policy`, `data_inventory`, `controls_map`) move into the package and are read
  through `importlib.resources`, so an installed copy needs nothing from the repository. A test
  builds the wheel and checks that every file the code loads at runtime is inside it, and a
  subprocess started in an empty directory with only the installed copy on its path loads them.
- Evaluation assets (gold sets, baseline, reports, the failure matrix) are development
  evidence, not runtime; they are not packaged, and the `check` command says so.
- `python -m regulus version` prints the package version and, when available, the git
  commit; nothing is fetched from the network at build or run time.

## 3. Configuration

A frozen `RegulusConfig` (extra keys forbidden) is loaded from an optional JSON file and
environment variables, with the environment taking precedence.

| Setting | Default | Rule |
|---|---|---|
| `host` | `127.0.0.1` | any other value requires `auth_mode = external` |
| `port` | `8765` | 1 to 65535 |
| `state_dir` | `./regulus-state` | writable; created on first start |
| `auth_mode` | `none` | `none` serves nothing but health (a test proves `/healthz` and `/readyz` answer while `/tasks` and every review POST are refused); `dev_header` trusts an actor header and **only** binds loopback; `external` is reserved for a host-provided identity function |
| `claim_ttl_seconds` | 900 | positive |
| `schedule` | Phase 11 defaults | the Phase 11 `ScheduleConfig` fields |
| `observation_buffer` | 1000 | positive |
| `retention_policy` | packaged illustrative file | path override allowed |
| `price_table` | none | optional path |

- **Secrets come only from the environment.** `REGULUS_CSRF_SECRET` is required, at least 32
  characters, never defaulted, never logged, never written to the state directory. A
  configuration file containing a key that looks like a secret (`secret`, `token`, `password`,
  `key`) is rejected.
- **Validation errors name the field and the rule, never the value.** `check` prints the
  effective configuration with secrets replaced by `<set>` or `<missing>`.
- `auth_mode = dev_header` exists so the reference can be exercised; it is **insecure by
  design** (any local process can claim any identity), so it refuses a non-loopback bind and
  prints a warning at startup. Real identity is a host function; Phase 16 does not implement it.

## 4. Runtime composition

`build(config) -> Runtime` constructs, in this order: the packaged data (matrix, retention
policy, inventory checked against the code), the stores restored from the state directory (or
empty), the observation buffer and metrics registry, the access audit and purge log, the
retention and identity objects, the Phase 10 review app, and the `GovernedApp` over it. The
review app is reachable **only** through the governed app. There is no code path that mounts
the ungoverned app in `serve`.

`python -m regulus` commands, each exiting `0` on success and a distinct non-zero code per
failure class (`2` configuration, `3` state integrity, `4` runtime):

| Command | Purpose |
|---|---|
| `version` | package version, commit if known |
| `check` | validate configuration, packaged data and inventory, and the state directory; no listening |
| `verify` | run `verify_all` over the stored state and report intact, broken and unreceipted streams |
| `seed-demo` | write a deterministic synthetic dataset into an empty state directory (no real or client data) |
| `serve` | start the governed review app and the health endpoints |
| `hold`, `release`, `purge`, `recover-purges` | the Phase 15 operator actions, audited, operator identity named on the command line |
| `snapshot` | write a snapshot now |

Operator commands act on a state directory **not in use by a running server** (single writer);
they refuse when a lock file shows a live process.

## 5. Health and readiness

Two unauthenticated, content-free endpoints on the same loopback listener:

- `GET /healthz` is **liveness**: the process is running and the event loop answers. It checks
  no dependency.
- `GET /readyz` is **readiness**, with a status per check and an overall `ready` flag:
  configuration valid, packaged data loaded, state integrity (`verify_all` intact), access audit
  appendable, state directory writable, clock monotonic, observation buffer not full, and the
  startup recovery finished. It returns `200` when ready and `503` with the failing checks
  otherwise.
- The body is ids, counts, check names and booleans only; no content, no configuration values,
  no secrets. Readiness reports `degraded` reasons (for example `audit_unavailable`,
  `buffer_full`, `unclean_shutdown_recovered`) rather than hiding them.
- Readiness must be **truthful**: each check is tested against an injected failure and must flip.

## 6. Startup and shutdown

**State files.** `snapshot.json` carries a monotonic `generation` and the state; `marker.json` is
`{generation, run_id}`; `lock` identifies the live process.

**Startup (deterministic, in order):**

1. load and validate configuration; load the packaged data; acquire the state lock;
2. restore the snapshot and **structurally verify** it: every chain and every replay;
3. **classify** what verification found:
   - *corruption*: a broken chain, a replay that fails, a record altered, deleted, reordered,
     spliced or truncated where an anchor exists, a snapshot that is partial or inconsistent;
   - *recoverable interrupted operation*: only the protocols Regulus itself defines, namely a
     `PURGE_INTENT` with no terminal record (and the stream present or absent), a submission in
     the intent phase, and open observability spans. A missing stream is `UNRECEIPTED`
     corruption **only if no `PURGE_INTENT` accounts for it**;
4. **any corruption refuses startup** (exit `3`): nothing is repaired, nothing listens;
5. **recover** the recoverable interrupted operations (`recover-purges`, complete intent-phase
   submissions, abandon open spans); recovery is re-runnable;
6. **verify again, fully**: the state must now be intact, otherwise exit `3`;
7. decide clean or unclean (below), **delete the shutdown marker**, write `STARTED(run_id)`,
   become ready, listen.

The rule that connects 3 to 5: **corruption is never recovered, and recoverable state is never
mistaken for corruption.**

**Clean versus unclean (A1).** The previous run shut down cleanly if and only if `marker.json`
exists **and its `generation` equals the restored snapshot's `generation`**. A marker left over
from an earlier generation does not count. Startup deletes the marker before serving, so a
marker can only mean "the generation it names was completed by a clean shutdown". An unclean
start runs the recoveries, reports `unclean_shutdown_recovered` in readiness and the log, and
states that changes since the last snapshot are lost.

**Shutdown (SIGTERM or SIGINT):** stop accepting requests; let in-flight requests finish within a
bounded grace period; drain the observation buffer to `events.jsonl`; write snapshot
**generation N+1** to a temporary file in the same directory (flush, then a best-effort sync) and
rename it over `snapshot.json`; write `marker.json` for generation N+1 last; release the lock.

**Atomicity claim, scoped (A3).** Under the controlled snapshot fault-injection model, a crash
at each defined step leaves the previous complete snapshot or the new complete snapshot, and the
marker names a generation only after that generation's snapshot is complete. The defined steps
are: before the temporary write, during it, after it, after the flush, after the rename, before
the marker, after the marker. The contract makes **no claim about arbitrary power loss, kernel
or filesystem behaviour, or durability**; an injected in-process crash is not a power failure.

**Restart after each crash step (tested):**

| Crash at | Snapshot on disk | Marker | Next start |
|---|---|---|---|
| before the temporary write | previous (N) | absent (deleted at startup) | unclean; recovers; state is generation N |
| during or after the temporary write, before the rename | previous (N), a stray temp file | absent | unclean; the stray temp file is ignored and removed; generation N |
| after the rename, before the marker | new (N+1) | absent | unclean; recovers; state is generation N+1 |
| after the marker | new (N+1) | names N+1 | clean |
| a stale marker naming N with snapshot N+1 | new (N+1) | names N | **unclean** (generations differ) |

## 7. Reference deployment

`deploy/` contains a `Dockerfile` (slim Python 3.12 base, non-root user, the lock installed, the
package installed, no secrets, no data baked in, state directory as a volume, a `HEALTHCHECK` on
`/healthz`), a `.dockerignore`, and `regulus.example.json` (every setting with its default, no
secrets). `docker run` needs `REGULUS_CSRF_SECRET` passed in. If a container runtime is
available the build and a `/healthz` probe are part of the evidence; if not, that evidence is
reported `NOT_MEASURABLE` and the Dockerfile is not claimed to work.

## 8. Runbook

`docs/16_runbook.md` is a tested procedure, one section per task, each with the exact command,
the expected output, and what to do on failure: build and install; configure and `check`; seed a
demo state; start; probe liveness and readiness; read a review page through the governed app;
inspect failures through `events.jsonl` and `metrics.txt`; run `verify`; place and release a
hold; purge and recover an interrupted purge; take a snapshot and **back up the state
directory** by the protocol below (a copy of a stopped, verified state directory is the backup unit); **restore** it and prove the
restore with `verify`; stop gracefully; recover from an unclean stop. A test executes the runbook's
commands against a temporary directory and fails if a documented command or expected output
changes.

**Backup and restore consistency boundary (A4).** A backup is valid only when taken from a state
directory whose lock is free, so no snapshot, temporary file or marker is changing:

```
stop the server (or snapshot, then stop the writer)  →  verify the state  →  copy the directory
→  verify the copy
```

A copy made while a server holds the lock is not a backup. A restore requires the target
directory to be unlocked and not in use: copy the backup into place, then run `verify`; startup
verifies again before serving. `check` reports whether the lock is free so the operator can
tell. Restoring is a manual, audited operator procedure; Regulus offers no automatic restore.

## 9. Failure semantics

| Situation | Behaviour |
|---|---|
| invalid or missing configuration, missing or short secret, secret key in a file | exit `2`, field names only, nothing started |
| non-loopback bind with `dev_header` | exit `2` |
| state integrity failure at startup | exit `3`, nothing listening, nothing repaired |
| state directory not writable | exit `4`; readiness never reports ready |
| second server on the same state directory | refused by the lock, exit `4` |
| operator command while a server holds the lock | refused, exit `4` |
| crash during snapshot | previous snapshot intact; no shutdown marker; next start recovers |
| audit log failing at runtime | governed pages fail closed (Phase 15); `/readyz` reports `audit_unavailable` |
| observation buffer full | events dropped and counted (Phase 13); `/readyz` reports `buffer_full`, meaning observability is degraded and the reference service is not considered ready, **not** that the application is unsafe or cannot function; Phase 13 non-interference is unchanged |
| SIGTERM during a request | request completes within the grace period, then snapshot and exit `0` |
| port in use | exit `4` before ready |

## 10. Hard invariants (tested as properties)

1. **Self-contained install.** An installed wheel loads every runtime data file with the
   repository absent.
2. **Lock completeness.** The lock pins the whole runtime dependency closure at the installed
   versions.
3. **Configuration safety.** Every invalid configuration is rejected with field names only; no
   secret appears in any output, log, state file or error; the secret is required.
4. **Governed only.** The served app is always the `GovernedApp`; health endpoints serve no
   review content.
5. **Restart convergence.** For any seeded state, snapshot then restore yields state whose
   `verify_all` is intact and whose logical content equals the snapshot's, repeatedly.
6. **Corruption refusal.** Each Phase 14 corruption class injected into a snapshot makes startup
   refuse (exit `3`) and change nothing.
7. **Snapshot atomicity under the fault-injection model, and marker coupling.** A crash at each
   defined step leaves the previous or the new snapshot complete and verifiable; a marker names a
   generation only if that generation's snapshot is complete; a stale marker never makes a start
   clean. No claim is made about arbitrary power loss or durability.
7a. **Recovery is not corruption.** Every recognized interrupted protocol state is recovered, and
    the fully verified state afterwards is intact; every corruption class is refused and none is
    recovered.
8. **Truthful readiness.** Each injected dependency failure flips `/readyz` to not ready with
   that check named; recovery flips it back.
9. **Content-free probes.** Health bodies, startup logs and `check` output contain no content,
   secret or configuration value.
10. **Deterministic reference run.** Two `seed-demo` runs produce identical state hashes and
    identical `verify` reports.

## 11. Evaluation (a Phase 12 layer)

A `deployment` layer joins the report. Evidence is `PROPERTY` or `REGRESSION`; there is no
availability, capacity or production row.

| Metric | Numerator / denominator | Gate |
|---|---|---|
| runtime data files missing from the built wheel | missing / files the code loads | **HARD: 0** |
| runtime dependencies missing or mismatched in the lock | such / runtime closure | **HARD: 0** |
| invalid configurations accepted | accepted / invalid configurations tried | **HARD: 0** |
| secrets found in outputs, logs, state or errors | artifacts with a secret / artifacts scanned | **HARD: 0** |
| non-governed routes served | review pages served without the governed app / routes probed | **HARD: 0** |
| restart divergence | restores whose verified content differs from the snapshot / restore cycles | **HARD: 0** |
| corrupted snapshots accepted at startup | accepted / injected corruptions (per class) | **HARD: 0** |
| non-atomic snapshot outcomes | crash points leaving a mixed or unverifiable state or a marker naming an incomplete generation / crash points tried | **HARD: 0** |
| misclassified startup state | recoverable interrupted states refused, or corruption recovered or accepted / classified cases | **HARD: 0** |
| untruthful readiness | injected failures not reflected or not recovered / injected failures | **HARD: 0** |
| non-content-free probe bodies | bodies with content, a secret or a configuration value / bodies scanned | **HARD: 0** |
| non-deterministic seeded runs | differing state hashes / paired seed runs | **HARD: 0** |
| runbook commands that fail or drift | failing steps / runbook steps executed | **HARD: 0** |
| container build and probe | built and healthy / attempts | `NOT_MEASURABLE` when no container runtime is available |

## 12. Claims

Allowed: "a clean checkout builds, installs, configures, starts, reports health, snapshots,
restores and stops under these tests", "state is verified before serving", "corrupted state is
refused".

Not allowed: "production-ready", "highly available", "durable", "scalable", "secure",
"hardened", "disaster-recoverable", "compliant", or any capacity or uptime figure. The README
states that the deployment is a reference deployment, that the stores are in-memory with
snapshot persistence, that `dev_header` authentication is insecure by design, and what is left
to a real deployment: a database behind the store ports, real identity, TLS and network
policy, backups with a tested restore on real storage, monitoring and alert routing, and
capacity testing.

## 13. Module layout

```
src/regulus/
├── __main__.py        command dispatch and exit codes
├── config.py          RegulusConfig, loading, validation, redaction
├── runtime.py         build(config): composition, startup and shutdown sequences
├── state.py           snapshot, atomic write, restore, lock, shutdown marker
├── health.py          /healthz and /readyz
├── seed.py            deterministic demo data
├── serve.py           listener, signals, grace period
└── governance/data/   packaged governance files (moved from governance/)
deploy/Dockerfile  deploy/.dockerignore  deploy/regulus.example.json
requirements.lock  scripts/lock.py
docs/16_runbook.md
src/regulus/evaluation/layers/deployment.py
tests/deployment/
```

## 14. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| wheel built, repository absent | every runtime data file loads from the installed copy |
| a data file the code loads but the wheel lacks | the packaging test fails |
| lock missing a dependency or with a wrong version | the lock test fails |
| each invalid setting (port range, empty state dir, unknown key, wrong type) | exit `2`, field named, value not shown |
| missing, short or defaulted secret | exit `2` |
| secret-like key inside the config file | exit `2` |
| `dev_header` with a non-loopback host | exit `2` |
| `check` output, startup log, health bodies, error messages | no secret, no configuration value, no content |
| `serve` | the app answering review routes is the governed app |
| `/healthz` and `/readyz` bodies | ids, counts, check names, booleans only |
| snapshot then restore, repeated | verified content equals the snapshot each time |
| each corruption class in a snapshot | startup exit `3`, nothing listening, nothing changed |
| truncated or partial snapshot file | startup exit `3` |
| crash at each snapshot step (before the temporary write, during it, after it, after the flush, after the rename, before the marker, after the marker), then restart | previous or new snapshot complete; the marker names a generation only if complete; start is clean exactly when the marker's generation equals the snapshot's; recoveries run otherwise |
| a stale marker from an earlier generation | start is unclean |
| a purge interrupted after the delete, then restart | recovered, not refused; `verify` intact afterwards; no `UNRECEIPTED` |
| a stream deleted with no `PURGE_INTENT` | refused as corruption (exit `3`) |
| an intent-phase submission, then restart | completed from its payload; intact afterwards |
| backup taken while the lock is held | flagged by `check` as not a valid backup |
| backup, restore into an unlocked directory, `verify` | intact; the app serves the same tasks |
| `auth_mode = none` | `/healthz` and `/readyz` answer; `/tasks` and every review POST are refused |
| start after an unclean stop | recoveries run; `unclean_shutdown_recovered` reported |
| two servers, one state directory | second refused |
| operator command with a server running | refused |
| audit log failing while serving | review pages fail closed, `/readyz` not ready, named |
| observation buffer full | events dropped and counted, `/readyz` degraded, named |
| state directory made read-only | `/readyz` not ready, named; restored, ready again |
| SIGTERM with a request in flight | request completes, snapshot written, exit `0` |
| `seed-demo` twice into empty directories | identical state hashes and `verify` reports |
| `seed-demo` into a non-empty directory | refused |
| restore from a backup copy | `verify` intact; the app serves the same tasks |
| every runbook command | executes and produces the documented output |
| Dockerfile present, runtime absent | container evidence `NOT_MEASURABLE`, no claim |

## 15. Gate

Contract frozen after review, then: package data moved and read through `importlib.resources`,
the lock and its script, configuration, state snapshot and restore with the lock and marker, the
composition and commands, health, startup and shutdown, the demo seed, the Dockerfile and example
configuration, the runbook and its executing test, every §14 row, the §10 properties, the
Phase 12 `deployment` layer with baseline, ruff and strict mypy clean, the README update with the
§12 statements, then freeze. After Phase 16 the milestone table is complete and the project is
frozen; further work is outside the phased plan.

## 16. Decisions to confirm

1. A reference deployment only; production deployment is a stated non-goal.
2. Persistence is snapshot-and-verified-restore of the in-memory reference stores, with a
   generation-coupled shutdown marker; a crash loses changes since the last snapshot; atomicity is
   claimed only under the fault-injection model; no durability claim.
3. The governance data files move into the package and are read through `importlib.resources`.
4. `dev_header` authentication exists for the reference only, loopback only, insecure by design;
   real identity is a host concern.
5. Secrets only from the environment; the CSRF secret is required and never defaulted.
6. Corrupted state refuses startup and is never repaired.
7. Container evidence is reported only if a container runtime is available.
8. A tested runbook is part of the deliverable, and a test executes it.
9. A `deployment` layer joins the Phase 12 report; no availability, capacity or production claim.
