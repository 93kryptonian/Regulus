import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from .models import (
    Discrepancy,
    DiscrepancyKind,
    ReferenceCorpus,
    ReferenceObligation,
    ReferenceRegulation,
    ReferenceSourceLink,
)
from .normalize import NORMALIZATION_VERSION, norm, parse_article
from .xlsx import SheetError, read_rows

DETAIL = "reference data.xlsx"
COUNTS = "obligations count.xlsx"
SECTORS = "sector reference.xlsx"
DETAIL_COLS = ("Obligation", "Regulation_id", "Pasal", "Bunyi_Pasal", "Regulation", "Sector")
COUNT_COLS = ("guid", "regulation", "obligation_count")
SECTOR_COLS = ("Sector",)

Row = dict[str, str]
LinkKey = tuple[int, str, str]


class ReferenceError(Exception):
    def __init__(self, fields: list[str], rule: str) -> None:
        self.fields = fields
        self.rule = rule
        super().__init__(f"{rule}: {', '.join(fields)}")


def obligation_id(regulation_id: str, normalized_text: str, ordinal: int) -> str:
    raw = f"{regulation_id}\x1f{normalized_text}\x1f{ordinal}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _declared(counts: list[Row]) -> dict[str, tuple[int | None, bool]]:
    seen: dict[str, set[int]] = defaultdict(set)
    for r in counts:
        try:
            seen[r["guid"].strip()].add(int(r["obligation_count"]))
        except ValueError:
            raise ReferenceError(["obligation_count"], "count is not an integer") from None
    return {g: (next(iter(v)) if len(v) == 1 else None, len(v) > 1) for g, v in seen.items()}


def _collapse_labels(rows: list[Row], rid: str, out: list[Discrepancy]) -> list[Row]:
    by_label: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_label[r["Regulation"]].append(r)
    if len(by_label) == 1:
        return rows

    def key(r: Row) -> tuple[str, int, str, str]:
        return (
            norm(r["Obligation"]),
            parse_article(r["Pasal"]) or -1,
            norm(r["Bunyi_Pasal"]),
            r["Sector"],
        )

    sigs = {frozenset(Counter(key(r) for r in rs).items()) for rs in by_label.values()}
    if len(sigs) != 1:
        raise ReferenceError(["Regulation"], "label copies differ")
    out.append(
        Discrepancy(
            kind=DiscrepancyKind.LABEL_COPIES_IDENTICAL,
            regulation_id=rid,
            detail={"copies": len(by_label)},
        )
    )
    return by_label[sorted(by_label)[0]]


