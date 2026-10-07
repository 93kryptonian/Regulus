import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import Field

from regulus.documents import ProcessedDocument
from regulus.domain.base import Model
from regulus.obligations import (
    FieldStatus,
    Lexicon,
    ObligationCandidate,
    RulesExtractor,
    load_lexicon,
)
from regulus.obligations.evaluate import GoldCase, _run_case

from .generate import generate
from .models import (
    CandidateTrace,
    Disposition,
    DropReason,
    FieldRef,
    GenerationConfig,
    GenerationInput,
    GenerationRequest,
    PermittedSource,
    RawGenerated,
    Status,
)
from .reference import ExtractiveGenerator
from .verify import tokens, verify_raw


def _value(c: ObligationCandidate, role: str) -> str | None:
    st = getattr(c, role, None)
    return (
        st.value.value if st is not None and st.status is FieldStatus.PRESENT and st.value else None
    )


def _replace(text: str, old: str, new: str) -> str | None:
    old_n = " ".join(old.split())
    return text.replace(old_n, new, 1) if old_n and old_n in text else None


def _drop(role: str) -> Callable[[ObligationCandidate, RawGenerated], RawGenerated | None]:
    def f(c: ObligationCandidate, r: RawGenerated) -> RawGenerated | None:
        values = {"condition": c.conditions, "exception": c.exceptions}
        v = values[role][0].value if role in values and values[role] else _value(c, role)
        out = _replace(r.text, v, "") if v else None
        return r.model_copy(update={"text": " ".join(out.split())}) if out is not None else None

    return f


def _text(
    fn: Callable[[ObligationCandidate, str], str | None],
) -> Callable[[ObligationCandidate, RawGenerated], RawGenerated | None]:
    def f(c: ObligationCandidate, r: RawGenerated) -> RawGenerated | None:
        out = fn(c, r.text)
        return None if out is None else r.model_copy(update={"text": out})

    return f


def _replace_actor(c: ObligationCandidate, t: str) -> str | None:
    a = _value(c, "actor")
    return _replace(t, a, "Menteri") if a else None


def _swap_marker(c: ObligationCandidate, t: str) -> str | None:
    m = " ".join(c.marker.value.split())
    other = "dilarang" if c.modality.value == "OBLIGATION" else "wajib"
    return _replace(t, m, other)


def _negate(c: ObligationCandidate, t: str) -> str | None:
    return _replace(
        t, " ".join(c.marker.value.split()), "tidak " + " ".join(c.marker.value.split())
    )


def _dup_marker(c: ObligationCandidate, t: str) -> str | None:
    m = " ".join(c.marker.value.split())
    return _replace(t, m, f"{m} {m}")


def _bump_number(c: ObligationCandidate, t: str) -> str | None:
    d = _value(c, "deadline") or _value(c, "frequency")
    m = re.search(r"\d+", d or "")
    if not d or not m:
        return None
    changed = d[: m.start()] + str(int(m.group(0)) + 2) + d[m.end() :]
    return _replace(t, d, changed)


def _actor_to_end(c: ObligationCandidate, t: str) -> str | None:
    a = _value(c, "actor")
    out = _replace(t, a, "") if a else None
    return " ".join((out + " " + " ".join(a.split())).split()) if out is not None and a else None


def _object_before_action(c: ObligationCandidate, t: str) -> str | None:
    a, o = _value(c, "action"), _value(c, "object")
    if not a or not o:
        return None
    pair = f"{' '.join(a.split())} {' '.join(o.split())}"
    return _replace(t, pair, f"{' '.join(o.split())} {' '.join(a.split())}")


def _move_deadline(c: ObligationCandidate, t: str) -> str | None:
    d = _value(c, "deadline") or _value(c, "frequency")
    out = _replace(t, d, "") if d else None
    if out is None or not d:
        return None
    dn = " ".join(d.split())
    moved = f"{dn} {' '.join(out.split())}" if t.endswith(dn) else f"{' '.join(out.split())} {dn}"
    return moved if moved != t else None


def _alter_actor(c: ObligationCandidate, r: RawGenerated) -> RawGenerated | None:
    return (
        r.model_copy(update={"content": {**r.content, "actor": "Menteri"}})
        if _value(c, "actor")
        else None
    )


def _drop_trace(c: ObligationCandidate, r: RawGenerated) -> RawGenerated | None:
    t = r.trace
    return r.model_copy(update={"trace": t.model_copy(update={"candidate": t.candidate[1:]})})


