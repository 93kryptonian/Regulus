import random
from collections import Counter
from collections.abc import Sequence

from regulus.domain import ObligationStatus as S
from regulus.review import ReviewRecord, replay, verify_chain

from ..builder import EC, HARD0, Builder
from ..harness import ReviewRun, obligation
from ..models import Formula, Status

L = "review"
POP = "review.harness_runs"
RUNS, STEPS, SEED = 60, 30, 20260901
TERMINAL = {S.APPROVED, S.REJECTED, S.PUBLISHED}


def four_eyes_violations(log: Sequence[ReviewRecord]) -> tuple[int, int]:
    last_editor = last_approver = None
    violations = checked = 0
    for r in log:
        to = r.decision.to_status
        if to is S.EDITED:
            last_editor = r.actor_id
        elif to is S.APPROVED:
            checked += 1
            violations += r.actor_id == last_editor
            last_approver = r.actor_id
        elif to is S.PUBLISHED:
            checked += 1
            violations += r.actor_id == last_approver
    return violations, checked


def evaluate(b: Builder) -> None:
    runs = []
    for i in range(RUNS):
        run = ReviewRun(f"obl-{i}", random.Random(SEED + i))
        for _ in range(STEPS):
            run.step()
        runs.append(run)
    b.population(POP, "seeded random action sequences by scripted reviewers", f"seeds {SEED}..{SEED + RUNS - 1}, {STEPS} steps each", RUNS,
                 "evaluation harness", "scripted reviewers and a scripted clock; no real human review data exists; descriptive only")  # fmt: skip
    m = b.metric
    decided = [r for r in runs if r.store.get(r.oid)[0].status in TERMINAL]
    approved = [r for r in decided if r.store.get(r.oid)[0].status in (S.APPROVED, S.PUBLISHED)]
    rejected = [r for r in decided if r.store.get(r.oid)[0].status is S.REJECTED]
    reasons = Counter(
        rec.decision.reason
        for r in rejected
        for rec in r.log()
        if rec.decision.to_status is S.REJECTED
    )
    b.record(
        m(
            f"{L}.approved_share",
            L,
            "approved share of decided tasks",
            POP,
            "tasks ending APPROVED or PUBLISHED",
            "tasks with a terminal decision",
            EC.PROPERTY,
        ),
        len(approved),
        len(decided),
        "scripted decisions, not reviewer behaviour",
    )
    b.record(
        m(
            f"{L}.rejected_share",
            L,
            "rejected share of decided tasks",
            POP,
            "tasks ending REJECTED",
            "tasks with a terminal decision",
            EC.PROPERTY,
        ),
        len(rejected),
        len(decided),
        f"reject reasons: {dict(sorted(reasons.items()))}",
    )
    edited = [r for r in decided if any(x.decision.to_status is S.EDITED for x in r.log())]
    b.record(
        m(
            f"{L}.edit_share",
            L,
            "share of decided tasks with at least one edit",
            POP,
            "decided tasks with an EDITED record",
            "tasks with a terminal decision",
            EC.PROPERTY,
        ),
        len(edited),
        len(decided),
    )
    res = [x for r in runs for rec in r.log() for x in rec.open_question_resolutions]
    b.record(
        m(
            f"{L}.accepted_as_is_share",
            L,
            "share of question resolutions accepted as is",
            POP,
            "resolutions recorded ACCEPTED_AS_IS",
            "recorded question resolutions",
            EC.PROPERTY,
        ),
        sum(x.resolution.value == "ACCEPTED_AS_IS" for x in res),
        len(res),
    )
    disp = [x for r in runs for rec in r.log() for x in rec.match_dispositions]
    b.record(
        m(
            f"{L}.not_a_duplicate_share",
            L,
            "share of dispositions recorded NOT_A_DUPLICATE",
            POP,
            "dispositions recorded NOT_A_DUPLICATE",
            "recorded dispositions",
            EC.PROPERTY,
        ),
        sum(x.disposition.value == "NOT_A_DUPLICATE" for x in disp),
        len(disp),
    )
    flagged = [
        (r, rec)
        for r in runs
        if r.task.snapshot.source_flags
        for rec in r.log()
        if rec.decision.to_status is S.APPROVED
    ]
    b.record(
        m(
            f"{L}.flagged_approvals_acknowledged",
            L,
            "approvals on flagged sources carrying an acknowledgement",
            POP,
            "such approvals with a recorded acknowledgement",
            "approvals on tasks whose snapshot has a source flag",
            EC.PROPERTY,
        ),
        sum(bool(rec.acknowledged_flags) for _, rec in flagged),
        len(flagged),
    )
    v = c = 0
    for r in runs:
        a, bb = four_eyes_violations(r.log())
        v, c = v + a, c + bb
    b.record(
        m(
            f"{L}.four_eyes_violations",
            L,
            "four-eyes violation rate",
            POP,
            "approvals by the last editor plus publishes by the approver",
            "approvals and publishes",
            EC.PROPERTY,
            HARD0,
        ),
        v,
        c,
        "log scan independent of the engine",
    )
    bad = sum(
        not (verify_chain(r.log()) and replay(obligation(r.oid), r.log()) == r.store.get(r.oid)[0])
        for r in runs
    )
    b.record(
        m(
            f"{L}.replay_violations",
            L,
            "replay equality violation rate",
            POP,
            "logs whose replay differs from the stored state or whose chain fails",
            "review logs",
            EC.PROPERTY,
            HARD0,
        ),
        bad,
        len(runs),
    )
    b.unmeasurable(m(f"{L}.stale_and_denied_actions", L, "stale and denied action rate", POP, "stale or denied actions", "submitted actions", EC.PROPERTY),
                   "failed actions leave no record by design; covered by the property tests only")  # fmt: skip
    lat: list[float] = []
    for r in decided:
        term = [rec for rec in r.log() if rec.decision.to_status in (S.APPROVED, S.REJECTED)]
        if term:
            lat.append((term[0].decision.at - r.created).total_seconds())
    b.record(m(f"{L}.submit_to_decision_seconds", L, "submit-to-decision elapsed seconds (mean)", POP, "sum of elapsed seconds from task creation to the first terminal decision", "decided tasks with both times", EC.PROPERTY, formula=Formula.MEAN),
             sum(lat), len(lat), f"{len(decided) - len(lat)} excluded; scripted clock, elapsed time is not reviewer effort")  # fmt: skip
    b.unmeasurable(m(f"{L}.reviewer_time_per_obligation", L, "reviewer time per obligation", POP, "active reviewer time", "obligations reviewed", EC.PROPERTY),
                   "claim durations and active time are not recorded, and no real reviewer data exists", Status.NOT_MEASURABLE)  # fmt: skip
