from enum import StrEnum

from pydantic import Field

from regulus.domain import Obligation
from regulus.domain.base import Model
from regulus.generation import TransformationTrace
from regulus.obligations import FieldStatus, Modality

CORE = ("actor", "action", "object")
PARAMS = ("deadline", "frequency", "condition", "exception")
FIELDS = (*CORE, *PARAMS)


class Label(StrEnum):
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    CONTRADICTORY_MODALITY = "CONTRADICTORY_MODALITY"
    VARIANT = "VARIANT"
    RELATED = "RELATED"
    SIMILAR_TEXT_ONLY = "SIMILAR_TEXT_ONLY"


TIER = {
    Label.POSSIBLE_DUPLICATE: 0,
    Label.CONTRADICTORY_MODALITY: 1,
    Label.VARIANT: 2,
    Label.RELATED: 3,
    Label.SIMILAR_TEXT_ONLY: 4,
}


class Relation(StrEnum):
    EQUAL = "EQUAL"
    OVERLAP = "OVERLAP"
    DIFFERENT = "DIFFERENT"
    ONE_MISSING = "ONE_MISSING"
    BOTH_NOT_STATED = "BOTH_NOT_STATED"
    UNDETERMINED = "UNDETERMINED"


class LineageContext(StrEnum):
    SAME_ARTICLE = "SAME_ARTICLE"
    ARTICLE_AMENDED_BY = "ARTICLE_AMENDED_BY"
    ARTICLE_AMENDS = "ARTICLE_AMENDS"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class SearchStatus(StrEnum):
    MATCHES = "MATCHES"
    NO_CANDIDATES = "NO_CANDIDATES"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_SEARCHABLE = "NOT_SEARCHABLE"


class FieldEntry(Model):
    state: FieldStatus
    tokens: tuple[str, ...] = ()
    value: str | None = None


class Representation(Model):
    obligation_id: str
    text: str
    text_tokens: tuple[str, ...]
    fields: dict[str, FieldEntry]
    modality: Modality | None
    hash: str


class FieldComparison(Model):
    field: str
    query_value: str | None
    match_value: str | None
    relation: Relation
    jaccard: float | None = None


class Verdict(Model):
    label: Label
    comparisons: tuple[FieldComparison, ...]
    supporting_fields: tuple[str, ...] = ()
    cap_reasons: tuple[str, ...] = ()
    composite: float = 0.0


class RelationConfig(Model):
    version: str = Field(default="1", min_length=1)
    tau_overlap: float = 0.5
    tau_dup: float = 0.8
    weights: dict[str, float] = {
        "actor": 0.2,
        "action": 0.25,
        "object": 0.25,
        "deadline": 0.1,
        "frequency": 0.05,
        "condition": 0.1,
        "exception": 0.05,
    }


class SimilarityEntry(Model):
    obligation: Obligation
    trace: TransformationTrace | None = None
    candidate_id: str | None = None


class Match(Model):
    obligation_id: str
    rank: int
    retrieval_score: float
    score_kind: str = "COSINE_UNCALIBRATED"
    verdict: Verdict
    lineage_context: LineageContext
    article_id: str


class SearchConfig(Model):
    config_version: str = Field(default="1", min_length=1)
    k: int = 3
    k_retrieve: int = 20
    include_statuses: tuple[str, ...] = ("APPROVED", "PUBLISHED")
    relation: RelationConfig = RelationConfig()


class SimilarityResult(Model):
    id: str
    query_id: str
    status: SearchStatus
    matches: tuple[Match, ...] = ()
    provider: str = ""
    index_version: str = ""
    config_version: str = ""
    retrieved: int = 0
    index_complete: bool = True
    diagnostics: tuple[str, ...] = ()
    reason: str | None = None