def _forge_trace(c: ObligationCandidate, r: RawGenerated) -> RawGenerated | None:
    fake = CandidateTrace(
        field=FieldRef(role="object", index=9),
        disposition=Disposition.DROPPED,
        reason=DropReason.DUPLICATE,
    )
    t = r.trace
    return r.model_copy(update={"trace": t.model_copy(update={"candidate": (*t.candidate, fake)})})


def _bad_drop(c: ObligationCandidate, r: RawGenerated) -> RawGenerated | None:
    t = r.trace
    for i, e in enumerate(t.candidate):
        if e.field.role == "actor" and e.disposition in (
            Disposition.PRESERVED,
            Disposition.NORMALIZED,
        ):
            bad = e.model_copy(update={"disposition": Disposition.DROPPED, "reason": "NOT_NEEDED"})
            return r.model_copy(
                update={
                    "trace": t.model_copy(
                        update={"candidate": (*t.candidate[:i], bad, *t.candidate[i + 1 :])}
                    )
                }
            )
    return None


MUTATIONS: dict[str, Callable[[ObligationCandidate, RawGenerated], RawGenerated | None]] = {
    "drop_condition": _drop("condition"),
    "drop_exception": _drop("exception"),
    "drop_deadline": _drop("deadline"),
    "drop_frequency": _drop("frequency"),
    "drop_actor": _drop("actor"),
    "replace_actor": _text(_replace_actor),
    "swap_modality": _text(_swap_marker),
    "add_negation": _text(_negate),
    "duplicate_marker": _text(_dup_marker),
    "invent_requirement": _text(lambda c, t: t + " dan wajib melaporkan setiap hari"),
    "invent_deadline": _text(lambda c, t: t + " paling lambat 7 hari"),
    "invent_exception": _text(lambda c, t: t + " kecuali ditentukan lain"),
    "expand_term": _text(lambda c, t: t + " sebagaimana didefinisikan dalam peraturan"),
    "convert_number": _text(_bump_number),
    "actor_to_end": _text(_actor_to_end),
    "object_before_action": _text(_object_before_action),
    "move_deadline": _text(_move_deadline),
    "alter_content_actor": _alter_actor,
    "drop_trace_entry": _drop_trace,
    "forge_trace_entry": _forge_trace,
    "bad_drop_reason": _bad_drop,
    "empty_text": lambda c, r: r.model_copy(update={"text": ""}),
}


class MutationReport(Model):
    applicable: dict[str, int]
    detected: dict[str, int]
    undetected: tuple[str, ...]


class Contradiction(Model):
    case_id: str = Field(min_length=1)
    article_text: str
    marker_index: int = Field(ge=0)
    generated_text: str
    rationale: str = Field(min_length=10)
    known_gap: bool = False


class ContradictionReport(Model):
    total: int
    rejected: int
    accepted_known_gaps: tuple[str, ...]
    accepted_unexpected: tuple[str, ...]


def candidates_for(cases: Sequence[GoldCase]):  # type: ignore[no-untyped-def]
    out = []
    for case in cases:
        res, doc = _run_case(case, RulesExtractor())
        out += [(c, doc) for c in res.candidates]
    return out


def source_of(c: ObligationCandidate, text: str) -> PermittedSource:
    return PermittedSource(
        clause=text[c.clause.start : c.clause.end],
        lead_in=text[c.lead_in.start : c.lead_in.end] if c.lead_in else None,
        items=tuple(text[i.start : i.end] for i in c.items),
    )


def _owner_text(doc: ProcessedDocument, owner_id: str) -> str:
    for a in doc.articles:
        if a.id == owner_id:
            return a.text
    raise KeyError(owner_id)


def run_mutations(pairs, lex: Lexicon | None = None) -> MutationReport:  # type: ignore[no-untyped-def]
    lex = lex or load_lexicon()
    gen = ExtractiveGenerator()
    applicable: Counter[str] = Counter()
    detected: Counter[str] = Counter()
    bad: list[str] = []
    for c, doc in pairs:
        text = _owner_text(doc, c.clause.owner_id)
        src = source_of(c, text)
        raw = gen.generate(GenerationRequest(candidate=c, source=src, config_version="1"))
        assert not verify_raw(c, src, raw, lex), "reference output must verify before mutation"
        for name, fn in MUTATIONS.items():
            mutated = fn(c, raw)
            if mutated is None or mutated == raw:
                continue
            applicable[name] += 1
            if verify_raw(c, src, mutated, lex):
                detected[name] += 1
            else:
                bad.append(f"{c.id}:{name}")
    return MutationReport(
        applicable=dict(applicable), detected=dict(detected), undetected=tuple(bad)
    )