def build_corpus(
    detail: list[Row],
    counts: list[Row],
    sectors: list[Row],
    digests: dict[str, str] | None = None,
) -> ReferenceCorpus:
    vocab = tuple(sorted({r["Sector"] for r in sectors if r["Sector"].strip()}))
    declared = _declared(counts)
    by_reg: dict[str, list[Row]] = defaultdict(list)
    for r in detail:
        by_reg[r["Regulation_id"].strip()].append(r)
    regs: list[ReferenceRegulation] = []
    obls: list[ReferenceObligation] = []
    links: list[ReferenceSourceLink] = []
    disc: list[Discrepancy] = []
    for rid in sorted(set(by_reg) | set(declared)):
        rows = by_reg.get(rid, [])
        labels = tuple(sorted({r["Regulation"] for r in rows}))
        count, conflict = declared.get(rid, (None, False))
        regs.append(ReferenceRegulation(regulation_id=rid, labels=labels, declared_count=count))
        if conflict:
            disc.append(
                Discrepancy(kind=DiscrepancyKind.DECLARED_COUNT_CONFLICT, regulation_id=rid)
            )
        parsed: list[tuple[Row, int]] = []
        bad = 0
        for r in rows:
            a = parse_article(r["Pasal"])
            if a is None:
                bad += 1
            else:
                parsed.append((r, a))
        if bad:
            disc.append(
                Discrepancy(
                    kind=DiscrepancyKind.PARSE_ERROR, regulation_id=rid, detail={"rows": bad}
                )
            )
        rows = _collapse_labels([r for r, _ in parsed], rid, disc) if parsed else []
        arts = {id(r): a for r, a in parsed}
        unknown = sum(1 for r in rows if r["Sector"] not in vocab)
        if unknown:
            disc.append(
                Discrepancy(
                    kind=DiscrepancyKind.UNKNOWN_SECTOR, regulation_id=rid, detail={"rows": unknown}
                )
            )
        article_texts: dict[int, set[str]] = defaultdict(set)
        groups: dict[str, dict[LinkKey, int]] = defaultdict(lambda: defaultdict(int))
        originals: dict[str, str] = {}
        raw_text: dict[tuple[str, int, str], set[str]] = defaultdict(set)
        for r in rows:
            a = arts[id(r)]
            nt = norm(r["Obligation"])
            originals.setdefault(nt, r["Obligation"].strip())
            groups[nt][(a, norm(r["Bunyi_Pasal"]), r["Sector"])] += 1
            article_texts[a].add(norm(r["Bunyi_Pasal"]))
            raw_text[(nt, a, r["Sector"])].add(r["Bunyi_Pasal"].strip())
        if sum(len(v) > 1 for v in article_texts.values()):
            disc.append(
                Discrepancy(
                    kind=DiscrepancyKind.MULTI_TEXT_ARTICLE,
                    regulation_id=rid,
                    detail={"articles": sum(len(v) > 1 for v in article_texts.values())},
                )
            )
        irregular = derived = 0
        for nt in sorted(groups):
            mult = groups[nt]
            m = min(mult.values())
            derived += m
            irregular += len(set(mult.values())) > 1
            sec = tuple(sorted({k[2] for k in mult}))
            for ordinal in range(1, m + 1):
                oid = obligation_id(rid, nt, ordinal)
                obls.append(
                    ReferenceObligation(
                        obligation_id=oid,
                        regulation_id=rid,
                        text=originals[nt],
                        normalized_text=nt,
                        ordinal=ordinal,
                        sectors=sec,
                    )
                )
                for a, s in sorted({(k[0], k[2]) for k in mult}):
                    links.append(
                        ReferenceSourceLink(
                            obligation_id=oid,
                            regulation_id=rid,
                            article=a,
                            article_texts=tuple(sorted(raw_text[(nt, a, s)])),
                            sector=s,
                        )
                    )
        if irregular:
            disc.append(
                Discrepancy(
                    kind=DiscrepancyKind.IRREGULAR_MULTIPLICITY,
                    regulation_id=rid,
                    detail={"groups": irregular},
                )
            )
        if count is None:
            kind = DiscrepancyKind.COUNT_UNDECLARED
        elif derived == count:
            kind = DiscrepancyKind.COUNT_MATCHED
        else:
            kind = (
                DiscrepancyKind.COUNT_EXCEEDS_DECLARED
                if derived > count
                else DiscrepancyKind.COUNT_BELOW_DECLARED
            )
        disc.append(
            Discrepancy(
                kind=kind,
                regulation_id=rid,
                detail={"derived": derived, "declared": count if count is not None else -1},
            )
        )
    return ReferenceCorpus(
        regulations=tuple(regs),
        obligations=tuple(
            sorted(obls, key=lambda o: (o.regulation_id, o.normalized_text, o.ordinal))
        ),
        links=tuple(
            sorted(links, key=lambda x: (x.regulation_id, x.obligation_id, x.article, x.sector))
        ),
        sectors=vocab,
        discrepancies=tuple(disc),
        source_digests=digests or {},
        normalization_version=NORMALIZATION_VERSION,
        rows_read=len(detail),
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def available(directory: Path) -> bool:
    return all((directory / n).is_file() for n in (DETAIL, COUNTS, SECTORS))


def load_corpus(directory: Path) -> ReferenceCorpus:
    paths = {DETAIL: DETAIL_COLS, COUNTS: COUNT_COLS, SECTORS: SECTOR_COLS}
    data: dict[str, list[Row]] = {}
    for name, cols in paths.items():
        try:
            data[name] = read_rows(directory / name, cols)
        except SheetError as e:
            raise ReferenceError(e.fields, f"cannot read {name}") from None
    digests = {name: _digest(directory / name) for name in paths}
    return build_corpus(data[DETAIL], data[COUNTS], data[SECTORS], digests)
