from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from regulus.domain.base import Model

from .models import Kind, WorkflowRecord


class Stage(StrEnum):
    DETECTED = "DETECTED"
    PROCESS = "PROCESS"
    GENERATE = "GENERATE"


class Status(StrEnum):
    PENDING = "PENDING"
    DONE = "DONE"
    RETRYING = "RETRYING"
    DEAD_LETTER = "DEAD_LETTER"


class UnitState(Model):
    status: Status = Status.PENDING
    attempts: int = 0
    next_attempt_at: datetime | None = None
    error_class: str | None = None
    detail: str | None = None


class RunStatus(StrEnum):
    UNSTARTED = "UNSTARTED"
    REJECTED = "REJECTED"
    COMPLETE = "COMPLETE"
    WAITING = "WAITING"
    PARTIAL_DEAD = "PARTIAL_DEAD"
    DEAD = "DEAD"
    IN_PROGRESS = "IN_PROGRESS"


class RunState(Model):
    started: bool = False
    rejected: str | None = None
    stages: dict[Stage, UnitState] = {}
    items: dict[str, UnitState] = {}
    item_ids: tuple[str, ...] = ()
    ref: str | None = None
    ready_emitted: bool = False

    def stage(self, s: Stage) -> UnitState:
        return self.stages.get(s, UnitState())

    @property
    def status(self) -> RunStatus:
        if self.rejected:
            return RunStatus.REJECTED
        if not self.started:
            return RunStatus.UNSTARTED
        units = [self.stage(s) for s in (Stage.PROCESS, Stage.GENERATE)]
        gen_done = self.stage(Stage.GENERATE).status is Status.DONE
        units += [self.items.get(i, UnitState()) for i in self.item_ids] if gen_done else []
        if any(u.status is Status.DEAD_LETTER for u in units[:2]):
            return RunStatus.DEAD
        if all(u.status in (Status.DONE, Status.DEAD_LETTER) for u in units) and gen_done:
            dead = any(u.status is Status.DEAD_LETTER for u in units)
            return RunStatus.PARTIAL_DEAD if dead else RunStatus.COMPLETE
        if any(u.status is Status.RETRYING for u in units):
            return RunStatus.WAITING
        return RunStatus.IN_PROGRESS


def project_run(records: Sequence[WorkflowRecord]) -> RunState:
    st = RunState()
    stages: dict[Stage, UnitState] = {}
    items: dict[str, UnitState] = {}
    for r in records:
        d = r.details
        if r.kind is Kind.RUN_STARTED:
            st = st.model_copy(update={"started": True})
        elif r.kind is Kind.RUN_REJECTED:
            st = st.model_copy(update={"rejected": d["reason"]})
        elif r.kind in (Kind.STAGE_DONE, Kind.STAGE_FAILED, Kind.STAGE_DEAD_LETTER):
            stage = Stage(r.key or "")
            cur = stages.get(stage, UnitState())
            if r.kind is Kind.STAGE_DONE:
                stages[stage] = UnitState(status=Status.DONE, attempts=cur.attempts + 1)
                if stage is Stage.PROCESS:
                    st = st.model_copy(update={"ref": d.get("ref")})
                if stage is Stage.GENERATE:
                    st = st.model_copy(update={"item_ids": tuple(d["items"])})
            elif r.kind is Kind.STAGE_FAILED:
                stages[stage] = UnitState(
                    status=Status.RETRYING,
                    attempts=d["attempt"],
                    next_attempt_at=datetime.fromisoformat(d["next_attempt_at"]),
                    error_class=d["error_class"],
                )
            else:
                stages[stage] = UnitState(
                    status=Status.DEAD_LETTER, attempts=d["attempt"], error_class=d["error_class"]
                )
        elif r.kind in (Kind.ITEM_DONE, Kind.ITEM_FAILED, Kind.ITEM_DEAD_LETTER):
            item = r.key or ""
            cur = items.get(item, UnitState())
            if r.kind is Kind.ITEM_DONE:
                items[item] = UnitState(
                    status=Status.DONE, attempts=cur.attempts + 1, detail=d.get("outcome")
                )
            elif r.kind is Kind.ITEM_FAILED:
                items[item] = UnitState(
                    status=Status.RETRYING,
                    attempts=d["attempt"],
                    next_attempt_at=datetime.fromisoformat(d["next_attempt_at"]),
                    error_class=d["error_class"],
                )
            else:
                items[item] = UnitState(
                    status=Status.DEAD_LETTER,
                    attempts=cur.attempts + 1,
                    error_class=d["error_class"],
                    detail=d.get("reason"),
                )
        elif r.kind is Kind.RUN_REQUEUED:
            target = d["target"]
            if target.startswith("stage:"):
                stages[Stage(target[6:])] = UnitState()
            else:
                items[target[5:]] = UnitState()
        elif r.kind is Kind.TICK_ACTION and r.key == "ready-emitted":
            st = st.model_copy(update={"ready_emitted": True})
    return st.model_copy(update={"stages": stages, "items": items})
