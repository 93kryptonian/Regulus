import importlib
import json
import types
import typing
from pathlib import Path

from pydantic import BaseModel

STORED = (
    "regulus.domain.obligation.Obligation",
    "regulus.domain.evidence.ObligationEvidence",
    "regulus.review.models.ReviewRecord",
    "regulus.review.models.ReviewTask",
    "regulus.workflow.models.WorkflowRecord",
    "regulus.workflow.models.PreparedSubmission",
    "regulus.documents.models.ProcessedDocument",
    "regulus.obligations.models.ObligationCandidate",
    "regulus.similarity.models.SimilarityResult",
    "regulus.observability.events.ObsEvent",
    "regulus.observability.cost.UsageRecord",
    "regulus.governance.chain.GovRecord",
)
CLASSES = {"PUBLIC", "INTERNAL", "RESTRICTED", "OPERATIONAL", "SECRET"}
RESTRICTED_FIELDS = {
    "actor_id",
    "reviewer",
    "principal_id",
    "claimed_by",
    "actor_roles",
    "reason",
    "note",
    "details",
    "fields",
    "text",
}


def load_model(path: str) -> type[BaseModel]:
    mod, _, name = path.rpartition(".")
    cls = getattr(importlib.import_module(mod), name)
    assert isinstance(cls, type) and issubclass(cls, BaseModel)
    return cls


def _models_in(annotation: object) -> list[type[BaseModel]]:
    out: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        out.append(annotation)
    for arg in typing.get_args(annotation):
        out += _models_in(arg)
    if isinstance(annotation, types.UnionType):
        for arg in annotation.__args__:
            out += _models_in(arg)
    return out


def closure(roots: tuple[str, ...] = STORED) -> dict[str, type[BaseModel]]:
    seen: dict[str, type[BaseModel]] = {}
    todo = [load_model(r) for r in roots]
    while todo:
        m = todo.pop()
        key = f"{m.__module__}.{m.__name__}"
        if key in seen:
            continue
        seen[key] = m
        for f in m.model_fields.values():
            todo += _models_in(f.annotation)
    return seen


def default_entry(key: str, model: type[BaseModel]) -> dict[str, object]:
    mod = key.split(".")[1]
    cls, personal, retention, deletion, store = {
        "documents": ("PUBLIC", "NONE", "SOURCE_DERIVED", "NONE", "document store"),
        "obligations": ("INTERNAL", "NONE", "SOURCE_DERIVED", "NONE", "pipeline artifacts"),
        "similarity": ("INTERNAL", "NONE", "SOURCE_DERIVED", "NONE", "pipeline artifacts"),
        "domain": ("INTERNAL", "NONE", "REVIEW_RECORD", "WHOLE_STREAM", "review store"),
        "review": ("RESTRICTED", "OPAQUE_ID", "REVIEW_RECORD", "WHOLE_STREAM", "review store"),
        "workflow": ("RESTRICTED", "OPAQUE_ID", "WORKFLOW", "WHOLE_STREAM", "workflow store"),
        "observability": ("OPERATIONAL", "NONE", "OPERATIONAL", "EPHEMERAL", "observation journal"),
        "governance": (
            "RESTRICTED",
            "OPAQUE_ID",
            "ACCESS_AUDIT",
            "WHOLE_STREAM",
            "governance logs",
        ),
    }[mod]
    fields = {
        n: (
            "RESTRICTED"
            if n in RESTRICTED_FIELDS and mod in ("review", "workflow", "governance")
            else cls
        )
        for n in model.model_fields
    }
    return {"model": key, "store": store, "class": cls, "personal_data": personal, "retention_class": retention, "deletion": deletion,
            "mutable": False, "fields": fields}  # fmt: skip


def generate() -> list[dict[str, object]]:
    return [default_entry(k, m) for k, m in sorted(closure().items())]


def check(entries: list[dict[str, object]]) -> list[str]:
    problems: list[str] = []
    models = closure()
    listed = {str(e["model"]): e for e in entries}
    for key, m in models.items():
        e = listed.get(key)
        if e is None:
            problems.append(f"{key}: stored model not in the inventory")
            continue
        fields = e["fields"]
        assert isinstance(fields, dict)
        for name in m.model_fields:
            if name not in fields:
                problems.append(f"{key}.{name}: field not classified")
            elif fields[name] not in CLASSES:
                problems.append(f"{key}.{name}: unknown class {fields[name]}")
        for name in fields:
            if name not in m.model_fields:
                problems.append(f"{key}.{name}: stale entry")
        if e["class"] not in CLASSES:
            problems.append(f"{key}: unknown class")
    for key in listed:
        if key not in models:
            problems.append(f"{key}: inventory entry for a model that is not stored")
    return problems


def load(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data
