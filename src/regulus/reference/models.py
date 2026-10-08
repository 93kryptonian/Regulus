from enum import StrEnum

from regulus.domain.base import Model


class Role(StrEnum):
    DEV = "DEV"
    TEST = "TEST"


class DiscrepancyKind(StrEnum):
    COUNT_MATCHED = "COUNT_MATCHED"
    COUNT_EXCEEDS_DECLARED = "COUNT_EXCEEDS_DECLARED"
    COUNT_BELOW_DECLARED = "COUNT_BELOW_DECLARED"
    COUNT_UNDECLARED = "COUNT_UNDECLARED"
    DECLARED_COUNT_CONFLICT = "DECLARED_COUNT_CONFLICT"
    IRREGULAR_MULTIPLICITY = "IRREGULAR_MULTIPLICITY"
    LABEL_COPIES_IDENTICAL = "LABEL_COPIES_IDENTICAL"
    MULTI_TEXT_ARTICLE = "MULTI_TEXT_ARTICLE"
    PARSE_ERROR = "PARSE_ERROR"
    UNKNOWN_SECTOR = "UNKNOWN_SECTOR"


class ReferenceRegulation(Model):
    regulation_id: str
    labels: tuple[str, ...]
    declared_count: int | None = None


class ReferenceObligation(Model):
    obligation_id: str
    regulation_id: str
    text: str
    normalized_text: str
    ordinal: int
    sectors: tuple[str, ...]


class ReferenceSourceLink(Model):
    obligation_id: str
    regulation_id: str
    article: int
    article_texts: tuple[str, ...]
    sector: str


class Discrepancy(Model):
    kind: DiscrepancyKind
    regulation_id: str
    detail: dict[str, int] = {}


class ReferenceCorpus(Model):
    regulations: tuple[ReferenceRegulation, ...]
    obligations: tuple[ReferenceObligation, ...]
    links: tuple[ReferenceSourceLink, ...]
    sectors: tuple[str, ...]
    discrepancies: tuple[Discrepancy, ...]
    source_digests: dict[str, str] = {}
    normalization_version: str

    def obligations_of(self, regulation_id: str) -> tuple[ReferenceObligation, ...]:
        return tuple(o for o in self.obligations if o.regulation_id == regulation_id)

    def articles_of(self, regulation_id: str) -> frozenset[int]:
        return frozenset(link.article for link in self.links if link.regulation_id == regulation_id)

    def kinds(self, regulation_id: str) -> frozenset[DiscrepancyKind]:
        return frozenset(d.kind for d in self.discrepancies if d.regulation_id == regulation_id)


class SplitAssignment(Model):
    regulation_id: str
    role: Role
    reason: str


class Split(Model):
    version: str
    assignments: tuple[SplitAssignment, ...]
    expected_obligations: dict[str, int] = {}

    def role_of(self, regulation_id: str) -> Role | None:
        for a in self.assignments:
            if a.regulation_id == regulation_id:
                return a.role
        return None

    def ids(self, role: Role) -> tuple[str, ...]:
        return tuple(a.regulation_id for a in self.assignments if a.role is role)


class MatchKind(StrEnum):
    EXACT_NORMALIZED = "EXACT_NORMALIZED"
    ARTICLE_OVERLAP = "ARTICLE_OVERLAP"
    NONE = "NONE"


class PredictedObligation(Model):
    text: str
    articles: tuple[int, ...] = ()
    sector: str | None = None


class SystemOutput(Model):
    regulation_id: str
    obligations: tuple[PredictedObligation, ...]


class MatchResult(Model):
    kind: MatchKind
    matched: tuple[str, ...] = ()
    overlapping: tuple[str, ...] = ()
    matcher_version: str
