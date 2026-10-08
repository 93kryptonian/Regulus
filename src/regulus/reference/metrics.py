import random
from collections import defaultdict

from regulus.domain.base import Model

from .matching import BASELINE, Matcher
from .models import (
    DiscrepancyKind,
    MatchKind,
    PredictedObligation,
    ReferenceCorpus,
    SystemOutput,
)

COUNT_FLAGS = (
    DiscrepancyKind.COUNT_EXCEEDS_DECLARED,
    DiscrepancyKind.COUNT_BELOW_DECLARED,
    DiscrepancyKind.COUNT_UNDECLARED,
    DiscrepancyKind.DECLARED_COUNT_CONFLICT,
)


class RegulationScore(Model):
    regulation_id: str
    reference_obligations: int
    predicted: int
    matched: int
    missing: int
    over_generated: int
    duplicate_predicted: int
    article_overlap_only: int
    reference_articles: int
    covered_articles: int
    predicted_articles: int
    correct_articles: int
    link_reference: int
    link_hit: int
    link_predicted: int
    sector_checked: int
    sector_agreed: int
    declared_count: int | None
    count_unreconciled: bool


def score(
    corpus: ReferenceCorpus, output: SystemOutput, matcher: Matcher = BASELINE
) -> RegulationScore:
    rid = output.regulation_id
    refs = tuple(sorted(corpus.obligations_of(rid), key=lambda o: (o.normalized_text, o.ordinal)))
    by_id = {o.obligation_id: o for o in refs}
    art: dict[str, set[int]] = defaultdict(set)
    for link in corpus.links:
        if link.regulation_id == rid:
            art[link.obligation_id].add(link.article)
    frozen = {k: frozenset(v) for k, v in art.items()}
    taken: set[str] = set()
    matched = over = dup = near = checked = agreed = hit = lpred = 0
    pred_articles: set[int] = set()
    for p in output.obligations:
        pred_articles |= set(p.articles)
        res = matcher.match(p, refs, frozen)
        if res.kind is MatchKind.EXACT_NORMALIZED:
            free = [i for i in res.matched if i not in taken]
            if not free:
                dup += 1
                continue
            taken.add(free[0])
            matched += 1
            mine = set(p.articles)
            hit += len(mine & art[free[0]])
            lpred += len(mine)
            if p.sector is not None:
                checked += 1
                agreed += p.sector in by_id[free[0]].sectors
        else:
            over += 1
            near += res.kind is MatchKind.ARTICLE_OVERLAP
    ref_articles = set().union(*art.values()) if art else set()
    reg = next((r for r in corpus.regulations if r.regulation_id == rid), None)
    return RegulationScore(
        regulation_id=rid,
        reference_obligations=len(refs),
        predicted=len(output.obligations),
        matched=matched,
        missing=len(refs) - len(taken),
        over_generated=over,
        duplicate_predicted=dup,
        article_overlap_only=near,
        reference_articles=len(ref_articles),
        covered_articles=len(ref_articles & pred_articles),
        predicted_articles=len(pred_articles),
        correct_articles=len(pred_articles & ref_articles),
        link_reference=sum(len(art[o.obligation_id]) for o in refs),
        link_hit=hit,
        link_predicted=lpred,
        sector_checked=checked,
        sector_agreed=agreed,
        declared_count=reg.declared_count if reg else None,
        count_unreconciled=bool(corpus.kinds(rid) & set(COUNT_FLAGS)),
    )


def oracle(corpus: ReferenceCorpus, rid: str) -> SystemOutput:
    art: dict[str, set[int]] = defaultdict(set)
    for link in corpus.links:
        if link.regulation_id == rid:
            art[link.obligation_id].add(link.article)
    return SystemOutput(
        regulation_id=rid,
        obligations=tuple(
            PredictedObligation(
                text=o.text,
                articles=tuple(sorted(art[o.obligation_id])),
                sector=o.sectors[0] if o.sectors else None,
            )
            for o in sorted(
                corpus.obligations_of(rid), key=lambda o: (o.normalized_text, o.ordinal)
            )
        ),
    )


def null(rid: str) -> SystemOutput:
    return SystemOutput(regulation_id=rid, obligations=())


def drop(out: SystemOutput, k: int) -> SystemOutput:
    return out.model_copy(update={"obligations": out.obligations[k:]})


