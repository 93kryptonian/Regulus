from regulus.evaluation.harness import NOW, OWNER, TEXT, generation_result
from regulus.runtime import Exit, Refused, Runtime
from regulus.state import SNAPSHOT
from regulus.workflow import SYSTEM, SnapshotInputs, submit_for_review

DEMO_ITEMS = 3


def seed_demo(rt: Runtime) -> int:
    if (rt.state.path / SNAPSHOT).exists() or rt.parts.store.tasks:
        raise Refused(Exit.RUNTIME, ["state directory is not empty"])
    rt.parts.texts[OWNER] = TEXT
    done = 0
    for i in range(DEMO_ITEMS):
        out = submit_for_review(
            rt.parts.store,
            generation_result(f"demo-{i}"),
            SnapshotInputs(permitted_source=TEXT),
            SYSTEM,
            NOW,
            rt.parts.texts,
        )
        done += out.task is not None
    return done
