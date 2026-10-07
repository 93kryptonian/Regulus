# Phase 16 runbook: reference deployment

Scope: a reference deployment of Regulus on one host, with in-memory stores and snapshot
persistence. It is not a production procedure. `dev_header` authentication is insecure by design.
All data in the demo is synthetic.

Every fenced `runbook` block below is executed by `tests/deployment/test_dep_runbook.py` against
a temporary directory, in document order. The test fails if a command or its expected output
changes. Grammar:

- `$ <command>` runs to completion; `regulus` means `python -m regulus`, `pip` means `python -m pip`.
- `ENV NAME=value` sets an environment variable for the steps that follow.
- `& <command>` starts a background process and waits for its `ready` line.
- `GET <path>` requests the background server; `GET <path> as <actor> <roles>` adds the development identity headers.
- `STOP` sends SIGTERM to the background server; `KILL` sends SIGKILL.
- `=> exit N`, `=> status N`, `=> contains "text"`, `=> absent "text"` are the expected results.

Variables `$WORK`, `$STATE`, `$BACKUP`, `$RESTORED`, `$PORT` and `$SECRET` come from the test.
Real deployments choose their own paths and generate the secret with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

Exit codes: `0` success, `2` configuration, `3` state integrity, `4` runtime.

## 1. Build and install

Use Python 3.12. The lock pins the runtime dependency closure; the package installs without
resolving anything else.

```runbook
$ pip wheel . --no-deps -w $WORK/wheel -q
=> exit 0
$ test -s $WORK/wheel/regulus-0.1.0-py3-none-any.whl
=> exit 0
```

Install with `pip install -r requirements.lock` then `pip install --no-deps $WORK/wheel/*.whl`.
On failure: check the Python version and that `requirements.lock` is current (`python scripts/lock.py`).

## 2. Configure and check

The secret comes only from the environment, at least 32 characters. Nothing is read from a file
for secrets, and no secret appears in any output.

```runbook
ENV REGULUS_CSRF_SECRET=$SECRET
ENV REGULUS_STATE_DIR=$STATE
ENV REGULUS_AUTH_MODE=dev_header
ENV REGULUS_PORT=$PORT
$ regulus version
=> exit 0
=> contains "version"
$ regulus check
=> exit 0
=> contains "<set>"
=> contains "\"packaged_data\": true"
=> contains "\"valid_backup_source\": true"
=> absent "$SECRET"
```

On failure (exit `2`): the message names the field and the rule, never the value. Fix the named
setting and run `check` again.

## 3. Seed a demo state

Writes a deterministic synthetic dataset into an empty state directory.

```runbook
$ regulus seed-demo
=> exit 0
=> contains "\"seeded\": 3"
$ regulus seed-demo
=> exit 4
$ regulus verify
=> exit 0
=> contains "\"broken\": []"
```

The second `seed-demo` is refused because the directory is not empty.

## 4. Start, probe and read a page

Start prints a warning for `dev_header` and a `ready` line. Liveness checks nothing else;
readiness verifies the state and its dependencies and names any failing check.

```runbook
& regulus serve
GET /healthz
=> status 200
=> contains "alive"
GET /readyz
=> status 200
=> contains "\"ready\": true"
GET /tasks
=> status 401
GET /tasks as r1 REVIEWER
=> status 200
=> contains "Review queue"
```

On failure: `GET /readyz` returns `503` with the failing check names under `failing`. An exit `3`
at start means the state failed verification (nothing was repaired); an exit `4` means the port
or state directory is in use or not writable.

## 5. Stop gracefully and inspect

Stopping drains events to `events.jsonl`, writes `metrics.txt` and a new snapshot generation.

```runbook
STOP
=> exit 0
$ test -s $STATE/events.jsonl
=> exit 0
$ test -s $STATE/metrics.txt
=> exit 0
$ test -s $STATE/marker.json
=> exit 0
```

## 6. Holds, purges and purge recovery

Operator commands act on a stopped state directory and name the operator. They are audited.
A running server holds the lock, and these commands then exit `4`.

```runbook
$ regulus hold --operator op1 --stream obligation:demo-0 --reason legal
=> exit 0
=> contains "\"result\": true"
$ regulus purge --operator op1 --stream obligation:demo-0 --reason elapsed
=> exit 0
=> contains "\"result\": \"REFUSED\""
$ regulus release --operator op1 --stream obligation:demo-0 --reason lifted
=> exit 0
=> contains "\"result\": true"
$ regulus recover-purges --operator op1
=> exit 0
=> contains "\"result\": 0"
$ regulus verify
=> exit 0
```

A purge interrupted after its intent is completed or cancelled by `recover-purges`, and
automatically at the next start. The purge is refused here because the obligation is not terminal.

## 7. Snapshot, back up, restore and prove it

A backup is valid only from a state directory whose lock is free: stop the server, verify, copy,
verify the copy. Restoring is manual: copy into an unlocked directory and run `verify`.

```runbook
$ regulus snapshot
=> exit 0
$ regulus check
=> contains "\"valid_backup_source\": true"
$ regulus verify
=> exit 0
$ cp -R $STATE $BACKUP
=> exit 0
ENV REGULUS_STATE_DIR=$BACKUP
$ regulus verify
=> exit 0
=> contains "\"broken\": []"
$ cp -R $BACKUP $RESTORED
=> exit 0
ENV REGULUS_STATE_DIR=$RESTORED
$ regulus verify
=> exit 0
& regulus serve
GET /readyz
=> status 200
GET /tasks as r1 REVIEWER
=> status 200
=> contains "PENDING_REVIEW"
STOP
=> exit 0
```

On failure: a `verify` exit `3` names the broken or unreceipted streams. Do not use that copy.

## 8. Recover from an unclean stop

```runbook
& regulus serve
KILL
$ regulus check
=> exit 0
=> contains "\"lock_free\": true"
& regulus serve
GET /readyz
=> status 200
=> contains "unclean_shutdown_recovered"
STOP
=> exit 0
```

An unclean stop loses changes since the last snapshot. Recoveries run at the next start, and
readiness reports `unclean_shutdown_recovered` rather than hiding it.

## 9. What this runbook does not cover

Production durability, real identity, TLS, network policy, monitoring and alert routing,
capacity, and restore on real storage. See the README.
