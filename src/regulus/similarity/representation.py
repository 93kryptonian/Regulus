import hashlib
import json

from regulus.domain import Obligation
from regulus.generation import TransformationTrace
from regulus.generation.models import Disposition
from regulus.generation.verify import tokens
from regulus.obligations import FieldStatus, Modality, load_lexicon
from regulus.obligations.segment import find_markers

from .models import FIELDS, FieldEntry, Representation

_ABSENT = {
    Disposition.ABSENT_NOT_STATED: FieldStatus.NOT_STATED,
    Disposition.ABSENT_UNDETERMINED: FieldStatus.UNDETERMINED,
}


def modality_of(text: str) -> Modality | None:
    marks = [m for m in find_markers(text, (0, len(text)), load_lexicon()) if not m.negated]
    kinds = {m.modality for m in marks}
    return next(iter(kinds)) if len(kinds) == 1 else None


def _state(name: str, value: str | None, trace: TransformationTrace | None) -> FieldStatus:
    if value is not None:
        return FieldStatus.PRESENT
    if trace is None:
        return FieldStatus.UNDETERMINED
    if name in ("condition", "exception"):
        if any(q.startswith(f"{name}:") for q in trace.open_questions):
            return FieldStatus.UNDETERMINED
        return FieldStatus.NOT_STATED
    for e in trace.candidate:
        if e.field.role == name:
            return _ABSENT.get(e.disposition, FieldStatus.NOT_STATED)
    return FieldStatus.UNDETERMINED


def represent(obligation: Obligation, trace: TransformationTrace | None = None) -> Representation:
    content = obligation.current
    fields: dict[str, FieldEntry] = {}
    for name in FIELDS:
        value = getattr(content, name)
        fields[name] = FieldEntry(
            state=_state(name, value, trace), tokens=tuple(tokens(value or "")), value=value
        )
    text_tokens = tuple(tokens(content.text))
    modality = modality_of(content.text)
    payload = json.dumps(
        [text_tokens, {k: [v.state, v.tokens] for k, v in fields.items()}, modality], default=str
    )
    return Representation(
        obligation_id=obligation.id,
        text=content.text,
        text_tokens=text_tokens,
        fields=fields,
        modality=modality,
        hash=hashlib.sha256(payload.encode()).hexdigest(),
    )


def embedding_text(rep: Representation) -> str:
    parts = [rep.text, *(v.value for v in rep.fields.values() if v.value)]
    return " ".join(parts)
