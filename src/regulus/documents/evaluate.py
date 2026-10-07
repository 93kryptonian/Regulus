import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from regulus.domain.base import Model

from .models import DocStatus, PageFailure, PageSource, ProcessedDocument, RawPage
from .processor import process
from .provenance import reconstruct
from .reader import UnreadableDocument

REG = "PP-1-2026"


class GoldPage(Model):
    text: str = ""
    failure: str | None = None


class ExpectedUnit(Model):
    number: str
    text: str


class GoldCase(Model):
    case_id: str = Field(min_length=1)
    pages: tuple[GoldPage, ...] = ()
    unreadable: bool = False
    expected_status: DocStatus
    expected_articles: tuple[ExpectedUnit, ...] = ()
    expected_units: tuple[str, ...] = ()
    expected_codes: tuple[str, ...] | None = None
    absent_text: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    rationale: str = Field(min_length=10)


class RoundTrip(Model):
    checked: int
    violations: int


class DocumentsReport(Model):
    cases: int
    status_ok: int
    expected_units: int
    recovered_units: int
    noise_cases: int
    noise_ok: int
    explicit_failure_cases: int
    explicit_failure_ok: int
    code_cases: int
    code_ok: int
    round_trip: RoundTrip
    tags: tuple[str, ...]
    mismatches: tuple[str, ...]


def load_gold(path: Path) -> list[GoldCase]:
    return [GoldCase.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def reader_for(case: GoldCase):  # type: ignore[no-untyped-def]
    def read(_: bytes) -> Sequence[RawPage | PageFailure]:
        if case.unreadable:
            raise UnreadableDocument("gold: unreadable")
        out: list[RawPage | PageFailure] = []
        for i, p in enumerate(case.pages, 1):
            if p.failure:
                out.append(PageFailure(number=i, error=p.failure))
            else:
                out.append(RawPage(number=i, source=PageSource.NATIVE, text=p.text))
        return out

    return read


def round_trip(doc: ProcessedDocument) -> RoundTrip:
    pmap = {p.number: p for p in doc.pages}
    checked = violations = 0
    owners: list[tuple[str, str]] = [(a.id, a.text) for a in doc.articles]
    owners += [(u.id, u.text) for u in doc.amendment_units]
    for oid, text in owners:
        spans = doc.provenance.get(oid)
        if spans is None:
            continue
        checked += 1
        try:
            violations += reconstruct(spans, pmap) != text
        except Exception:
            violations += 1
    return RoundTrip(checked=checked, violations=violations)


def evaluate_gold(cases: Sequence[GoldCase]) -> DocumentsReport:
    status_ok = exp_units = rec_units = noise = noise_ok = fail_cases = fail_ok = 0
    code_cases = code_ok = checked = viol = 0
    bad: list[str] = []
    for c in cases:
        doc = process(f"gold:{c.case_id}".encode(), REG, reader_for(c))
        status_ok += doc.status is c.expected_status
        if doc.status is not c.expected_status:
            bad.append(f"{c.case_id}: status {doc.status.value}")
        got = {a.number: a.text for a in doc.articles}
        for u in c.expected_articles:
            exp_units += 1
            rec_units += got.get(u.number) == u.text
        got_units = [u.label for u in doc.amendment_units]
        exp_units += len(c.expected_units)
        rec_units += sum(1 for x in c.expected_units if x in got_units)
        if [a.number for a in doc.articles] != [u.number for u in c.expected_articles] or (
            got_units != list(c.expected_units)
        ):
            bad.append(f"{c.case_id}: units {list(got)} {got_units}")
        if c.absent_text:
            noise += 1
            everything = "\n".join(
                [a.text for a in doc.articles] + [u.text for u in doc.amendment_units]
            )
            noise_ok += not any(t in everything for t in c.absent_text)
        if c.expected_status in (DocStatus.FAILED, DocStatus.PARTIAL):
            fail_cases += 1
            fail_ok += doc.status is c.expected_status
        if c.expected_codes is not None:
            code_cases += 1
            code_ok += Counter(d.code.value for d in doc.diagnostics) == Counter(c.expected_codes)
            if Counter(d.code.value for d in doc.diagnostics) != Counter(c.expected_codes):
                bad.append(f"{c.case_id}: codes {[d.code.value for d in doc.diagnostics]}")
        rt = round_trip(doc)
        checked += rt.checked
        viol += rt.violations
    return DocumentsReport(
        cases=len(cases), status_ok=status_ok, expected_units=exp_units, recovered_units=rec_units,
        noise_cases=noise, noise_ok=noise_ok, explicit_failure_cases=fail_cases,
        explicit_failure_ok=fail_ok, code_cases=code_cases, code_ok=code_ok,
        round_trip=RoundTrip(checked=checked, violations=viol),
        tags=tuple(sorted({t for c in cases for t in c.tags})), mismatches=tuple(bad),
    )  # fmt: skip