def duplicate(out: SystemOutput, k: int) -> SystemOutput:
    return out.model_copy(update={"obligations": out.obligations + out.obligations[:k]})


def alter_text(out: SystemOutput, k: int) -> SystemOutput:
    items = tuple(
        p.model_copy(update={"text": p.text + " tambahan"}) if i < k else p
        for i, p in enumerate(out.obligations)
    )
    return out.model_copy(update={"obligations": items})


def shift_articles(out: SystemOutput, offset: int = 100000) -> SystemOutput:
    items = tuple(
        p.model_copy(update={"articles": tuple(a + offset for a in p.articles)})
        for p in out.obligations
    )
    return out.model_copy(update={"obligations": items})


def rotate_articles(out: SystemOutput) -> SystemOutput:
    tuples = [p.articles for p in out.obligations]
    n = len(tuples)
    items = tuple(
        p.model_copy(update={"articles": tuples[(i + 1) % n]})
        for i, p in enumerate(out.obligations)
    )
    return out.model_copy(update={"obligations": items})


def wrong_sector(out: SystemOutput, sectors: tuple[str, ...]) -> SystemOutput:
    rng = random.Random(0)
    items = []
    for p in out.obligations:
        other = [s for s in sectors if s != p.sector]
        items.append(
            p.model_copy(update={"sector": rng.choice(other) if other and p.sector else p.sector})
        )
    return out.model_copy(update={"obligations": tuple(items)})


def _same_articles(out: SystemOutput) -> bool:
    return len({p.articles for p in out.obligations}) < 2


def instrument_problems(corpus: ReferenceCorpus, matcher: Matcher = BASELINE) -> list[str]:
    bad: list[str] = []
    for reg in corpus.regulations:
        rid = reg.regulation_id
        n = len(corpus.obligations_of(rid))
        if n == 0:
            continue
        o = oracle(corpus, rid)
        s = score(corpus, o, matcher)
        if not (
            s.matched == n
            and s.missing == 0
            and s.over_generated == 0
            and s.duplicate_predicted == 0
        ):
            bad.append(f"{rid}: oracle does not match every obligation")
        if not (
            s.covered_articles == s.reference_articles
            and s.link_hit == s.link_reference == s.link_predicted
        ):
            bad.append(f"{rid}: oracle does not reproduce every article link")
        if s.sector_agreed != s.sector_checked:
            bad.append(f"{rid}: oracle sector disagrees with itself")
        z = score(corpus, null(rid), matcher)
        if not (z.matched == 0 and z.missing == n and z.over_generated == 0 and z.predicted == 0):
            bad.append(f"{rid}: null system is not scored as empty")
        k = 1
        d = score(corpus, drop(o, k), matcher)
        if not (
            d.matched == n - k
            and d.missing == k
            and d.over_generated == 0
            and d.duplicate_predicted == 0
        ):
            bad.append(f"{rid}: dropping changes more than missing")
        u = score(corpus, duplicate(o, k), matcher)
        if not (
            u.matched == n
            and u.duplicate_predicted == k
            and u.over_generated == 0
            and u.missing == 0
        ):
            bad.append(f"{rid}: duplicating changes more than duplicate-predicted")
        a = score(corpus, alter_text(o, k), matcher)
        if not (
            a.matched == n - k
            and a.over_generated == k
            and a.missing == k
            and a.article_overlap_only == k
        ):
            bad.append(f"{rid}: altering text is not scored as over-generated and missing")
        h = score(corpus, shift_articles(o), matcher)
        if not (
            h.matched == n
            and h.covered_articles == 0
            and h.correct_articles == 0
            and h.link_hit == 0
        ):
            bad.append(f"{rid}: shifted articles are not detected")
        if not _same_articles(o):
            r = score(corpus, rotate_articles(o), matcher)
            if not (
                r.matched == n and (r.link_hit < r.link_reference or r.link_hit < r.link_predicted)
            ):
                bad.append(f"{rid}: rotated article links are not detected")
        if len(corpus.sectors) > 1 and s.sector_checked:
            w = score(corpus, wrong_sector(o, corpus.sectors), matcher)
            if not (w.matched == n and w.sector_agreed < w.sector_checked):
                bad.append(f"{rid}: wrong sectors are not detected")
    return bad