def run_contradictions(
    cases: Sequence[Contradiction], lex: Lexicon | None = None
) -> ContradictionReport:
    lex = lex or load_lexicon()
    rejected, gaps, unexpected = 0, [], []
    for case in cases:
        gold = GoldCase(
            case_id=case.case_id,
            source="CONTRADICTION",
            text=case.article_text,
            rationale=case.rationale,
        )
        res, doc = _run_case(gold, RulesExtractor())
        c = sorted(res.candidates, key=lambda x: x.marker.citation.start)[case.marker_index]
        text = _owner_text(doc, c.clause.owner_id)
        src = source_of(c, text)
        base = ExtractiveGenerator().generate(
            GenerationRequest(candidate=c, source=src, config_version="1")
        )
        forged = base.model_copy(update={"text": " ".join(case.generated_text.split())})
        if verify_raw(c, src, forged, lex):
            rejected += 1
        elif case.known_gap:
            gaps.append(case.case_id)
        else:
            unexpected.append(case.case_id)
    return ContradictionReport(
        total=len(cases),
        rejected=rejected,
        accepted_known_gaps=tuple(gaps),
        accepted_unexpected=tuple(unexpected),
    )


class GenerationReport(Model):
    total: int
    generated: int
    rejected: int
    hallucinated_tokens: int
    citation_failures: int
    incomplete_fields: int
    unaccounted_fields: int
    open_questions: int
    tokens_checked: int = 0
    evidence_checked: int = 0
    trace_refs: int = 0
    undetermined_candidates: int = 0
    open_question_missing: int = 0


def run_generation(pairs, config: GenerationConfig | None = None) -> GenerationReport:  # type: ignore[no-untyped-def]
    gen = ExtractiveGenerator()
    gen_n = rej = halluc = cite = incomplete = unacc = oq = ntok = nev = nref = und = oqmiss = 0
    for c, doc in pairs:
        out = generate(
            GenerationInput(candidates=(c,), documents={c.change_ref.owner_id.split(":")[0]: doc}),
            gen,
            config,
        )
        (r,) = out.results
        if r.status is not Status.GENERATED or r.obligation is None or r.trace is None:
            rej += 1
            continue
        gen_n += 1
        text = _owner_text(doc, c.clause.owner_id)
        src = source_of(c, text)
        halluc += sum(
            (
                Counter(tokens(r.obligation.generated.content.text))
                - Counter(tokens(src.all_text()))
            ).values()
        )
        ntok += len(tokens(r.obligation.generated.content.text))
        nev += len(r.evidence)
        cite += sum(1 for e in r.evidence if text[e.span[0] : e.span[1]] != e.quote)
        t = r.obligation.generated.content.text
        tt = tokens(t)
        for e in r.evidence:
            if (
                tokens(e.quote)
                and not _contains(tt, tokens(e.quote))
                and e.quote not in text[c.clause.start : c.clause.end]
            ):
                incomplete += 1
        refs = [(e.field.role, e.field.index) for e in r.trace.candidate]
        unacc += len(refs) - len(set(refs))
        nref += len(refs)
        oq += len(r.open_questions)
        if c.undetermined or any(
            getattr(c, f).status.value == "UNDETERMINED"
            for f in ("actor", "action", "object", "deadline", "frequency")
        ):
            und += 1
            oqmiss += not r.open_questions
    return GenerationReport(
        total=len(pairs),
        generated=gen_n,
        rejected=rej,
        hallucinated_tokens=halluc,
        citation_failures=cite,
        incomplete_fields=incomplete,
        unaccounted_fields=unacc,
        open_questions=oq,
        tokens_checked=ntok,
        evidence_checked=nev,
        trace_refs=nref,
        undetermined_candidates=und,
        open_question_missing=oqmiss,
    )


def _contains(hay: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(hay[i : i + n] == needle for i in range(len(hay) - n + 1))


def load_contradictions(path: Path) -> list[Contradiction]:
    return [Contradiction.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]
