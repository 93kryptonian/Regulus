from regulus.obligations import FieldStatus, ObligationCandidate

from .models import (
    CandidateTrace,
    ContentTrace,
    Disposition,
    DropReason,
    FieldRef,
    Step,
    TransformationTrace,
)

SLOTS = {
    "actor": "actor",
    "action": "action",
    "object": "object",
    "deadline": "deadline",
    "frequency": "frequency",
}
CONTENT_FIELDS = ("actor", "action", "object", "condition", "deadline", "frequency", "exception")
_PUNCT = " \t\r\n,;:."


def normalize_value(value: str) -> tuple[str, tuple[Step, ...]]:
    collapsed = " ".join(value.split())
    trimmed = collapsed.strip(_PUNCT)
    steps = []
    if collapsed != value:
        steps.append(Step.WHITESPACE_COLLAPSE)
    if trimmed != collapsed:
        steps.append(Step.TRIM_PUNCTUATION)
    return trimmed, tuple(steps) or (Step.PRESERVE,)


def _disposition(steps: tuple[Step, ...]) -> Disposition:
    return Disposition.PRESERVED if steps == (Step.PRESERVE,) else Disposition.NORMALIZED


def expected(candidate: ObligationCandidate) -> tuple[dict[str, str | None], TransformationTrace]:
    content: dict[str, str | None] = dict.fromkeys(CONTENT_FIELDS)
    cand: list[CandidateTrace] = []
    srcs: dict[str, list[FieldRef]] = {n: [] for n in CONTENT_FIELDS}
    steps: dict[str, set[Step]] = {n: set() for n in CONTENT_FIELDS}
    open_q: list[str] = []
    cand.append(
        CandidateTrace(
            field=FieldRef(role="clause"), disposition=Disposition.PRESERVED, target="text"
        )
    )
    if candidate.lead_in is not None:
        cand.append(
            CandidateTrace(
                field=FieldRef(role="lead_in"), disposition=Disposition.PRESERVED, target="text"
            )
        )
    cand.append(
        CandidateTrace(
            field=FieldRef(role="marker"), disposition=Disposition.PRESERVED, target="text"
        )
    )
    for role in SLOTS:
        st = getattr(candidate, role)
        ref = FieldRef(role=role)
        if st.status is FieldStatus.PRESENT and st.value:
            value, sp = normalize_value(st.value.value)
            content[role] = value
            srcs[role].append(ref)
            steps[role].update(sp)
            cand.append(
                CandidateTrace(field=ref, disposition=_disposition(sp), steps=sp, target=role)
            )
        elif st.status is FieldStatus.UNDETERMINED:
            cand.append(
                CandidateTrace(
                    field=ref, disposition=Disposition.ABSENT_UNDETERMINED, reason=st.reason
                )
            )
            open_q.append(f"{role}:{st.reason}")
        else:
            cand.append(CandidateTrace(field=ref, disposition=Disposition.ABSENT_NOT_STATED))
    for role, slot, values in (
        ("condition", "condition", candidate.conditions),
        ("exception", "exception", candidate.exceptions),
    ):
        kept: list[str] = []
        for i, v in enumerate(values):
            value, sp = normalize_value(v.value)
            ref = FieldRef(role=role, index=i)
            if value in kept:
                cand.append(
                    CandidateTrace(
                        field=ref,
                        disposition=Disposition.DROPPED,
                        steps=sp,
                        target=slot,
                        reason=DropReason.DUPLICATE,
                    )
                )
                continue
            kept.append(value)
            srcs[slot].append(ref)
            steps[slot].update(sp)
            cand.append(
                CandidateTrace(field=ref, disposition=_disposition(sp), steps=sp, target=slot)
            )
        if kept:
            content[slot] = "; ".join(kept)
            if len(kept) > 1:
                steps[slot].add(Step.JOIN)
    for name in candidate.undetermined:
        open_q.append(f"{name.rstrip('s')}:undelimited trigger")
    for i, _ in enumerate(candidate.items):
        cand.append(
            CandidateTrace(
                field=FieldRef(role="item", index=i),
                disposition=Disposition.PRESERVED,
                target="text",
            )
        )
    contents = []
    for name in CONTENT_FIELDS:
        if content[name] is not None:
            ordered = tuple(sorted(steps[name], key=lambda s: list(Step).index(s)))
            contents.append(ContentTrace(field=name, sources=tuple(srcs[name]), steps=ordered))
    text_src = [FieldRef(role="clause"), FieldRef(role="marker")]
    text_src += [FieldRef(role="lead_in")] if candidate.lead_in is not None else []
    text_src += [FieldRef(role="item", index=i) for i in range(len(candidate.items))]
    for name in CONTENT_FIELDS:
        text_src += srcs[name]
    contents.append(ContentTrace(field="text", sources=tuple(text_src)))
    return content, TransformationTrace(
        candidate=tuple(cand), content=tuple(contents), open_questions=tuple(open_q)
    )
